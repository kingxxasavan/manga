import json
import os
import socket
import sys
import threading
import time

import httpx
import pytest

from anexis.config import Settings
from anexis.desktop import watch
from anexis.desktop.supervisor import Supervisor


def test_snapshot_sees_new_changed_and_removed_files(tmp_path):
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "notes.txt").write_text("skip me")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "a.pyc").write_text("skip")
    first = watch.snapshot(tmp_path, (".py",))
    assert list(first) == [str(tmp_path / "a.py")]
    (tmp_path / "a.py").write_text("x = 22")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("y = 1")
    second = watch.snapshot(tmp_path, (".py",))
    assert watch.changed(first, second) == sorted([str(tmp_path / "a.py"), str(tmp_path / "sub" / "b.py")])
    (tmp_path / "a.py").unlink()
    assert watch.changed(second, watch.snapshot(tmp_path, (".py",))) == [str(tmp_path / "a.py")]
    assert watch.changed(second, second) == []


def test_broken_finds_the_file_and_line_that_do_not_parse(tmp_path):
    good, bad = tmp_path / "good.py", tmp_path / "bad.py"
    good.write_text("x = 1\n")
    bad.write_text("x = 1\ndef broken(:\n    pass\n")
    found = watch.broken([str(good), str(bad), str(tmp_path / "gone.py"), str(tmp_path / "x.txt")])
    assert [(e["file"], e["line"]) for e in found] == [(str(bad), 2)]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Running:
    """A supervisor in a thread, with the lines it printed."""

    def __init__(self, tmp_path, **kw):
        self.lines: list[str] = []
        self.code = tmp_path / "code"
        self.code.mkdir()
        (self.code / "part.py").write_text("x = 1\n")
        settings = Settings(home=tmp_path / "home", workspace=tmp_path / "ws", port=free_port(), token="tok")
        self.sup = Supervisor(settings, self.lines.append, watch_root=self.code, poll=0.15, **kw)
        self.sup.backoff = 0.05
        self.url = settings.url
        self.thread = threading.Thread(target=self.sup.run, daemon=True)
        self.thread.start()

    def states(self) -> list[str]:
        return [json.loads(line.split(" ", 1)[1]).get("state", "ready") for line in self.lines]

    def wait_for(self, state: str, count: int = 1, seconds: float = 60) -> dict:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.states().count(state) >= count:
                matching = [line for line in self.lines if json.loads(line.split(" ", 1)[1]).get("state", "ready") == state]
                return json.loads(matching[count - 1].split(" ", 1)[1])
            time.sleep(0.05)
        raise AssertionError(f"never saw {state} x{count}. Saw: {self.states()}")

    def health(self) -> dict:
        return httpx.get(self.url + "/health", headers={"Authorization": "Bearer tok"}, timeout=5).json()

    def stop(self) -> None:
        self.sup.stopping = True
        self.thread.join(30)


@pytest.fixture
def running(tmp_path, monkeypatch):
    monkeypatch.setenv("ANEXIS_OUTSIDE_TOOLS", "0")
    started = []

    def start(**kw):
        started.append(Running(tmp_path, **kw))
        return started[-1]

    yield start
    for one in started:
        one.stop()


def test_the_brain_comes_up_and_restarts_when_its_code_changes(running):
    r = running()
    ready = r.wait_for("ready")
    assert ready == {"url": r.url, "token": "tok"} and r.lines[1].startswith("ANEXIS_READY ")
    first = r.sup.child.pid
    assert r.health()["name"] == "Anexis"

    (r.code / "part.py").write_text("x = 2\n")
    note = r.wait_for("restarting")
    assert note["why"] == "code changed" and note["files"][0].endswith("part.py")
    r.wait_for("running")
    assert r.sup.child.pid != first and r.health()["name"] == "Anexis"


def test_a_file_that_does_not_parse_never_replaces_a_working_brain(running):
    r = running()
    r.wait_for("ready")
    first = r.sup.child.pid
    (r.code / "part.py").write_text("def broken(:\n")
    held = r.wait_for("held")
    assert held["errors"][0]["line"] == 1 and held["errors"][0]["file"].endswith("part.py")
    time.sleep(1.0)
    assert r.sup.child.pid == first and "restarting" not in r.states()
    assert r.health()["name"] == "Anexis"  # the old brain is still answering

    (r.code / "part.py").write_text("def fixed():\n    pass\n")
    r.wait_for("restarting")
    r.wait_for("running")
    assert r.sup.child.pid != first


def test_the_brain_can_ask_to_be_restarted(running):
    r = running()
    r.wait_for("ready")
    first = r.sup.child.pid
    reply = httpx.post(r.url + "/app/restart", headers={"Authorization": "Bearer tok"}, timeout=5).json()
    assert reply == {"restarting": True}
    assert r.wait_for("restarting")["why"] == "asked"
    r.wait_for("running")
    assert r.sup.child.pid != first


def test_a_brain_that_keeps_dying_is_left_alone_until_the_code_changes(running):
    r = running(command=[sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"], start_timeout=10)
    waiting = r.wait_for("waiting")
    assert r.states().count("crashed") == 3 and "boom" in waiting["log"]
    before = len(r.lines)
    time.sleep(0.6)
    assert len(r.lines) == before  # no restart loop
    (r.code / "part.py").write_text("x = 3\n")
    r.wait_for("restarting")


def test_stopping_the_supervisor_ends_the_brain(running):
    from anexis import platform

    r = running()
    r.wait_for("ready")
    pid = r.sup.child.pid
    r.stop()
    assert not platform.is_running(pid)
    assert not os.path.exists(r.sup.settings.home / "server.pid")


def test_being_told_to_end_takes_the_brain_along(tmp_path, monkeypatch):
    """`anexis desktop` killed with SIGTERM must not leave a brain running."""
    import signal
    import subprocess

    from anexis import platform

    port = free_port()
    env = {**os.environ, "ANEXIS_HOME": str(tmp_path / "home"), "ANEXIS_WORKSPACE": str(tmp_path / "ws"),
           "ANEXIS_PORT": str(port), "ANEXIS_OUTSIDE_TOOLS": "0"}
    proc = subprocess.Popen([sys.executable, "-m", "anexis", "desktop"], env=env, stdout=subprocess.PIPE, text=True)
    try:
        ready = ""
        while not ready.startswith("ANEXIS_READY"):
            ready = proc.stdout.readline()
            assert ready, "the supervisor ended before the brain was up"
        token = json.loads(ready.split(" ", 1)[1])["token"]
        assert len(token) >= 32  # the desktop always makes itself a token
        pid = int((tmp_path / "home" / "server.pid").read_text())
        assert platform.is_running(pid)
        proc.send_signal(signal.SIGTERM)
        proc.wait(30)
        deadline = time.monotonic() + 10
        while platform.is_running(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not platform.is_running(pid)
    finally:
        proc.kill()


def _sleeper():
    import subprocess

    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])


def _gone(pid: int, seconds: float = 20) -> bool:
    from anexis import platform

    deadline = time.monotonic() + seconds
    while platform.is_running(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    return not platform.is_running(pid)


def test_the_brain_ends_when_the_app_that_started_it_is_gone(tmp_path):
    """The Windows bug: quitting the app hard-ended the supervisor, and the brain
    under it (with JARVIS listening) kept running with no window. Here the
    "app" is a plain process that gets killed, like Windows does."""
    import subprocess

    from anexis import platform

    app = _sleeper()
    port = free_port()
    env = {**os.environ, "ANEXIS_HOME": str(tmp_path / "home"), "ANEXIS_WORKSPACE": str(tmp_path / "ws"),
           "ANEXIS_PORT": str(port), "ANEXIS_OUTSIDE_TOOLS": "0", "ANEXIS_PARENT_PID": str(app.pid)}
    sup = subprocess.Popen([sys.executable, "-m", "anexis", "desktop"], env=env, stdout=subprocess.PIPE, text=True)
    try:
        ready = ""
        while not ready.startswith("ANEXIS_READY"):
            ready = sup.stdout.readline()
            assert ready, "the supervisor ended before the brain was up"
        brain = int((tmp_path / "home" / "server.pid").read_text())
        assert platform.is_running(brain)
        app.kill()
        app.wait()
        sup.wait(30)
        assert _gone(brain), "the brain kept running after the app was gone"
    finally:
        sup.kill()
        app.kill()
        pid_file = tmp_path / "home" / "server.pid"
        if pid_file.exists():  # a failing run must not leave a brain behind
            platform.kill_tree(int(pid_file.read_text()))


def test_a_brain_whose_supervisor_was_killed_ends_itself(tmp_path):
    """The supervisor ended without a chance to clean up (Windows ends it hard
    when the app quits). The brain notices and ends too."""
    import subprocess

    supervisor = _sleeper()  # stands in for the supervisor that started the brain
    port = free_port()
    env = {**os.environ, "ANEXIS_HOME": str(tmp_path / "home"), "ANEXIS_WORKSPACE": str(tmp_path / "ws"),
           "ANEXIS_PORT": str(port), "ANEXIS_OUTSIDE_TOOLS": "0", "ANEXIS_TOKEN": "tok",
           "ANEXIS_PARENT_PID": str(supervisor.pid)}
    brain = subprocess.Popen([sys.executable, "-m", "anexis", "serve"], env=env)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/health", headers={"Authorization": "Bearer tok"}, timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        supervisor.kill()
        supervisor.wait()
        brain.wait(30)
    finally:
        brain.kill()
        supervisor.kill()
