"""Builds every part of Anexis and holds them together."""

from __future__ import annotations

import asyncio

from anexis.coder.claude import ClaudeRunner
from anexis.coder.fallback import FallbackCoder
from anexis.coder.task import make_code_tool
from anexis.config import Settings
from anexis.core.agent import Agent
from anexis.core.events import EventBus
from anexis.llm.router import Router
from anexis.memory.consolidate import consolidate
from anexis.memory.learn import Learner
from anexis.memory.store import Memory
from anexis.tools.builtin import register_builtin
from anexis.tools.mcp_client import MCPManager
from anexis.tools.registry import Registry


class AnexisApp:
    def __init__(self, settings: Settings, router=None):
        self.settings = settings
        settings.home.mkdir(parents=True, exist_ok=True)
        settings.workspace.mkdir(parents=True, exist_ok=True)
        self.memory = Memory(settings.db_path)
        self.events = EventBus()
        self.router = router or Router(settings)
        self.registry = Registry()
        register_builtin(self.registry)
        self.claude = ClaudeRunner(settings, self.memory)
        self.fallback = FallbackCoder(settings, self.memory, self.router, self.registry)
        self.registry.add(make_code_tool(self.claude, self.fallback))
        self.mcp = MCPManager(settings, self.registry)
        self.learner = Learner(self.memory, self.router)
        self.agent = Agent(settings, self.memory, self.router, self.registry, self.learner, self.events)
        self._voice = None
        self._tasks: list[asyncio.Task] = []

    @property
    def voice(self):
        if self._voice is None:
            from anexis.voice import Voice

            self._voice = Voice(self.settings)
        return self._voice

    async def start(self) -> None:
        # Tool servers can take a while the first time (they download), so the
        # server answers right away and tools join as they come up.
        self._tasks.append(asyncio.create_task(self._start_tools()))
        if self.settings.consolidate_minutes > 0:
            self._tasks.append(asyncio.create_task(self._upkeep()))

    async def _start_tools(self) -> None:
        try:
            if self.settings.outside_tools:
                await self.mcp.start()
            await self.registry.embed_all(self.router)
        except Exception as e:
            self.memory.log("tools_failed", {"error": str(e)[:300]})

    async def _upkeep(self) -> None:
        while True:
            await asyncio.sleep(self.settings.consolidate_minutes * 60)
            try:
                report = await consolidate(self.memory, self.router)
                self.memory.log("consolidate", report)
            except Exception as e:
                self.memory.log("consolidate_failed", {"error": str(e)[:300]})

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.agent.drain()
        await self.mcp.stop()
        await self.router.close()
        self.memory.close()
