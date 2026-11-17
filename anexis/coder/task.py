"""The code_task tool: Claude first, Anexis's own coder when Claude cannot."""

from __future__ import annotations

import re
import time
from pathlib import Path

from anexis.coder.claude import ClaudeRunner
from anexis.coder.fallback import FallbackCoder
from anexis.tools.base import DANGER, Tool, ToolContext, params, text


def project_dir(settings, name: str) -> Path:
    """Every project lives in its own folder directly under the workspace."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")[:60] or "project"
    return settings.workspace / slug


def _guidance(memory, task: str) -> str:
    """What the owner has said about how they like their code, for the coder to follow."""
    found = memory.search(f"code coding programming style {task}", k=8)
    lines = [m.text for m in found if m.kind in ("lesson", "preference")][:5]
    if not lines:
        return ""
    return "The owner's standing preferences:\n" + "\n".join(f"- {line}" for line in lines)


def make_code_tool(claude: ClaudeRunner, fallback: FallbackCoder) -> Tool:
    async def code_task(args: dict, ctx: ToolContext) -> str:
        task = str(args.get("task", "")).strip()
        if not task:
            return "Error: describe what to build"
        project = project_dir(ctx.settings, args.get("project") or "project")
        project.mkdir(parents=True, exist_ok=True)
        guidance = _guidance(ctx.memory, task)

        usable, why_not = claude.available()
        if usable:
            ctx.emit({"type": "status", "text": "Claude is coding..."})
            result = await claude.run(task, project, guidance)
            if result.ok:
                which = f" ({result.note})" if result.note else ""
                return f"Written by: Claude Code{which}\nProject folder: {project}\n\n{result.text}"
            if result.limited:
                until = time.strftime("%H:%M", time.localtime(result.reset_at))
                why_not = f"Claude is out of usage until {until}"
            else:
                why_not = result.error

        ctx.emit({"type": "status", "text": f"{why_not}. Coding it myself..."})
        own = await fallback.run(task, project, guidance)
        if not own.ok:
            return (
                f"Error: the coding task did not finish.\nClaude: {why_not}\n"
                f"My own coder: {own.text}\nProject folder: {project}"
            )
        files = f"\nFiles: {', '.join(own.files)}" if own.files else ""
        return (
            f"Written by: Anexis's own coder model ({own.model}), because {why_not}.\n"
            f"Project folder: {project}{files}\n\n{own.text}"
        )

    return Tool(
        "code_task",
        "Build or change software: write a program, script, app, fix a bug, add a feature. "
        "Hands the job to a coding agent that works in its own project folder, writes files and runs them. "
        "Use this for any real coding work instead of writing code in the chat. Always tell the owner who wrote the code, as stated in the result.",
        params(["project", "task"],
               project=text("Short project name. Reuse the same name to keep working on a project."),
               task=text("Everything the coder needs: what to build, language, inputs, outputs, how to check it works.")),
        code_task,
        tier=DANGER,
    )
