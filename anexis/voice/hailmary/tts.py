"""From the Hail Mary project (the owner's own JARVIS voice). Brought into
Anexis with only its imports changed; see anexis/voice/hailmary/__init__.py."""

import logging
import re

import numpy as np
import onnxruntime
import soxr
from piper import PiperVoice, SynthesisConfig

from pathlib import Path

from anexis.voice.hailmary.audio import RATE

log = logging.getLogger(__name__)

ABBREVIATIONS = {"e.g.", "i.e.", "mr.", "mrs.", "dr.", "vs.", "etc.", "st."}
EARLY_BREAK_CHARS = 40
BOUNDARY = re.compile(r"""[.!?;]["')\]\u201d\u2019]*(?=\s)|,(?=\s)|\n""")
MAX_UNBROKEN_CHARS = 200
LIST_NUMBER = re.compile(r"\(?\d+[.!?;]*[)\]]?")
OPENERS = "([{\"'\u201c\u2018"
CLOSERS = ")]}\"'\u201d\u2019"


class SentenceChunker:
    def __init__(self) -> None:
        self._buf = ""
        self._first = True

    def feed(self, text: str) -> list[str]:
        self._buf += text
        out = []
        while (cut := self._next_cut()) is not None:
            chunk = self._buf[:cut].strip()
            self._buf = self._buf[cut:].lstrip()
            if chunk:
                out.append(chunk)
                self._first = False
        return out

    def flush(self) -> list[str]:
        rest = self._buf.strip()
        self._buf = ""
        self._first = True
        return [rest] if rest else []

    def _next_cut(self) -> int | None:
        for m in BOUNDARY.finditer(self._buf):
            if self._ends_chunk(m.group()[0], m.end()):
                return m.end()
        if len(self._buf) > MAX_UNBROKEN_CHARS:
            return self._overflow_cut()
        return None

    def _overflow_cut(self) -> int | None:
        comma = self._buf.rfind(", ")
        if comma != -1:
            return comma + 1
        space = self._buf.rfind(" ")
        return space + 1 if space != -1 else None

    def _ends_chunk(self, mark: str, end: int) -> bool:
        chunk = self._buf[:end].strip()
        if LIST_NUMBER.fullmatch(chunk):
            return False
        if mark == "\n":
            return True
        if mark == ",":
            return self._first and len(chunk) >= EARLY_BREAK_CHARS
        if mark == ".":
            return chunk.split()[-1].lstrip(OPENERS).rstrip(CLOSERS).lower() not in ABBREVIATIONS
        return True


def clean_for_speech(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(?<!\S)#+(?=\s)", " ", text)
    text = re.sub(r"^\s*[-\u2022]\s+", " ", text, flags=re.M)
    text = re.sub(r"[*`]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


class Voice:
    def __init__(self, cfg: dict) -> None:
        tts = cfg["tts"]
        self._piper = self._load(Path(cfg["models"]) / tts["model"], tts["use_cuda"])
        self._syn = SynthesisConfig(length_scale=tts.get("length_scale", 1.0))
        self._rate = self._piper.config.sample_rate
        self.device = "cuda" if "CUDAExecutionProvider" in self._piper.session.get_providers() else "cpu"
        log.info("Piper voice on %s", self.device)

    @staticmethod
    def _load(path, use_cuda: bool) -> PiperVoice:
        onnxruntime.set_default_logger_severity(3)
        if use_cuda:
            try:
                onnxruntime.preload_dlls()
                return PiperVoice.load(path, use_cuda=True)
            except Exception:
                log.warning("Piper CUDA load failed, using CPU", exc_info=True)
        return PiperVoice.load(path, use_cuda=False)

    def synth(self, text: str) -> np.ndarray:
        parts = [c.audio_float_array for c in self._piper.synthesize(text, self._syn)]
        if not parts:
            return np.zeros(0, np.float32)
        audio = np.concatenate(parts)
        return np.clip(soxr.resample(audio, self._rate, RATE), -1.0, 1.0)
