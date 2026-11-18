"""Starts Hail Mary's JARVIS voice inside Anexis and stops it again.

Settings come from Anexis (anexis.toml, [voice]), with Hail Mary's own
settings.toml values as the defaults. `parts` swaps any piece for a stand in
(tests, or a computer without a microphone)."""

from __future__ import annotations

import asyncio
import logging
from importlib.util import find_spec

from anexis.voice.hailmary.bus import bus
from anexis.voice.hailmary.runtime import ctx

log = logging.getLogger(__name__)

PACKAGES = ("sounddevice", "soxr", "livekit", "onnx_asr", "piper", "onnxruntime", "huggingface_hub")


def config(settings) -> dict:
    """Hail Mary's settings.toml voice sections, with the owner's choices on top."""
    from anexis.voice.hailmary import models

    return {
        "models": str(models.folder(settings)),
        "user": {"title": settings.voice_title},
        "audio": {"input_device": settings.voice_input, "output_device": settings.voice_output,
                  "host_api": settings.voice_host_api, "delay_ms": 0, "aec": True},
        "listen": {"vad_threshold": 0.5, "start_windows": 3, "pre_roll_ms": 300, "silence_ms": 300, "max_pause_ms": 1500,
                   "max_utterance_s": 25, "barge_in_ms": 250, "turn_threshold": 0.5},
        "stt": {"model": settings.voice_stt_model, "quantization": settings.voice_stt_quantization, "device": "cuda"},
        "attention": {"mode": settings.voice_attention, "wake_words": list(settings.voice_wake_words),
                      "lead_ins": ["hey", "hi", "hello", "ok", "okay", "yo", "um", "uh", "so", "well", "please", "yeah"],
                      "follow_up_s": 8, "armed_s": 6, "judge": True, "judge_timeout_s": 1.5},
        "tts": {"model": "jarvis-high.onnx", "use_cuda": True, "length_scale": 1.0},
        "llm": {"max_prompt_chars": {"judge": 4000}},
    }


def _installed(name: str) -> bool:
    import sys

    if sys.modules.get(name) is not None:  # already loaded (a test may stand one in with no spec)
        return True
    try:
        return find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def available(settings) -> tuple[bool, str]:
    missing = [name for name in PACKAGES if not _installed(name)]
    if missing:
        return False, "Not installed: " + ", ".join(missing) + ". Open Setup and tick Voice."
    try:
        import sounddevice  # noqa: F401  (also needs the PortAudio library, which a server may not have)
    except OSError as e:
        return False, f"No sound system here: {e}"
    from anexis.voice.hailmary import models

    gone = models.missing(settings)
    if gone:
        return False, "Voice models not downloaded yet: " + ", ".join(gone) + ". Open Setup and tick Voice."
    return True, ""


class JudgeLLM:
    """The "was that for me?" judge, asked through Anexis's own models: the fast
    tool model when one is picked, else the small one."""

    def __init__(self, router):
        self.router = router

    async def complete(self, messages: list[dict], chain: str = "judge", max_tokens: int = 3, **_) -> str:
        role = "tools" if getattr(self.router, "has_role", lambda r: False)("tools") else "small"
        reply = await self.router.chat(role, messages)
        return reply.content or ""


class HailMaryEngine:
    name = "hailmary"

    def __init__(self, app, **parts):
        self.app = app
        self.parts = parts
        self.conversation = None
        self.audio = self.worker = None
        self._task: asyncio.Task | None = None
        self._state = "off"

    @property
    def state(self) -> str:
        if self._state == "listening" and self.conversation is not None and self.conversation.state != "idle":
            return self.conversation.state
        return self._state

    def start(self) -> None:
        self._state = "starting"
        self._task = asyncio.create_task(self._start())

    async def _start(self) -> None:
        from anexis.voice.hailmary.attention import Attention
        from anexis.voice.hailmary.audio import Player
        from anexis.voice.hailmary.brain import AnexisBrain
        from anexis.voice.hailmary.conversation import Conversation

        settings, parts = self.app.settings, self.parts
        cfg = config(settings)
        bus.bind(asyncio.get_running_loop(), self.app.events.publish)
        ctx.mode = cfg["attention"]["mode"]
        brain = AnexisBrain(self.app)
        player = parts.get("player") or Player()
        conv = Conversation(cfg, None, Attention(cfg, parts.get("judge") or JudgeLLM(self.app.router)), brain, None, player)
        brain.conversation = conv
        self.conversation = conv
        try:
            conv.voice, conv.stt = await asyncio.to_thread(self._load_speech, cfg)
            if "audio" in parts:  # a stand in: no microphone, no models
                self.audio = parts["audio"]
            else:
                self.audio, self.worker = await asyncio.to_thread(self._open_microphone, cfg, conv)
        except Exception as e:
            log.exception("voice failed to start")
            self._state = "failed"
            self.app.events.publish({"type": "wake_failed", "error": f"{type(e).__name__}: {e}"[:300]})
            return
        self._state = "listening"
        self.app.events.publish({"type": "wake_listening", "engine": self.name})

    def _load_speech(self, cfg: dict):
        """The voice and the ears: slow the first time, so off the main loop."""
        import numpy as np

        if "voice" in self.parts and "stt" in self.parts:
            return self.parts["voice"], self.parts["stt"]
        from anexis.voice.hailmary.stt import STT
        from anexis.voice.hailmary.tts import Voice

        voice, stt = Voice(cfg), STT(cfg)
        voice.synth("Ready.")                       # the first run of each model is slow;
        stt.transcribe(np.zeros(16000, np.float32))  # better here than on the first reply
        return voice, stt

    def _open_microphone(self, cfg: dict, conv):
        from pathlib import Path

        from anexis.voice.hailmary.audio import AudioIO, make_apm
        from anexis.voice.hailmary.listen import ListenWorker, Segmenter, SileroVAD, SmartTurn
        from anexis.voice.hailmary.models import SILERO_FILE, TURN_FILE

        here = Path(cfg["models"])
        segmenter = Segmenter(SileroVAD(here / SILERO_FILE), SmartTurn(here / TURN_FILE), cfg, conv.on_listen)
        worker = ListenWorker(segmenter)
        audio = AudioIO(cfg, conv.player, worker.put, apm=make_apm(cfg))
        worker.start()
        audio.start()
        return audio, worker

    async def say(self, text: str) -> None:
        """Says something on its own, like a heads up from the check ins."""
        if self.conversation is not None and self._state == "listening":
            await self.conversation.say(text)

    def stop(self) -> None:
        for part in (self.audio, self.worker):
            try:
                if part is not None and hasattr(part, "stop"):
                    part.stop()
            except Exception:
                log.exception("stopping a voice part failed")
        if self.conversation is not None:
            self.conversation.stop()
        if self._task is not None and not self._task.done():
            self._task.cancel()
        bus.unbind()
        self._state = "off"
