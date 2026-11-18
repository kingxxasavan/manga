"""The event bus Hail Mary's voice files publish to, passed on to Anexis's own
events so the deck can show what was heard and said. Safe to call from the
audio thread."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

LEVELS_EVERY_S = 0.1  # mic and speaker loudness come twenty times a second; the deck's circle needs ten


class Bus:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sink: Callable[[dict], None] | None = None
        self._levels_at = 0.0

    def bind(self, loop: asyncio.AbstractEventLoop, sink: Callable[[dict], None]) -> None:
        self._loop, self._sink = loop, sink

    def unbind(self) -> None:
        self._loop = self._sink = None

    def publish(self, name: str, **fields) -> None:
        if self._sink is None or self._loop is None:
            return
        if name == "levels":
            now = time.monotonic()
            if now - self._levels_at < LEVELS_EVERY_S:
                return
            self._levels_at = now
            fields = {k: round(float(v), 5) for k, v in fields.items()}
        event = {"type": f"voice_{name}", **fields}
        try:
            if asyncio.get_running_loop() is self._loop:
                self._sink(event)
                return
        except RuntimeError:
            pass
        try:
            self._loop.call_soon_threadsafe(self._sink, event)
        except RuntimeError:  # the loop closed while shutting down
            pass


bus = Bus()
