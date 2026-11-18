import asyncio
import threading

import numpy as np

from anexis.voice.wake import FRAME, RATE, record_utterance, to_wav
from tests.conftest import make_app

WAKE = 12345  # a pretend frame that the pretend detector hears as "hey jarvis"


def quiet(n):
    return [np.zeros(FRAME, dtype=np.int16) for _ in range(n)]


def talk(n):
    return [(np.sin(np.arange(FRAME) / 3) * 3000).astype(np.int16) for _ in range(n)]


def wake_frame():
    frame = np.zeros(FRAME, dtype=np.int16)
    frame[0] = WAKE
    return frame


class PretendEars:
    """A microphone that plays a script of frames, then stays quiet."""

    def __init__(self, script):
        self.script = script
        self.closed = False

    def frames(self, stop: threading.Event):
        yield from self.script
        while not stop.is_set():
            stop.wait(0.05)
            yield np.zeros(FRAME, dtype=np.int16)

    def close(self):
        self.closed = True


def detector(frame):
    return 1.0 if frame[0] == WAKE else 0.0


def test_recording_stops_after_the_speaker_goes_quiet():
    audio = record_utterance(iter(quiet(3) + talk(20) + quiet(30) + talk(50)))
    seconds = audio.size / RATE
    assert 2.8 < seconds < 3.3          # 0.24 s quiet, 1.6 s talking, 1.2 s of quiet; never the later talking


def test_recording_gives_up_when_nobody_talks():
    assert record_utterance(iter(quiet(200))).size / RATE <= 6.1


def test_wav_is_16khz_mono():
    import io
    import wave

    with wave.open(io.BytesIO(to_wav(np.zeros(RATE, dtype=np.int16)))) as w:
        assert (w.getframerate(), w.getnchannels(), w.getnframes()) == (RATE, 1, RATE)


async def test_hey_jarvis_then_a_question_gets_a_spoken_answer(settings):
    anexis, _ = make_app(settings, "Nothing is due this week.")
    seen = []
    anexis.events.publish = seen.append
    played, heard_audio = [], []

    def transcribe(wav):
        heard_audio.append(len(wav))
        return "whats due this week"

    async def speak(text):
        return b"RIFF-pretend-" + text.encode()

    ears = PretendEars([*quiet(5), wake_frame(), *quiet(2), *talk(15), *quiet(20)])
    ok, _ = anexis.start_wake(ears=ears, detector=detector, transcribe=transcribe, speak=speak, play=played.append)
    assert ok
    for _ in range(200):
        if played:
            break
        await asyncio.sleep(0.05)
    anexis.stop_wake()
    assert played == [b"RIFF-pretend-Nothing is due this week."]
    kinds = [e["type"] for e in seen]
    assert kinds[:4] == ["wake_listening", "wake", "voice_heard", "voice_reply"]
    assert {"type": "voice_heard", "text": "whats due this week"} in seen
    assert [m["content"] for m in anexis.memory.history("voice", 10)] == ["whats due this week", "Nothing is due this week."]
    assert ears.closed and heard_audio[0] > 10000


async def test_no_wake_word_means_nothing_happens(settings):
    anexis, _ = make_app(settings)
    seen = []
    anexis.events.publish = seen.append
    anexis.start_wake(ears=PretendEars(talk(30)), detector=detector, transcribe=lambda w: "x", speak=None, play=print)
    await asyncio.sleep(0.4)
    anexis.stop_wake()
    assert [e["type"] for e in seen] == ["wake_listening"]
    assert anexis.router.calls == []


async def test_a_missing_microphone_is_reported_not_crashed(settings, monkeypatch):
    from anexis.voice import wake

    anexis, _ = make_app(settings)
    seen = []
    anexis.events.publish = seen.append

    def no_microphone():
        raise OSError("no input device")

    monkeypatch.setattr(wake, "Ears", no_microphone)
    anexis.start_wake(detector=detector, transcribe=lambda w: "", speak=None, play=print)
    for _ in range(40):
        if anexis.wake.state == "failed":
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.05)  # the note about it is passed back to the main loop a moment later
    assert anexis.wake.state == "failed"
    assert seen[-1]["type"] == "wake_failed" and "no input device" in seen[-1]["error"]
    anexis.stop_wake()


async def test_the_switch_says_why_it_cannot_turn_on(live, monkeypatch):
    import httpx

    from anexis.voice import wake

    monkeypatch.setattr(wake, "can_wake", lambda: (False, "Not installed: openwakeword. Open Setup and tick Voice."))
    anexis, client = await live()
    anexis.settings.voice_engine = "simple"  # this test is about the simple engine
    async with httpx.AsyncClient(base_url=client.url) as http:
        state = (await http.get("/voice/wake")).json()
        assert state["on"] is False and state["word"] == "hey jarvis"
        refused = await http.post("/voice/wake", json={"on": True})
        assert refused.status_code == 400 and "openwakeword" in refused.json()["detail"]
