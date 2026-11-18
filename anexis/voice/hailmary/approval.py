"""Spoken approvals: before a risky tool runs, JARVIS asks out loud and waits
for a yes or a no, said or clicked. Written to fit how Hail Mary's
conversation.py uses it."""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

YES = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "go ahead", "do it", "go for it", "approve", "approved",
       "proceed", "affirmative", "please do", "yes please", "of course"}
NO = {"no", "nope", "nah", "don't", "do not", "deny", "denied", "cancel", "stop", "never mind", "nevermind",
      "not now", "no thanks", "negative", "abort"}


def _normal(text: str) -> str:
    text = text.lower().replace("\u2019", "'")  # a curly apostrophe counts as a plain one
    text = re.sub(r"[^\w\s']", " ", text)  # "yeah, do it." reads as "yeah do it"
    return " ".join(text.split())


def answer(text: str) -> bool | None:
    """True for a yes, False for a no, None when it is neither (a new request)."""
    said = _normal(text)
    said = re.sub(r"^(?:jarvis|hey jarvis)[ ,]*", "", said)
    said = re.sub(r"[ ,]*(?:sir|jarvis)$", "", said)
    if said in YES:
        return True
    if said in NO:
        return False
    first = said.split(" ", 1)[0] if said else ""
    if first in {"yes", "yeah", "yep", "sure"} and len(said.split()) <= 4:
        return True
    if first in {"no", "nope", "nah"} and len(said.split()) <= 4:
        return False
    return None


def spoken_prompt(title: str, tool: str, args: dict | None) -> str:
    what = tool.replace("_", " ").strip() or "that"
    detail = ""
    for key in ("command", "path", "target", "url", "task", "name"):
        if args and args.get(key):
            detail = str(args[key])
            break
    detail = f" {detail[:80]}" if detail else ""
    # Worded the way Hail Mary asks in text ("Shall I proceed?"). The answer
    # only counts with the name in it ("Jarvis, go ahead" / "Jarvis, cancel"),
    # so a TV saying "yes" can never approve anything, and it must not repeat
    # words of the question, or it is taken for JARVIS's own echo.
    return f"{title.capitalize()}, I would like to use {what}{detail}. Shall I proceed?"


@dataclass
class Pending:
    id: str
    summary: str
    tool: str
    args: dict
    future: asyncio.Future = field(repr=False)


class Approvals:
    def __init__(self, bus) -> None:
        self.bus = bus
        self.pending: Pending | None = None

    async def request(self, summary: str, timeout_s: float, *, tool: str = "", args: dict | None = None,
                      ask: Callable[[Pending], Awaitable[None]] | None = None) -> str:
        """"approved", "denied" or "timeout". One at a time."""
        future = asyncio.get_running_loop().create_future()
        self.pending = Pending(uuid.uuid4().hex[:10], summary, tool, dict(args or {}), future)
        self.bus.publish("approval", id=self.pending.id, summary=summary, tool=tool, args=self.pending.args)
        try:
            if ask is not None:
                await ask(self.pending)
            approved = await asyncio.wait_for(asyncio.shield(future), timeout_s)
            return "approved" if approved else "denied"
        except TimeoutError:
            return "timeout"
        finally:
            self.pending = None

    def resolve(self, verdict: bool, channel: str, id: str | None = None) -> bool:
        pending = self.pending
        if pending is None or pending.future.done() or (id is not None and id != pending.id):
            return False
        pending.future.set_result(bool(verdict))
        self.bus.publish("approval_done", id=pending.id, approved=bool(verdict), channel=channel)
        return True
