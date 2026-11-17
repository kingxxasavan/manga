// Starts the deck and wires the panels together. Each panel lives in its own
// file next to this one; this file only connects them.

import * as activity from "./activity.js";
import * as api from "./api.js";
import * as chat from "./chat.js";
import { $, $$, h, toast } from "./dom.js";
import * as files from "./files.js";
import * as memory from "./memory.js";
import * as overlays from "./overlays.js";
import { openSetup } from "./setup.js";
import { initStats } from "./stats.js";
import * as terminal from "./terminal.js";
import * as tools from "./tools.js";
import * as voice from "./voice.js";

const root = document.documentElement, deck = $("#deck");
const THEMES = ["ion", "ember", "verdant", "ultra"];
let control = "", name = "Anexis", reloadWaiting = false, linkDown = false;

// ---- look ----------------------------------------------------------------
function setTheme(value) {
  if (!THEMES.includes(value)) return false;
  root.dataset.theme = value;
  localStorage.setItem("anexis-theme", value);
  terminal.retheme();
  return true;
}
function setFx(on) {
  root.dataset.fx = on ? "on" : "off";
  localStorage.setItem("anexis-fx", root.dataset.fx);
}
setTheme(localStorage.getItem("anexis-theme") || "ion");
setFx(localStorage.getItem("anexis-fx") !== "off");

// ---- which panel is showing ----------------------------------------------
function show(panel) {
  if (["chat", "terminal"].includes(panel)) deck.dataset.center = panel;
  if (["memory", "tools"].includes(panel)) deck.dataset.right = panel;
  deck.dataset.view = panel;
  for (const tab of $$("[data-center]", $(".p-center .tabs"))) tab.setAttribute("aria-selected", String(tab.dataset.center === deck.dataset.center));
  for (const tab of $$("[data-right]", $(".p-right .tabs"))) tab.setAttribute("aria-selected", String(tab.dataset.right === deck.dataset.right));
  for (const button of $$(".views button")) button.setAttribute("aria-current", String(button.dataset.view === panel));
  if (deck.dataset.center === "terminal" && panel !== "memory" && panel !== "tools") terminal.showTerminal();
  $("#center-meta").textContent = deck.dataset.center === "chat" ? "Enter sends · Shift+Enter new line · Esc stops" : "a real shell on this computer";
}
function terminalAt(folder, run = "") {
  show("terminal");
  terminal.openShell({ cwd: folder, run });
}

// ---- top bar -------------------------------------------------------------
function banner(text, kind = "", action = null) {
  const el = $("#banner");
  if (!text) { el.hidden = true; return; }
  el.className = `banner ${kind}`;
  el.replaceChildren(h("span.grow", text), action);
  el.hidden = false;
}

function showControl(value) {
  control = value;
  const pill = $("#control");
  pill.dataset.control = value;
  pill.lastElementChild.textContent = value === "full" ? "full control" : "ask first";
}

async function setControl(value) {
  try {
    showControl((await api.post("/settings", { control: value })).control);
    toast(value === "full" ? "Full control is on. Tools run without asking." : "Ask first is on. Risky tools wait for your yes.");
  } catch (e) {
    toast(e.message, "bad");
  }
}

function controlSheet() {
  if (control === "full") return setControl("ask");
  overlays.openSheet("Full control", [
    h("p", h("b", "Let Anexis act without asking?"), " It will run commands, open and close apps, change files anywhere, and use the keyboard and mouse the moment it decides to."),
    h("p", "Every action shows in the Activity panel as it happens. STOP, or the Esc key, ends whatever is running. Pushing the mouse into a screen corner stops mouse and keyboard control."),
    h("div.sheet-foot",
      h("button.btn.ghost", { type: "button", onclick: () => overlays.closeSheet() }, "Keep asking"),
      h("button.btn.primary", { type: "button", onclick: () => { overlays.closeSheet(); setControl("full"); } }, "Turn on full control")),
  ]);
}

function showName(value) {
  name = value;
  $("#brand-name").textContent = value.toUpperCase();
  document.title = value;
  chat.setName(value);
}

async function pulse() {
  let health;
  try {
    health = await api.get("/health");
  } catch (e) {
    if (e.status === 401) overlays.openLock(start);
    return null;
  }
  if (health.name !== name) showName(health.name);
  if (health.control !== control) showControl(health.control);
  const model = $("#st-model");
  const sources = health.providers || [];
  model.className = `stat ${sources.length ? "ok" : "bad"}`;
  model.lastElementChild.textContent = sources.length ? sources.join(" → ") : "none set up";
  $("#st-memory").lastElementChild.textContent = health.memories;
  const starting = health.tool_servers_starting?.length;
  $("#st-tools").lastElementChild.textContent = `${health.tools}${starting ? ` (${starting} servers starting)` : ""}`;
  tools.setDue(health.due || []);
  return health;
}

// ---- live events ---------------------------------------------------------
function reloadDeck(changed) {
  if (changed.length && changed.every((f) => f.endsWith(".css"))) {
    for (const link of $$('link[rel="stylesheet"]')) {
      const url = new URL(link.href);
      url.searchParams.set("v", Date.now());
      link.href = url;
    }
    return toast("Styles updated.");
  }
  if (chat.state.busy) {  // reloading now would cut the reply off
    if (!reloadWaiting) toast("The screen changed. It reloads when Anexis finishes.");
    reloadWaiting = true;
    return;
  }
  location.reload();
}

function onEvent(event) {
  if (event.type === "activity") activity.add(event);
  else if (event.type === "reload") reloadDeck(event.files || []);
  else if (event.type === "settings") { showControl(event.control); showName(event.name); }
  else if (event.type === "brain_restarting") toast(`Code changed (${event.files.join(", ")}). Restarting the brain.`);
  else if (event.type === "brain_error") {
    const first = event.errors[0];
    banner(`Not restarting: ${first.file} line ${first.line} has a mistake (${first.message}). The brain that works keeps running until the file is fixed.`,
      "bad", h("button", { type: "button", onclick: () => banner("") }, "hide"));
  }
}

function onLink(up) {
  if (up === "locked") return overlays.openLock(start);
  if (!up) {
    linkDown = true;
    banner("The brain is restarting. Reconnecting by itself...");
  } else if (linkDown) {
    linkDown = false;
    banner("");
    pulse();
    memory.refresh();
    tools.refresh();
    files.show();
  }
}

// ---- boot sequence -------------------------------------------------------
async function boot(health) {
  if (sessionStorage.getItem("anexis-booted") || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  sessionStorage.setItem("anexis-booted", "1");
  const el = $("#boot"), lines = $("#boot-lines");
  $("#boot-name").textContent = (health?.name || name).toUpperCase();
  el.hidden = false;
  let skipped = false;
  const skip = () => { skipped = true; };
  addEventListener("keydown", skip, { once: true });
  el.addEventListener("pointerdown", skip, { once: true });
  const rows = health ? [
    ["link to the brain", "ok", "ok"],
    ["model source", health.providers.length ? health.providers.join(", ") : "none yet", health.providers.length ? "ok" : "warn"],
    ["memory", `${health.memories} things remembered`, "ok"],
    ["tools", `${health.tools} ready`, "ok"],
    ["control", health.control === "full" ? "full" : "ask first", health.control === "full" ? "warn" : "ok"],
  ] : [["link to the brain", "waiting", "warn"]];
  for (const [label, value, kind] of rows) {
    if (skipped) break;
    lines.append(h(`li.${kind}`, h("span", label), h("b", value)));
    await new Promise((r) => setTimeout(r, 150));
  }
  if (!skipped) await new Promise((r) => setTimeout(r, 450));
  removeEventListener("keydown", skip);
  el.classList.add("leaving");
  await new Promise((r) => setTimeout(r, 420));  // let it fade before anything opens on top
  el.hidden = true;
}

// ---- start ---------------------------------------------------------------
let started = false;
async function start() {
  const health = await pulse();
  if (!health || started) return;
  started = true;
  const booting = boot(health);

  overlays.initSheet();
  const open = (which) => ({
    setup: openSetup, keys: overlays.openKeys, doctor: overlays.openDoctor, about: overlays.openAbout,
    app: () => overlays.openApp({ setTheme, setFx, terminalAt, onName: showName }),
  })[which]?.();

  chat.initChat({
    name: health.name,
    open,
    onBusy: (busy) => { if (!busy && reloadWaiting) location.reload(); },
    onDone: (event, said) => {
      memory.markUsed((event.memories_used || []).map((m) => m.id));
      pulse();
      voice.speak(said);
    },
    remember: memory.remember,
    forget: memory.remove,
    searchMemory: (words) => { show("memory"); memory.search(words); },
    why: () => { show("memory"); chat.note("The memories that shaped the last reply are marked in the Memory panel."); },
    showTools: () => show("tools"),
    setControl,
    setTheme: (value) => setTheme(value) && chat.note(`Theme is now **${value}**.`),
    toggleVoice: () => { voice.setReadAloud(!voice.readAloud); chat.note(`Reading replies out loud is **${voice.readAloud ? "on" : "off"}**.`); },
  });
  initStats();
  terminal.initTerminal();
  memory.initMemory();
  tools.initTools();
  activity.initActivity();
  files.initFiles({ terminalAt });
  api.follow(onEvent, onLink);
  setInterval(() => !document.hidden && pulse(), 4000);

  $("#control").addEventListener("click", controlSheet);
  $("#mic").addEventListener("click", () => voice.toggleMic((text) => chat.send(text)));
  for (const button of $$("[data-open]")) button.addEventListener("click", () => open(button.dataset.open));
  for (const tab of $$(".tabs [data-center]")) tab.addEventListener("click", () => show(tab.dataset.center));
  for (const tab of $$(".tabs [data-right]")) tab.addEventListener("click", () => show(tab.dataset.right));
  for (const button of $$(".views button")) button.addEventListener("click", () => show(button.dataset.view));
  addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (overlays.sheetOpen()) overlays.closeSheet();
    else if (chat.state.busy) chat.stop();
    voice.hush();
  });
  show("chat");

  await booting;
  // A brand new install opens setup by itself. After that it is behind the Setup button.
  try {
    if (!(await api.get("/setup")).done && !overlays.sheetOpen()) openSetup();
  } catch { /* setup stays one click away */ }
  $("#input").focus();
}

function tick() {
  $("#clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}
tick();
setInterval(tick, 5000);

start().then(() => {
  if (!started) {  // the brain is not up yet: keep knocking
    banner("Waiting for the brain to start...");
    const knock = setInterval(async () => {
      await start();
      if (started) { clearInterval(knock); banner(""); }
    }, 1000);
  }
});
