"""Keeps the brain running and restarts it when its code changes.

This is what makes the desktop app editable in place: change a Python file
under anexis/ and the server is started again within a second or two, with no
installer and no rebuild. A file that does not parse never replaces a brain
that works: the restart waits until the file is fixed.

It talks to whatever started it (the desktop frame, or `anexis ui`) through
single lines on standard output:
    ANEXIS_READY {"url": ..., "token": ...}   the brain answers, the first time
    ANEXIS_STATE {"state": ..., ...}          every change after that
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from anexis.config import REPO_ROOT, Settings
from anexis.desktop import watch
from anexis.platform import kill_tree, spawn_kwargs, stop_process

RESTART_CODE = 75
CRASH_WINDOW = 60.0   # this many seconds ...
CRASH_LIMIT = 4       # ... may hold this many crashes before it stops trying


class Supervisor:
    def __init__(
        self,
        settings: Settings,
        say: Callable[[str], None] | None = None,
        command: list[str] | None = None,
        watch_root: Path | None = None,
        poll: float = 0.5,
        start_timeout: float = 90.0,
    ):
        self.settings = settings
        self.say = say or (lambda line: print(line, flush=True))
        self.command = command or [sys.executable, "-m", "anexis", "serve"]
        self.watch_root = Path(watch_root or REPO_ROOT / "anexis")
        self.poll = poll
        self.start_timeout = start_timeout
        self.backoff = 1.0  # seconds before the first retry after a crash, doubled each time
        self.child: subprocess.Popen | None = None
        self.announced = False
        self.stopping = False
        self.crashes: list[float] = []
        self.waiting_for_fix = False
        self.log_path = settings.home / "server.log"

    # ---- talking to whoever started us -------------------------------------
    def state(self, state: str, **more) -> None:
        self.say("ANEXIS_STATE " + json.dumps({"state": state, **more}))

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.settings.token}"} if self.settings.token else {}

    def _healthy(self) -> bool:
        try:
            return httpx.get(f"{self.settings.url}/health", headers=self._headers(), timeout=3).status_code == 200
        except httpx.HTTPError:
            return False

    def notice(self, event: dict) -> None:
        """Shows something in the deck, through the brain that is still up."""
        try:
            httpx.post(f"{self.settings.url}/app/notice", json=event, headers=self._headers(), timeout=3)
        except httpx.HTTPError:
            pass

    # ---- the brain ---------------------------------------------------------
    def start(self) -> bool:
        """Starts the brain and waits until it answers. False when it died first."""
        self.settings.home.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ, "ANEXIS_SUPERVISED": "1", "PYTHONUNBUFFERED": "1",
            # The brain must come up exactly where this supervisor expects it.
            "ANEXIS_HOME": str(self.settings.home), "ANEXIS_HOST": self.settings.host,
            "ANEXIS_PORT": str(self.settings.port), "ANEXIS_WORKSPACE": str(self.settings.workspace),
        }
        if self.settings.token:
            env["ANEXIS_TOKEN"] = self.settings.token
        env["PYTHONPATH"] = os.pathsep.join(p for p in (str(REPO_ROOT), env.get("PYTHONPATH", "")) if p)
        with open(self.log_path, "a", encoding="utf-8") as log:
            log.write(f"\n--- starting the brain, {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            log.flush()
            self.child = subprocess.Popen(
                self.command, cwd=str(REPO_ROOT), env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=log, **spawn_kwargs(),
            )
        deadline = time.monotonic() + self.start_timeout
        while time.monotonic() < deadline and not self.stopping:
            if self.child.poll() is not None:
                return False
            if self._healthy():
                if not self.announced:
                    self.announced = True
                    self.say("ANEXIS_READY " + json.dumps({"url": self.settings.url, "token": self.settings.token}))
                else:
                    self.state("running")
                return True
            time.sleep(0.2)
        return False

    def stop_child(self) -> None:
        if self.child and self.child.poll() is None:
            stop_process(self.child.pid, grace=8)
            kill_tree(self.child.pid)
            try:
                self.child.wait(5)
            except subprocess.TimeoutExpired:
                pass
        # A brain that was told to stop does not get to tidy up after itself.
        (self.settings.home / "server.pid").unlink(missing_ok=True)

    def _log_tail(self, lines: int = 12) -> str:
        try:
            return "\n".join(self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
        except OSError:
            return ""

    def _crashed(self) -> bool:
        """Notes a crash. True when it is worth trying again right away."""
        now = time.monotonic()
        self.crashes = [t for t in self.crashes if now - t < CRASH_WINDOW] + [now]
        return len(self.crashes) < CRASH_LIMIT

    # ---- the loop ----------------------------------------------------------
    def run(self) -> int:
        """Runs until the brain is stopped on purpose. Returns the exit code."""
        seen = watch.snapshot(self.watch_root, (".py",))
        pending: list[str] = []
        quiet_since = 0.0
        self.state("starting")
        ok = self.start()
        try:
            while not self.stopping:
                if not ok or (self.child and self.child.poll() is not None):
                    code = self.child.poll() if self.child else 1
                    if ok and code == 0:
                        return 0  # stopped on purpose (`anexis stop`, or the frame closing)
                    if ok and code == RESTART_CODE:
                        self.state("restarting", why="asked")
                        ok = self.start()
                        continue
                    self.stop_child()
                    if self._crashed() and not self.waiting_for_fix:
                        self.state("crashed", code=code, log=self._log_tail())
                        time.sleep(min(self.backoff * 2 ** (len(self.crashes) - 1), 15))
                        ok = self.start()
                        continue
                    if not self.waiting_for_fix:
                        self.waiting_for_fix = True
                        self.state("waiting", why="The brain keeps stopping right after it starts. "
                                   "It will be started again when a file under anexis/ changes.",
                                   log=self._log_tail())

                time.sleep(self.poll)
                now = watch.snapshot(self.watch_root, (".py",))
                touched = watch.changed(seen, now)
                seen = now
                if touched:
                    pending = sorted(set(pending) | set(touched))
                    quiet_since = time.monotonic()
                    continue
                if not pending or time.monotonic() - quiet_since < self.poll:
                    continue  # an editor saving several files: wait for it to finish

                bad = watch.broken(pending)
                short = [os.path.relpath(p, REPO_ROOT) for p in pending]
                if bad:
                    for entry in bad:
                        entry["file"] = os.path.relpath(entry["file"], REPO_ROOT)
                    self.state("held", files=short, errors=bad)
                    self.notice({"type": "brain_error", "files": short, "errors": bad})
                    pending = [p for p in pending if any(os.path.relpath(p, REPO_ROOT) == e["file"] for e in bad)]
                    quiet_since = float("inf")  # nothing more to do until one of them changes again
                    continue
                pending = []
                self.crashes, self.waiting_for_fix = [], False
                self.state("restarting", why="code changed", files=short)
                self.notice({"type": "brain_restarting", "files": short})
                self.stop_child()
                ok = self.start()
            return 0
        except KeyboardInterrupt:
            return 0
        finally:
            self.stopping = True
            self.stop_child()
