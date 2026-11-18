"""The shared context and prompt helper Hail Mary's voice files import."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

from anexis.voice.hailmary.bus import bus

ctx = SimpleNamespace(bus=bus, mode="smart")


def shrink(build: Callable[[list[str]], list[dict]], turns: list[str], budget: int | None) -> list[dict]:
    """The messages `build` makes, dropping the oldest turns until they fit `budget` characters."""
    turns = list(turns)
    while True:
        messages = build(turns)
        if budget is None or not turns or sum(len(m["content"]) for m in messages) <= budget:
            return messages
        turns.pop(0)
