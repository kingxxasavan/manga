"""The Hail Mary JARVIS voice inside Anexis. The microphone, speakers and the
speech models get stand ins here; everything between them is the real code."""

import asyncio
import sys
import types

import numpy as np
import pytest

try:
    import sounddevice  # noqa: F401
except (ImportError, OSError):  # no PortAudio on this machine: a stand in, so the files can be imported
    stub = types.ModuleType("sounddevice")
    stub.PortAudioError = OSError
    stub.CallbackStop = type("CallbackStop", (Exception,), {})
    stub.Stream = object
    sys.modules["sounddevice"] = stub

pytest.importorskip("soxr")
pytest.importorskip("livekit")

from anexis.voice.hailmary.approval import answer, spoken_prompt
from anexis.voice.hailmary.attention import Attention, addressed, find_wake
from anexis.voice.hailmary.engine import config
from anexis.voice.hailmary.listen import WINDOW, Segmenter
from anexis.voice.hailmary.tts import SentenceChunker, clean_for_speech
from tests.conftest import make_app
from tests.fakes import call

WAKE = ["jarvis", "j", "jay"]
LEAD = ["hey", "hi", "hello", "ok", "okay", "yo", "um", "uh", "so", "well", "please", "yeah"]


# ---- the pure parts --------------------------------------------------------

def test_the_wake_word_is_found_and_taken_off():
    assert find_wake("Hey Jarvis, what's due this week?", WAKE, LEAD) == (True, "what's due this week?")
    assert find_wake("what's the time, Jarvis?", WAKE, LEAD)[0] is True
    assert find_wake("Jarvas open my notes", WAKE, LEAD) == (True, "open my notes")      # a misheard name still counts
    assert find_wake("I told Jarvis about it yesterday", WAKE, LEAD)[0] is False         # the name in the middle is not a call


def test_requests_and_chatter_are_told_apart_without_a_model():
    assert addressed("what's the weather tomorrow") is True
    assert addressed("honey did you pick up the kids") is False
    assert addressed("the game last night was crazy") is None   # only the judge can tell


async def test_smart_mode_asks_the_judge_and_a_slow_judge_means_no():
    class Judge:
        def __init__(self, said, wait=0.0):
            self.said, self.wait, self.asked = said, wait, 0

        async def complete(self, messages, **_):
            self.asked += 1
            await asyncio.sleep(self.wait)
            return self.said

    settings_cfg = {"attention": {"mode": "smart", "wake_words": WAKE, "lead_ins": LEAD, "follow_up_s": 8, "judge": True,
                                  "judge_timeout_s": 0.2}}
    yes = Attention(settings_cfg, Judge("yes"))
    assert (await yes.decide("the game last night was crazy", [])).directed is True
    slow = Attention(settings_cfg, Judge("yes", wait=1.0))
    assert (await slow.decide("the game last night was crazy", [])).directed is False


def test_spoken_yes_and_no():
    for said in ("yes", "Yeah, do it.", "go ahead", "yes please jarvis", "Sure."):
        assert answer(said) is True, said
    for said in ("no", "Nope.", "don't", "no thanks", "never mind"):
        assert answer(said) is False, said
    assert answer("what's the weather in Paris") is None
    assert spoken_prompt("sir", "run_shell", {"command": "dir"}) == "Sir, I would like to use run shell dir. Shall I proceed?"


def test_replies_are_spoken_sentence_by_sentence():
    chunker = SentenceChunker()
    out = chunker.feed("Your chem lab is due Thursday. ") + chunker.feed("Also, e.g. the essay is due Monday! Done")
    out += chunker.flush()
    assert out == ["Your chem lab is due Thursday.", "Also, e.g. the essay is due Monday!", "Done"]
    assert clean_for_speech("**Bold** and [a link](http://x) and `code`") == "Bold and a link and code"


def test_speech_is_cut_into_turns():
    events = []
    cfg = {"listen": {"vad_threshold": 0.5, "start_windows": 3, "pre_roll_ms": 300, "silence_ms": 300, "max_pause_ms": 1500,
                      "max_utterance_s": 25, "barge_in_ms": 250, "turn_threshold": 0.5}}

    class Vad:
        def reset(self):
            pass

        def __call__(self, chunk):
            return 1.0 if np.abs(chunk).mean() > 0.05 else 0.0

    seg = Segmenter(Vad(), lambda audio: 0.9, cfg, lambda name, audio: events.append((name, None if audio is None else len(audio))))
    speech = np.full(WINDOW * 40, 0.3, np.float32)
    silence = np.zeros(WINDOW * 40, np.float32)
    seg.feed(np.concatenate([silence[: WINDOW * 5], speech, silence]))
    names = [name for name, _ in events]
    assert names == ["speech_start", "speech_sustained", "utterance"]
    assert events[-1][1] > len(speech)                  # the words plus a little before and after


def test_the_microphone_path_cleans_and_resamples_with_the_real_echo_canceller():
    from anexis.voice.hailmary.audio import BLOCK, AudioIO, Player, make_apm

    cfg = config(type("S", (), {"home": __import__("pathlib").Path("/tmp"), "voice_title": "sir", "voice_input": "", "voice_output": "",
                                 "voice_host_api": "Windows WASAPI", "voice_stt_model": "m", "voice_stt_quantization": "fp32",
                                 "voice_attention": "smart", "voice_wake_words": ("jarvis",)})())
    heard = []
    player = Player()
    player.play(np.full(BLOCK * 4, 0.2, np.float32))   # something playing, so the canceller has a reference
    io = AudioIO(cfg, player, heard.append, apm=make_apm(cfg))
    out = np.zeros((BLOCK, 1), np.float32)
    for _ in range(20):
        io.process(np.random.default_rng(1).normal(0, 0.05, (BLOCK, 1)).astype(np.float32), out)
    total = sum(len(h) for h in heard)
    assert abs(total - 20 * BLOCK // 3) <= BLOCK      # 48 kHz in, 16 kHz out
    assert out[:, 0].max() == 0.0                     # what was queued has played


# ---- the whole conversation, with Anexis as the brain ------------------------

class Speaker:
    """Stands in for the speakers: keeps what would have been played."""

    def __init__(self):
        self.played = []

    def play(self, audio):
        self.played.append(len(audio))

    def read(self, n):
        return np.zeros(n, np.float32)

    def pause(self):
        pass

    def resume(self):
        pass

    def clear(self):
        pass

    busy = False
    pending = 0
    paused = False

    async def wait_done(self):
        return None


class Ears:
    """Stands in for the speech model: what it "heard" comes from a list."""

    def __init__(self, *texts):
        self.texts = list(texts)

    def transcribe(self, audio):
        return self.texts.pop(0) if self.texts else ""


class Mouth:
    def __init__(self):
        self.said = []

    def synth(self, text):
        self.said.append(text)
        return np.ones(4800, np.float32)


class NoJudge:
    async def complete(self, *a, **k):
        return "no"


async def started(settings, *script, heard=(), attention="wake"):
    settings.voice_attention = attention
    anexis, _ = make_app(settings, *script)
    seen = []
    anexis.events.publish = seen.append
    mouth, speaker = Mouth(), Speaker()
    ok, _ = anexis.start_wake(engine="hailmary", voice=mouth, stt=Ears(*heard), audio=object(), player=speaker, judge=NoJudge())
    assert ok
    for _ in range(100):
        if anexis.wake.state == "listening":
            break
        await asyncio.sleep(0.02)
    return anexis, seen, mouth, speaker


async def say_into(anexis):
    conv = anexis.wake.conversation
    conv.on_listen("speech_start", None)
    conv.on_listen("utterance", np.zeros(16000, np.float32))


async def until(check, seconds=5.0):
    for _ in range(int(seconds / 0.02)):
        if check():
            return True
        await asyncio.sleep(0.02)
    return False


async def test_jarvis_hears_answers_with_anexis_and_speaks(settings):
    anexis, seen, mouth, speaker = await started(settings, "Nothing is due this week, sir.", heard=["Hey Jarvis, what's due this week?"])
    await say_into(anexis)
    assert await until(lambda: speaker.played)
    assert anexis.router.calls[0]["messages"][-1]["content"] == "what's due this week?"     # the name is taken off
    assert mouth.said == ["Nothing is due this week, sir."]
    assert [m["content"] for m in anexis.memory.history("voice", 5)] == ["what's due this week?", "Nothing is due this week, sir."]
    kinds = [e["type"] for e in seen]
    assert "voice_heard" in kinds and "voice_reply" in kinds
    assert next(e for e in seen if e["type"] == "voice_heard")["directed"] is True
    anexis.stop_wake()


async def test_talk_that_is_not_for_jarvis_is_left_alone(settings):
    anexis, seen, _, speaker = await started(settings, heard=["I think we should leave around six"])
    await say_into(anexis)
    assert await until(lambda: any(e["type"] == "voice_heard" for e in seen))
    await asyncio.sleep(0.1)
    assert anexis.router.calls == [] and speaker.played == []
    assert next(e for e in seen if e["type"] == "voice_heard")["directed"] is False
    anexis.stop_wake()


async def test_a_risky_tool_is_asked_about_out_loud_and_a_spoken_yes_runs_it(settings):
    anexis, _, mouth, _ = await started(
        settings, call("run_shell", command="echo voice > said.txt"), "Done, sir.",
        heard=["Jarvis, make a file", "Jarvis, go ahead"])
    settings.workspace.mkdir(parents=True, exist_ok=True)
    await say_into(anexis)
    assert await until(lambda: any("Shall I proceed" in s for s in mouth.said))
    assert " ".join(mouth.said[:2]) == "Sir, I would like to use run shell echo voice > said.txt. Shall I proceed?"
    await say_into(anexis)   # "Jarvis, go ahead": without the name (a TV, say) it would not count
    assert await until(lambda: "Done, sir." in mouth.said)
    assert (settings.workspace / "said.txt").exists()
    anexis.stop_wake()


async def test_a_heads_up_from_a_check_in_is_said_out_loud(settings):
    import json
    from datetime import datetime

    from anexis.core.initiative import Initiative

    anexis, _, mouth, _ = await started(settings, json.dumps({"action": "say", "text": "Your chem lab is due tomorrow."}))
    settings.autonomy = "ask"
    await Initiative(anexis).check_in(datetime(2026, 11, 18, 12, 0))
    assert await until(lambda: mouth.said == ["Your chem lab is due tomorrow."])
    anexis.stop_wake()


async def test_without_the_packages_it_says_what_to_install(settings, monkeypatch):
    from anexis.voice.hailmary import engine

    anexis, _ = make_app(settings)
    monkeypatch.setattr(engine, "_installed", lambda name: name != "livekit")
    ok, why = anexis.start_wake(engine="hailmary")
    assert not ok and "livekit" in why and "Setup" in why


async def test_an_answer_without_the_name_does_not_approve(settings):
    anexis, _, mouth, _ = await started(
        settings, call("run_shell", command="echo nope > nope.txt"), "ok", heard=["Jarvis, make a file", "go ahead"])
    settings.workspace.mkdir(parents=True, exist_ok=True)
    await say_into(anexis)
    assert await until(lambda: any("Shall I proceed" in s for s in mouth.said))
    await say_into(anexis)   # "go ahead" without the name
    await asyncio.sleep(0.3)
    assert not (settings.workspace / "nope.txt").exists()
    anexis.stop_wake()


async def test_voice_levels_reach_the_deck_ten_times_a_second():
    import asyncio

    from anexis.voice.hailmary.bus import Bus

    got: list[dict] = []
    bus = Bus()
    bus.bind(asyncio.get_running_loop(), got.append)
    for _ in range(5):  # twenty a second from the audio thread, all at once here
        bus.publish("levels", mic=0.123456789, out=0.0)
    bus.publish("state", value="listening")
    assert [e["type"] for e in got] == ["voice_levels", "voice_state"]
    assert got[0]["mic"] == 0.12346
