// The JARVIS voice screen: black, with one circle in the middle. It is the
// main screen: the app opens on it, and saying "Jarvis" brings it back.
//
// The circle stays dark while nobody is talking. While JARVIS waits for its
// name it glows a little with any voice it hears, so you can see the
// microphone works. Once you talk to it, it lights up blue with your voice,
// and with its own voice while it answers. While it thinks the ring breathes.
//
// Under the circle it always says the truth about the voice: not set up yet,
// off, waking up, failed (and why), or listening, with a button that fixes it.

import * as api from "./api.js";
import { h, toast } from "./dom.js";

const BACK_AFTER_MS = 20_000;   // opened by "Jarvis": quiet this long and the deck comes back
const WORDS = { idle: 'say "Jarvis"', listening: "listening", thinking: "thinking", speaking: "speaking" };
const HEARD_WHILE_WAITING = 0.3;  // how much any voice lights it before it is talked to

let root, glow, ring, status, note, action, you, him, ask;
let state = "idle", pinned = false, backTimer = 0;
let voice = null;          // GET /voice/wake: is the voice set up, on, running, failed
let installing = "", failure = "";
let target = 0, shown = 0, frame = 0, simpleTimer = 0;

/** Loudness (RMS of -1..1 audio) to 0..1, on a dB scale so quiet voices still show. */
function level(rms) {
  if (!(rms > 0)) return 0;
  const db = 20 * Math.log10(rms);
  return Math.min(1, Math.max(0, (db + 52) / 36));   // -52 dB is silence, -16 dB is loud
}

function build() {
  glow = h("div.orb-glow", { "aria-hidden": "true" });
  ring = h("div.orb-ring", h("span.orb-name", "JARVIS"));
  status = h("div.orb-status", { "aria-live": "polite" });
  note = h("p.orb-note");
  action = h("div.orb-action");
  you = h("p.orb-you");
  him = h("p.orb-him");
  ask = h("div.orb-ask", { hidden: true });
  root = h("div.orb", { id: "orb", hidden: true, role: "region", "aria-label": "JARVIS voice" },
    h("button.orb-back", { type: "button", title: "Back to the deck (Esc)", onclick: () => close() }, "deck"),
    h("div.orb-stage", glow, ring),
    status, note, action, h("div.orb-lines", you, him), ask);
  document.body.append(root);
}

/** Where the voice is at, worked out from /voice/wake. */
function phase() {
  if (installing) return "setup-running";
  if (!voice) return "unknown";
  if (!voice.available) return "setup";
  if (voice.state === "failed" || voice.error) return "failed";
  if (!voice.on || voice.state === "off") return "off";
  if (voice.state === "starting") return "starting";
  return "ready";
}

function button(label, run) {
  return h("button", { type: "button", onclick: async (e) => { e.currentTarget.disabled = true; await run(); } }, label);
}

function paint() {
  if (!root) return;
  const now = phase();
  root.dataset.phase = now;
  root.dataset.state = now === "ready" ? state : now === "starting" || now === "setup-running" ? "thinking" : "idle";
  let words = WORDS[state] || state, said = "", fix = null;
  if (now === "unknown") { words = "connecting"; said = "Waiting for the brain to answer."; }
  else if (now === "setup") { words = "voice not set up"; said = failure || voice.why; fix = button("set up voice", install); }
  else if (now === "setup-running") { words = "setting up the voice"; said = installing; }
  else if (now === "failed") { words = "voice failed"; said = failure || voice.error; fix = button("try again", turnOn); }
  else if (now === "off") { words = "voice is off"; said = failure || "Turn it on and JARVIS listens for its name, even with the window hidden."; fix = button("turn on", turnOn); }
  else if (now === "starting") { words = "waking up"; said = "Loading the voice. The first time takes a minute."; }
  else if (voice.engine === "simple" && state === "idle") { words = `say "${voice.word}"`; said = "The simple voice. Open Setup and tick Voice for the full JARVIS voice."; }
  status.textContent = words;
  note.textContent = said || "";
  action.replaceChildren(...(fix ? [fix] : []));
  if (now !== "ready" || state === "thinking") target = 0;
  wake();
}

export async function refresh() {
  try { voice = await api.get("/voice/wake"); } catch { voice = null; }
  paint();
}

async function turnOn() {
  failure = "";
  try { voice = await api.post("/voice/wake", { on: true }); } catch (e) { failure = e.message; }
  paint();
}

/** Installs the JARVIS voice right here, the same step Setup runs. */
async function install() {
  failure = "";
  installing = "starting the download";
  paint();
  let ok = false;
  try {
    await api.stream("POST", "/setup/install", { voice: true }, (event) => {
      if (event.step !== "voice") return;
      if (event.state === "done") ok = true;
      if (event.state === "failed") failure = event.message;
      else if (event.line || event.message) installing = event.line || event.message;
      paint();
    });
  } catch (e) { failure = e.message; }
  installing = "";
  await refresh();
  if (ok) await turnOn();
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
  if (!frame && root && !root.hidden && (shown || target)) frame = requestAnimationFrame(tick);
}

function backLater() {
  clearTimeout(backTimer);
  if (!pinned && state === "idle") backTimer = setTimeout(() => close(), BACK_AFTER_MS);
}

function setState(value) {
  const next = value || "idle";
  if (next !== state) target = 0;  // the next level that comes in lights it for the new state
  state = next;
  paint();
  backLater();
}

export const isOpen = () => Boolean(root && !root.hidden);

/** Shows the voice screen. `stay` keeps it up until closed by hand. */
export function open(stay = false) {
  if (!root) build();
  pinned = pinned || stay;
  const was = root.hidden;
  root.hidden = false;
  paint();
  if (was) refresh();
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

// The simple voice says less: it woke, it heard, it answered. Light it by that.
function simple(event) {
  clearTimeout(simpleTimer);
  if (event.type === "wake") { setState("listening"); target = 0.7; }
  else if (event.type === "voice_heard") setState("thinking");
  else if (event.type === "voice_reply") {
    setState("speaking"); target = 0.7;
    simpleTimer = setTimeout(() => { target = 0; setState("idle"); }, 4000);
  }
  wake();
}

/** Every voice event goes through here. */
export function onEvent(event) {
  if (!root) build();
  switch (event.type) {
    case "wake":
      open();
      if (voice?.engine === "simple") simple(event);
      break;
    case "wake_listening":
    case "wake_failed":
    case "voice_error":
      if (event.error || event.message) failure = event.error || event.message;
      if (event.type === "wake_listening") failure = "";
      refresh();
      break;
    case "voice_state":
      if (event.value && event.value !== "idle") open();
      setState(event.value);
      break;
    case "voice_levels":
      if (phase() !== "ready") break;
      target = state === "listening" ? level(event.mic)
        : state === "speaking" ? level(event.out)
        : state === "idle" ? level(event.mic) * HEARD_WHILE_WAITING : 0;
      wake();
      break;
    case "voice_user":
      you.textContent = event.text || "";
      him.textContent = "";
      break;
    case "voice_heard":
      if (event.directed && event.text) { you.textContent = event.text; him.textContent = ""; }
      if (voice?.engine === "simple") { you.textContent = event.text || ""; him.textContent = ""; simple(event); }
      break;
    case "voice_assistant_delta":
      him.textContent += event.text || "";
      break;
    case "voice_reply":
      if (event.text) him.textContent = event.text;
      if (voice?.engine === "simple") simple(event);
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
