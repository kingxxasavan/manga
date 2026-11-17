"""Runs the deck's browser test (tests/ui/deck.mjs) as part of the suite.

It needs Node with Playwright and a Chromium it can start. Where those are
missing the test is skipped, not failed: the rest of the suite does not need
a browser.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _playwright_ready() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    probe = subprocess.run([node, "-e", "require('playwright')"], capture_output=True, cwd=REPO)
    return probe.returncode == 0


@pytest.mark.skipif(not _playwright_ready(), reason="needs Node with Playwright")
def test_the_deck_works_in_a_real_browser():
    run = subprocess.run(
        ["node", "tests/ui/deck.mjs"], cwd=REPO, capture_output=True, text=True, timeout=420,
        env={**__import__("os").environ, "DECK_PYTHON": sys.executable},
    )
    assert run.returncode == 0, run.stdout[-4000:] + run.stderr[-2000:]
