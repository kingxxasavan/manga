"""Downloads the voice models, the same ones Hail Mary's setup.py fetched,
into Anexis's home folder (voices/hailmary). Each is fetched once."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

TURN_FILE = "smart-turn-v3.2-cpu.onnx"
SILERO_FILE = "silero_vad.onnx"
HF_FILES = [
    ("jgkawell/jarvis", "en/en_GB/jarvis/high/jarvis-high.onnx"),
    ("jgkawell/jarvis", "en/en_GB/jarvis/high/jarvis-high.onnx.json"),
    ("pipecat-ai/smart-turn-v3", TURN_FILE),
]
SILERO_URL = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"


def folder(settings) -> Path:
    return settings.home / "voices" / "hailmary"


def stt_cached(stt_model: str, quantization: str) -> bool:
    try:
        from onnx_asr.loader import create_asr_resolver

        from anexis.voice.hailmary.stt import onnx_quantization

        create_asr_resolver(stt_model, offline=True).resolve_model(quantization=onnx_quantization(quantization))
    except Exception:
        return False
    return True


def missing(settings) -> list[str]:
    here = folder(settings)
    names = [Path(f).name for _, f in HF_FILES] + [SILERO_FILE]
    out = sorted(n for n in names if not (here / n).exists())
    if not stt_cached(settings.voice_stt_model, settings.voice_stt_quantization):
        out.append(f"{settings.voice_stt_model} (speech to text)")
    return out


def ensure(settings, say: Callable[[str], None] = lambda line: None) -> None:
    """Fetches whatever is missing. Raises with a plain reason when it cannot."""
    import httpx
    import onnx_asr
    from huggingface_hub import hf_hub_download

    from anexis.voice.hailmary.stt import onnx_quantization

    here = folder(settings)
    here.mkdir(parents=True, exist_ok=True)
    for repo, filename in HF_FILES:
        target = here / Path(filename).name
        if target.exists():
            continue
        say(f"downloading {target.name}")
        with tempfile.TemporaryDirectory(dir=here, ignore_cleanup_errors=True) as tmp:
            Path(hf_hub_download(repo, filename, local_dir=tmp)).replace(target)
    target = here / SILERO_FILE
    if not target.exists():
        say(f"downloading {SILERO_FILE}")
        response = httpx.get(SILERO_URL, follow_redirects=True, timeout=60)
        response.raise_for_status()
        part = target.with_suffix(".part")
        part.write_bytes(response.content)
        part.replace(target)
    if not stt_cached(settings.voice_stt_model, settings.voice_stt_quantization):
        say(f"downloading the speech model {settings.voice_stt_model}, about 600 MB")
        onnx_asr.load_model(settings.voice_stt_model, quantization=onnx_quantization(settings.voice_stt_quantization),
                            providers=["CPUExecutionProvider"])


if __name__ == "__main__":  # the Setup step runs this: python -m anexis.voice.hailmary.models
    from anexis.config import load_settings

    ensure(load_settings(), say=lambda line: print(line, flush=True))
    print("voice models ready", flush=True)
