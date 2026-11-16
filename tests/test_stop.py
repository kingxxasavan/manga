import subprocess
import sys
import time

from anexis.cli.main import pid_file, stop_server, write_pid


def spawn(*argv):
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", *argv])


def test_stop_ends_the_running_server_and_cleans_up(settings):
    settings.home.mkdir(parents=True)
    server = spawn("anexis", "serve")
    write_pid(settings.home, server.pid)
    assert stop_server(settings.home) is True
    assert server.wait(timeout=10) is not None
    assert not pid_file(settings.home).exists()


def test_stop_with_nothing_running_says_so(settings):
    settings.home.mkdir(parents=True)
    assert stop_server(settings.home) is False


def test_stop_never_kills_some_other_program_that_got_the_old_number(settings):
    settings.home.mkdir(parents=True)
    bystander = spawn("something", "else")
    write_pid(settings.home, bystander.pid)
    try:
        assert stop_server(settings.home) is False
        time.sleep(0.3)
        assert bystander.poll() is None  # still alive
        assert not pid_file(settings.home).exists()
    finally:
        bystander.kill()
