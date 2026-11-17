"""The `start` script in the repo folder: the simplest way to open the chat."""

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).parent.parent
PLAIN_PATH = "/usr/bin:/bin"


def fake_command(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "anexis"
    script.write_text('#!/bin/sh\necho "ran: $@"\n')
    script.chmod(0o755)


def start(script: Path, home: Path, path: str, *args):
    return subprocess.run(
        ["bash", str(script), *args], env={"PATH": path, "HOME": str(home)}, capture_output=True, text=True
    )


def copy_of_start(tmp_path: Path) -> Path:
    """The script alone in an empty folder, as if nothing is installed yet."""
    target = tmp_path / "clone" / "start"
    target.parent.mkdir()
    shutil.copy(REPO / "start", target)
    return target


def test_start_opens_the_installed_command_and_passes_arguments_on(tmp_path):
    fake_command(tmp_path / "bin")
    result = start(copy_of_start(tmp_path), tmp_path, f"{tmp_path / 'bin'}:{PLAIN_PATH}", "doctor", "--x")
    assert result.returncode == 0 and result.stdout.strip() == "ran: doctor --x"


def test_start_finds_the_command_in_the_home_folder_when_path_was_never_set_up(tmp_path):
    fake_command(tmp_path / ".local" / "bin")
    result = start(copy_of_start(tmp_path), tmp_path, PLAIN_PATH)
    assert result.returncode == 0 and result.stdout.strip() == "ran:"


def test_start_uses_the_copy_inside_the_folder_when_nothing_else_is_installed(tmp_path):
    script = copy_of_start(tmp_path)
    fake_command(script.parent / ".venv" / "bin")
    result = start(script, tmp_path, PLAIN_PATH, "ask", "hi")
    assert result.returncode == 0 and result.stdout.strip() == "ran: ask hi"


def test_start_before_setup_says_what_to_run(tmp_path):
    result = start(copy_of_start(tmp_path), tmp_path, PLAIN_PATH)
    assert result.returncode != 0
    assert "bash setup.sh" in result.stdout + result.stderr
