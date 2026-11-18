"""From the Hail Mary project (the owner's own JARVIS voice). Brought into
Anexis with only its imports changed; see anexis/voice/hailmary/__init__.py."""

import logging
import queue
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path

import numpy as np
import onnxruntime as ort

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
QUEUE_CHUNKS = 1000
STOP_WAIT_S = 2
WINDOW = 512
CONTEXT = 64
MIN_VOICED_MS = 250
TURN_SECONDS = 8
TURN_RECHECK_MS = 300
TURN_SAMPLES = TURN_SECONDS * SAMPLE_RATE
N_FFT = 400
HOP = 160
N_MELS = 80
WINDOW_MS = WINDOW * 1000 / SAMPLE_RATE


def _session(path: Path) -> ort.InferenceSession:
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


class SileroVAD:
    def __init__(self, path: Path) -> None:
        self._session = _session(path)
        self._sr = np.array(SAMPLE_RATE, np.int64)
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), np.float32)
        self._context = np.zeros(CONTEXT, np.float32)

    def __call__(self, chunk: np.ndarray) -> float:
        x = np.concatenate([self._context, np.asarray(chunk, np.float32)])[None]
        out, self._state = self._session.run(None, {"input": x, "state": self._state, "sr": self._sr})
        self._context = x[0, -CONTEXT:]
        return float(out[0, 0])


def _hz_to_mel(hz: np.ndarray) -> np.ndarray:
    hz = np.asarray(hz, np.float64)
    log_part = 15 + np.log(np.maximum(hz, 1000) / 1000) / (np.log(6.4) / 27)
    return np.where(hz >= 1000, log_part, hz / (200 / 3))


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    log_part = 1000 * np.exp((np.log(6.4) / 27) * (mel - 15))
    return np.where(mel >= 15, log_part, mel * (200 / 3))


def mel_filterbank() -> np.ndarray:
    fft_freqs = np.linspace(0, SAMPLE_RATE / 2, N_FFT // 2 + 1)
    edges = _mel_to_hz(np.linspace(_hz_to_mel(0), _hz_to_mel(SAMPLE_RATE / 2), N_MELS + 2))
    ramps = edges[:, None] - fft_freqs[None]
    lower = -ramps[:-2] / np.diff(edges)[:-1, None]
    upper = ramps[2:] / np.diff(edges)[1:, None]
    weights = np.maximum(0, np.minimum(lower, upper))
    return (weights * (2 / (edges[2:] - edges[:-2]))[:, None]).astype(np.float32)


_FILTERS = mel_filterbank()
_HANN = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)


def log_mel(audio16k: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio16k, np.float32)[-TURN_SAMPLES:]
    audio = np.pad(audio, (TURN_SAMPLES - len(audio), 0))
    audio = (audio - audio.mean()) / np.sqrt(audio.var() + 1e-7)
    padded = np.pad(audio, N_FFT // 2, mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, N_FFT)[::HOP]
    power = np.abs(np.fft.rfft(frames * _HANN, axis=1)) ** 2
    mel = _FILTERS @ power[:-1].T
    log = np.log10(np.maximum(mel, 1e-10))
    log = np.maximum(log, log.max() - 8)
    return ((log + 4) / 4).astype(np.float32)


class SmartTurn:
    def __init__(self, path: Path) -> None:
        self._session = _session(path)

    def __call__(self, audio16k: np.ndarray) -> float:
        out = self._session.run(None, {"input_features": log_mel(audio16k)[None]})
        return float(out[0][0][0])


class Segmenter:
    def __init__(self, vad, turn, cfg: dict, emit: Callable[[str, np.ndarray | None], None]) -> None:
        c = cfg["listen"]
        self.vad, self.turn, self.emit = vad, turn, emit
        self.threshold = c["vad_threshold"]
        self.start_windows = c["start_windows"]
        self.silence_ms = c["silence_ms"]
        self.max_pause_ms = c["max_pause_ms"]
        self.max_samples = int(c["max_utterance_s"] * SAMPLE_RATE)
        self.barge_in_ms = c["barge_in_ms"]
        self.turn_threshold = c["turn_threshold"]
        pre_roll = -(-c["pre_roll_ms"] * SAMPLE_RATE // 1000 // WINDOW)
        self._ring: deque[np.ndarray] = deque(maxlen=pre_roll + self.start_windows)
        self.reset()

    def reset(self) -> None:
        self._pending = np.zeros(0, np.float32)
        self._clear_utterance()

    def _clear_utterance(self) -> None:
        self.vad.reset()
        self._ring.clear()
        self._run = 0
        self._speaking = False
        self._buffer: list[np.ndarray] = []
        self._samples = 0
        self._voiced_ms = 0.0
        self._silence_run = 0.0
        self._sustained = False
        self._next_check_ms = self.silence_ms

    def feed(self, samples16k: np.ndarray) -> None:
        self._pending = np.concatenate([self._pending, np.asarray(samples16k, np.float32)])
        usable = len(self._pending) // WINDOW * WINDOW
        windows, self._pending = self._pending[:usable], self._pending[usable:]
        for window in windows.reshape(-1, WINDOW):
            self._window(window)

    def _window(self, window: np.ndarray) -> None:
        voiced = self.vad(window) >= self.threshold
        if self._speaking:
            self._speaking_window(window, voiced)
        else:
            self._idle_window(window, voiced)

    def _idle_window(self, window: np.ndarray, voiced: bool) -> None:
        self._ring.append(window)
        self._run = self._run + 1 if voiced else 0
        if self._run >= self.start_windows:
            self._begin()

    def _begin(self) -> None:
        self._speaking = True
        self._buffer = list(self._ring)
        self._samples = len(self._buffer) * WINDOW
        self._voiced_ms = self._run * WINDOW_MS
        self._ring.clear()
        self.emit("speech_start", None)
        self._check_sustained()

    def _speaking_window(self, window: np.ndarray, voiced: bool) -> None:
        self._buffer.append(window)
        self._samples += WINDOW
        if voiced:
            self._voiced_ms += WINDOW_MS
            self._silence_run = 0.0
            self._next_check_ms = self.silence_ms
            self._check_sustained()
        else:
            self._silence_run += WINDOW_MS
        if self._should_finish():
            self._finish()

    def _check_sustained(self) -> None:
        if not self._sustained and self._voiced_ms >= self.barge_in_ms:
            self._sustained = True
            self.emit("speech_sustained", None)

    def _should_finish(self) -> bool:
        if self._samples >= self.max_samples or self._silence_run >= self.max_pause_ms:
            return True
        if self._silence_run < self._next_check_ms:
            return False
        if self._voiced_ms < MIN_VOICED_MS:
            return True
        self._next_check_ms = self._silence_run + TURN_RECHECK_MS
        return self.turn(np.concatenate(self._buffer)) >= self.turn_threshold

    def _finish(self) -> None:
        audio = np.concatenate(self._buffer)
        name = "discard" if self._voiced_ms < MIN_VOICED_MS else "utterance"
        self._clear_utterance()
        self.emit(name, audio if name == "utterance" else None)


class ListenWorker:
    def __init__(self, segmenter, max_chunks: int = QUEUE_CHUNKS) -> None:
        self._segmenter = segmenter
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=max_chunks)
        self._thread = threading.Thread(target=self._run, name="listen", daemon=True)
        self._dropping = False

    def put(self, samples16k: np.ndarray) -> None:
        try:
            self._queue.put_nowait(samples16k)
        except queue.Full:
            if not self._dropping:
                self._dropping = True
                log.warning("listener is falling behind, dropping microphone audio")
        else:
            self._dropping = False

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        if not self._thread.is_alive():
            return
        while True:
            try:
                self._queue.put_nowait(None)
                break
            except queue.Full:
                self._discard_one()
        self._thread.join(STOP_WAIT_S)

    def _discard_one(self) -> None:
        try:
            self._queue.get_nowait()
        except queue.Empty:
            pass

    def _run(self) -> None:
        failing = False
        while (samples := self._queue.get()) is not None:
            try:
                self._segmenter.feed(samples)
            except Exception:
                if not failing:
                    log.exception("listening failed")
                failing = True
            else:
                failing = False
