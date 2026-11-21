"""From the Hail Mary project (the owner's own JARVIS voice). Brought into
Anexis with only its imports changed; see anexis/voice/hailmary/__init__.py."""

import asyncio
import logging
import re
import time
from collections import deque
from contextlib import aclosing
from pathlib import Path

from anexis.voice.hailmary.approval import Approvals, Pending, answer, spoken_prompt
from anexis.voice.hailmary.attention import MODES, find_wake, is_backchannel, is_stop
from anexis.voice.hailmary.runtime import ctx
from anexis.voice.hailmary.tts import SentenceChunker, clean_for_speech

log = logging.getLogger(__name__)

ECHO_OVERLAP = 0.6
AWAITING = "awaiting_approval"
JOIN_WINDOW_S = 4.0
WORDS = re.compile(r"[\w']+")


def words(text: str) -> list[str]:
    return WORDS.findall(text.lower().replace("’", "'"))


class Conversation:
    resume_timeout_s: float = 4.0
    voice_on: bool = True
    ack_delay_s: float = 0.8
    mode_file: Path | None = None

    def __init__(self, cfg: dict, stt, attention, brain, voice, player) -> None:
        self.stt, self.attention, self.brain, self.voice, self.player = stt, attention, brain, voice, player
        self.state = "idle"
        self._title = cfg["user"].get("title") or "sir"
        self._wake_words = cfg["attention"]["wake_words"]
        self._lead_ins = cfg["attention"]["lead_ins"]
        self._loop = asyncio.get_running_loop()
        self._task: asyncio.Task | None = None
        self._announcing: str | None = None
        self._announcements: deque[str] = deque()
        self._spoken: list[str] = []
        self._resume_timer: asyncio.TimerHandle | None = None
        self._ack_timer: asyncio.TimerHandle | None = None
        self._ignored: tuple[str, float] | None = None
        self._acted_at = 0.0
        self._heard_at: float | None = None
        self._stt_ms = 0
        self._decide_ms = 0
        self._utterances = asyncio.Lock()
        self._jobs: set[asyncio.Task] = set()
        self.approvals = Approvals(ctx.bus)

    def on_listen(self, event: str, audio) -> None:
        try:
            self._loop.call_soon_threadsafe(self._on_event, event, audio)
        except RuntimeError:  # loop already closed during shutdown
            pass

    async def handle_text(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if self.approvals.pending is not None and self._decide_approval(answer(text), "text"):
            return
        ctx.bus.publish("user", text=text)
        await self._cancel()
        self._start(self._reply, text)

    async def say(self, text: str, interrupt: bool = False) -> None:
        """Speak proactively. Without interrupt the text is queued and spoken once current speech ends; a queued
        or interrupted announcement is never dropped, only the user's stop clears it."""
        self._show(text)
        if interrupt:
            await self._cancel()
            return self._start(self._announce, text, keep=True)
        self._announcements.append(text)
        if not self._active():
            self._start(self._announce, self._announcements.popleft(), keep=True)

    def stop(self) -> None:
        self._halt()
        self.attention.disarm()
        self._announcements.clear()
        self._set_state("idle")

    async def approve(self, summary: str, timeout_s: float = 30, *, tool: str = "", args: dict | None = None) -> bool:
        try:
            outcome = await self.approvals.request(summary, timeout_s, tool=tool, args=args, ask=self._ask_approval)
        finally:
            if self.state == AWAITING:
                self._set_state(self._speaking_state())
        if outcome == "timeout":
            await self._announce(f"I'll leave that for now, {self._title}.")
        return outcome == "approved"

    def receive(self, message: dict) -> None:
        if message.get("type") == "approval" and isinstance(message.get("approved"), bool) and message.get("id"):
            self.approvals.resolve(message["approved"], "gui", id=message["id"])

    async def _ask_approval(self, pending: Pending) -> None:
        self._set_state(AWAITING)
        await self._announce(spoken_prompt(self._title, pending.tool, pending.args))

    def _decide_approval(self, verdict: bool | None, channel: str) -> bool:
        return verdict is not None and self.approvals.resolve(verdict, channel)

    async def _approval_answer(self, text: str) -> None:
        if is_stop(text, self._wake_words, self._lead_ins):
            self._heard(text, True, "stop")
            self.approvals.resolve(False, "voice")
            return self.stop()
        found, command = find_wake(text, self._wake_words, self._lead_ins)
        if not found or not command or self._is_echo(text) or is_backchannel(command):
            return self._heard(text, False, "no name, during a question")
        verdict = answer(command)
        if verdict is None:
            self._heard(text, True, "a new request during a question")
            self.approvals.resolve(False, "voice")
            return await self._act(command, text)
        self._heard(text, not self.player.busy and self._decide_approval(verdict, "voice"), "answer to a question")

    def set_mode(self, mode: str) -> str:
        if mode not in MODES:
            return f"error: mode must be one of {', '.join(MODES)}"
        self.attention.mode = ctx.mode = mode
        if self.mode_file is not None:
            self.mode_file.write_text(mode, encoding="utf-8")
        ctx.bus.publish("mode", value=mode)
        return f"Attention mode set to {mode}."

    def _on_event(self, event: str, audio) -> None:
        if event == "speech_start":
            self._cancel_ack()
            if self.state == "idle":
                self._set_state("listening")
        elif event == "speech_sustained" and self.state != AWAITING:
            self._pause()
        elif event == "discard":
            if self.attention.armed() and not self._active():
                self._arm_ack()
            else:
                self._settle()
        elif event == "utterance":
            self._heard_at = time.monotonic()
            awaiting = self.state == AWAITING
            barge = self._active() and not awaiting
            if not awaiting:
                self._pause()
            if self.state == "paused":
                self._arm_resume_timer()
            job = self._loop.create_task(self._utterance(audio, barge))
            self._jobs.add(job)
            job.add_done_callback(self._jobs.discard)

    async def _utterance(self, audio, barge: bool) -> None:
        async with self._utterances:
            try:
                text = await asyncio.to_thread(self.stt.transcribe, audio)
                self._stt_ms = self._since_heard()
                if self.approvals.pending is not None:
                    await self._approval_answer(text)
                elif barge or self.state == "paused":
                    await self._barge_in(text)
                else:
                    await self._request(text)
            except Exception:
                log.exception("could not handle what was heard")
                ctx.bus.publish("error", message="Could not handle what was heard")
                self._settle()

    async def _request(self, text: str) -> None:
        if not text:
            return self._settle()
        if is_stop(text, self._wake_words, self._lead_ins):
            self._heard(text, True, "stop")
            return self.stop()
        decision = await self.attention.decide(text, self.brain.history)
        self._decide_ms = self._since_heard() - self._stt_ms
        directed = decision.directed and not (decision.reason == "always" and is_backchannel(decision.command))
        self._heard(text, directed, decision.reason)
        if not directed:
            self._ignored = (text, time.monotonic())
            return self._settle()
        await self._act(decision.command or self._just_ignored(), text)

    async def _barge_in(self, text: str) -> None:
        if not text:
            return self._resume()
        if is_stop(text, self._wake_words, self._lead_ins):
            self._heard(text, True, "stop")
            return self.stop()
        found, command = find_wake(text, self._wake_words, self._lead_ins)
        if self._is_echo(text) or is_backchannel(command):
            self._heard(text, False, "its own echo, or just yeah or ok")
            return self._resume()
        if found and not command and time.monotonic() - self._acted_at < JOIN_WINDOW_S:
            self._heard(text, True, "the name again")
            return self._resume()
        if self.attention.mode == "wake" and not found and self._active() and not self.attention.armed():
            self._heard(text, False, "no name (wake mode)")
            return self._resume()
        self._pause()
        if self.attention.mode == "smart":
            self.attention.mark_spoke()
        decision = await self.attention.decide(text, self.brain.history)
        directed = decision.directed and not is_backchannel(decision.command)
        self._heard(text, directed, decision.reason)
        if not directed:
            return self._resume()
        await self._act(decision.command, text)

    def _just_ignored(self) -> str:
        """For "what time is it... Jarvis", where the name arrives as its own utterance after the question."""
        ignored, self._ignored = self._ignored, None
        return ignored[0] if ignored and time.monotonic() - ignored[1] < JOIN_WINDOW_S else ""

    async def _act(self, command: str, text: str) -> None:
        if not command.strip():
            await self._cancel()
            self.attention.arm()
            self._set_state("listening")
            return self._arm_ack()
        self._acted_at = time.monotonic()
        self.attention.disarm()
        ctx.bus.publish("user", text=command)
        await self._cancel()
        self._start(self._reply, command)

    def _arm_ack(self) -> None:
        self._cancel_ack()
        self._ack_timer = self._loop.call_later(self.ack_delay_s, self._acknowledge)

    def _cancel_ack(self) -> None:
        if self._ack_timer is not None:
            self._ack_timer.cancel()
            self._ack_timer = None

    def _acknowledge(self) -> None:
        """Only speak up if the user paused after the name; if they kept talking, "Yes, sir?" would talk over them."""
        self._ack_timer = None
        if self._active():
            return
        line = f"Yes, {self._title}?"
        self._show(line)
        self.attention.arm()
        self._start(self._announce, line)

    def _since_heard(self) -> int:
        return round((time.monotonic() - self._heard_at) * 1000) if self._heard_at else 0

    def _show(self, text: str) -> None:
        ctx.bus.publish("assistant_delta", text=text)
        ctx.bus.publish("assistant_done")

    def _heard(self, text: str, directed: bool, why: str = "") -> None:
        log.debug("heard %d chars (%s)", len(text), "directed" if directed else "ignored")
        ctx.bus.publish("heard", text=text, directed=directed, why=why)

    def _is_echo(self, text: str) -> bool:
        heard = words(text)
        if not heard or not self._spoken:
            return False
        playing = min(len(self._spoken) - self.player.pending, len(self._spoken) - 1)
        recent = set(words(" ".join(self._spoken[max(0, playing - 1) : playing + 1])))
        return sum(w in recent for w in heard) / len(heard) >= ECHO_OVERLAP

    def _start(self, speak, text: str, keep: bool = False) -> None:
        self._spoken = []
        self._announcing = text if keep else None
        self._set_state("thinking")
        self._task = self._loop.create_task(self._run(speak, text))

    async def _run(self, speak, text: str) -> None:
        try:
            await speak(text)
            await self.player.wait_done()
        except Exception:
            log.exception("speaking failed")
            ctx.bus.publish("error", message="Speaking failed")
            self.player.clear()
        if self._task is not asyncio.current_task():
            return
        if self._announcements:
            return self._start(self._announce, self._announcements.popleft(), keep=True)
        self._task = None
        self._cancel_resume_timer()
        self.player.resume()
        self._set_state("idle")
        self.attention.mark_spoke()

    async def _reply(self, text: str) -> None:
        chunker = SentenceChunker()
        async with aclosing(self.brain.respond(text)) as chunks:
            async for chunk in chunks:
                await self._speak(chunker.feed(chunk))
        await self._speak(chunker.flush())

    async def _announce(self, text: str) -> None:
        chunker = SentenceChunker()
        await self._speak(chunker.feed(text) + chunker.flush())

    async def _speak(self, sentences: list[str]) -> None:
        if not self.voice_on:
            return
        for sentence in sentences:
            text = clean_for_speech(sentence)
            if not text:
                continue
            audio = await asyncio.to_thread(self.voice.synth, text)
            if len(audio) == 0:
                continue
            log.debug("saying %d chars", len(text))
            self.player.play(audio)
            if self._heard_at is not None:
                log.info("first audio %d ms after speech ended (speech to text %d, deciding %d)", self._since_heard(), self._stt_ms, self._decide_ms)
                self._heard_at = None
            self._spoken.append(text)
            if self.state == "thinking":
                self._set_state("speaking")

    def _active(self) -> bool:
        return self._task is not None and not self._task.done()

    def _halt(self) -> asyncio.Task | None:
        self._cancel_resume_timer()
        self._cancel_ack()
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            if self._announcing is not None:
                self._announcements.appendleft(self._announcing)
        self.player.clear()
        return task

    async def _cancel(self) -> None:
        task = self._halt()
        while task is not None and task is not asyncio.current_task():
            await asyncio.wait({task})
            task = self._halt() if self._active() else None

    def _pause(self) -> None:
        if not self._active() or self.state == "paused":
            return
        self.player.pause()
        self._set_state("paused")
        self._arm_resume_timer()

    def _resume(self) -> None:
        self._cancel_resume_timer()
        self.player.resume()
        if self.state == "paused":
            self._set_state(self._speaking_state())

    def _settle(self) -> None:
        if self.state == "paused":
            self._resume()
        elif self.state == "listening":
            self._set_state("idle")

    def _speaking_state(self) -> str:
        if not self._active():
            return "idle"
        return "speaking" if self._spoken else "thinking"

    def _arm_resume_timer(self) -> None:
        self._cancel_resume_timer()
        self._resume_timer = self._loop.call_later(self.resume_timeout_s, self._resume)

    def _cancel_resume_timer(self) -> None:
        if self._resume_timer is not None:
            self._resume_timer.cancel()
            self._resume_timer = None

    def _set_state(self, value: str) -> None:
        if value != self.state:
            self.state = value
            ctx.bus.publish("state", value=value)
