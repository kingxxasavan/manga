"""The few places where Windows and Linux differ, kept in one file.

Everything else in Anexis calls these instead of asking which system it is on.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

IS_WINDOWS = sys.platform == "win32"


def spawn_kwargs(detached: bool = False) -> dict:
    """Keyword arguments that give a new program its own process group, so a
    timeout or a stop can end everything it started. `detached` also cuts it
    loose from this window, for a server that outlives the chat."""
    if not IS_WINDOWS:
        return {"start_new_session": True}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    if detached:
        flags |= subprocess.DETACHED_PROCESS
    return {"creationflags": flags}


def kill_tree(pid: int) -> None:
    """Ends a program and everything it started. Never raises for one that is
    already gone."""
    try:
        parent = psutil.Process(pid)
        family = parent.children(recursive=True)
    except psutil.Error:
        parent, family = None, []
    if not IS_WINDOWS:
        try:  # the whole group at once, which also catches children that were handed off
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    for proc in [*family, *([parent] if parent else [])]:
        try:
            proc.kill()
        except psutil.Error:
            pass
    psutil.wait_procs([*family, *([parent] if parent else [])], timeout=5)


def powershell() -> str:
    """PowerShell 7 when it is installed, the one built into Windows otherwise."""
    return shutil.which("pwsh") or shutil.which("powershell") or "powershell"


def shell_argv(command: str) -> list[str]:
    """How to run one line of shell on this system."""
    if IS_WINDOWS:
        return [powershell(), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
    return ["/bin/sh", "-c", command]


def interactive_shell() -> list[str]:
    """The shell a terminal panel opens."""
    if IS_WINDOWS:
        return [powershell(), "-NoLogo"]
    return [os.environ.get("SHELL") or shutil.which("bash") or "/bin/sh"]


def private_file(path) -> None:
    """Readable only by the owner. Windows keeps files in the user profile
    private already, and chmod means nothing there."""
    if not IS_WINDOWS:
        os.chmod(path, 0o600)


def _words(pid: int) -> list[str] | None:
    try:
        proc = psutil.Process(pid)
        if proc.status() == psutil.STATUS_ZOMBIE:
            return None
        return [re.split(r"[\\/]", part)[-1].lower() for part in proc.cmdline()]
    except psutil.Error:
        return None


def is_running(pid: int) -> bool:
    return _words(pid) is not None


def is_anexis_server(pid: int) -> bool:
    """True only when that process really is `anexis serve`, so a stale pid
    file can never get some other program stopped."""
    words = _words(pid) or []
    return "serve" in words and any(w in ("anexis", "anexis.exe") for w in words)


def watch_parent(pid: int, on_gone, every: float = 2.0) -> None:
    """Calls `on_gone()` once, from a background thread, when process `pid`
    has ended. For a program that must not outlive whatever started it:
    Windows never ends a program because its parent ended, so without this a
    hard ended app leaves its brain (and JARVIS listening) running alone."""
    import threading

    try:
        parent = psutil.Process(pid)
    except psutil.Error:
        parent = None

    def alive() -> bool:
        try:  # is_running() also checks the start time, so a reused pid does not count
            return parent is not None and parent.is_running() and parent.status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            return False

    def watch() -> None:
        while alive():
            time.sleep(every)
        on_gone()

    threading.Thread(target=watch, name="watch-parent", daemon=True).start()


def parent_from_env() -> int | None:
    """The pid in ANEXIS_PARENT_PID: the program this one must not outlive."""
    try:
        return int(os.environ.get("ANEXIS_PARENT_PID", "")) or None
    except ValueError:
        return None


def stop_process(pid: int, grace: float = 10.0) -> None:
    """Asks a program to stop, and ends it for real when it does not. Whatever
    it started (tool servers, a running command) is ended with it, so nothing
    is left behind without a parent."""
    try:
        proc = psutil.Process(pid)
        family = proc.children(recursive=True)
        proc.terminate()
        try:
            proc.wait(grace)
        except psutil.TimeoutExpired:
            kill_tree(pid)
    except psutil.Error:
        return
    for child in family:
        try:
            child.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(family, timeout=5)


def find_program(name: str, search_path: str | None = None) -> str:
    """The full path of a program given by name. On Windows a tool installed
    by npm is a .cmd file, which only starts when named in full."""
    if os.path.dirname(name):
        return name
    return shutil.which(name, path=search_path) or name


def memory_gb() -> float:
    return psutil.virtual_memory().total / 1024**3


def open_with_default_app(path: str) -> None:
    """Opens a file, folder or link the way a double click would. The path is
    handed over as one argument, never as part of a shell line."""
    if IS_WINDOWS:
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path], **spawn_kwargs())
    else:
        opener = shutil.which("xdg-open")
        if not opener:
            raise OSError("No program to open things with (xdg-open is missing)")
        subprocess.Popen([opener, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **spawn_kwargs())


def bundled_runtime() -> Path | None:
    """The folder the Windows installer put Python, Node and uv in, when this
    is the installed app."""
    given = os.environ.get("ANEXIS_RUNTIME")
    return Path(given) if given and Path(given).is_dir() else None
