"""From the Hail Mary project (the owner's own JARVIS voice). Brought into
Anexis with only its imports changed; see anexis/voice/hailmary/__init__.py."""

import logging
import string

import numpy as np
import onnx_asr
import onnxruntime

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
MIN_ALNUM = 2
FULL_PRECISION = {"", "fp32", "none"}


def onnx_quantization(value: str) -> str | None:
    value = value.lower()
    return None if value in FULL_PRECISION else value


class STT:
    def __init__(self, cfg: dict) -> None:
        stt = cfg["stt"]
        self.device = self._resolve_device(stt["device"])
        self._wake_words = {w.lower() for w in cfg["attention"]["wake_words"]}
        quantization = onnx_quantization(stt["quantization"])
        try:
            self._model = self._load(stt["model"], quantization)
        except Exception:
            if self.device != "cuda":
                raise
            log.warning("STT: loading on CUDA failed, using CPU", exc_info=True)
            self.device = "cpu"
            self._model = self._load(stt["model"], quantization)
        log.info("STT %s (%s) on %s", stt["model"], quantization or "fp32", self.device)

    def _load(self, model: str, quantization: str | None):
        return onnx_asr.load_model(model, quantization=quantization, providers=self._providers(self.device))

    @staticmethod
    def _resolve_device(requested: str) -> str:
        if requested != "cuda":
            return "cpu"
        if "CUDAExecutionProvider" in onnxruntime.get_available_providers():
            return "cuda"
        log.warning("STT: CUDA requested but CUDAExecutionProvider is unavailable, using CPU")
        return "cpu"

    @staticmethod
    def _providers(device: str) -> list[str]:
        if device == "cuda":
            onnxruntime.preload_dlls()
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def transcribe(self, audio16k: np.ndarray) -> str:
        if len(audio16k) == 0:
            return ""
        text = self._model.recognize(audio16k, sample_rate=SAMPLE_RATE).strip()
        return text if self._worth_keeping(text) else ""

    def _worth_keeping(self, text: str) -> bool:
        if sum(c.isalnum() for c in text) >= MIN_ALNUM:
            return True
        return text.strip(string.punctuation + string.whitespace).lower() in self._wake_words
