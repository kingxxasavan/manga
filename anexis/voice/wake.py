"""Hands free: say "hey Jarvis", then talk. Anexis listens in the background,
even with its window hidden in the tray.

The loop:  hear the wake word  ->  record until you stop talking  ->  turn the
speech into text  ->  answer it like a chat message  ->  say the answer out loud.

Every step is its own piece (`Ears`, `Detector`, `record_utterance`, the
transcriber and the speaker), so a different wake word engine or voice can be
dropped in without touching the rest.

Runs on this computer only: openWakeWord hears the wake word, faster-whisper
writes down what was said, Piper speaks. No audio leaves the machine.
"""

from __future__ import annotations

import asyncio
import io
import threading
import time
import wave
from collections.abc import Callable, Iterator
from importlib.util import find_spec

import numpy as np

RATE = 16000          # samples a second: what the wake word and speech models want
FRAME = 1280          # 80 ms, the size openWakeWord reads at a time
VOICE_SESSION = "voice"


def can_wake() -> tuple[bool, str]:
    missing = [name for name in ("openwakeword", "sounddevice", "faster_whisper") if find_spec(name) is None]
    if missing:
        return False, "Not installed: " + ", ".join(missing) + ". Open Setup and tick Voice."
    return True, ""


class Ears:
    """The microphone, as 80 ms frames of 16 bit audio."""

    def __init__(self):
        import sounddevice

        self._queue: list[np.ndarray] = []
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._stream = sounddevice.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME, callback=self._take)
        self._stream.start()

    def _take(self, data, frames, when, status) -> None:
        with self._lock:
            self._queue.append(data[:, 0].copy())
            if len(self._queue) > 200:  # nobody reading: keep only the last 16 seconds
                self._queue = self._queue[-200:]
        self._ready.set()

    def frames(self, stop: threading.Event) -> Iterator[np.ndarray]:
        while not stop.is_set():
            self._ready.wait(0.5)
            with self._lock:
                ready, self._queue = self._queue, []
                self._ready.clear()
            yield from ready

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


class Detector:
    """openWakeWord with its ready made "hey jarvis" model."""

    def __init__(self, word: str = "hey_jarvis", models_dir=None):
        import openwakeword
        from openwakeword.model import Model

        try:
            openwakeword.utils.download_models([word])  # once: a few MB, kept with the package
        except Exception:
            pass  # already there, or offline: loading below says if it is missing
        self.model = Model(wakeword_models=[word], inference_framework="onnx")
        self.word = word

    def __call__(self, frame: np.ndarray) -> float:
        scores = self.model.predict(frame)
        return float(max(scores.values())) if scores else 0.0

    def reset(self) -> None:
        self.model.reset()


def record_utterance(frames: Iterator[np.ndarray], silence_after: float = 1.2, longest: float = 20.0,
                     shortest: float = 0.6) -> np.ndarray:
    """Takes frames until the speaker has been quiet for `silence_after`
    seconds (after saying something), or `longest` seconds have passed."""
    taken: list[np.ndarray] = []
    loud_seen, quiet_for = False, 0.0
    room: list[float] = []  # how loud the room is, from the first moments
    for frame in frames:
        taken.append(frame)
        level = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
        if len(room) < 4:
            room.append(level)
        loud = level > max(350.0, sorted(room)[len(room) // 2] * 2.5)
        seconds = len(taken) * FRAME / RATE
        if loud:
            loud_seen, quiet_for = True, 0.0
        else:
            quiet_for += FRAME / RATE
        if (loud_seen and quiet_for >= silence_after and seconds >= shortest) or seconds >= longest:
            break
        if not loud_seen and seconds >= 6.0:  # woke up but nobody said anything
            break
    return np.concatenate(taken) if taken else np.zeros(0, dtype=np.int16)


def to_wav(audio: np.ndarray) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(audio.astype(np.int16).tobytes())
    return out.getvalue()


def play_wav(data: bytes) -> None:
    """Plays a WAV file on the speakers and waits until it is done."""
    import sounddevice

    with wave.open(io.BytesIO(data)) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        sounddevice.play(audio, w.getframerate())
    sounddevice.wait()


class WakeListener:
    """The background loop. `on_heard(text)` answers a spoken message and
    returns the reply text. Everything else can be swapped for tests or for
    another voice engine."""

    def __init__(self, app, on_heard: Callable, detector=None, ears=None, transcribe=None, speak=None,
                 play=play_wav, threshold: float = 0.5):
        self.app = app
        self.on_heard = on_heard
        self._detector, self._ears = detector, ears
        self.transcribe = transcribe or app.voice.transcribe
        self.speak = speak or app.voice.speak
        self.play = play
        self.threshold = threshold
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.state = "off"

    def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="wake-word", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(5)
        self.state = "off"

    def _publish(self, event: dict) -> None:
        if self.loop:
            self.loop.call_soon_threadsafe(self.app.events.publish, event)

    def _run(self) -> None:
        try:
            ears = self._ears or Ears()
            detector = self._detector or Detector(self.app.settings.wake_word)
        except Exception as e:  # no microphone, or the packages are missing
            self.state = "failed"
            self._publish({"type": "wake_failed", "error": f"{type(e).__name__}: {e}"[:300]})
            return
        self.state = "listening"
        self._publish({"type": "wake_listening"})
        frames = ears.frames(self.stop_event)
        try:
            for frame in frames:
                if self.stop_event.is_set():
                    break
                if detector(frame) < self.threshold:
                    continue
                self._turn(frames)
                if hasattr(detector, "reset"):
                    detector.reset()  # forget the wake word that was just heard
        finally:
            if hasattr(ears, "close"):
                ears.close()

    def _turn(self, frames) -> None:
        """One spoken exchange, after the wake word."""
        self.state = "awake"
        self._publish({"type": "wake"})  # the deck brings the window back
        audio = record_utterance(frames)
        text = (self.transcribe(to_wav(audio)) or "").strip() if audio.size else ""
        if not text:
            self._publish({"type": "voice_heard", "text": ""})
            self.state = "listening"
            return
        self._publish({"type": "voice_heard", "text": text})
        future = asyncio.run_coroutine_threadsafe(self.on_heard(text), self.loop)
        try:
            reply = future.result(timeout=600)
        except Exception as e:
            reply = f"Sorry, that did not work: {e}"
        if reply:
            try:
                sound = asyncio.run_coroutine_threadsafe(self.speak(reply), self.loop).result(timeout=120)
                self.state = "speaking"
                self.play(sound)
            except Exception as e:
                self._publish({"type": "wake_failed", "error": f"Could not speak: {e}"[:300]})
        self.state = "listening"
        time.sleep(0.2)
