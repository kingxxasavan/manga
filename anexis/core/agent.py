"""The chat loop: build context, ask the model, run tools, repeat, then learn."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime

from anexis.config import Settings
from anexis.llm.provider import ProviderError
from anexis.llm.router import AllProvidersFailed
from anexis.memory.store import Memory, quality
from anexis.memory.style import THINKING_KEY, style_lines
from anexis.tools.base import Tool, ToolContext
from anexis.tools.builtin.core import due_soon
from anexis.tools.permissions import decide
from anexis.tools.registry import Registry

MODES = ("general", "school", "work", "project")
ABOUT_BUDGET = 3000  # characters of About Me always sent
LESSON_BUDGET = 1500  # characters of standing instructions always sent

SYSTEM = """You are {name}, a personal assistant that lives on your owner's own server. You help with school, work and whatever projects they are thinking through.

Now: {now}. Mode: {mode}.

How to behave:
- Talk like a sharp friend: direct, short, no filler. Match how the owner talks.
- Use what you know about the owner below. Never ask for something you already know.
- Use tools when they help instead of guessing. If none of the offered tools fit, call find_tools.
- If the owner declines a tool, do not retry it. Say what you wanted to do and carry on.
- Never invent facts, sources, file contents or tool results. If you do not know, say so.
- You learn automatically from the conversation. Call remember only when asked to remember something.
{control}{about}{lessons}{style}{recalled}{due}{summary}"""


FULL_CONTROL = (
    "- You have full control of this computer. Tools run without asking first, so "
    "think before anything that deletes, overwrites, sends or spends, and say what you did.\n"
)


def _block(title: str, lines: list[str]) -> str:
    return f"\n{title}\n" + "\n".join(f"- {line}" for line in lines) + "\n" if lines else ""


async def _deny(tool: Tool, args: dict, reason: str) -> bool:
    return False


class Agent:
    def __init__(self, settings: Settings, memory: Memory, router, registry: Registry, learner=None, events=None):
        self.events = events
        self.settings = settings
        self.memory = memory
        self.router = router
        self.registry = registry
        self.learner = learner
        self._background: set[asyncio.Task] = set()

    async def drain(self) -> None:
        """Wait for background learning to finish. Used on shutdown and in tests."""
        while self._background:
            await asyncio.gather(*list(self._background), return_exceptions=True)

    def _fit(self, history: list[dict]) -> list[dict]:
        """Newest messages that fit the character budget. Small local models have
        small context windows, and when they overflow the model silently loses
        the start of the prompt, which is where its instructions are."""
        kept, used = [], 0
        for message in reversed(history):
            used += len(message["content"])
            if used > self.settings.history_chars:
                break
            kept.append(message)
        return kept[::-1]

    def _about(self) -> list[str]:
        lines, used = [], 0
        for row in sorted(self.memory.pinned(), key=lambda m: -m.importance):
            if used + len(row.text) > ABOUT_BUDGET:
                break
            lines.append(row.text)
            used += len(row.text)
        return lines

    def _lessons(self) -> list:
        """Standing instructions: what the owner told Anexis about how to behave.
        They apply to every reply, so they are always sent, strongest first,
        instead of waiting for a search to happen to find them."""
        now = time.time()
        rows = [m for m in self.memory.list("lesson", 200) if m.key != THINKING_KEY and not m.pinned]
        kept, used = [], 0
        for row in sorted(rows, key=lambda m: -quality(m, now)):
            if used + len(row.text) > LESSON_BUDGET:
                break
            kept.append(row)
            used += len(row.text)
        return kept

    async def _recall(self, text: str) -> tuple[list, list, object]:
        """(standing instructions, memories that fit this message, the message as a vector)."""
        try:
            embedded = await self.router.embed([text], "query")
        except Exception:
            embedded = None
        tag, query_vec = (embedded[0], embedded[1][0]) if embedded else (None, None)
        lessons = self._lessons()
        shown = {m.id for m in lessons}
        recalled = [
            m for m in self.memory.search(text, self.settings.recall_k, query_vec, tag)
            if not m.pinned and m.id not in shown and m.key != THINKING_KEY
        ]
        return lessons, recalled, query_vec

    async def system_for(self, text: str) -> str:
        """The instructions the model would get for this message. Used by `anexis train`."""
        lessons, recalled, _ = await self._recall(text)
        return self._system({"mode": "general", "summary": ""}, recalled, lessons)

    def _system(self, session: dict, recalled: list, lessons: list) -> str:
        due = [f"{i['title']} ({i['type']}, due {i['due_at']})" for i in due_soon(self.memory)]
        summary = f"\nEarlier in this conversation: {session['summary']}\n" if session["summary"] else ""
        return SYSTEM.format(
            name=self.settings.name,
            now=datetime.now().astimezone().strftime("%A %Y-%m-%d %H:%M %Z"),
            mode=session["mode"],
            control=FULL_CONTROL if self.settings.control == "full" else "",
            about=_block("About your owner (always true):", self._about()),
            lessons=_block("Standing instructions from your owner. Follow them in every reply:", [m.text for m in lessons]),
            style=_block("How your owner talks and thinks (learned from their own messages):", style_lines(self.memory)),
            recalled=_block(
                "Things you remember that may matter right now:",
                [f"[{m.kind}] {m.text}" for m in recalled],
            ),
            due=_block("Due in the next week:", due),
            summary=summary,
        )

    async def run_turn(
        self,
        session_id: str | None,
        text: str,
        emit: Callable[[dict], None] | None = None,
        confirm: Callable[[Tool, dict, str], Awaitable[bool]] | None = None,
        mode: str | None = None,
    ) -> dict:
        emit = emit or (lambda event: None)
        sid = self.memory.ensure_session(session_id, mode if mode in MODES else None)
        session = self.memory.session(sid)
        history = self._fit(self.memory.history(sid, self.settings.history_messages))
        self.memory.add_message(sid, "user", text)

        lessons, recalled, query_vec = await self._recall(text)
        messages: list[dict] = [{"role": "system", "content": self._system(session, recalled, lessons)}]
        messages += [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({"role": "user", "content": text})

        ctx = ToolContext(
            settings=self.settings, memory=self.memory, router=self.router, registry=self.registry,
            session_id=sid, confirm=confirm or _deny, emit=emit,
        )
        result = {"session_id": sid, "text": "", "tools_used": [], "memories_used": [m.public() for m in recalled]}
        stats = self.memory.tool_stats()
        reply = None

        try:
            for _ in range(max(1, self.settings.max_steps)):
                offered = self.registry.pick(text, self.settings.max_tools, query_vec, stats, ctx.extra_tools)
                reply = await self.router.chat(
                    "chat", messages, [t.schema() for t in offered],
                    on_text=lambda piece: emit({"type": "text", "delta": piece}),
                )
                if not reply.tool_calls:
                    break
                messages.append(reply.message())
                for tool_call in reply.tool_calls:
                    output = await self._run_tool(tool_call, ctx, result)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": output})
            else:
                note = (
                    f"I stopped because I hit my step limit of {self.settings.max_steps} tool rounds "
                    "before finishing. Tell me to keep going if you want."
                )
                emit({"type": "text", "delta": note})
                reply.content = note
            if not reply.content.strip():
                note = "I got an empty reply from the model. Ask again, and if it keeps happening run `anexis doctor`."
                emit({"type": "text", "delta": note})
                reply.content = note
        except asyncio.CancelledError:
            # The owner pressed stop. Keep the conversation in a state the next
            # message can continue from.
            self.memory.add_message(sid, "assistant", "(stopped before finishing)", meta={"stopped": True})
            raise
        except (AllProvidersFailed, ProviderError) as e:
            message = f"No model could answer right now. {e}"
            emit({"type": "error", "message": message})
            return {**result, "error": message}

        result.update(text=reply.content, provider=reply.provider, model=reply.model)
        self.memory.add_message(
            sid, "assistant", reply.content,
            meta={"tools_used": result["tools_used"], "memories_used": [m.id for m in recalled],
                  "provider": reply.provider, "model": reply.model},
        )
        self.memory.mark_used([m.id for m in recalled])
        emit({"type": "done", **{k: v for k, v in result.items() if k != "text"}})

        if self.learner and self.settings.learn:
            task = asyncio.create_task(self._learn(text, reply.content))
            self._background.add(task)
            task.add_done_callback(self._background.discard)
        return result

    async def _learn(self, text: str, reply: str) -> None:
        try:
            await self.learner.learn(text, reply)
        except Exception as e:  # learning is a bonus, it must never break a chat
            self.memory.log("learn_failed", {"error": f"{type(e).__name__}: {e}"[:300]})

    async def _run_tool(self, tool_call, ctx: ToolContext, result: dict) -> str:
        tool = self.registry.get(tool_call.name)
        if tool is None:
            return f"Error: there is no tool named {tool_call.name}. Use find_tools to look for one that fits."
        args = tool_call.arguments
        if "_unparsed" in args:
            return f"Error: the arguments for {tool.name} were not valid JSON, so it was not run. Send them again as one JSON object."
        def activity(status: str, **more) -> None:
            if self.events:
                self.events.publish({
                    "type": "activity", "tool": tool.name, "args": args, "status": status,
                    "session_id": ctx.session_id, "call": tool_call.id, **more,
                })

        verdict, reason = decide(tool, args, self.settings)
        if verdict == "ask":
            ctx.emit({"type": "tool", "name": tool.name, "args": args, "status": "asking"})
            activity("asking", reason=reason)
            if not await ctx.confirm(tool, args, reason):
                activity("declined")
                return "The owner declined to let this run. Do not try it again. Tell them what you wanted to do."
        ctx.emit({"type": "tool", "name": tool.name, "args": args, "status": "running"})
        activity("running")
        started = time.monotonic()
        try:
            output = str(await tool.handler(args, ctx))
            ok = not output.startswith("Error:")
        except asyncio.CancelledError:
            activity("stopped")
            raise
        except Exception as e:  # a broken tool must never take the conversation down
            output, ok = f"Error: the tool crashed ({type(e).__name__}: {e})", False
        self.memory.record_tool(tool.name, ok, (time.monotonic() - started) * 1000)
        result["tools_used"].append(tool.name)
        limit = self.settings.tool_output_chars
        if len(output) > limit:
            output = output[:limit] + f"\n... (cut, {len(output) - limit} more characters)"
        ctx.emit({"type": "tool_result", "name": tool.name, "ok": ok, "preview": output[:200]})
        activity("done" if ok else "failed", preview=output[:400], ms=round((time.monotonic() - started) * 1000))
        return output
