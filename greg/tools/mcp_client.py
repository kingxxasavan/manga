"""Outside tools. Each entry in tools/manifest.yaml is an MCP server that Greg
starts as its own process (or reaches over HTTP) and whose tools join the
registry.

Nothing from those projects is copied into this repo. The manifest pins a
version for each one, and npx or uvx fetches exactly that version on the server.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from mcp import Client, StdioServerParameters
from mcp.client.stdio import get_default_environment
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from greg.config import Settings
from greg.tools.base import DANGER, SAFE, WRITE, Tool, ToolContext
from greg.tools.registry import Registry

TYPES = ("npm", "pypi", "command", "http")
# Network plumbing a server may need to download itself or reach the web.
# Everything else in the environment (keys, tokens) stays with Greg unless the
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
    """Where install.sh puts its own Node when the system one is missing or too old."""
    return Path.home() / ".local" / "share" / "greg" / "node" / "bin"


def tool_path() -> str:
    """PATH for tool servers, with the installer's Node first when it exists."""
    current = os.environ.get("PATH", "")
    return f"{node_dir()}:{current}" if node_dir().is_dir() else current


def launch_command(spec: ServerSpec, settings: Settings) -> list[str]:
    args = [_fill(str(a), settings) for a in spec.args]
    if spec.type == "npm":
        npx = shutil.which("npx", path=tool_path()) or "npx"
        return [npx, "-y", f"{spec.package}@{spec.version}", *args]
    if spec.type == "pypi":
        return ["uvx", "--from", f"{spec.package}=={spec.version}", spec.bin or spec.package, *args]
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
        opened and closed by the same task."""
        info = self.status[spec.name]
        source = f"mcp:{spec.name}"
        try:
            self.settings.workspace.mkdir(parents=True, exist_ok=True)
            with open(os.devnull, "w") as quiet:
                connection = self._connection(spec)
                if isinstance(connection, StdioServerParameters):
                    from mcp import stdio_client

                    connection = stdio_client(connection, errlog=quiet)
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
                        for remote in tools:
                            self.registry.add(self._wrap(spec, source, client, remote))
                        info.update(state="running", tools=len(tools))
                        ready.set()
                        await self._stop.wait()
        except TimeoutError:
            info.update(state="failed", error=f"did not start within {self.start_timeout:g} seconds")
        except BaseException as e:  # includes ExceptionGroup from the client's task group
            if isinstance(e, asyncio.CancelledError):
                raise
            info.update(state="failed", error=_explain(e))
        finally:
            self.registry.remove_source(source)
            if info["state"] == "running":
                info.update(state="stopped", tools=0)
            ready.set()

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
