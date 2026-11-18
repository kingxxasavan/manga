"""The event bus Hail Mary's voice files publish to, passed on to Anexis's own
events so the deck can show what was heard and said. Safe to call from the
audio thread."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

SKIPPED = {"levels"}  # twenty times a second: too chatty for the live feed


class Bus:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sink: Callable[[dict], None] | None = None

    def bind(self, loop: asyncio.AbstractEventLoop, sink: Callable[[dict], None]) -> None:
        self._loop, self._sink = loop, sink

    def unbind(self) -> None:
        self._loop = self._sink = None

    def publish(self, name: str, **fields) -> None:
        if name in SKIPPED or self._sink is None or self._loop is None:
            return
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
