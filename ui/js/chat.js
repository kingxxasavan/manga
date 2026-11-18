// The chat panel: talking to Anexis, watching its tool calls, answering when
// it asks first, and the slash commands.

import * as api from "./api.js";
import { $, ago, h, markdown, shortArgs, toast } from "./dom.js";

const MODES = ["general", "school", "work", "project"];
const COMMANDS = [
  ["/new", "start a fresh chat (this one is kept under Chats)"],
  ["/clear", "delete this chat (what was learned stays)"],
  ["/chats", "your past chats"],
  ["/mode", "general, school, work or project"],
  ["/code", "build something: /code a script that renames my photos"],
  ["/remember", "save something on purpose"],
  ["/memory", "search what Anexis remembers"],
  ["/forget", "delete a memory by its number"],
  ["/why", "which memories shaped the last reply"],
  ["/control", "full or ask: may tools run without asking"],
  ["/stop", "stop what Anexis is doing"],
  ["/voice", "read replies out loud, on or off"],
  ["/setup", "preset, options and downloads"],
  ["/models", "which model does which job"],
  ["/keys", "API keys, Claude sign in, Canvas"],
  ["/doctor", "check that every part works"],
  ["/aboutme", "tell Anexis about yourself"],
  ["/app", "this app: live editing, theme, restart"],
  ["/theme", "tron, ion, ember, verdant or ultra"],
  ["/help", "this list"],
];
const IDEAS = [
  "What can you do on this computer?",
  "Whats due this week?",
  "What am I missing on Canvas?",
  "Download the slides from all my classes",
  "/code a script that sorts my Desktop into folders by file type",
];

let hooks = {};
let sessionId = localStorage.getItem("anexis-session") || "";
let mode = localStorage.getItem("anexis-mode") || "general";
let busy = false;
let name = "Anexis";
const log = () => $("#chat-log");

export const state = { get busy() { return busy; }, get sessionId() { return sessionId; }, get mode() { return mode; } };

function pinned() {
  const el = log();
  return el.scrollHeight - el.scrollTop - el.clientHeight < 60;
}
function scrollDown(force) {
  const el = log();
  if (force || pinned()) el.scrollTop = el.scrollHeight;
}

function showEmpty() {
  log().replaceChildren(h("div.chat-empty",
    h("h3", name.toUpperCase()),
    h("p", "Type what you want done. It can run commands, open apps, read and write files, search the web, remember things about you, and write code."),
    h("div.ideas", IDEAS.map((idea) => h("button.btn.ghost", { type: "button", onclick: () => send(idea) }, idea))),
  ));
}

export function note(text) {
  $(".chat-empty", log())?.remove();
  const el = h("div.note");
  el.innerHTML = markdown(text);
  log().append(el);
  scrollDown(true);
  return el;
}

function message(kind, text = "") {
  $(".chat-empty", log())?.remove();
  // `ran` holds the tool calls of a reply, above its text: what it did, then what it says.
  const body = h("div.body"), ran = h("div.ran");
  const el = h(`div.msg.${kind}`, h("div.who", kind === "you" ? "you" : name), ran, body);
  if (kind === "you") body.textContent = text; else body.innerHTML = markdown(text);
  log().append(el);
  return { el, body, ran };
}

function setBusy(value) {
  busy = value;
  $("#send").disabled = value;
  $("#stop").disabled = !value;
  hooks.onBusy?.(value);
}

async function ensureSession() {
  if (!sessionId) {
    sessionId = (await api.post("/sessions/new", { mode })).session_id;
    localStorage.setItem("anexis-session", sessionId);
  }
  return sessionId;
}

/** Sends a message and plays the reply as it streams in. */
export async function send(text) {
  text = text.trim();
  if (!text) return;
  if (text.startsWith("/")) return command(text);
  if (busy) return toast("Still working on the last one. Press STOP to cut it short.");
  message("you", text);
  if ($("#chat-title")?.textContent === "New chat") setTitle(text.replace(/\s+/g, " ").slice(0, 80));
  const reply = message("ai");
  const cursor = h("span.cursor");
  reply.body.append(cursor);
  scrollDown(true);
  setBusy(true);

  let said = "", frame = 0, statusLine = null;
  const chips = [];
  const paint = () => {
    frame = 0;
    const stick = pinned();
    reply.body.innerHTML = markdown(said);
    if (busy) reply.body.append(cursor);
    if (stick) scrollDown(true);
  };
  const openChip = (toolName) => chips.findLast((c) => c.name === toolName && !c.finished);

  const onEvent = (event) => {
    if (event.type === "text") {
      said += event.delta;
      frame ||= requestAnimationFrame(paint);
    } else if (event.type === "tool") {
      let chip = openChip(event.name);
      if (!chip) {
        const el = h("button.tool-chip", { type: "button", dataset: { status: event.status } },
          h("b", event.name), h("span", shortArgs(event.args)), h("i", event.status));
        chip = { name: event.name, el, out: null, finished: false };
        el.onclick = () => chip.out && (chip.out.hidden = !chip.out.hidden);
        chips.push(chip);
        reply.ran.append(el);
      }
      chip.el.dataset.status = event.status;
      chip.el.lastChild.textContent = event.status === "asking" ? "waiting for you" : "running";
      scrollDown();
    } else if (event.type === "confirm") {
      askFirst(reply.ran, event, openChip(event.tool));
    } else if (event.type === "tool_result") {
      const chip = openChip(event.name);
      if (chip) {
        chip.finished = true;
        chip.el.dataset.status = event.ok ? "done" : "failed";
        chip.el.lastChild.textContent = event.ok ? "done" : "failed";
        chip.out = h("pre.tool-out", { hidden: event.ok }, event.preview || "(no output)");
        chip.el.after(chip.out);
      }
      statusLine?.remove();
      statusLine = null;
    } else if (event.type === "status") {
      statusLine ||= reply.el.appendChild(h("div.msg-foot"));
      statusLine.textContent = event.text;
      scrollDown();
    } else if (event.type === "error") {
      reply.el.classList.add("error");
      said += (said ? "\n\n" : "") + event.message;
      paint();
    } else if (event.type === "stopped") {
      said += (said ? "\n\n" : "") + "(stopped)";
      for (const chip of chips.filter((c) => !c.finished)) {
        chip.el.dataset.status = "declined";
        chip.el.lastChild.textContent = "stopped";
      }
    } else if (event.type === "done") {
      const used = [...new Set(event.tools_used || [])];
      const memories = (event.memories_used || []).length;
      const parts = [];
      if (used.length) parts.push(`used: ${used.join(", ")}`);
      if (memories) parts.push(`${memories} ${memories === 1 ? "memory" : "memories"}`);
      if (event.model) parts.push(`${event.provider} ${event.model}`);
      if (parts.length) reply.el.append(h("div.msg-foot", parts.join("  ·  ")));
      hooks.onDone?.(event, said);
    }
  };

  try {
    await api.stream("POST", "/chat", { text, session_id: await ensureSession(), mode }, onEvent);
  } catch (e) {
    reply.el.classList.add("error");
    said += (said ? "\n\n" : "") + (e.status === 0 ? "Lost the connection to Anexis. It reconnects by itself, then ask again." : e.message);
  }
  setBusy(false);
  cancelAnimationFrame(frame);
  $$confirms(reply.el).forEach((card) => card.remove());
  paint();
  if (!said && !chips.length) reply.body.textContent = "(no reply)";
  scrollDown();
}

const $$confirms = (root) => [...root.querySelectorAll(".confirm")];

/** Ask first mode: a risky tool waits here for a yes or a no. */
function askFirst(parent, event, chip) {
  const answer = async (allow) => {
    card.remove();
    try {
      await api.post("/confirm", { id: event.id, allow });
    } catch { /* it already timed out, or the turn was stopped */ }
    if (chip && !allow) {
      chip.finished = true;
      chip.el.dataset.status = "declined";
      chip.el.lastChild.textContent = "declined";
    }
  };
  const card = h("div.confirm",
    h("p", h("b", event.tool), ` wants to run. ${event.reason ? event.reason[0].toUpperCase() + event.reason.slice(1) + "." : ""}`),
    h("pre", JSON.stringify(event.args, null, 2)),
    h("div.row",
      h("button.btn.primary", { type: "button", onclick: () => answer(true) }, "Allow"),
      h("button.btn.ghost", { type: "button", onclick: () => answer(false) }, "Deny"),
      h("small", "Tired of this? Switch to full control with /control full"),
    ));
  if (chip) chip.el.after(card); else parent.append(card);
  card.querySelector("button").focus();
  scrollDown(true);
}

export async function stop() {
  if (!busy) return;
  try {
    await api.post("/chat/stop", sessionId ? { session_id: sessionId } : {});
  } catch (e) {
    toast(e.message, "bad");
  }
}

export function setMode(value) {
  if (!MODES.includes(value)) return false;
  mode = value;
  localStorage.setItem("anexis-mode", mode);
  $("#mode").value = mode;
  return true;
}

export function newConversation() {
  sessionId = "";
  localStorage.removeItem("anexis-session");
  showEmpty();
  setTitle("New chat");
}

function setTitle(text) {
  const el = $("#chat-title");
  if (el) { el.textContent = text; el.title = text; }
}

/** Clear chat: this conversation is deleted. Asks once by arming the button. */
export async function clearConversation(button) {
  if (busy) return toast("Wait for the reply to finish, or press STOP first.");
  if (button && !button.dataset.sure) {
    button.dataset.sure = "1";
    button.textContent = "Sure?";
    setTimeout(() => { delete button.dataset.sure; button.textContent = "Clear"; }, 3000);
    return;
  }
  if (button) { delete button.dataset.sure; button.textContent = "Clear"; }
  if (sessionId) {
    try { await api.del(`/sessions/${encodeURIComponent(sessionId)}`); } catch (e) { return toast(e.message, "bad"); }
  }
  newConversation();
  toast("Chat cleared. What Anexis learned from it is still in Memory.");
}

/** Switches to one of the past chats. */
export async function openConversation(id) {
  if (busy) return toast("Wait for the reply to finish, or press STOP first.");
  sessionId = id;
  localStorage.setItem("anexis-session", id);
  await loadHistory();
}

/** The list of past chats, for the Chats screen. */
export function chatList(rows, done) {
  if (!rows.length) return h("div.empty", "No chats yet.");
  return h("div.chats", rows.map((row) => {
    const remove = h("button.btn.ghost", { type: "button" }, "Delete");
    const el = h(`div.chat-row${row.id === sessionId ? ".current" : ""}`,
      h("button", { type: "button", style: "text-align:left;min-width:0", onclick: async () => { await openConversation(row.id); done(); } }, h("b", row.title)),
      h("button.btn", { type: "button", onclick: async () => { await openConversation(row.id); done(); } }, "Open"),
      remove,
      h("small", `${row.messages} messages · ${row.mode} · ${ago(row.updated_at)}`));
    remove.onclick = async () => {
      if (!remove.dataset.sure) { remove.dataset.sure = "1"; remove.textContent = "Sure?"; return; }
      try { await api.del(`/sessions/${encodeURIComponent(row.id)}`); } catch (e) { return toast(e.message, "bad"); }
      if (row.id === sessionId) newConversation();
      el.remove();
    };
    return el;
  }));
}

async function command(line) {
  const [head, ...rest] = line.slice(1).split(/\s+/);
  const arg = rest.join(" ").trim();
  const open = (which) => hooks.open?.(which);
  switch (head.toLowerCase()) {
    case "help": return note(COMMANDS.map(([c, about]) => `**${c}**  ${about}`).join("\n"));
    case "new": newConversation(); return toast("Fresh chat. The last one is under Chats.");
    case "clear": return clearConversation();
    case "chats": return hooks.openChats?.();
    case "mode": return note(setMode(arg) ? `Mode is now **${arg}**.` : `Modes: ${MODES.join(", ")}`);
    case "code": return arg ? send(`Use the code_task tool to build this: ${arg}`) : note("Usage: /code what to build");
    case "remember": return arg ? hooks.remember?.(arg) : note("Usage: /remember something about you");
    case "memory": return hooks.searchMemory?.(arg);
    case "forget": return /^#?\d+$/.test(arg) ? hooks.forget?.(Number(arg.replace("#", ""))) : note("Usage: /forget and the number shown in the Memory panel");
    case "why": return hooks.why?.();
    case "control": return ["full", "ask"].includes(arg) ? hooks.setControl?.(arg) : note("Usage: /control full  or  /control ask");
    case "stop": return stop();
    case "voice": return hooks.toggleVoice?.();
    case "setup": return open("setup");
    case "keys": return open("keys");
    case "models": return open("models");
    case "doctor": return open("doctor");
    case "aboutme": return open("about");
    case "app": return open("app");
    case "theme": return hooks.setTheme?.(arg) || note(`Themes: ${(hooks.themes || []).join(", ")}`);
    case "tools": return hooks.showTools?.();
    default: return note(`No command /${head}. Type /help for the list.`);
  }
}

function suggestions(input) {
  const box = $("#suggest");
  const typed = input.value;
  if (!typed.startsWith("/") || /\s/.test(typed)) { box.hidden = true; return; }
  const matches = COMMANDS.filter(([c]) => c.startsWith(typed.toLowerCase()));
  if (!matches.length) { box.hidden = true; return; }
  box.replaceChildren(...matches.map(([c, about], i) => h("button", {
    type: "button", "aria-selected": i === 0 ? "true" : "false",
    onclick: () => { input.value = c + " "; box.hidden = true; input.focus(); },
  }, h("b", c), h("span", about))));
  box.hidden = false;
}

export async function loadHistory() {
  if (!sessionId) return showEmpty();
  try {
    const past = await api.get(`/sessions/${encodeURIComponent(sessionId)}/messages`);
    setMode(past.mode);
    const first = past.messages.find((m) => m.role === "user");
    setTitle(first ? first.content.replace(/\s+/g, " ").slice(0, 80) : "New chat");
    if (!past.messages.length) return showEmpty();
    log().replaceChildren();
    for (const m of past.messages) {
      const made = message(m.role === "user" ? "you" : "ai", m.content);
      const used = [...new Set(m.meta?.tools_used || [])];
      if (used.length) made.el.append(h("div.msg-foot", `used: ${used.join(", ")}`));
    }
    scrollDown(true);
  } catch (e) {
    if (e.status === 404) newConversation(); else showEmpty();
  }
}

export function initChat(options) {
  hooks = options;
  const input = $("#input"), form = $("#composer");
  setName(options.name || name);
  const grow = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight + 2, 180) + "px"; };
  input.addEventListener("input", () => { grow(); suggestions(input); });
  input.addEventListener("keydown", (e) => {
    const box = $("#suggest");
    if (e.key === "Tab" && !box.hidden) {
      e.preventDefault();
      box.querySelector('[aria-selected="true"]')?.click();
    } else if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value;
    input.value = "";
    grow();
    $("#suggest").hidden = true;
    send(text);
  });
  $("#mode").addEventListener("change", (e) => setMode(e.target.value));
  $("#stop").addEventListener("click", stop);
  setMode(mode);
  setBusy(false);
  loadHistory();
}

export function setName(value) {
  name = value;
  $("#input").placeholder = `Tell ${name} what to do. / for commands`;
  const title = $(".chat-empty h3", log());
  if (title) title.textContent = name.toUpperCase();
}

export function fill(text) {
  const input = $("#input");
  input.value = text;
  input.dispatchEvent(new Event("input"));
  input.focus();
}
