"""anexis doctor: one line per part, working or what is missing and how to fix it."""

from __future__ import annotations

import importlib.util
import re
import shutil

from anexis.tools.builtin.system import run_process
from anexis.tools.mcp_client import tool_path


def check(part: str, ok: bool, detail: str, fix: str = "", optional: bool = False) -> dict:
    """`optional` parts are extras. When missing they are shown, but Anexis is not broken."""
    return {"part": part, "ok": ok, "detail": detail, "fix": "" if ok else fix, "optional": optional}


async def _version(program: str, path: str | None = None) -> str | None:
    found = shutil.which(program, path=path)
    if not found:
        return None
    try:
        code, output = await run_process([found, "--version"], ".", 15)
    except OSError:
        return None
    return output.strip().splitlines()[0] if code == 0 and output.strip() else None


async def doctor(anexis) -> list[dict]:
    settings = anexis.settings
    out: list[dict] = []

    problems = settings.problems() + settings.warnings()
    out.append(check("config", not problems, "; ".join(problems) or "ok", "run `anexis setup --keys` for keys, or `anexis setup` to redo the settings"))

    for provider in await anexis.router.status():
        name = f"model: {provider['name']}"
        if not provider["ok"]:
            fix = "start Ollama (`ollama serve`)" if provider["name"] == "ollama" else "check the API key and your network"
            out.append(check(name, False, provider.get("error", "not reachable"), fix))
        elif provider["missing"]:
            pull = " && ".join(f"ollama pull {m}" for m in provider["missing"])
            fix = pull if provider["name"] == "ollama" else "these were retired or renamed. Pick ones this provider has now: Models in the app, or anexis.toml"
            out.append(check(name, False, "missing models: " + ", ".join(provider["missing"]), fix))
        else:
            out.append(check(name, True, ", ".join(f"{r}={m}" for r, m in provider["models"].items()) or "reachable"))

    try:
        embedded = await anexis.router.embed(["hello"], "query")
    except Exception:
        embedded = None
    out.append(check("embeddings", bool(embedded), f"using {embedded[0]}" if embedded else "no embedding model answered",
                     "memory still works by word match. For meaning search: ollama pull the embed model", optional=True))

    out.append(check("memory", True, f"{anexis.memory.count()} memories in {settings.db_path}"))
    pinned = len(anexis.memory.pinned())
    out.append(check("about me", pinned > 0, f"{pinned} things known about you", "open About me in the app, or run `anexis aboutme`", optional=True))

    claude = await _version(settings.claude_bin)
    usable, why = anexis.claude.available()
    if not claude:
        out.append(check("claude code", False, "not installed", "npm install -g @anthropic-ai/claude-code, then run `claude` once to log in or set ANTHROPIC_API_KEY. Code tasks use Anexis's own coder until then.", optional=True))
    elif not usable:
        out.append(check("claude code", False, why, "nothing to do, it comes back by itself", optional=True))
    else:
        auth = await anexis.claude.auth()
        how = {"claude.ai": "your Claude plan", "oauth_token": "your Claude plan", "api_key": "an API key"}.get(auth["method"], auth["method"])
        if auth["signed_in"]:
            reading = await anexis.claude.usage() if auth.get("plan") else None
            used = f", plan {reading['percent']:.0f}% used" if reading else ""
            out.append(check("claude code", True, f"{claude}, signed in with {how}{used}"))
        else:
            out.append(check("claude code", False, f"{claude}, not signed in",
                             "sign in with your Claude plan: Keys in the app, or `claude auth login` in a terminal. Code tasks use Anexis's own coder until then.", optional=True))

    node = await _version("node", tool_path())
    major = int(re.search(r"v?(\d+)", node).group(1)) if node and re.search(r"v?(\d+)", node) else 0
    out.append(check("node", major >= 24, node or "not installed", "run bash setup.sh again and say yes to Node, the npm tool servers need version 24 or newer"))
    uvx = shutil.which("uvx", path=tool_path())
    out.append(check("uv", bool(uvx), uvx or "not installed", "install uv, the Python tool servers are run with uvx"))

    if not settings.outside_tools:
        out.append(check("outside tools", True, "switched off, only the built in tools are used"))
    for name, info in sorted(anexis.mcp.status.items()):
        state = info["state"]
        if state == "running":
            out.append(check(f"tool: {name}", True, f"{info['tools']} tools"))
        elif state == "needs key":
            out.append(check(f"tool: {name}", True, f"off, add {', '.join(info['needs'])} to .env to turn on"))
        elif state == "off":
            out.append(check(f"tool: {name}", True, "off in tools/manifest.yaml"))
        else:
            out.append(check(f"tool: {name}", False, info.get("error", state), "run `anexis tools sync` to see the full error"))

    whisper = importlib.util.find_spec("faster_whisper") is not None
    out.append(check("voice in", whisper, "speech to text ready" if whisper else "faster-whisper not installed", "bash setup.sh and say yes to voice", optional=True))
    piper = shutil.which(settings.piper_bin)
    out.append(check("voice out", bool(piper), piper or "piper not installed", "bash setup.sh and say yes to voice", optional=True))
    return out
