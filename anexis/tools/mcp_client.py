"""Outside tools. Each entry in tools/manifest.yaml is an MCP server that Anexis
starts as its own process (or reaches over HTTP) and whose tools join the
registry.

Nothing from those projects is copied into this repo. The manifest pins a
version for each one, and npx or uvx fetches exactly that version on the server.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from mcp import Client, StdioServerParameters
from mcp.client.stdio import get_default_environment
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from anexis.config import Settings
from anexis.platform import bundled_runtime
from anexis.tools.base import DANGER, SAFE, WRITE, Tool, ToolContext
from anexis.tools.registry import Registry

TYPES = ("npm", "pypi", "command", "http")
# Network plumbing a server may need to download itself or reach the web.
# Everything else in the environment (keys, tokens) stays with Anexis unless the
# manifest entry names it under `env`.
PLUMBING = (
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
    "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS", "CURL_CA_BUNDLE",
    "NPM_CONFIG_REGISTRY", "npm_config_registry", "UV_INDEX_URL", "PIP_INDEX_URL",
    "XDG_CACHE_HOME", "UV_CACHE_DIR", "PLAYWRIGHT_BROWSERS_PATH", "TMPDIR",
)


@dataclass
class ServerSpec:
    name: str
    type: str
    package: str = ""
    version: str = ""
    bin: str = ""
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    env: list[str] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)
    enabled: bool = True
    risk: str = WRITE
    about: str = ""
    source: str = ""
    license: str = ""

    def state(self, settings: Settings) -> str:
        if not self.enabled:
            return "off"
        if any(not settings.env.get(key) for key in self.needs):
            return "needs key"
        return "ready"


def load_manifest(settings: Settings) -> list[ServerSpec]:
    if not settings.manifest.is_file():
        return []
    raw = yaml.safe_load(settings.manifest.read_text()) or {}
    specs = []
    for entry in raw.get("servers", []):
        spec = ServerSpec(**entry)
        if spec.type not in TYPES:
            raise ValueError(f"{spec.name}: type must be one of {', '.join(TYPES)}")
        if spec.type in ("npm", "pypi") and not (spec.package and spec.version):
            raise ValueError(f"{spec.name}: needs a package and a pinned version")
        if spec.risk not in (SAFE, WRITE, DANGER):
            raise ValueError(f"{spec.name}: risk must be safe, write or danger")
        spec.version = str(spec.version)
        specs.append(spec)
    return specs


def _fill(value: str, settings: Settings) -> str:
    """{workspace} and {home} become folders, ${NAME} becomes that env value."""
    value = value.replace("{workspace}", str(settings.workspace)).replace("{home}", str(settings.home))
    return re.sub(r"\$\{(\w+)\}", lambda m: settings.env.get(m.group(1), ""), value)


def node_dir() -> Path:
    """Where setup.sh puts its own Node when the system one is missing or too old."""
    return Path.home() / ".local" / "share" / "anexis" / "node" / "bin"


def tool_path() -> str:
    """PATH for tool servers. The runtime the Windows installer ships comes
    first, then the Node that setup.sh installed, then whatever is on PATH."""
    parts = []
    runtime = bundled_runtime()
    if runtime:
        parts += [str(p) for p in (runtime / "node", runtime / "python", runtime / "python" / "Scripts", runtime) if p.is_dir()]
    if node_dir().is_dir():
        parts.append(str(node_dir()))
    parts.append(os.environ.get("PATH", ""))
    return os.pathsep.join(p for p in parts if p)


def npm_dir(spec: ServerSpec, settings: Settings) -> Path:
    """Where one npm tool server is installed, one folder per pinned version."""
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", f"{spec.package}@{spec.version}")
    return settings.home / "tool-servers" / safe


def npm_entry(spec: ServerSpec, settings: Settings) -> Path | None:
    """The script an installed npm server starts from, or None when it is not
    installed yet. Read from the package's own bin field."""
    pkg = npm_dir(spec, settings) / "node_modules" / Path(*spec.package.split("/"))
    try:
        meta = json.loads((pkg / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    bins = meta.get("bin")
    if isinstance(bins, str):
        rel = bins
    elif isinstance(bins, dict) and bins:
        rel = bins.get(spec.bin) or bins.get(spec.package.split("/")[-1]) or next(iter(bins.values()))
    else:
        rel = meta.get("main")
    entry = (pkg / rel).resolve() if rel else None
    return entry if entry and entry.is_file() else None


async def npm_install(spec: ServerSpec, settings: Settings, log) -> Path | None:
    """Installs one npm server into its own folder, once. Running it from there
    afterwards needs no download, which is what makes starting reliable: npx
    downloading several servers at once fights over one cache on Windows."""
    entry = npm_entry(spec, settings)
    if entry:
        return entry
    from anexis.platform import find_program
    from anexis.tools.builtin.system import run_process

    folder = npm_dir(spec, settings)
    folder.mkdir(parents=True, exist_ok=True)
    npm = find_program("npm", tool_path())
    env = {**os.environ, "PATH": tool_path(), "npm_config_update_notifier": "false", "npm_config_fund": "false"}
    code, output = await run_process(
        [npm, "install", "--prefix", str(folder), "--no-audit", "--no-fund", "--omit=dev", "--loglevel=error",
         f"{spec.package}@{spec.version}"], folder, 600, env=env)
    log.write(output)
    log.flush()
    if code != 0:
        raise RuntimeError(f"npm could not install {spec.package}@{spec.version}: {(output.strip().splitlines() or ['no output'])[-1][:200]}")
    return npm_entry(spec, settings)


def launch_command(spec: ServerSpec, settings: Settings) -> list[str]:
    args = [_fill(str(a), settings) for a in spec.args]
    if spec.type == "npm":
        entry = npm_entry(spec, settings)
        if entry:  # installed: start it straight with node, no npx
            node = shutil.which("node", path=tool_path()) or "node"
            return [node, str(entry), *args]
        npx = shutil.which("npx", path=tool_path()) or "npx"
        return [npx, "-y", f"{spec.package}@{spec.version}", *args]
    if spec.type == "pypi":
        return [shutil.which("uvx", path=tool_path()) or "uvx", "--from", f"{spec.package}=={spec.version}", spec.bin or spec.package, *args]
    return [_fill(str(c), settings) for c in spec.command] + args


def _server_env(spec: ServerSpec, settings: Settings) -> dict[str, str]:
    env = get_default_environment()
    env["PATH"] = tool_path()
    for key in PLUMBING:
        if os.environ.get(key):
            env[key] = os.environ[key]
    for key in [*spec.env, *spec.needs]:
        if settings.env.get(key):
            env[key] = settings.env[key]
    return env


def _result_text(result) -> str:
    parts = []
    for block in result.content or []:
        text = getattr(block, "text", None)
        parts.append(text if text is not None else f"[{getattr(block, 'type', 'content')} omitted]")
    body = "\n".join(parts).strip() or "(no output)"
    return f"Error: {body}" if result.is_error else body


class MCPManager:
    def __init__(self, settings: Settings, registry: Registry, start_timeout: float = 90.0, call_timeout: float = 180.0):
        self.settings = settings
        self.registry = registry
        self.start_timeout = start_timeout
        self.call_timeout = call_timeout
        self.status: dict[str, dict] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._stop = asyncio.Event()
        # npx servers start one at a time. Several npx downloads at once write
        # to the same npm cache, and on Windows they knock each other over.
        self._one_at_a_time = {"npm": asyncio.Lock()}
        self.log_dir = settings.home / "tool-logs"
        self.install_npm = True  # tests that stand in for npm turn this off

    async def start(self, only: set[str] | None = None) -> None:
        """Start every usable server at once and wait until each is up or failed."""
        self._stop.clear()
        ready: list[asyncio.Event] = []
        for spec in load_manifest(self.settings):
            if only is not None and spec.name not in only:
                continue
            state = spec.state(self.settings)
            self.status[spec.name] = {"state": state, "tools": 0, "about": spec.about, "needs": spec.needs}
            if state != "ready":
                continue
            self.status[spec.name]["state"] = "starting"
            event = asyncio.Event()
            ready.append(event)
            self._tasks[spec.name] = asyncio.create_task(self._serve(spec, event))
        if ready:
            await asyncio.gather(*(e.wait() for e in ready))

    async def stop(self) -> None:
        self._stop.set()
        if self._tasks:
            # Running servers leave on their own. One still stuck starting is cancelled.
            _, stuck = await asyncio.wait(self._tasks.values(), timeout=10)
            for task in stuck:
                task.cancel()
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    def _connection(self, spec: ServerSpec):
        if spec.type == "http":
            headers = {k: _fill(v, self.settings) for k, v in spec.headers.items()}
            return streamable_http_client(spec.url, http_client=create_mcp_http_client(headers=headers))
        command = launch_command(spec, self.settings)
        return StdioServerParameters(
            command=command[0], args=command[1:], env=_server_env(spec, self.settings),
            cwd=str(self.settings.workspace),
        )

    async def _serve(self, spec: ServerSpec, ready: asyncio.Event) -> None:
        """One task owns one server for its whole life, so the connection is
        opened and closed by the same task. A server that falls over before it
        is up gets one more try, since a first download often fails once."""
        info = self.status[spec.name]
        source = f"mcp:{spec.name}"
        tries = 1 if spec.type == "http" else 2
        try:
            for attempt in range(1, tries + 1):
                try:
                    await self._connect(spec, source, info, ready)
                    return  # it ran and was asked to stop
                except TimeoutError:
                    info.update(state="failed", error=f"did not start within {self.start_timeout:g} seconds")
                except BaseException as e:  # includes ExceptionGroup from the client's task group
                    if isinstance(e, asyncio.CancelledError):
                        raise
                    info.update(state="failed", error=_explain(e))
                said = self._log_tail(spec.name)
                if said:
                    info["log"] = said
                    info["error"] = f"{info['error']}. It said: {said.splitlines()[-1][:200]}"
                if ready.is_set() or self._stop.is_set() or attempt == tries:
                    return  # it was up and then died, or there is no point trying again
                info.update(state="starting", error="", retried=True)
        finally:
            self.registry.remove_source(source)
            if info["state"] == "running":
                info.update(state="stopped", tools=0)
            ready.set()

    def _log_path(self, name: str) -> Path:
        return self.log_dir / f"{name}.log"

    def _log_tail(self, name: str, lines: int = 12) -> str:
        """The last things a server wrote before it stopped: the real reason."""
        try:
            text = self._log_path(name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        kept = [line.rstrip() for line in text.splitlines() if line.strip()]
        return "\n".join(kept[-lines:])[-1500:]

    async def _connect(self, spec: ServerSpec, source: str, info: dict, ready: asyncio.Event) -> None:
        self.settings.workspace.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        lock = self._one_at_a_time.get(spec.type)
        if lock:
            await lock.acquire()

        def let_next_start() -> None:
            nonlocal lock
            if lock:
                lock.release()
                lock = None

        try:
            # What the server prints to its error stream is kept, so a failed
            # start can be explained instead of just reported.
            with open(self._log_path(spec.name), "w", encoding="utf-8") as said:
                if spec.type == "npm" and self.install_npm:
                    try:
                        await npm_install(spec, self.settings, said)
                    except (OSError, RuntimeError) as e:
                        said.write(f"\n{e}\n")  # npx below is the fallback
                connection = self._connection(spec)
                if isinstance(connection, StdioServerParameters):
                    from mcp import stdio_client

                    connection = stdio_client(connection, errlog=said)
                async with asyncio.timeout(self.start_timeout) as deadline:
                    async with Client(connection) as client:
                        tools, cursor = [], None
                        while True:
                            page = await client.list_tools(cursor=cursor)
                            tools.extend(page.tools)
                            cursor = getattr(page, "next_cursor", None)
                            if not cursor:
                                break
                        deadline.reschedule(None)  # it is up, no more deadline
                        let_next_start()
                        for remote in tools:
                            self.registry.add(self._wrap(spec, source, client, remote))
                        info.update(state="running", tools=len(tools), error="")
                        info.pop("log", None)
                        ready.set()
                        await self._stop.wait()
        finally:
            let_next_start()

    def _wrap(self, spec: ServerSpec, source: str, client: Client, remote) -> Tool:
        read_only = bool(remote.annotations and remote.annotations.read_only_hint)
        remote_name = remote.name

        async def handler(args: dict, ctx: ToolContext) -> str:
            try:
                result = await asyncio.wait_for(client.call_tool(remote_name, args), self.call_timeout)
            except TimeoutError:
                return f"Error: {spec.name} did not answer within {self.call_timeout:g} seconds"
            except Exception as e:
                return f"Error: {_explain(e)}"
            return _result_text(result)

        return Tool(
            name=f"{spec.name}_{remote.name}",
            description=remote.description or remote.title or remote.name,
            parameters=remote.input_schema or {"type": "object", "properties": {}},
            handler=handler,
            tier=SAFE if read_only else spec.risk,
            source=source,
        )


def _explain(error: BaseException) -> str:
    """The real reason inside an ExceptionGroup, in one line."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return f"{type(error).__name__}: {error}"[:300]
