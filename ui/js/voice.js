// Voice: talk instead of typing, and have replies read out loud. Both run on
// this machine (Whisper and Piper), so no audio leaves it.

import * as api from "./api.js";
import { $, toast } from "./dom.js";

let recorder = null, chunks = [], speaking = null;
export let readAloud = localStorage.getItem("anexis-voice") === "on";

/** Whisper wants a plain WAV file: one channel, 16 kHz, 16 bit. */
async function toWav(blob) {
  const context = new AudioContext();
  const audio = await context.decodeAudioData(await blob.arrayBuffer());
  context.close();
  const rate = 16000, length = Math.ceil(audio.duration * rate);
  const offline = new OfflineAudioContext(1, length, rate);
  const source = offline.createBufferSource();
  source.buffer = audio;
  source.connect(offline.destination);
  source.start();
  const samples = (await offline.startRendering()).getChannelData(0);
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const text = (at, s) => [...s].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  text(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); text(8, "WAVEfmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, "data"); view.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return view.buffer;
}

/** First press starts listening, second press stops and returns what was said. */
export async function toggleMic(onText) {
  const mic = $("#mic");
  if (recorder) { recorder.stop(); return; }
  let media;
  try {
    media = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    return toast("No microphone, or it was not allowed. Check the Windows sound and privacy settings.", "bad");
  }
  chunks = [];
  recorder = new MediaRecorder(media);
  recorder.ondataavailable = (e) => chunks.push(e.data);
  recorder.onstop = async () => {
    media.getTracks().forEach((t) => t.stop());
    const blob = new Blob(chunks, { type: recorder.mimeType });
    recorder = null;
    mic.dataset.state = "working";
    try {
      const { text } = await api.postRaw("/voice/transcribe", await toWav(blob));
      if (text.trim()) onText(text.trim()); else toast("Did not catch that.");
    } catch (e) {
      toast(e.status === 503 ? `${e.message} Or open Setup and tick voice.` : e.message || "Could not understand the recording.", "bad");
    }
    delete mic.dataset.state;
  };
  recorder.start();
  mic.dataset.state = "recording";
}

export async function speak(text) {
  if (!readAloud || !text.trim()) return;
  try {
    const wav = await api.postForBlob("/voice/speak", { text });
    speaking?.pause();
    speaking = new Audio(URL.createObjectURL(wav));
    speaking.onended = () => URL.revokeObjectURL(speaking.src);
    await speaking.play();
  } catch (e) {
    if (e.status === 503) {
      setReadAloud(false);
      toast(`${e.message} Reading aloud is off again.`, "bad");
    }
  }
}

export function hush() {
  speaking?.pause();
}

export function setReadAloud(on) {
  readAloud = on;
  localStorage.setItem("anexis-voice", on ? "on" : "off");
  if (!on) hush();
}
