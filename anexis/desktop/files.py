"""The deck's file browser: look around, nothing more. Changing files is done
through chat tools or the terminal, where it shows up in the activity feed."""

from __future__ import annotations

from pathlib import Path

import psutil

from anexis.platform import IS_WINDOWS

MAX_ENTRIES = 500


def list_folder(path: str, workspace: Path) -> dict:
    """Raises FileNotFoundError or NotADirectoryError with a message for the owner."""
    folder = Path(path).expanduser() if path else workspace
    if not folder.is_absolute():
        folder = workspace / folder
    folder = folder.resolve()
    if not folder.exists():
        raise FileNotFoundError(f"There is no folder at {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"{folder} is a file, not a folder")
    entries, hidden, denied = [], 0, False
    try:
        children = list(folder.iterdir())
    except PermissionError:
        children, denied = [], True
    for child in children:
        try:
            info = child.stat()
            is_dir = child.is_dir()
        except OSError:  # a broken link or something Windows will not let us look at
            hidden += 1
            continue
        entries.append({"name": child.name, "dir": is_dir, "size": 0 if is_dir else info.st_size,
                        "modified": info.st_mtime})
    entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
    parent = str(folder.parent) if folder.parent != folder else ""
    return {
        "path": str(folder), "parent": parent, "entries": entries[:MAX_ENTRIES],
        "more": max(0, len(entries) - MAX_ENTRIES), "unreadable": hidden, "denied": denied,
    }


def roots(workspace: Path, app_folder: Path) -> list[dict]:
    """Starting points: the places an owner actually goes."""
    home = Path.home()
    places = [("Workspace", workspace), ("Home", home)]
    places += [(name, home / name) for name in ("Desktop", "Documents", "Downloads")]
    places.append(("Anexis app", app_folder))
    if IS_WINDOWS:
        places += [(part.device.rstrip("\\"), Path(part.mountpoint)) for part in psutil.disk_partitions()]
    else:
        places.append(("/", Path("/")))
    seen, out = set(), []
    for name, path in places:
        if path.is_dir() and str(path) not in seen:
            seen.add(str(path))
            out.append({"name": name, "path": str(path)})
    return out
