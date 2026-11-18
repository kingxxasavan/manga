// The JARVIS voice screen: black, with one circle in the middle.
//
// It takes over the window when you say "Jarvis" and goes back to the deck
// after a while of quiet (or on Esc, or the "deck" button). The circle stays
// dark while nobody is talking. It lights up blue with your voice while
// JARVIS is listening to you, and with JARVIS's own voice while it speaks.
// While it thinks the ring breathes softly.

import * as api from "./api.js";
import { h, toast } from "./dom.js";

const BACK_AFTER_MS = 20_000;   // quiet this long and the deck comes back
const WORDS = { idle: 'say "Jarvis"', listening: "listening", thinking: "thinking", speaking: "speaking" };

let root, glow, ring, status, you, him, ask;
let state = "idle", pinned = false, backTimer = 0;
let target = 0, shown = 0, frame = 0;

/** Loudness (RMS of -1..1 audio) to 0..1, on a dB scale so quiet voices still show. */
function level(rms) {
  if (!(rms > 0)) return 0;
  const db = 20 * Math.log10(rms);
  return Math.min(1, Math.max(0, (db + 52) / 36));   // -52 dB is silence, -16 dB is loud
}

function build() {
  glow = h("div.orb-glow", { "aria-hidden": "true" });
  ring = h("div.orb-ring", h("span.orb-name", "JARVIS"));
  status = h("div.orb-status", { "aria-live": "polite" }, WORDS.idle);
  you = h("p.orb-you");
  him = h("p.orb-him");
  ask = h("div.orb-ask", { hidden: true });
  root = h("div.orb", { id: "orb", hidden: true, role: "dialog", "aria-label": "JARVIS voice" },
    h("button.orb-back", { type: "button", title: "Back to the deck (Esc)", onclick: () => close() }, "deck"),
    h("div.orb-stage", glow, ring),
    status, h("div.orb-lines", you, him), ask);
  document.body.append(root);
}

function paint() {
  root.dataset.state = state;
  status.textContent = WORDS[state] || state;
  if (state === "idle" || state === "thinking") target = 0;
}

// The glow follows the voice. Levels come in about ten times a second, so
// each frame eases toward the newest one; transform and opacity only.
function tick() {
  shown += (target - shown) * 0.25;
  if (Math.abs(target - shown) < 0.002) shown = target;
  glow.style.opacity = String(shown);
  glow.style.transform = `scale(${(0.92 + shown * 0.22).toFixed(3)})`;
  ring.style.setProperty("--lit", shown.toFixed(3));
  frame = shown || target ? requestAnimationFrame(tick) : 0;
}

function wake() {
  if (!frame && !root.hidden) frame = requestAnimationFrame(tick);
}

function backLater() {
  clearTimeout(backTimer);
  if (!pinned && state === "idle") backTimer = setTimeout(() => close(), BACK_AFTER_MS);
}

export const isOpen = () => root && !root.hidden;

/** Shows the voice screen. `stay` keeps it up until closed by hand. */
export function open(stay = false) {
  if (!root) build();
  pinned = pinned || stay;
  root.hidden = false;
  paint();
  backLater();
}

export function close() {
  if (!root) return;
  clearTimeout(backTimer);
  pinned = false;
  root.hidden = true;
  target = shown = 0;
  if (frame) cancelAnimationFrame(frame);
  frame = 0;
}

/** Every voice event goes through here. Returns nothing; draws if open. */
export function onEvent(event) {
  if (!root) build();
  switch (event.type) {
    case "wake":
      open();
      break;
    case "voice_state":
      state = event.value || "idle";
      if (state !== "idle") open();
      paint();
      backLater();
      break;
    case "voice_levels": {
      // Your voice lights it while it listens to you; its own voice while it speaks.
      const now = state === "listening" ? level(event.mic) : state === "speaking" ? level(event.out) : 0;
      target = now;
      wake();
      break;
    }
    case "voice_user":
      you.textContent = event.text || "";
      him.textContent = "";
      break;
    case "voice_heard":
      if (event.directed && event.text) { you.textContent = event.text; him.textContent = ""; }
      break;
    case "voice_assistant_delta":
      him.textContent += event.text || "";
      break;
    case "voice_reply":
      if (event.text) him.textContent = event.text;
      break;
    case "voice_approval":
      open();
      askAbout(event);
      break;
    case "voice_approval_done":
      ask.hidden = true;
      ask.replaceChildren();
      break;
  }
}

function askAbout(event) {
  const answer = async (approved) => {
    ask.hidden = true;
    try { await api.post("/voice/approval", { id: event.id, approved }); } catch (e) { toast(e.message, "bad"); }
  };
  ask.replaceChildren(
    h("span", `May I use ${(event.tool || "a tool").replace(/_/g, " ")}? Say "Jarvis, go ahead" or "Jarvis, cancel".`),
    h("span.orb-ask-buttons",
      h("button", { type: "button", onclick: () => answer(true) }, "go ahead"),
      h("button", { type: "button", onclick: () => answer(false) }, "cancel")));
  ask.hidden = false;
}
