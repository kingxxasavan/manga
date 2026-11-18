"""Notices when files change, by looking. Polling a few dozen files once a
second costs nothing and works the same on every system and every disk."""

from __future__ import annotations

import os
from pathlib import Path

SKIP = {"__pycache__", "node_modules", ".git", ".venv", "dist", "build"}


def snapshot(root, suffixes: tuple[str, ...] = ()) -> dict[str, tuple[float, int]]:
    """path -> (modified time, size) for every file under root with one of the
    suffixes, or every file when none are given."""
    found: dict[str, tuple[float, int]] = {}
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for name in names:
            if suffixes and not name.endswith(suffixes):
                continue
            if name.endswith(("~", ".tmp", ".swp")) or name.startswith(".#"):
                continue  # an editor's scratch copy, not a real change
            path = os.path.join(folder, name)
            try:
                info = os.stat(path)
            except OSError:
                continue
            found[path] = (info.st_mtime, info.st_size)
    return found


def changed(before: dict, after: dict) -> list[str]:
    """Files that are new, gone or different, sorted."""
    return sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))


def broken(paths: list[str]) -> list[dict]:
    """Python files among `paths` that do not even parse. Starting the brain
    on one of these would only crash it."""
    out = []
    for path in paths:
        if not path.endswith(".py") or not os.path.isfile(path):
            continue
        try:
            compile(Path(path).read_text(encoding="utf-8"), path, "exec")
        except SyntaxError as e:
            out.append({"file": path, "line": e.lineno or 0, "message": e.msg})
        except (OSError, ValueError) as e:
            out.append({"file": path, "line": 0, "message": str(e)})
    return out
