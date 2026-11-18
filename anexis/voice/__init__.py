"""Voice, the backup way to talk to Anexis. Everything runs on the server with
local models, so no audio leaves your machines.

Hearing: faster-whisper (optional install: uv sync --extra voice).
Speaking: Piper, run as its own program (uv tool install piper-tts).
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
from importlib.util import find_spec
from pathlib import Path

from anexis.config import Settings
from anexis.tools.builtin.system import run_process

MAX_SPOKEN = 1300


def speakable(text: str) -> str:
    """Turns a chat reply into something that sounds right read aloud."""
    text = re.sub(r"```.*?```", "\nCode is on screen.\n", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "the link", text)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(#{1,6}|[-*+]|\d+[.)])\s+", "", line)
        line = re.sub(r"[*_`#>|]", "", line).strip()
        if line:
            lines.append(line)
    spoken = ""
    for i, line in enumerate(lines):
        last = i == len(lines) - 1
        spoken += line if last or line[-1] in ".,:;!?" else line + "."
        spoken += "" if last else " "
    if len(spoken) > MAX_SPOKEN:
        cut = spoken[:MAX_SPOKEN]
        stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        spoken = cut[: stop + 1] if stop > MAX_SPOKEN // 2 else cut
    return spoken


def _load_whisper(name: str):
    from faster_whisper import WhisperModel

    return WhisperModel(name, device="auto", compute_type="auto")


class Voice:
    def __init__(self, settings: Settings, model_factory=None):
        self.settings = settings
        self._factory = model_factory or _load_whisper
        self._injected = model_factory is not None
        self._model = None
        self._lock = threading.Lock()
        self.voices_dir = settings.home / "voices"

    def can_hear(self) -> tuple[bool, str]:
        if self._injected or find_spec("faster_whisper") is not None:
            return True, ""
        return False, "Speech to text is not installed on the server. Run: uv sync --extra voice"

    def can_speak(self) -> tuple[bool, str]:
        if not shutil.which(self.settings.piper_bin):
            return False, "Text to speech is not installed on the server. Run: uv tool install piper-tts"
        voice = self.settings.tts_voice
        if not (self.voices_dir / f"{voice}.onnx").exists():
            return False, (
                f"The voice {voice} is not downloaded. Run: uvx --from piper-tts python -m "
                f"piper.download_voices {voice} --data-dir {self.voices_dir}"
            )
        return True, ""

    def transcribe(self, wav: bytes) -> str:
        """Blocking. Call it from a worker thread."""
        with self._lock:  # one model, one transcription at a time
            if self._model is None:
                self._model = self._factory(self.settings.stt_model)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav)
            try:
                segments, _ = self._model.transcribe(f.name, vad_filter=True)
                return " ".join(s.text.strip() for s in segments if s.text.strip())
            finally:
                os.unlink(f.name)

    async def speak(self, text: str) -> bytes:
        spoken = speakable(text) or "Done."
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "speech.wav"
            command = [
                self.settings.piper_bin, "-m", self.settings.tts_voice,
                "--data-dir", str(self.voices_dir), "-f", str(out),
            ]
            code, output = await run_process(command, folder, 120, stdin=spoken.encode())
            if code != 0 or not out.exists():
                raise RuntimeError(f"Piper failed: {output.strip()[-300:] or 'no output'}")
            return out.read_bytes()
