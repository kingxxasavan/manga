import subprocess
import sys
import time

import psutil

from anexis import platform
from anexis.tools.builtin.system import run_process

PARENT = (
    "import subprocess, sys, time;"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
    "print(child.pid, flush=True); time.sleep(60)"
)


def test_kill_tree_ends_a_program_and_what_it_started():
    parent = subprocess.Popen([sys.executable, "-c", PARENT], stdout=subprocess.PIPE, **platform.spawn_kwargs())
    child_pid = int(parent.stdout.readline())
    assert psutil.pid_exists(child_pid)
    platform.kill_tree(parent.pid)
    parent.wait(5)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and platform.is_running(child_pid):
        time.sleep(0.05)
    assert not platform.is_running(child_pid)


def test_kill_tree_is_quiet_about_a_program_that_is_gone():
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    platform.kill_tree(done.pid)


def test_shell_argv_runs_one_line_of_shell():
    out = subprocess.run(platform.shell_argv("echo hi"), capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "hi"


async def test_a_timed_out_command_leaves_nothing_running(tmp_path):
    marker = tmp_path / "pid"
    script = f"import os, time; open(r'{marker}', 'w').write(str(os.getpid())); time.sleep(60)"
    code, _ = await run_process([sys.executable, "-c", script], tmp_path, timeout=2)
    assert code is None
    assert not platform.is_running(int(marker.read_text()))


async def test_a_shell_line_goes_through_the_system_shell(tmp_path):
    code, output = await run_process("echo one && echo two", tmp_path, timeout=30)
    assert code == 0 and output.split() == ["one", "two"]


def test_only_a_real_anexis_server_counts_as_one():
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "serve"])
    try:
        assert not platform.is_anexis_server(other.pid)
        assert platform.is_running(other.pid)
    finally:
        other.kill()
        other.wait()
    assert not platform.is_running(other.pid)


def test_tool_path_puts_the_bundled_runtime_first(tmp_path, monkeypatch):
    from anexis.tools import mcp_client

    (tmp_path / "node").mkdir()
    monkeypatch.setenv("ANEXIS_RUNTIME", str(tmp_path))
    assert mcp_client.tool_path().split(platform.os.pathsep)[0] == str(tmp_path / "node")


def test_stopping_a_program_ends_what_it_started_too():
    parent = subprocess.Popen([sys.executable, "-c", PARENT], stdout=subprocess.PIPE)
    child_pid = int(parent.stdout.readline())
    platform.stop_process(parent.pid, grace=5)
    parent.wait(5)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and platform.is_running(child_pid):
        time.sleep(0.05)
    assert not platform.is_running(child_pid)


def test_a_program_is_found_by_name_and_a_path_is_left_alone(tmp_path):
    assert platform.find_program(sys.executable) == sys.executable
    assert platform.os.path.isabs(platform.find_program("python3" if not platform.IS_WINDOWS else "python"))
    assert platform.find_program("no-such-program-xyz") == "no-such-program-xyz"
    tool = tmp_path / "mytool"
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    assert platform.find_program("mytool", str(tmp_path)) == str(tool)
