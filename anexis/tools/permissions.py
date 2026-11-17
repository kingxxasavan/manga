"""Decides if a tool call just runs or has to ask the owner first."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from anexis.tools.base import DANGER, SAFE, Tool

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


def _from_uri(value: str) -> str:
    return unquote(urlparse(value).path) if value.startswith("file://") else value


def _looks_like_path(value: str) -> bool:
    """A single word that starts like an absolute path, a home path, a climb
    out of the folder, or a file link. Ordinary text has spaces and web links
    start with http, so neither is caught."""
    if len(value) < 2 or len(value) > 1024 or any(c.isspace() for c in value):
        return False
    return value.startswith(("/", "~/", "../", "file://")) or value in ("~", "..")


def _paths(args, under_path_key: bool = False) -> list[str]:
    """Every value that is a path: anything under a known path argument name,
    plus anything anywhere that plainly looks like a path. Tool servers name
    their arguments however they like, so the name alone is not trusted."""
    if isinstance(args, dict):
        found: list[str] = []
        for key, value in args.items():
            found += _paths(value, str(key).lower() in PATH_KEYS)
        return found
    if isinstance(args, (list, tuple)):
        return [p for value in args for p in _paths(value, under_path_key)]
    if isinstance(args, (str, Path)) and str(args) and (under_path_key or _looks_like_path(str(args))):
        return [_from_uri(str(args))]
    return []


def decide(tool: Tool, args: dict, settings) -> tuple[str, str]:
    """Returns ("allow" or "ask", reason)."""
    override = settings.permissions.get(tool.name)
    if override in ("allow", "ask"):
        return override, "set in your config"
    if getattr(settings, "control", "ask") == "full":
        return "allow", "full control is on"
    if tool.tier == SAFE:
        return "allow", ""
    if tool.tier == DANGER:
        return "ask", "this can change things on the server or send things out"
    outside = [p for p in _paths(args) if not inside(p, settings.workspace)]
    if outside:
        return "ask", f"touches a path outside the workspace: {outside[0]}"
    return "allow", ""
