"""Decides if a tool call just runs or has to ask the owner first."""

from __future__ import annotations

from pathlib import Path

from greg.tools.base import DANGER, SAFE, Tool

# Argument names that hold a file or folder path, across built in and MCP tools.
PATH_KEYS = {
    "path", "paths", "file", "filepath", "file_path", "filename", "directory", "dir",
    "source", "destination", "target", "repo_path", "cwd", "output_path", "input_path",
}


def resolve(path: str, workspace: Path) -> Path:
    """Where a path really points. Relative paths start at the workspace."""
    p = Path(str(path)).expanduser()
    if not p.is_absolute():
        p = workspace / p
    return p.resolve()


def inside(path: str, workspace: Path) -> bool:
    return resolve(path, workspace).is_relative_to(workspace.resolve())


def _paths(args: dict) -> list[str]:
    found: list[str] = []
    for key, value in args.items():
        if key.lower() not in PATH_KEYS:
            continue
        values = value if isinstance(value, list) else [value]
        found.extend(str(v) for v in values if isinstance(v, (str, Path)) and str(v))
    return found


def decide(tool: Tool, args: dict, settings) -> tuple[str, str]:
    """Returns ("allow" or "ask", reason)."""
    override = settings.permissions.get(tool.name)
    if override in ("allow", "ask"):
        return override, "set in your config"
    if tool.tier == SAFE:
        return "allow", ""
    if tool.tier == DANGER:
        return "ask", "this can change things on the server or send things out"
    outside = [p for p in _paths(args) if not inside(p, settings.workspace)]
    if outside:
        return "ask", f"touches a path outside the workspace: {outside[0]}"
    return "allow", ""
