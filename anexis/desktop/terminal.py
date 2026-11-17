"""A real terminal for the deck's terminal panel.

Linux and macOS use a pty. Windows uses ConPTY through pywinpty. When neither
can be loaded the shell still runs on plain pipes, which is enough for normal
commands but not for full screen programs.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import threading
from pathlib import Path

from anexis.platform import IS_WINDOWS, interactive_shell, kill_tree, spawn_kwargs


class Terminal:
    kind = "none"

    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._out: asyncio.Queue[bytes] = asyncio.Queue()
        self.closed = False

    def _feed(self, data: bytes) -> None:
        """Called from a reader thread. An empty chunk means the shell ended."""
        try:
            self._loop.call_soon_threadsafe(self._out.put_nowait, data)
        except RuntimeError:  # the server is shutting down
            pass

    async def read(self) -> bytes:
        """The next output. Empty bytes means the shell is gone."""
        return await self._out.get()

    def write(self, data: bytes) -> None: ...
    def resize(self, cols: int, rows: int) -> None: ...
    def close(self) -> None: ...


class PosixTerminal(Terminal):
    kind = "pty"

    def __init__(self, argv: list[str], cwd: str, cols: int, rows: int, env: dict):
        super().__init__()
        import pty

        self._master, slave = pty.openpty()
        self.resize(cols, rows)

        def own_terminal() -> None:  # runs in the child: make the pty its terminal
            import fcntl
            import termios

            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        try:
            self._proc = subprocess.Popen(
                argv, cwd=cwd, env=env, stdin=slave, stdout=slave, stderr=slave,
                preexec_fn=own_terminal, close_fds=True,
            )
        finally:
            os.close(slave)
        self._loop.add_reader(self._master, self._on_readable)

    def _on_readable(self) -> None:
        try:
            data = os.read(self._master, 65536)
        except OSError:
            data = b""
        if not data:
            self._loop.remove_reader(self._master)
        self._out.put_nowait(data)

    def write(self, data: bytes) -> None:
        if not self.closed:
            try:
                os.write(self._master, data)
            except OSError:
                pass

    def resize(self, cols: int, rows: int) -> None:
        import fcntl
        import struct
        import termios

        fcntl.ioctl(self._master, termios.TIOCSWINSZ, struct.pack("HHHH", max(1, rows), max(1, cols), 0, 0))

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self._loop.remove_reader(self._master)
        except (ValueError, OSError):
            pass
        kill_tree(self._proc.pid)
        self._proc.wait()
        os.close(self._master)


class WindowsTerminal(Terminal):
    kind = "conpty"

    def __init__(self, argv: list[str], cwd: str, cols: int, rows: int, env: dict):
        super().__init__()
        from winpty import PtyProcess

        self._proc = PtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=(max(1, rows), max(1, cols)))
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        while True:
            try:
                data = self._proc.read(65536)
            except (EOFError, OSError):
                data = ""
            if not data:
                self._feed(b"")
                return
            self._feed(data.encode("utf-8", errors="replace") if isinstance(data, str) else data)

    def write(self, data: bytes) -> None:
        if not self.closed:
            try:
                self._proc.write(data.decode("utf-8", errors="replace"))
            except (EOFError, OSError):
                pass

    def resize(self, cols: int, rows: int) -> None:
        try:
            self._proc.setwinsize(max(1, rows), max(1, cols))
        except (EOFError, OSError):
            pass

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            pid = self._proc.pid
            self._proc.terminate(force=True)
            kill_tree(pid)
        except Exception:  # already gone
            pass


class PipeTerminal(Terminal):
    """No terminal device at all, just the shell on pipes."""

    kind = "pipes"

    def __init__(self, argv: list[str], cwd: str, cols: int, rows: int, env: dict):
        super().__init__()
        self._proc = subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0, **spawn_kwargs(),
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        while True:
            data = self._proc.stdout.read(65536)  # unbuffered, so this returns what is there
            if not data:
                self._feed(b"")
                return
            self._feed(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))

    def write(self, data: bytes) -> None:
        if self.closed:
            return
        try:  # there is no terminal to echo what was typed or to turn Enter into a new line
            self._feed(data.replace(b"\r", b"\r\n"))
            self._proc.stdin.write(data.replace(b"\r", b"\n"))
            self._proc.stdin.flush()
        except OSError:
            pass

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        kill_tree(self._proc.pid)


def open_terminal(cwd: str | Path, cols: int = 100, rows: int = 30, argv: list[str] | None = None, plain: bool = False) -> Terminal:
    """Starts a shell in `cwd`. Must be called from the running event loop."""
    argv = argv or interactive_shell()
    folder = str(cwd) if Path(cwd).is_dir() else str(Path.home())
    env = {**os.environ, "TERM": "xterm-256color", "COLORTERM": "truecolor", "ANEXIS_TERMINAL": "1"}
    if not plain:
        try:
            kind = WindowsTerminal if IS_WINDOWS else PosixTerminal
            return kind(argv, folder, cols, rows, env)
        except (ImportError, OSError):
            pass
    return PipeTerminal(argv, folder, cols, rows, env)
