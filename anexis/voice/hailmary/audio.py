"""From the Hail Mary project (the owner's own JARVIS voice). Brought into
Anexis with only its imports changed; see anexis/voice/hailmary/__init__.py."""

import asyncio
import logging
import threading
from collections import deque
from collections.abc import Callable

import numpy as np
import sounddevice as sd
import soxr
from livekit import rtc

from anexis.voice.hailmary.bus import bus

log = logging.getLogger(__name__)

RATE = 48000
BLOCK = 480
MIC_RATE = 16000
LEVEL_EVERY_BLOCKS = 5
RETRY_S = 5
MAX_CONSECUTIVE_FAILURES = 50


class Player:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chunks: deque[np.ndarray] = deque()
        self._offset = 0
        self._paused = False

    def play(self, audio: np.ndarray) -> None:
        if len(audio) == 0:
            return
        with self._lock:
            self._chunks.append(np.array(audio, dtype=np.float32, order="C").reshape(-1))

    def read(self, n: int) -> np.ndarray:
        out = np.zeros(n, np.float32)
        with self._lock:
            if self._paused:
                return out
            filled = 0
            while filled < n and self._chunks:
                head = self._chunks[0]
                take = head[self._offset : self._offset + n - filled]
                out[filled : filled + len(take)] = take
                filled += len(take)
                self._offset += len(take)
                if self._offset >= len(head):
                    self._chunks.popleft()
                    self._offset = 0
        return out

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def clear(self) -> None:
        with self._lock:
            self._chunks.clear()
            self._offset = 0
            self._paused = False

    @property
    def busy(self) -> bool:
        with self._lock:
            return bool(self._chunks) and not self._paused

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._chunks)

    @property
    def paused(self) -> bool:
        with self._lock:
            return self._paused

    async def wait_done(self, poll: float = 0.03) -> None:
        while self._queued():
            await asyncio.sleep(poll)

    def _queued(self) -> bool:
        with self._lock:
            return bool(self._chunks)


def make_apm(cfg: dict) -> rtc.AudioProcessingModule | None:
    if not cfg["audio"]["aec"]:
        return None
    return rtc.AudioProcessingModule(echo_cancellation=True, noise_suppression=True, high_pass_filter=True)


def resolve_devices(cfg: dict) -> tuple[int | None, int | None]:
    devices, apis = sd.query_devices(), sd.query_hostapis()
    wanted = cfg["host_api"].lower()
    api = next((i for i, a in enumerate(apis) if wanted in a["name"].lower()), None)
    if api is None:
        return None, None
    return (
        _pick_device(devices, apis[api], api, cfg["input_device"], "input"),
        _pick_device(devices, apis[api], api, cfg["output_device"], "output"),
    )


def _pick_device(devices, api_info: dict, api: int, name: str, kind: str) -> int:
    if name:
        for i, d in enumerate(devices):
            if d["hostapi"] == api and d[f"max_{kind}_channels"] > 0 and name.lower() in d["name"].lower():
                return i
        log.warning("%s device %r not found in %s, using its default", kind, name, api_info["name"])
    return api_info[f"default_{kind}_device"]


class _Int16Frame:
    def __init__(self) -> None:
        self._buf = bytearray(BLOCK * 2)
        self._pcm = np.frombuffer(self._buf, np.int16)
        self.frame = rtc.AudioFrame(self._buf, RATE, 1, BLOCK)

    def load(self, block: np.ndarray) -> None:
        self._pcm[:] = np.clip(block * 32768.0, -32768, 32767)

    def read(self) -> np.ndarray:
        return self._pcm.astype(np.float32) / 32768.0


class AudioIO:
    def __init__(self, cfg: dict, player: Player, on_mic: Callable[[np.ndarray], None], apm=None) -> None:
        self.cfg = cfg["audio"]
        self.player = player
        self.on_mic = on_mic
        self.apm = apm
        self.muted = False
        self._reverse = _Int16Frame()
        self._capture = _Int16Frame()
        self._resampler = soxr.ResampleStream(RATE, MIC_RATE, 1, dtype="float32")
        self._silence = np.zeros(BLOCK, np.float32)
        self._blocks = 0
        self._stream: sd.Stream | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._retry: asyncio.TimerHandle | None = None
        self._stopped = False
        self._failures = 0
        self._consumer_failed = False

    def start(self) -> bool:
        self._remember_loop()
        self._stopped = False
        if self._stream is not None:
            return True
        try:
            self._stream = self._open_stream()
        except (sd.PortAudioError, ValueError) as e:
            log.warning("audio device failed: %s", e)
            bus.publish("error", message=f"Audio device failed: {e}")
            self._schedule_retry()
            return False
        self._cancel_retry()
        return True

    def stop(self) -> None:
        self._stopped = True
        self._cancel_retry()
        self._close_stream()

    def process(self, indata: np.ndarray, outdata: np.ndarray) -> None:
        ref = self.player.read(BLOCK)
        outdata[:, 0] = ref
        mic = self._clean(ref, indata[:, 0])
        if self.muted:
            mic = self._silence
        self._publish_levels(mic, ref)
        resampled = self._resampler.resample_chunk(mic)
        if len(resampled):
            self._deliver(resampled)

    def _deliver(self, resampled: np.ndarray) -> None:
        try:
            self.on_mic(resampled)
        except Exception:
            if not self._consumer_failed:
                self._consumer_failed = True
                log.exception("on_mic consumer failed")
        else:
            self._consumer_failed = False

    def _clean(self, ref: np.ndarray, mic: np.ndarray) -> np.ndarray:
        if self.apm is None:
            return np.ascontiguousarray(mic)
        self._reverse.load(ref)
        self.apm.process_reverse_stream(self._reverse.frame)
        self._capture.load(mic)
        self.apm.process_stream(self._capture.frame)
        return self._capture.read()

    def _publish_levels(self, mic: np.ndarray, out: np.ndarray) -> None:
        self._blocks += 1
        if self._blocks % LEVEL_EVERY_BLOCKS == 0:
            bus.publish("levels", mic=_rms(mic), out=_rms(out))

    def _open_stream(self) -> sd.Stream:
        stream = sd.Stream(
            samplerate=RATE,
            blocksize=BLOCK,
            channels=1,
            dtype="float32",
            device=resolve_devices(self.cfg),
            callback=self._callback,
            finished_callback=self._on_finished,
        )
        try:
            if self.apm is not None:
                self.apm.set_stream_delay_ms(self.cfg["delay_ms"] or round(sum(stream.latency) * 1000))
            stream.start()
        except BaseException:
            stream.close()
            raise
        return stream

    def _callback(self, indata, outdata, frames, time, status) -> None:
        try:
            if frames != BLOCK:
                raise ValueError(f"unexpected block size {frames}")
            self.process(indata, outdata)
        except Exception:
            self._processing_failed(outdata)
        else:
            self._failures = 0

    def _processing_failed(self, outdata: np.ndarray) -> None:
        outdata.fill(0)
        self._failures += 1
        if self._failures == 1:
            log.exception("audio processing failed")
            bus.publish("error", message="Audio processing failed")
        if self._failures >= MAX_CONSECUTIVE_FAILURES:
            self._failures = 0
            raise sd.CallbackStop

    def _on_finished(self) -> None:
        if self._stream is None:
            return
        bus.publish("error", message="Audio stream stopped, reopening")
        self._schedule_retry()

    def _close_stream(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            stream.stop()
        finally:
            stream.close()

    def _remember_loop(self) -> None:
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

    def _schedule_retry(self) -> None:
        if self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._arm_retry)
        except RuntimeError:  # loop already closed during shutdown
            pass

    def _arm_retry(self) -> None:
        if self._stopped:
            return
        self._cancel_retry()
        try:
            self._close_stream()
        except sd.PortAudioError as e:
            log.warning("closing dead audio stream failed: %s", e)
        self._retry = self._loop.call_later(RETRY_S, self._retry_start)

    def _cancel_retry(self) -> None:
        if self._retry is not None:
            self._retry.cancel()
            self._retry = None

    def _retry_start(self) -> None:
        self._retry = None
        self.start()


def _rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(block))))
