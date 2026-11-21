"""The voice log: what JARVIS heard, whether it took it as meant for it and
why, what it answered, and what it said on its own. One plain line each, in
voice.log next to server.log, so "what set it off?" always has an answer.
The JARVIS screen shows the end of it (GET /voice/log)."""

from __future__ import annotations

import time
from pathlib import Path

LIMIT = 1_000_000  # bytes; then it starts over, keeping the last file as voice.log.1

WHY = {
    "wake": "you said its name",
    "armed": "right after you said its name",
    "request": "sounded like a request",
    "chatter": "sounded like talk with someone else",
    "judge": "the judge model said it was for JARVIS",
    "none": "not for JARVIS",
    "follow_up": "right after JARVIS spoke",
    "always": "always mode answers everything",
}


def describe(event: dict) -> str:
    """One readable line for a voice event, or "" for one not worth keeping."""
    kind = event.get("type", "")
    if kind == "voice_heard":
        text = str(event.get("text") or "").strip()
        if not text:
            return "heard something, but no words"
        why = WHY.get(event.get("why", ""), event.get("why", ""))
        took = "for JARVIS" if event.get("directed") else "ignored"
        return f"heard ({took}{', ' + why if why else ''}): {text}"
    if kind == "voice_reply":
        return f"answered: {str(event.get('text') or '').strip()[:400]}"
    if kind == "initiative":
        return f"said on its own ({event.get('action', '')}): {event.get('text', '')}"
    if kind in ("voice_error", "wake_failed"):
        return f"problem: {event.get('message') or event.get('error') or ''}"
    if kind == "wake_listening":
        return f"voice started ({event.get('engine', '')}), listening"
    if kind == "voice_mode":
        return f"now answers in {event.get('value', '')} mode"
    if kind == "game":
        name = event.get("name", "")
        return f"game in front ({name}): only answers to its name, no check ins" if name else "game closed: back to normal"
    if kind == "voice_approval":
        return f"asked before using {event.get('tool') or 'a tool'}"
    if kind == "voice_approval_done":
        return f"that was answered {'yes' if event.get('approved') else 'no'} ({event.get('channel', '')})"
    return ""


class VoiceLog:
    def __init__(self, path: Path, limit: int = LIMIT):
        self.path = Path(path)
        self.limit = limit

    def write(self, event: dict) -> None:
        line = describe(event)
        if not line:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.is_file() and self.path.stat().st_size > self.limit:
                self.path.replace(self.path.with_suffix(".log.1"))
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event.get("at") or time.time()))
            with self.path.open("a", encoding="utf-8") as f:
                f.write(f"{stamp}  {' '.join(line.split())}\n")
        except OSError:
            pass  # a full disk must never stop JARVIS

    def tail(self, n: int = 80) -> list[str]:
        try:
            return self.path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
        except OSError:
            return []
