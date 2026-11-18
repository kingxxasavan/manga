"""One place every part of Anexis reports what it is doing, so the deck can
show it live: tool calls, file changes that need a reload, install progress."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator


class EventBus:
    def __init__(self, keep: int = 200):
        self._recent: deque[dict] = deque(maxlen=keep)
        self._listeners: set[asyncio.Queue] = set()

    def publish(self, event: dict) -> None:
        event = {"at": time.time(), **event}
        if event.get("type") == "activity":
            self._recent.append(event)
        for queue in list(self._listeners):
            if queue.full():  # a listener that stopped reading must not hold anything up
                queue.get_nowait()
            queue.put_nowait(event)

    def recent(self, n: int = 200) -> list[dict]:
        return list(self._recent)[-n:]

    async def subscribe(self) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._listeners.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._listeners.discard(queue)
