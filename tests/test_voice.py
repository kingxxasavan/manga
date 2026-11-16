import io
import wave
from pathlib import Path
from types import SimpleNamespace

from anexis.voice import Voice, speakable

FAKE_PIPER = str(Path(__file__).parent / "fake_piper.py")


def wav_bytes():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)
    return buf.getvalue()


def test_transcribe_hands_the_audio_to_the_model_and_joins_what_it_heard(settings):
    seen = {}

    class Model:
        def transcribe(self, path, **kw):
            seen["audio"] = Path(path).read_bytes()
            return [SimpleNamespace(text=" what is due"), SimpleNamespace(text=" this week ")], None

    voice = Voice(settings, model_factory=lambda name: Model())
    audio = wav_bytes()
    assert voice.transcribe(audio) == "what is due this week"
    assert seen["audio"] == audio


def test_the_speech_model_is_loaded_once(settings):
    loads = []

    class Model:
        def transcribe(self, path, **kw):
            return [], None

    def factory(name):
        loads.append(name)
        return Model()

    voice = Voice(settings, model_factory=factory)
    voice.transcribe(wav_bytes())
    voice.transcribe(wav_bytes())
    assert loads == [settings.stt_model]


def test_hearing_is_reported_unavailable_with_the_fix_when_whisper_is_missing(settings, monkeypatch):
    monkeypatch.setattr("anexis.voice.find_spec", lambda name: None)
    ok, why = Voice(settings).can_hear()
    assert not ok and "uv sync --extra voice" in why


def test_speaking_needs_the_piper_program(settings):
    settings.piper_bin = "/nonexistent/piper"
    ok, why = Voice(settings).can_speak()
    assert not ok and "piper-tts" in why


def test_speaking_needs_the_voice_file_and_says_how_to_get_it(settings):
    settings.piper_bin = FAKE_PIPER
    ok, why = Voice(settings).can_speak()
    assert not ok and "download_voices" in why and settings.tts_voice in why


async def test_speak_returns_wav_audio_of_the_cleaned_text(settings):
    settings.piper_bin = FAKE_PIPER
    voices = settings.home / "voices"
    voices.mkdir(parents=True)
    (voices / f"{settings.tts_voice}.onnx").write_bytes(b"x")
    voice = Voice(settings)
    assert voice.can_speak() == (True, "")
    audio = await voice.speak("**Two things** are due. See `notes.txt`.")
    assert audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"


def test_speakable_strips_markup_code_and_links():
    spoken = speakable("## Plan\n**Two** things:\n- read [the doc](https://x.io/a)\n```python\nprint(1)\n```\nVisit https://example.com/page now")
    assert spoken == "Plan. Two things: read the doc. Code is on screen. Visit the link now"


def test_speakable_keeps_long_replies_short():
    assert len(speakable("word " * 2000)) <= 1300


def test_a_missing_audio_library_is_named_with_the_command_that_fixes_it(monkeypatch):
    import builtins

    from anexis.cli.audio import audio_ready

    real_import = builtins.__import__

    def no_portaudio(name, *args, **kw):
        if name == "sounddevice":
            raise OSError("PortAudio library not found")
        return real_import(name, *args, **kw)

    monkeypatch.setattr(builtins, "__import__", no_portaudio)
    ok, why = audio_ready()
    assert not ok and "libportaudio2" in why


def test_no_voice_packages_at_all_points_at_the_installer(monkeypatch):
    import builtins

    from anexis.cli.audio import audio_ready

    real_import = builtins.__import__

    def missing(name, *args, **kw):
        if name == "sounddevice":
            raise ModuleNotFoundError("No module named 'sounddevice'")
        return real_import(name, *args, **kw)

    monkeypatch.setattr(builtins, "__import__", missing)
    ok, why = audio_ready()
    assert not ok and "setup.sh" in why
