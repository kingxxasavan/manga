#!/usr/bin/env python3
"""Pretends to be the `piper` program: reads text on stdin, writes a short WAV to -f."""
import struct
import sys
import wave

args = sys.argv[1:]
out = args[args.index("-f") + 1]
text = sys.stdin.read()
with open(out + ".txt", "w") as f:
    f.write(text)
with wave.open(out, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    w.writeframes(struct.pack("<h", 0) * 160)
