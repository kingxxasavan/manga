"""JARVIS voice, from the owner's Hail Mary project.

Hail Mary's own files, with only their imports pointed at Anexis:
    audio.py         microphone and speakers through WASAPI, echo cancellation and
                     noise suppression (LiveKit), resampled to 16 kHz
    listen.py        Silero VAD splits speech, Smart Turn v3 decides when you are done
    stt.py           speech to text, nemo-parakeet through onnx-asr (GPU, or CPU)
    tts.py           the jarvis-high Piper voice, said sentence by sentence
    attention.py     wake words ("jarvis") and "is this for me", with a judge model
    conversation.py  ties it together: barge in, echo filtering, spoken approvals
    judge.md         the judge's instructions

Written for Anexis, because Hail Mary's versions were not part of the voice code:
    bus.py, runtime.py, approval.py   the small helpers those files import
    brain.py                          Hail Mary's brain, played by Anexis's chat loop
    engine.py                         starts and stops it all inside Anexis
    models.py                         downloads the models, as Hail Mary's setup did
"""
