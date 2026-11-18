// Starts the deck and wires the panels together. Each panel lives in its own
// file next to this one; this file only connects them.

import * as activity from "./activity.js";
import * as api from "./api.js";
import * as chat from "./chat.js";
import { $, $$, h, notify, showWindow, toast } from "./dom.js";
import * as files from "./files.js";
import { initKeyboard } from "./keyboard.js";
import * as memory from "./memory.js";
import * as overlays from "./overlays.js";
import { openSetup } from "./setup.js";
import { initStats } from "./stats.js";
import * as terminal from "./terminal.js";
import * as tools from "./tools.js";
import * as voice from "./voice.js";

const root = document.documentElement, deck = $("#deck");
const THEMES = ["tron", "ion", "ember", "verdant", "ultra"];
const CENTER = ["chat", "terminal", "memory", "tools"];
let control = "", name = "Anexis", reloadWaiting = false, linkDown = false, claude = null, due = [];

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
setTheme(localStorage.getItem("anexis-theme") || "tron");
setFx(localStorage.getItem("anexis-fx") !== "off");

// ---- which panel is showing ----------------------------------------------
function show(panel) {
  if (CENTER.includes(panel)) deck.dataset.center = panel;
  deck.dataset.view = panel;
  for (const tab of $$(".tabs [data-center]")) tab.setAttribute("aria-selected", String(tab.dataset.center === deck.dataset.center));
  for (const button of $$(".views button")) button.setAttribute("aria-current", String(button.dataset.view === panel));
  if (panel === "terminal") terminal.showTerminal();
  $("#center-meta").textContent = {
    chat: "Enter sends · Shift+Enter new line · Esc stops", terminal: "a real shell on this computer",
    memory: "what it knows about you", tools: "everything it can use",
  }[deck.dataset.center];
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
  $("#brain > h3 b").textContent = value;
  document.title = value;
  chat.setName(value);
}

// ---- the status block in the right column --------------------------------
let health = null;
function drawBrain() {
  if (!health) return;
  const rows = [];
  const sources = health.providers || [];
  const first = sources[0], model = first ? (health.chat_models?.[first] || "no chat model") : "";
  rows.push(h("div.brain-row", h("span", "model"),
    sources.length ? h("b", { title: sources.map((s) => `${s}: ${health.chat_models?.[s] || "?"}`).join("\n") }, `${first} · ${model}`)
                   : h("button", { type: "button", onclick: () => open("models") }, "none set up. Pick one")));
  if (claude?.installed) {
    if (!claude.signed_in) {
      rows.push(h("div.brain-row", h("span", "claude"), h("button", { type: "button", onclick: () => open("keys") }, "not signed in. Sign in")));
    } else if (claude.usage) {
      const used = claude.usage.percent, bar = h("div.bar", h("i"));
      bar.firstChild.style.transform = `scaleX(${Math.min(1, used / 100)})`;
      bar.classList.toggle("hot", used >= claude.switch_percent);
      rows.push(h("div.brain-row", h("span", "claude"),
        h(`b${used >= claude.switch_percent ? ".warn" : ""}`, { title: claude.note || `Switches to ${claude.switch_model} at ${claude.switch_percent}%` },
          `plan ${used.toFixed(0)}% used · codes on ${claude.model}`), bar));
    } else {
      rows.push(h("div.brain-row", h("span", "claude"), h("b", claude.plan ? "signed in with your plan" : "signed in with a key")));
    }
  }
  rows.push(h("div.brain-row", h("span", "due"), due.length ? h("b.warn", `${due.length} in the next 2 days`) : h("b", "nothing in the next 2 days")));
  for (const line of due.slice(0, 3)) rows.push(h("div.due-line", { title: line }, line));
  $("#brain-body").replaceChildren(...rows);
  $("#brain-sub").textContent = health.busy?.length ? "working" : "idle";
}

/** Tells the owner about work that is due, once a day per item, as a toast
 *  and (when Windows allows it) as a desktop notification. */
function remind(lines) {
  const today = new Date().toDateString();
  let told = {};
  try { told = JSON.parse(localStorage.getItem("anexis-reminded") || "{}"); } catch { told = {}; }
  const fresh = lines.filter((line) => told[line] !== today);
  if (!fresh.length) return;
  for (const line of fresh) told[line] = today;
  localStorage.setItem("anexis-reminded", JSON.stringify(Object.fromEntries(Object.entries(told).filter(([, day]) => day === today))));
  const text = fresh.length === 1 ? `Due soon: ${fresh[0]}` : `${fresh.length} things are due soon. The first: ${fresh[0]}`;
  toast(text);
  notify(`${name}: due soon`, fresh.join("\n"));
}

async function pulse() {
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
  due = health.due || [];
  tools.setDue(due);
  remind(due);
  drawBrain();
  return health;
}

async function pulseClaude() {
  try {
    claude = await api.get("/claude");
    drawBrain();
  } catch { /* shown again on the next round */ }
}

/** A model that was retired stops Anexis from answering at all, so it is
 *  checked on every start and pointed out loudly. */
async function checkModels() {
  let state;
  try { state = await api.get("/models"); } catch { return; }
  const on = state.providers.filter((p) => p.enabled && p.has_key);
  const gone = on.filter((p) => p.reachable && p.models.chat && p.missing.includes(p.models.chat));
  const none = on.length && on.every((p) => !p.models.chat);
  const works = on.some((p) => p.reachable && p.models.chat && !p.missing.includes(p.models.chat));
  $('[data-open="models"]').classList.toggle("alert", Boolean(gone.length || none || !on.length));
  if ((gone.length || none) && !works) {
    const what = gone.length ? `${gone[0].title} retired the model Anexis was set to use (${gone[0].models.chat}).` : "No chat model is picked yet.";
    const stand = gone[0]?.suggested?.chat;
    const fix = async () => {
      banner("Switching models and restarting the brain...");
      try {
        await api.post("/models/heal");
        await overlays.restartBrain(() => {});
        banner("");
        toast(`Now using ${stand}. Change it any time under Models.`);
        checkModels();
      } catch (e) { banner(e.message, "bad"); }
    };
    banner(`${what} It cannot answer until another is picked.`, "bad", h("span",
      stand ? h("button", { type: "button", onclick: fix }, `use ${stand}`) : null, stand ? "  " : "",
      h("button", { type: "button", onclick: () => open("models") }, "pick myself")));
  }
}

/** About Me is what Anexis always knows about its owner. Until it has at
 *  least a name it says so, once per window, with the form one click away.
 *  What Anexis already knows is filled in there, so only the rest is asked. */
function askAboutMe(state) {
  const known = state?.about_me || {};
  $('[data-open="about"]').classList.toggle("alert", !known.name);
  if (known.name || !$("#banner").hidden || sessionStorage.getItem("anexis-asked-about")) return;
  sessionStorage.setItem("anexis-asked-about", "1");
  banner("I know how you like to be talked to, but not who you are yet. Fill in your name, school and classes once and I never have to ask.", "",
    h("span", h("button", { type: "button", onclick: () => { banner(""); open("about"); } }, "fill in About me"), "  ",
      h("button", { type: "button", onclick: () => banner("") }, "later")));
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
  else if (event.type === "canvas_synced") { pulse(); if (event.added) toast(`Canvas: ${event.added} new ${event.added === 1 ? "assignment" : "assignments"} added to your list.`); }
  else if (event.type === "synced" && event.from === "school") {
    const got = (event.memories || 0) + (event.items || 0) + (event.messages || 0);
    if (got) { toast(`Synced with the school server: ${got} new ${got === 1 ? "thing" : "things"} from school.`); memory.refresh(); pulse(); }
  }
  else if (event.type === "sync_failed") $('[data-open="keys"]').title = `School sync: ${event.error}`;
  else if (event.type === "task_done") notify(`${name}: done`, event.text || "Finished what you asked.");
  else if (event.type === "wake") showWindow();
  else if (event.type === "canvas_failed") toast(`Canvas could not be reached: ${event.error}`, "bad");
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
    pulseClaude();
    checkModels();
    memory.refresh();
    tools.refresh();
    files.show();
  }
}

// ---- boot sequence -------------------------------------------------------
async function boot(state) {
  if (sessionStorage.getItem("anexis-booted") || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  sessionStorage.setItem("anexis-booted", "1");
  const el = $("#boot"), log = $("#boot-log"), lines = $("#boot-lines"), mark = $("#boot-name");
  mark.textContent = (state?.name || name).toUpperCase();
  el.hidden = false;
  let skipped = false;
  const skip = () => { skipped = true; };
  addEventListener("keydown", skip, { once: true });
  el.addEventListener("pointerdown", skip, { once: true });
  const wait = (ms) => new Promise((r) => setTimeout(r, skipped ? 0 : ms));

  // First the fast scroll of a machine waking up, made of what is really loaded.
  const waking = [
    "anexis kernel: loading", "mount: memory database", "mount: workspace", "net: local link, loopback only", "lock: token required",
    `tools: ${state?.tools ?? 0} registered`, `memory: ${state?.memories ?? 0} entries`, `control: ${state?.control || "ask"}`,
    ...(state?.providers || []).map((p) => `model source: ${p} (${state.chat_models?.[p] || "no chat model"})`),
    "deck: panels up", "ready",
  ];
  for (const line of waking) {
    if (skipped) break;
    log.append(h("li", line));
    log.scrollTop = log.scrollHeight;
    await wait(55);
  }
  log.hidden = true;
  mark.hidden = false;
  const rows = state ? [
    ["link to the brain", "ok", "ok"],
    ["model source", state.providers.length ? state.providers.join(", ") : "none yet", state.providers.length ? "ok" : "warn"],
    ["memory", `${state.memories} things remembered`, "ok"],
    ["tools", `${state.tools} ready`, "ok"],
    ["control", state.control === "full" ? "full" : "ask first", state.control === "full" ? "warn" : "ok"],
  ] : [["link to the brain", "waiting", "warn"]];
  for (const [label, value, kind] of rows) {
    if (skipped) break;
    lines.append(h(`li.${kind}`, h("span", label), h("b", value)));
    await wait(110);
  }
  await wait(450);
  removeEventListener("keydown", skip);
  el.classList.add("leaving");
  await new Promise((r) => setTimeout(r, 420));  // let it fade before anything opens on top
  el.hidden = true;
}

async function openChats() {
  overlays.openSheet("Chats", h("div.empty", "Loading..."));
  try {
    const rows = await api.get("/sessions");
    overlays.openSheet("Chats", [
      h("p", "Your past chats, newest first. Deleting one does not make Anexis forget what it learned there."),
      chat.chatList(rows, () => overlays.closeSheet()),
      h("div.sheet-foot", h("button.btn.primary", { type: "button", onclick: () => { overlays.closeSheet(); chat.newConversation(); } }, "New chat")),
    ]);
  } catch (e) { overlays.openSheet("Chats", h("p", e.message)); }
}

// ---- full screen: the top bar hides until the mouse touches the top edge --
addEventListener("mousemove", (e) => {
  if (root.dataset.fullscreen !== "on") return;
  const bar = $(".top");
  if (e.clientY <= 6) bar.classList.add("reveal");
  else if (!bar.contains(e.target) && e.clientY > bar.offsetHeight + 20) bar.classList.remove("reveal");
});

// ---- start ---------------------------------------------------------------
function open(which) {
  return ({
    setup: openSetup, keys: () => overlays.openKeys({ terminalAt, onChange: pulseClaude }), models: () => overlays.openModels({ onSaved: checkModels }),
    doctor: overlays.openDoctor, about: overlays.openAbout,
    app: () => overlays.openApp({ setTheme, setFx, terminalAt, onName: showName, themes: THEMES }),
  })[which]?.();
}

let started = false;
async function start() {
  const state = await pulse();
  if (!state || started) return;
  started = true;
  const booting = boot(state);

  overlays.initSheet();
  chat.initChat({
    name: state.name,
    open,
    onBusy: (busy) => { if (!busy && reloadWaiting) location.reload(); },
    onDone: (event, said) => {
      // Work asked for and finished while the owner looked away gets a notification.
      if (document.hidden || !document.hasFocus()) {
        const first = said.replace(/[*_`#>]/g, "").split("\n").find((line) => line.trim()) || "Finished.";
        notify(`${name}: done`, first.trim());
      }
      memory.markUsed((event.memories_used || []).map((m) => m.id));
      pulse();
      if ((event.tools_used || []).includes("code_task")) pulseClaude();
      voice.speak(said);
    },
    remember: memory.remember,
    forget: memory.remove,
    searchMemory: (words) => { show("memory"); memory.search(words); },
    why: () => { show("memory"); chat.note("The memories that shaped the last reply are marked in the Memory tab."); },
    showTools: () => show("tools"),
    openChats,
    setControl,
    setTheme: (value) => setTheme(value) && chat.note(`Theme is now **${value}**.`),
    themes: THEMES,
    toggleVoice: () => { voice.setReadAloud(!voice.readAloud); chat.note(`Reading replies out loud is **${voice.readAloud ? "on" : "off"}**.`); },
  });
  initStats();
  terminal.initTerminal();
  memory.initMemory();
  tools.initTools();
  activity.initActivity();
  files.initFiles({ terminalAt });
  initKeyboard({ terminalShowing: () => deck.dataset.center === "terminal", toTerminal: terminal.sendKeys });
  api.follow(onEvent, onLink);
  setInterval(() => !document.hidden && pulse(), 4000);
  pulseClaude();
  setInterval(() => !document.hidden && pulseClaude(), 120_000);

  $("#control").addEventListener("click", controlSheet);
  $("#chat-new").addEventListener("click", () => { chat.newConversation(); $("#input").focus(); });
  $("#chat-clear").addEventListener("click", (e) => chat.clearConversation(e.currentTarget));
  $("#chat-list").addEventListener("click", openChats);
  $("#mic").addEventListener("click", () => voice.toggleMic((text) => chat.send(text)));
  for (const button of $$("[data-open]")) button.addEventListener("click", () => open(button.dataset.open));
  for (const tab of $$(".tabs [data-center]")) tab.addEventListener("click", () => show(tab.dataset.center));
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
    else {
      await checkModels();
      askAboutMe(await pulse());
    }
  } catch { /* setup stays one click away */ }
  $("#input").focus();
}

start().then(() => {
  if (!started) {  // the brain is not up yet: keep knocking
    banner("Waiting for the brain to start...");
    const knock = setInterval(async () => {
      await start();
      if (started) { clearInterval(knock); banner(""); }
    }, 1000);
  }
});
