"""Builds every part of Anexis and holds them together."""

from __future__ import annotations

import asyncio
import time

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
        register_builtin(self.registry, settings)
        self.claude = ClaudeRunner(settings, self.memory)
        self.fallback = FallbackCoder(settings, self.memory, self.router, self.registry)
        self.registry.add(make_code_tool(self.claude, self.fallback))
        self.mcp = MCPManager(settings, self.registry)
        self.learner = Learner(self.memory, self.router)
        self.agent = Agent(settings, self.memory, self.router, self.registry, self.learner, self.events)
        self._voice = None
        self._sync_transport = None  # tests stand in for the school server here
        self._tasks: list[asyncio.Task] = []

    @property
    def voice(self):
        if self._voice is None:
            from anexis.voice import Voice

            self._voice = Voice(self.settings)
        return self._voice

    async def start(self) -> None:
        if self.settings.seed_owner:
            from anexis.profile.seed import seed_owner

            try:
                report = seed_owner(self.memory)
                if not report["skipped"]:
                    self.memory.log("owner_seeded", report)
            except Exception as e:  # knowing less is never a reason not to start
                self.memory.log("owner_seed_failed", {"error": str(e)[:300]})
        # Tool servers can take a while the first time (they download), so the
        # server answers right away and tools join as they come up.
        self._tasks.append(asyncio.create_task(self._start_tools()))
        if self.settings.consolidate_minutes > 0:
            self._tasks.append(asyncio.create_task(self._upkeep()))
        if self.settings.ui and self.settings.ui_dir.is_dir():
            self._tasks.append(asyncio.create_task(self._watch_deck()))
        from anexis.tools.builtin import canvas as canvas_tools

        if canvas_tools.configured(self.settings):
            self._tasks.append(asyncio.create_task(self._canvas()))
        if self.settings.env.get("ANEXIS_SYNC_URL"):
            self._tasks.append(asyncio.create_task(self._sync_loop()))
        if self.settings.autonomy_minutes > 0:
            self._tasks.append(asyncio.create_task(self._initiative_loop()))

    async def _initiative_loop(self) -> None:
        """Anexis checking in on its own (core/initiative.py). It reads the
        setting every round, so turning it off or on takes effect at once."""
        from anexis.core.initiative import Initiative

        initiative = Initiative(self)
        await asyncio.sleep(120)  # let the tools and the first sync settle first
        while True:
            try:
                await initiative.check_in()
            except Exception as e:  # a check in must never take anything else down
                self.memory.log("initiative_failed", {"error": f"{type(e).__name__}: {e}"[:300]})
            await asyncio.sleep(max(5, self.settings.autonomy_minutes) * 60)

    async def sync_now(self) -> dict:
        """One sync with the school server. Never raises: the answer says how it went."""
        from anexis.memory.sync import sync_with

        url = self.settings.env.get("ANEXIS_SYNC_URL", "")
        if not url:
            return {"ok": False, "error": "No school server is set. Add its address and token in Keys."}
        try:
            report = await sync_with(self.memory, url, self.settings.env.get("ANEXIS_SYNC_TOKEN", ""), self._sync_transport)
        except Exception as e:  # offline, at school with no link, server down: try again later
            report = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300], "at": time.time()}
            self.memory.log("sync_failed", report)
            self.events.publish({"type": "sync_failed", "error": report["error"]})
            return report
        self.memory.log("synced", report)
        self.events.publish({"type": "synced", "from": "school", **report["received"]})
        return report

    async def _sync_loop(self) -> None:
        """Syncs as soon as Anexis starts (which is when the computer starts,
        when Anexis opens with Windows), then every 15 minutes."""
        await asyncio.sleep(3)
        while True:
            await self.sync_now()
            await asyncio.sleep(15 * 60)

    async def _canvas(self) -> None:
        """Keeps the assignment list in step with Canvas: once soon after
        starting, then every hour. That is what makes reminders work without
        anyone asking."""
        from anexis.tools.builtin import canvas

        await asyncio.sleep(5)
        while True:
            client = canvas.client_for(self.settings, canvas._transport)
            if client is None:  # signed out since this started
                return
            try:
                report = await canvas.sync(self.memory, client)
                self.memory.log("canvas_sync", report)
                self.events.publish({"type": "canvas_synced", **report})
            except Exception as e:  # the school site being down must never hurt anything else
                self.memory.log("canvas_sync_failed", {"error": f"{type(e).__name__}: {e}"[:300]})
                self.events.publish({"type": "canvas_failed", "error": str(e)[:300]})
            finally:
                await client.close()
            await asyncio.sleep(3600)

    async def _watch_deck(self) -> None:
        """Tells open decks to reload when one of their files is edited, so a
        change to the UI shows up without restarting or rebuilding anything."""
        from anexis.desktop import watch

        seen = await asyncio.to_thread(watch.snapshot, self.settings.ui_dir)
        while True:
            await asyncio.sleep(1.0)
            now = await asyncio.to_thread(watch.snapshot, self.settings.ui_dir)
            touched = watch.changed(seen, now)
            seen = now
            if touched:
                root = str(self.settings.ui_dir)
                self.events.publish({"type": "reload", "files": [t[len(root):].lstrip("\\/").replace("\\", "/") for t in touched]})

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
