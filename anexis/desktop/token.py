"""The desktop app always runs with a token. The server it starts can drive
the whole PC, so nothing but the app itself may talk to it."""

from __future__ import annotations

import secrets
from pathlib import Path

from anexis.config import read_dotenv


def ensure_token(home) -> str:
    """The saved token, made the first time it is asked for."""
    from anexis.cli.setup import update_env_file

    path = Path(home) / ".env"
    token = read_dotenv(path).get("ANEXIS_TOKEN", "")
    if not token:
        token = secrets.token_urlsafe(32)
        update_env_file(path, {"ANEXIS_TOKEN": token})
    return token
