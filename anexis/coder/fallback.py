"""Anexis's own coder, used when Claude is out of usage or unavailable.

A plain loop with the coder model: look, look things up, write, run, fix.
Everything it does is fenced to the project folder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from anexis.config import Settings
from anexis.llm.provider import ProviderError
from anexis.llm.router import AllProvidersFailed
from anexis.memory.store import Memory
from anexis.tools.base import Tool, ToolContext, params, text
from anexis.tools.builtin.system import _report, run_process
from anexis.tools.registry import Registry

# Reference tools borrowed from the main registry when they exist.
REFERENCE_TOOLS = ("github_search_repos", "github_search_code", "github_read_file", "web_search", "web_fetch")
REFERENCE_SOURCES = ("mcp:docs", "mcp:deepwiki")

# The owner approved work inside the project folder, not these.
NOT_ALLOWED = [
    r"\bsudo\b", r"\bsu\s", r"\bgit\s+push\b", r"\|\s*(ba|z)?sh\b", r"\bmkfs", r"\bdd\s+if=",
    r"\b(shutdown|reboot|halt|poweroff)\b", r">\s*/dev/", r":\(\)\s*\{",
    r"\brm\s+(-\w+\s+)*(/|~|\$HOME|\.\.)", r"\b(ssh|scp|rsync)\b", r"\b(npm\s+publish|twine\s+upload)\b",
    r"\bcrontab\b", r"\bsystemctl\b",
]

SYSTEM = """You are a careful software engineer working alone inside one project folder. The task comes from the owner of this server.

Work in small steps: look at what already exists, look up reference code or documentation when you are not sure how something is done, write the files, run them or their tests, and fix what fails. All file paths are relative to the project folder and you cannot leave it.

When you are finished, reply without calling a tool: say what you built, how to run it, and anything that does not work yet. Never say something works unless you ran it and saw it work.
{guidance}"""


@dataclass
class CodeResult:
    ok: bool
    text: str
    files: list[str] = field(default_factory=list)
    model: str = ""


class FallbackCoder:
    def __init__(self, settings: Settings, memory: Memory, router, registry: Registry):
        self.settings = settings
        self.memory = memory
        self.router = router
        self.registry = registry

    def _tools(self, project: Path, written: list[str]) -> dict[str, Tool]:
        root = project.resolve()

        def locate(raw) -> Path | None:
            path = (root / str(raw or ".")).resolve() if not Path(str(raw or ".")).is_absolute() else Path(str(raw)).resolve()
            return path if path.is_relative_to(root) else None

        outside = "Error: that path is outside the project folder, which is not allowed."

        async def list_dir(args, ctx):
            path = locate(args.get("path"))
            if path is None:
                return outside
            if not path.is_dir():
                return "Error: no such folder"
            names = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())
            return "\n".join(names[:300]) or "(empty)"

        async def read_file(args, ctx):
            path = locate(args.get("path"))
            if path is None:
                return outside
            if not path.is_file():
                return "Error: file not found"
            return path.read_text(errors="replace")[:60_000]

        async def write_file(args, ctx):
            path = locate(args.get("path"))
            if path is None or path == root:
                return outside
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(args.get("content", "")))
            relative = str(path.relative_to(root))
            if relative not in written:
                written.append(relative)
            return f"Wrote {relative}"

        async def run(args, ctx):
            command = str(args.get("command", "")).strip()
            if not command:
                return "Error: no command given"
            if any(re.search(pattern, command) for pattern in NOT_ALLOWED):
                return "Error: that command is not allowed here. Stay inside the project folder, no sudo, no pushing, no piping downloads into a shell."
            timeout = min(float(args.get("timeout") or 120), 600)
            code, output = await run_process(command, root, timeout)
            return _report(code, output, timeout, self.settings.tool_output_chars)

        path_arg = text("Path relative to the project folder")
        own = [
            Tool("list_dir", "List files in the project folder.", params(path=path_arg), list_dir),
            Tool("read_file", "Read a file in the project.", params(["path"], path=path_arg), read_file),
            Tool("write_file", "Create or overwrite a file in the project. Always send the full content.",
                 params(["path", "content"], path=path_arg, content=text("Full file content")), write_file),
            Tool("run", "Run a shell command in the project folder, for example tests or the program itself.",
                 params(["command"], command=text("The command"), timeout={"type": "number"}), run),
        ]
        tools = {t.name: t for t in own}
        for candidate in self.registry.all():
            if candidate.name in REFERENCE_TOOLS or candidate.source in REFERENCE_SOURCES:
                tools.setdefault(candidate.name, candidate)
        return tools

    async def run(self, task: str, project: Path, guidance: str = "") -> CodeResult:
        written: list[str] = []
        tools = self._tools(project, written)
        schemas = [t.schema() for t in tools.values()]
        ctx = ToolContext(settings=self.settings, memory=self.memory, router=self.router,
                          registry=self.registry, session_id="coder")
        messages = [
            {"role": "system", "content": SYSTEM.format(guidance=guidance)},
            {"role": "user", "content": f"Project folder: {project}\n\nTask:\n{task}"},
        ]
        model = ""
        try:
            for _ in range(self.settings.fallback_rounds):
                reply = await self.router.chat("coder", messages, schemas)
                model = f"{reply.provider}:{reply.model}"
                if not reply.tool_calls:
                    return CodeResult(True, reply.content, written, model)
                messages.append(reply.message())
                for tool_call in reply.tool_calls:
                    tool = tools.get(tool_call.name)
                    if tool is None:
                        output = f"Error: no tool named {tool_call.name}"
                    else:
                        try:
                            output = str(await tool.handler(tool_call.arguments, ctx))
                        except Exception as e:
                            output = f"Error: {type(e).__name__}: {e}"
                    limit = self.settings.tool_output_chars
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": output[:limit]})
        except (AllProvidersFailed, ProviderError) as e:
            return CodeResult(False, f"No model could do the coding. {e}", written, model)
        return CodeResult(
            False,
            f"Stopped after {self.settings.fallback_rounds} rounds without finishing. "
            f"Files written so far: {', '.join(written) or 'none'}.",
            written, model,
        )
