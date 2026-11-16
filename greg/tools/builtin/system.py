"""Files, shell and Python on the server."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import tempfile

from greg.tools.base import DANGER, WRITE, Tool, ToolContext, params, text
from greg.tools.permissions import resolve

MAX_READ = 200_000


async def read_file(args: dict, ctx: ToolContext) -> str:
    path = resolve(args.get("path", ""), ctx.settings.workspace)
    if not path.is_file():
        return f"Error: file not found: {path}"
    data = path.read_bytes()[:MAX_READ]
    if b"\x00" in data[:4096]:
        return f"Error: {path.name} looks like a binary file ({path.stat().st_size} bytes)"
    return data.decode("utf-8", errors="replace")


async def write_file(args: dict, ctx: ToolContext) -> str:
    path = resolve(args.get("path", ""), ctx.settings.workspace)
    content = str(args.get("content", ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    if args.get("append"):
        with path.open("a", encoding="utf-8") as f:
            f.write(content)
    else:
        path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {path}"


async def list_dir(args: dict, ctx: ToolContext) -> str:
    path = resolve(args.get("path") or ".", ctx.settings.workspace)
    if not path.is_dir():
        return f"Error: folder not found: {path}"
    entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))[:300]
    if not entries:
        return f"{path} is empty."
    return f"{path}:\n" + "\n".join(
        f"  {e.name}/" if e.is_dir() else f"  {e.name}  ({e.stat().st_size} bytes)" for e in entries
    )


async def run_process(argv: list[str] | str, cwd, timeout: float, env: dict | None = None, stdin: bytes | None = None) -> tuple[int | None, str]:
    """Runs a program, returns (exit code or None on timeout, combined output).

    The program gets its own process group so a timeout kills everything it
    started, not just the first process.
    """
    kwargs = dict(
        cwd=str(cwd),
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
        env=env,
    )
    if isinstance(argv, str):
        proc = await asyncio.create_subprocess_shell(argv, **kwargs)
    else:
        proc = await asyncio.create_subprocess_exec(*argv, **kwargs)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(stdin), timeout)
        return proc.returncode, out.decode("utf-8", errors="replace")
    except TimeoutError:
        return None, ""
    finally:
        # Timed out, or the owner hung up mid command: nothing is left running.
        if proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await asyncio.shield(proc.wait())


def _report(code: int | None, output: str, timeout: float, limit: int) -> str:
    if code is None:
        return f"Error: timed out after {timeout:g} seconds and was stopped."
    if len(output) > limit:
        output = output[: limit // 2] + "\n... (middle cut) ...\n" + output[-limit // 2 :]
    return f"exit code {code}\n{output}".rstrip()


async def run_shell(args: dict, ctx: ToolContext) -> str:
    command = str(args.get("command", "")).strip()
    if not command:
        return "Error: no command given"
    cwd = resolve(args.get("cwd") or ".", ctx.settings.workspace)
    cwd.mkdir(parents=True, exist_ok=True)
    timeout = min(float(args.get("timeout") or 120), 1800)
    code, output = await run_process(command, cwd, timeout)
    return _report(code, output, timeout, ctx.settings.tool_output_chars)


async def run_python(args: dict, ctx: ToolContext) -> str:
    code = str(args.get("code", ""))
    if not code.strip():
        return "Error: no code given"
    ctx.settings.workspace.mkdir(parents=True, exist_ok=True)
    timeout = min(float(args.get("timeout") or 120), 1800)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
    try:
        status, output = await run_process([sys.executable, f.name], ctx.settings.workspace, timeout)
    finally:
        os.unlink(f.name)
    return _report(status, output, timeout, ctx.settings.tool_output_chars)


_PATH = text("File path. Relative paths start in the workspace folder.")

TOOLS = [
    Tool("read_file", "Read a text file.", params(["path"], path=_PATH), read_file, tier=WRITE),
    Tool("write_file", "Create or overwrite a text file. Set append to add to the end instead.",
         params(["path", "content"], path=_PATH, content=text("Full file content"), append={"type": "boolean"}),
         write_file, tier=WRITE),
    Tool("list_dir", "List the files and folders in a folder.", params(path=_PATH), list_dir, tier=WRITE),
    Tool("run_shell", "Run a shell command on the server. The owner is asked before it runs.",
         params(["command"], command=text("The command"), cwd=text("Folder to run in, default is the workspace"),
                timeout={"type": "number", "description": "Seconds before it is stopped, default 120"}),
         run_shell, tier=DANGER),
    Tool("run_python", "Run a Python script on the server and return what it prints. The owner is asked before it runs.",
         params(["code"], code=text("Python source"), timeout={"type": "number"}), run_python, tier=DANGER),
]
