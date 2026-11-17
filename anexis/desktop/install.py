"""The downloads setup in the app can do for the owner: Ollama, the models,
Claude Code, the tool servers, voice. Each step reports as it goes.

Every step takes `run` (start a program, get its lines) and `fetch` (download
a file) as arguments, so the tests can script them.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from anexis.cli.setup import find_ollama
from anexis.config import REPO_ROOT
from anexis.platform import IS_WINDOWS, kill_tree, spawn_kwargs
from anexis.tools.mcp_client import tool_path

OLLAMA_WINDOWS = "https://ollama.com/download/OllamaSetup.exe"
OLLAMA_API = "http://127.0.0.1:11434"
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,120}")
PERCENT = re.compile(r"(\d{1,3})%")
ORDER = ("ollama", "models", "claude", "tools", "voice")

Emit = Callable[[dict], None]
Run = Callable[..., Awaitable[int]]
Fetch = Callable[..., Awaitable[None]]


class StepFailed(Exception):
    """A step could not finish. The message is shown to the owner as is."""


async def run_lines(argv: list[str], on_line: Callable[[str], None], env: dict | None = None, cwd=None) -> int:
    """Runs a program and hands over its output line by line. Progress bars
    that redraw one line with a carriage return count as lines too."""
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=cwd, env=env, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, **spawn_kwargs(),
    )
    pending = b""
    try:
        while chunk := await proc.stdout.read(4096):
            *lines, pending = re.split(rb"[\r\n]+", pending + chunk)
            for line in lines:
                if text := line.decode("utf-8", errors="replace").strip():
                    on_line(text)
        if text := pending.decode("utf-8", errors="replace").strip():
            on_line(text)
        return await proc.wait()
    finally:
        if proc.returncode is None:  # the owner closed setup half way
            kill_tree(proc.pid)
            await asyncio.shield(proc.wait())


async def fetch_file(url: str, dest: Path, on_percent: Callable[[int], None]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as http, http.stream("GET", url) as resp:
        resp.raise_for_status()
        total, got, shown = int(resp.headers.get("content-length") or 0), 0, -1
        with part.open("wb") as f:
            async for chunk in resp.aiter_bytes(1 << 16):
                f.write(chunk)
                got += len(chunk)
                percent = got * 100 // total if total else 0
                if percent != shown:
                    shown = percent
                    on_percent(percent)
    part.replace(dest)


def _tool_env() -> dict:
    return {**os.environ, "PATH": tool_path()}


async def _ollama_up() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as http:
            return (await http.get(f"{OLLAMA_API}/api/version")).status_code == 200
    except httpx.HTTPError:
        return False


async def step_ollama(settings, wanted, say, run: Run, fetch: Fetch) -> str:
    if find_ollama():
        return "already installed"
    if not IS_WINDOWS:
        raise StepFailed("Install Ollama yourself with: curl -fsSL https://ollama.com/install.sh | sh  (it needs your password, so the app cannot do it)")
    installer = settings.home / "downloads" / "OllamaSetup.exe"
    say("downloading the Ollama installer")
    await fetch(OLLAMA_WINDOWS, installer, lambda percent: say(f"downloading {percent}%", percent))
    say("installing Ollama")
    code = await run([str(installer), "/VERYSILENT", "/NORESTART"], say)
    if code != 0 or not find_ollama():
        raise StepFailed(f"The Ollama installer did not finish (exit code {code}). Run {installer} yourself, then press retry.")
    installer.unlink(missing_ok=True)
    return "installed"


async def step_models(settings, wanted, say, run: Run, fetch: Fetch) -> str:
    models = [m for m in wanted.get("models") or [] if isinstance(m, str)]
    if not models:
        return "nothing to download"
    bad = [m for m in models if not MODEL_NAME.fullmatch(m)]
    if bad:
        raise StepFailed(f"That is not a model name: {bad[0]}")
    ollama = find_ollama()
    if not ollama:
        raise StepFailed("Ollama is not installed, so there is nothing to download the models with.")
    if not await _ollama_up():
        say("starting Ollama")
        import subprocess

        subprocess.Popen([ollama, "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **spawn_kwargs(detached=True))
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await _ollama_up():
                break
        else:
            raise StepFailed("Ollama is installed but did not start. Open Ollama from the Start menu, then press retry.")
    for number, model in enumerate(models, 1):
        def progress(line: str, model=model, number=number) -> None:
            found = PERCENT.search(line)
            say(f"{model}  ({number} of {len(models)})  {line[:80]}", int(found.group(1)) if found else None)

        code = await run([ollama, "pull", model], progress)
        if code != 0:
            raise StepFailed(f"Could not download {model}. Check the internet connection and free disk space, then press retry.")
    return f"{len(models)} models ready"


async def step_claude(settings, wanted, say, run: Run, fetch: Fetch) -> str:
    path = tool_path()
    claude = shutil.which(settings.claude_bin, path=path)
    if not claude:
        npm = shutil.which("npm", path=path)
        if not npm:
            raise StepFailed("Node is not installed, and Claude Code needs it. Install Node 24 from nodejs.org, then press retry.")
        code = await run([npm, "install", "-g", "@anthropic-ai/claude-code"], say, env=_tool_env())
        claude = shutil.which(settings.claude_bin, path=tool_path())
        if code != 0 or not claude:
            raise StepFailed("Claude Code did not install. See the lines above for why.")
    # Lets Claude look up the owner's preferences while it codes. A bonus, so a
    # failure here (it is already registered, mostly) never fails the step.
    memory_server = [sys.executable, "-m", "anexis", "mcp"]
    await run([claude, "mcp", "add", "--scope", "user", "-e", f"PYTHONPATH={REPO_ROOT}", "anexis-memory", "--", *memory_server],
              lambda line: None, env=_tool_env())
    return "ready. Add an Anthropic key, or run `claude` once in the terminal panel to log in"


async def step_tools(settings, wanted, say, run: Run, fetch: Fetch) -> str:
    code = await run([sys.executable, "-m", "anexis", "tools", "sync"], say, env=_tool_env(), cwd=str(REPO_ROOT))
    if code != 0:
        raise StepFailed("Some tool servers did not start. They are tried again each time Anexis starts.")
    return "downloaded"


async def step_voice(settings, wanted, say, run: Run, fetch: Fetch) -> str:
    uv = shutil.which("uv", path=tool_path())
    if not uv:
        raise StepFailed("uv is missing, so the voice packages cannot be installed.")
    say("installing speech to text and text to speech")
    code = await run([uv, "pip", "install", "--python", sys.executable, "--break-system-packages",
                      "faster-whisper>=1.1", "piper-tts"], say, env=_tool_env())
    if code != 0:
        raise StepFailed("The voice packages did not install. See the lines above for why.")
    say(f"downloading the voice {settings.tts_voice}")
    code = await run([sys.executable, "-m", "piper.download_voices", settings.tts_voice,
                      "--data-dir", str(settings.home / "voices")], say, env=_tool_env())
    if code != 0:
        raise StepFailed("The voice file did not download. Press retry when the internet is back.")
    return "installed"


STEPS = {"ollama": step_ollama, "models": step_models, "claude": step_claude, "tools": step_tools, "voice": step_voice}


def chosen_steps(wanted: dict) -> list[str]:
    return [name for name in ORDER if wanted.get(name)]


async def install(settings, wanted: dict, emit: Emit, run: Run = run_lines, fetch: Fetch = fetch_file) -> bool:
    """Runs the chosen steps in order. One failing step does not stop the
    ones after it, except that models are skipped when Ollama failed."""
    ok, failed = True, set()
    for name in chosen_steps(wanted):
        if name == "models" and "ollama" in failed:
            emit({"step": name, "state": "skipped", "message": "Ollama is not installed"})
            continue

        def say(line: str, percent: int | None = None, name=name) -> None:
            emit({"step": name, "state": "progress", "line": line, **({"percent": percent} if percent is not None else {})})

        emit({"step": name, "state": "start"})
        try:
            message = await STEPS[name](settings, wanted, say, run, fetch)
            emit({"step": name, "state": "done", "message": message})
        except StepFailed as e:
            ok = False
            failed.add(name)
            emit({"step": name, "state": "failed", "message": str(e)})
        except (OSError, httpx.HTTPError) as e:
            ok = False
            failed.add(name)
            emit({"step": name, "state": "failed", "message": f"{type(e).__name__}: {e}"})
    emit({"state": "finished", "ok": ok})
    return ok
