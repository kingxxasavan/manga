"""Hail Mary's brain, played by Anexis: what JARVIS hears goes through
Anexis's own chat loop (memory, tools, Canvas, the models picked in the app),
and the reply comes back as it is written, so speaking starts with the first
sentence."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

SESSION = "voice"


class AnexisBrain:
    def __init__(self, app, session: str = SESSION):
        self.app = app
        self.session = session
        self.conversation = None  # set by the engine, for spoken approvals

    @property
    def title(self) -> str:
        return self.app.settings.voice_title

    @property
    def history(self) -> list[dict]:
        rows = self.app.memory.history(self.session, 8) if self.app.memory.session(self.session) else []
        return [{"role": m["role"], "content": m["content"]} for m in rows]

    async def _confirm(self, tool, args, reason) -> bool:
        if self.conversation is None:
            return False
        return await self.conversation.approve(f"run {tool.name}", 30, tool=tool.name, args=args)

    async def respond(self, text: str) -> AsyncIterator[str]:
        self.app.memory.ensure_session(self.session, "general")
        queue: asyncio.Queue = asyncio.Queue()

        async def turn() -> None:
            try:
                result = await self.app.agent.run_turn(self.session, text, emit=queue.put_nowait, confirm=self._confirm)
                if result.get("error"):
                    queue.put_nowait({"type": "text", "delta": result["error"]})
                self.app.events.publish({"type": "voice_reply", "heard": text, "text": result.get("text") or result.get("error") or "",
                                         "session_id": self.session})
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(turn())
        try:
            while (event := await queue.get()) is not None:
                if event.get("type") == "text":
                    yield event["delta"]
        finally:
            if not task.done():  # talked over (barge in): stop the work as well
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
