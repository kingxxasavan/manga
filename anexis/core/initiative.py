"""Anexis on its own: it checks in every so often without being asked.

Each check in it looks at what it knows (what is due or overdue, how the
computer and Anexis itself are doing, what it still does not know about the
owner, what the owner has been talking about) and picks one of:

    none   most of the time: nothing worth interrupting for
    say    a short heads up, like work that is due or something broken
    ask    one question, to learn something it needs to help better
    do     a task it can do with its tools, like getting new class slides

What it says lands in its own chat ("From Anexis") with a notification, and
the owner answers there like in any chat. A task is done at once when
autonomy is "act", and offered first when it is "ask". With "off" none of
this runs.
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
import time
from datetime import datetime

import psutil

from anexis.profile.about import export_profile
from anexis.tools.builtin.core import due_soon

INBOX = "inbox"              # the chat Anexis writes in when it starts something itself
SAID_KEY = "initiative_said"  # what it said lately, so it never says the same thing twice
COUNT_KEY = "initiative_count"
LEVELS = ("off", "ask", "act")
WANTED = ("name", "school", "classes", "schedule", "goals", "work", "projects")

PROMPT = """You are {name}, the owner's personal assistant, checking in on your own. Nobody asked you anything right now.
Decide if there is ONE thing worth doing at this moment. Most of the time the answer is nothing: only speak up when it really helps.

Choose one:
- "none": nothing worth an interruption.
- "say": a short heads up the owner would want, like work due soon or overdue, or something broken that needs them.
- "ask": one short, specific question to learn something you need to help them better (start with gaps in what you know about them).
- "do": one concrete task you can do yourself with your tools that clearly helps, like downloading new class slides or checking what is due. Never anything that deletes, sends, buys or posts.

Rules: never repeat or rephrase anything in "already said". Keep "text" to one or two short sentences, in the owner's style. No dashes.
Answer with JSON only: {{"action": "none|say|ask|do", "text": "what to tell or ask the owner", "task": "for do: the task in one sentence", "why": "a few words"}}

What you know right now:
{context}"""


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def quiet(now: datetime, span: str) -> bool:
    """True inside quiet hours, like "22:00-07:00" (which wraps past midnight)."""
    try:
        start, end = (datetime.strptime(part.strip(), "%H:%M").time() for part in span.split("-"))
    except ValueError:
        return False
    t = now.time()
    return start <= t < end if start < end else (t >= start or t < end)


def _decision(text: str) -> dict | None:
    """The JSON the model answered with, found even inside other words."""
    found = re.search(r"\{.*\}", text or "", re.S)
    if not found:
        return None
    try:
        data = json.loads(found.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("action") not in ("none", "say", "ask", "do"):
        return None
    return data


class Initiative:
    def __init__(self, app):
        self.app = app

    # ---- what it knows ------------------------------------------------------
    def context(self) -> dict:
        app, memory = self.app, self.app.memory
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        soon = [f"{i['title']} (due {i['due_at']})" for i in due_soon(memory, days=3)]
        overdue = [f"{r['title']} (was due {r['due_at']})" for r in memory.db.execute(
            "SELECT title, due_at FROM items WHERE done=0 AND due_at IS NOT NULL AND due_at < ? ORDER BY due_at LIMIT 8", (today,))]

        health = []
        try:
            disk = psutil.disk_usage(str(app.settings.home))
            if disk.percent >= 90:
                health.append(f"the disk is {disk.percent:.0f}% full, {shutil.disk_usage(str(app.settings.home)).free / 1024**3:.1f} GB left")
            mem = psutil.virtual_memory()
            if mem.percent >= 92:
                health.append(f"memory is {mem.percent:.0f}% used")
        except OSError:
            pass
        broken = [name for name, s in getattr(app.mcp, "status", {}).items() if s.get("state") == "failed"]
        if broken:
            health.append("tool servers that failed: " + ", ".join(broken))
        for provider, error in getattr(app.router, "last_errors", {}).items():
            health.append(f"model source {provider} had an error: {str(error)[:120]}")
        resting, why = app.claude.available()
        if not resting:
            health.append(why)

        about = export_profile(memory)
        gaps = [key for key in WANTED if not about.get(key)]
        lately = [m["content"][:160] for m in reversed(memory.db.execute(
            "SELECT content FROM messages WHERE role='user' ORDER BY id DESC LIMIT 8").fetchall())]
        return {
            "now": now.strftime("%A %Y-%m-%d %H:%M"),
            "due in the next 3 days": soon or ["nothing"],
            "overdue": overdue or ["nothing"],
            "health of the computer and of you": health or ["all fine"],
            "what you do not know about the owner yet": gaps or ["nothing important"],
            "what the owner said lately": lately or ["nothing yet"],
            "already said": memory.kv_get(SAID_KEY, [])[-15:] or ["nothing"],
            "autonomy": self.app.settings.autonomy,
        }

    # ---- one check in ---------------------------------------------------------
    def _allowed(self, now: datetime) -> str:
        """Why not to check in right now, or "" when it may."""
        settings = self.app.settings
        if settings.autonomy not in ("ask", "act"):
            return "autonomy is off"
        if quiet(now, settings.autonomy_quiet):
            return "quiet hours"
        counts = self.app.memory.kv_get(COUNT_KEY, {})
        if counts.get(now.strftime("%Y-%m-%d"), 0) >= settings.autonomy_daily:
            return "enough for today"
        return ""

    def _repeat(self, text: str) -> bool:
        said = self.app.memory.kv_get(SAID_KEY, [])
        new = _normal(text)
        return any(difflib.SequenceMatcher(None, new, _normal(old)).ratio() > 0.85 for old in said)

    def _post(self, action: str, text: str, extra: dict | None = None) -> None:
        memory = self.app.memory
        memory.ensure_session(INBOX)
        memory.add_message(INBOX, "assistant", text, meta={"initiative": action, **(extra or {})})
        said = [*memory.kv_get(SAID_KEY, [])[-29:], text]
        memory.kv_set(SAID_KEY, said)
        day = datetime.now().strftime("%Y-%m-%d")
        counts = memory.kv_get(COUNT_KEY, {})
        memory.kv_set(COUNT_KEY, {day: counts.get(day, 0) + 1})
        self.app.events.publish({"type": "initiative", "action": action, "text": text, "session_id": INBOX})
        # With JARVIS listening, it also says it out loud.
        speaker = getattr(self.app.wake, "say", None)
        if speaker is not None:
            import asyncio

            asyncio.get_running_loop().create_task(speaker(text))

    async def check_in(self, now: datetime | None = None) -> dict:
        """Looks around once and maybe does one thing. Says what it did."""
        now = now or datetime.now()
        why_not = self._allowed(now)
        if why_not:
            return {"action": "skipped", "why": why_not}
        router = self.app.router
        role = "tools" if getattr(router, "has_role", lambda r: False)("tools") else "chat"
        context = json.dumps(self.context(), indent=1)
        prompt = PROMPT.format(name=self.app.settings.name, context=context)
        try:
            reply = await router.chat(role, [{"role": "system", "content": prompt},
                                             {"role": "user", "content": "Check in now. JSON only."}])
        except Exception as e:  # a model being down is not worth a fuss here
            self.app.memory.log("initiative_failed", {"error": f"{type(e).__name__}: {e}"[:300]})
            return {"action": "failed", "why": str(e)[:200]}
        decision = _decision(reply.content)
        if decision is None:
            self.app.memory.log("initiative_unclear", {"said": reply.content[:300]})
            return {"action": "none", "why": "the model did not answer in the expected form"}
        action, text = decision["action"], str(decision.get("text") or "").strip()
        task = str(decision.get("task") or "").strip()
        if action == "none" or (action != "do" and not text) or (action == "do" and not task):
            return {"action": "none", "why": decision.get("why", "")}
        if self._repeat(text or task):
            return {"action": "none", "why": "already said"}
        self.app.memory.log("initiative", decision)

        if action in ("say", "ask"):
            self._post(action, text)
            return {"action": action, "text": text}
        if self.app.settings.autonomy == "ask":
            offer = f"{text + ' ' if text else ''}I can do this for you: {task}. Want me to? Just say yes here."
            self._post("offer", offer, {"task": task})
            return {"action": "offer", "text": offer, "task": task}
        return await self._do(task, text)

    async def _do(self, task: str, text: str) -> dict:
        """Does a task on its own, then reports it in its chat."""
        async def no(tool, args, reason) -> bool:
            return False  # nobody is there to say yes, so anything that has to ask is skipped

        session = self.app.memory.ensure_session(f"auto-{int(time.time())}", "general")
        result = await self.app.agent.run_turn(
            session, f"Do this on your own now, then report in two sentences what you did: {task}", confirm=no)
        done = (result.get("text") or result.get("error") or "").strip()
        report = f"I did this on my own: {task}.\n\n{done}"
        self._post("did", report, {"task": task, "session": session})
        self.app.events.publish({"type": "task_done", "text": f"{task}. {done[:160]}"})
        return {"action": "did", "task": task, "text": done}
