"""Runs the scripted server under the real supervisor, the way the desktop
app runs the real brain. Usage: supervise.py <home> <port> <code dir> <ui dir>"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from anexis.config import Settings
from anexis.desktop.supervisor import Supervisor

home, port, code, ui = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
os.environ.update(ANEXIS_UI_DIR=ui, ANEXIS_OUTSIDE_TOOLS="0")
settings = Settings(home=home / "home", workspace=home / "workspace", port=port, token="deck-test-token")
supervisor = Supervisor(settings, command=[sys.executable, str(Path(__file__).with_name("serve.py"))], watch_root=code, poll=0.2)
sys.exit(supervisor.run())
