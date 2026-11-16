"""Microphone and speakers on the machine the CLI runs on.

Optional: needs the sounddevice package and a real audio device. Over plain
SSH there is none, and Greg just stays in text.
"""

from __future__ import annotations

import io
import wave

RATE = 16000


def audio_ready() -> tuple[bool, str]:
    try:
        import sounddevice as sd

        devices = sd.query_devices()
    except ImportError:
        return False, "Voice is not installed on this machine. Run ./install.sh and say yes to voice."
    except OSError as e:
        if "portaudio" in str(e).lower():
            return False, "The audio library is missing on this machine. Install it with: sudo apt install libportaudio2"
        return False, f"No audio on this machine ({e})."
    except Exception as e:
        return False, f"No audio on this machine ({type(e).__name__})."
    if not any(d.get("max_input_channels", 0) > 0 for d in devices):
        return False, "No microphone found on this machine."
    return True, ""


def record(wait_for_stop) -> bytes:
    """Records from the default microphone until wait_for_stop() returns. WAV bytes back."""
    import sounddevice as sd

    chunks: list[bytes] = []
    with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16",
                           callback=lambda data, frames, time, status: chunks.append(bytes(data))):
        wait_for_stop()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(chunks))
    return buf.getvalue()


def play(wav: bytes) -> None:
    import numpy as np
    import sounddevice as sd

    with wave.open(io.BytesIO(wav), "rb") as w:
        frames = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        if w.getnchannels() > 1:
            frames = frames.reshape(-1, w.getnchannels())
        sd.play(frames, w.getframerate())
        sd.wait()
