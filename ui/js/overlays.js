// The screens that open over the deck: keys, checkup, About me and the App
// screen. Setup has its own file (setup.js).

import * as api from "./api.js";
import { $, h, toast } from "./dom.js";

let onClose = null, locked = false, lastFocus = null;

/** Opens the sheet with a title and a body. `lock` stops it being closed
 *  half way through something (an install, a restart). */
export function openSheet(title, body, options = {}) {
  lastFocus = lastFocus || document.activeElement;
  $("#sheet-title").textContent = title;
  $("#sheet-body").replaceChildren(...[body].flat());
  $("#overlay").hidden = false;
  onClose = options.onClose || null;
  setLocked(Boolean(options.lock));
  ($("#sheet-body").querySelector("[autofocus], input, textarea, select, button") || $("#sheet-close")).focus();
}

export function setLocked(value) {
  locked = value;
  $("#sheet-close").hidden = value;
}

export function closeSheet(force = false) {
  if (locked && !force) return;
  $("#overlay").hidden = true;
  $("#sheet-body").replaceChildren();
  locked = false;
  onClose?.();
  onClose = null;
  lastFocus?.focus?.();
  lastFocus = null;
}

export const sheetOpen = () => !$("#overlay").hidden;

export function initSheet() {
  $("#sheet-close").addEventListener("click", () => closeSheet());
  $("#overlay").addEventListener("pointerdown", (e) => e.target === $("#overlay") && closeSheet());
  $("#overlay").addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;  // keep Tab inside the sheet
    const stops = [...$("#sheet").querySelectorAll("button, input, textarea, select, a[href]")].filter((el) => !el.disabled && el.offsetParent);
    if (!stops.length) return;
    const first = stops[0], last = stops.at(-1);
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
}

/** Restarts the brain and resolves once it answers again. */
export async function restartBrain(say = () => {}) {
  const reply = await api.post("/app/restart");
  if (!reply.restarting) { say(reply.why); return false; }
  say("Restarting the brain...");
  await new Promise((r) => setTimeout(r, 1200));
  for (let i = 0; i < 120; i++) {
    try { await api.get("/health"); say("Back up."); return true; } catch { await new Promise((r) => setTimeout(r, 500)); }
  }
  say("It is taking a long time. Look at server.log in the Anexis home folder.");
  return false;
}

// ---- keys ----------------------------------------------------------------

/** The list of key fields, shared by setup and the Keys screen. */
export function keyFields(keys) {
  const inputs = new Map();
  const el = h("div", keys.map((key) => {
    const input = h("input", {
      type: key.secret === false ? "text" : "password", autocomplete: "off", "aria-label": key.label,
      placeholder: key.set ? "leave empty to keep it" : key.secret === false ? "https://yourschool.instructure.com" : key.label,
    });
    const warn = h("div.warnline");
    inputs.set(key.env, { input, warn });
    return h("div.keyrow",
      h("div", h("b", key.title), h("small", `Turns on: ${key.turns_on}`), h("small", `Get one: ${key.get_it}`)),
      h("div", input, h("small.state", !key.set ? "" : key.secret === false ? `saved: ${key.ends}. Type - to remove it.`
        : `saved${key.ends ? `, ends in ...${key.ends}` : ""}. Type - to remove it.`)),
      warn);
  }));
  return {
    el,
    values() {
      const out = {};
      for (const [env, { input }] of inputs) if (input.value.trim()) out[env] = input.value.trim();
      return out;
    },
    showWarnings(warnings) {
      for (const [env, { warn }] of inputs) warn.textContent = warnings[env] || "";
    },
  };
}

/** How Claude Code is signed in, with the button to sign in with a Claude
 *  plan and the rule for switching to a cheaper model when the plan runs low. */
async function claudeBlock(hooks) {
  let state;
  try { state = await api.get("/claude"); } catch { return null; }
  if (!state.installed) {
    return h("div.prov", h("h4", h("b", "Claude for code"), h("span", "not installed")),
      h("p", "Claude Code is not installed, so Anexis writes code with its own model. Open Setup and tick Claude Code to add it."));
  }
  const how = state.plan ? `signed in with your Claude plan${state.subscription ? ` (${state.subscription})` : ""}${state.email ? `, ${state.email}` : ""}`
    : state.signed_in ? "signed in with an API key" : "not signed in";
  const percent = h("input", { type: "text", value: String(state.switch_percent), inputMode: "numeric", style: "width:64px" });
  const cheaper = h("input", { type: "text", value: state.switch_model, style: "width:110px", "aria-label": "Model to switch to" });
  const said = h("small");
  const save = async () => {
    try {
      await api.post("/claude", { switch_percent: Number(percent.value) || 0, switch_model: cheaper.value.trim() });
      said.textContent = "Saved.";
      hooks.onChange?.();
    } catch (e) { said.textContent = e.message; }
  };
  return h("div.prov",
    h("h4", h("b", "Claude for code"), h(`span${state.signed_in ? ".ok" : ".warn"}`, how)),
    h("p", "You do not need an API key. A Claude plan (Pro or Max) works: sign in once and Claude writes your code on that plan."),
    state.usage ? h("p", `Your plan is ${state.usage.percent.toFixed(0)}% used right now. Code tasks run on ${state.model}.`) : null,
    h("div.actions",
      h(`button.btn${state.signed_in ? "" : ".primary"}`, { type: "button", onclick: () => { closeSheet(); hooks.terminalAt("", "claude auth login"); } },
        state.signed_in ? "Sign in again" : "Sign in with my Claude plan"),
      state.signed_in ? h("button.btn.ghost", { type: "button", onclick: () => { closeSheet(); hooks.terminalAt("", "claude auth logout"); } }, "Sign out") : null),
    h("div.inline", "When the plan is", percent, "% used, code on", cheaper, h("button.btn", { type: "button", onclick: save }, "Save"), said),
    h("small", "0 turns the switch off. The model before the switch is Claude's own best one."));
}

/** The Canvas sign in when the window's bridge (preload.js) did not load:
 *  ask the window through a special link instead. An older window does not
 *  know that link, which is said plainly after a few seconds. */
function signInWithoutBridge(url) {
  return new Promise((resolve) => {
    let started = false;
    const listen = (event) => {
      if (event.detail.started) { started = true; return; }
      removeEventListener("anexis-canvas", listen);
      resolve(event.detail);
    };
    addEventListener("anexis-canvas", listen);
    window.open(`about:blank#anexis-canvas=${encodeURIComponent(url)}`);
    setTimeout(() => {
      if (started) return;
      removeEventListener("anexis-canvas", listen);
      resolve({ ok: false, error: "The Anexis window is still the old one. Quit Anexis completely (Ctrl+Q) and open it again. If this keeps showing, run update.ps1 again." });
    }, 4000);
  });
}

/** Canvas through the school's own login page: no password goes through
 *  Anexis and no token has to be made by hand. Only the desktop app can open
 *  that login window, so in a plain browser the token boxes below are the way. */
async function canvasBlock() {
  let state;
  try { state = await api.get("/canvas"); } catch { return null; }
  const address = h("input", { type: "text", value: state.url || "", placeholder: "https://yourschool.instructure.com", "aria-label": "Canvas address", spellcheck: false });
  const said = h("small", state.method === "session" ? `Signed in${state.user ? ` as ${state.user}` : ""} at ${state.url}.`
    : state.method === "token" ? "Using a Canvas token from the keys below." : "Not signed in yet.");
  if (state.method !== "none") said.className = "ok";
  const app = window.anexisFrame;
  const inApp = Boolean(app) || /Electron\//.test(navigator.userAgent);
  const go = h("button.btn.primary", { type: "button", disabled: !inApp }, state.method === "session" ? "Sign in again" : "Sign in with my browser");
  go.onclick = async () => {
    const url = address.value.trim();
    if (!url) { said.className = "bad"; said.textContent = "Put in your school's Canvas address first."; return address.focus(); }
    go.disabled = true;
    said.className = "";
    said.textContent = "A Canvas window is open. Sign in there the way you always do.";
    const result = app ? await app.canvasSignIn(url) : await signInWithoutBridge(url);
    go.disabled = false;
    if (!result.ok) { said.className = "bad"; said.textContent = result.error; return; }
    said.className = "ok";
    said.textContent = `Signed in${result.user ? ` as ${result.user}` : ""}. Loading your classes...`;
    setLocked(true);
    await restartBrain(() => {});
    setLocked(false);
    closeSheet();
    toast(`Canvas is connected${result.user ? ` for ${result.user}` : ""}. Your assignments show up in a moment.`);
  };
  const out = state.method === "session"
    ? h("button.btn.ghost", { type: "button", onclick: async () => {
        await api.del("/canvas/session");
        setLocked(true);
        await restartBrain(() => {});
        setLocked(false);
        closeSheet();
        toast("Signed out of Canvas.");
      } }, "Sign out") : null;
  return h("div.prov",
    h("h4", h("b", "Canvas"), h(`span${state.method === "none" ? ".warn" : ".ok"}`, state.method === "none" ? "not connected" : "connected")),
    h("p", "Your school's own Canvas login opens in a window. Sign in there like always. Anexis never sees your username or password."),
    h("div.inline", address, go, out),
    said,
    inApp ? null : h("small", "This button works in the Anexis app. In a plain browser, use a Canvas token in the boxes below."));
}

/** A part of a screen that fills itself in when its data arrives, so a slow
 *  question (like asking Claude Code about the plan) never holds the screen up. */
function later(load, waiting) {
  const spot = h("div.prov", h("p", waiting));
  load().then((el) => spot.replaceWith(el || h("span")), (e) => spot.replaceWith(h("div.prov", h("p", e.message || String(e)))));
  return spot;
}

export async function openKeys(hooks = {}) {
  openSheet("Keys", h("div.empty", "Loading..."));
  let state;
  try {
    state = await api.get("/setup");
  } catch (e) { closeSheet(true); return toast(e.message, "bad"); }
  const claude = later(() => claudeBlock(hooks), "Checking how Claude is signed in...");
  const canvas = later(canvasBlock, "Checking Canvas...");
  const fields = keyFields(state.keys), status = h("span.left");
  const save = h("button.btn.primary", { type: "button" }, "Save keys");
  save.onclick = async () => {
    const keys = fields.values();
    if (!Object.keys(keys).length) return closeSheet();
    save.disabled = true;
    try {
      const reply = await api.post("/setup", { keys });
      fields.showWarnings(reply.warnings);
      setLocked(true);
      const ok = await restartBrain((line) => { status.textContent = line; });
      setLocked(false);
      if (ok && !Object.keys(reply.warnings).length) { closeSheet(); toast("Keys saved and loaded."); }
    } catch (e) {
      status.textContent = e.message;
    }
    save.disabled = false;
  };
  openSheet("Keys", [
    claude,
    canvas,
    h("p", "Each key turns one thing on. They are saved in a private file on this computer and nowhere else. What you type stays hidden."),
    fields.el,
    h("div.sheet-foot", status, h("button.btn.ghost", { type: "button", onclick: () => closeSheet() }, "Cancel"), save),
  ]);
}

// ---- models --------------------------------------------------------------

/** Which model does which job. The lists come live from each provider, so a
 *  model that was retired shows up as gone, with something to use instead. */
export async function openModels(hooks = {}) {
  openSheet("Models", h("div.empty", "Asking each provider which models it has..."));
  let state;
  try { state = await api.get("/models"); } catch (e) { return openSheet("Models", h("p", e.message)); }
  const status = h("span.left");
  const blocks = state.providers.map((p) => ({ p, enabled: p.enabled, inputs: {} }));

  const draw = () => {
    const body = blocks.map((block, index) => {
      const { p } = block;
      const listId = `models-${p.name}`;
      const sub = !p.has_key ? "needs a key" : p.reachable ? `${p.available.length} models` : "not reachable";
      const toggle = h("input", { type: "checkbox", checked: block.enabled, onchange: (e) => { block.enabled = e.target.checked; draw(); } });
      const rows = !block.enabled ? [] : state.roles.map((role) => {
        const gone = p.missing.includes(p.models[role.name]);
        const input = block.inputs[role.name] ||= h("input", {
          type: "text", value: p.models[role.name] || "", placeholder: role.name === "chat" ? "pick a model" : "empty", "aria-label": `${p.title} ${role.name} model`,
        });
        input.setAttribute("list", listId);
        const said = h("small", gone ? `${p.models[role.name]} is gone from ${p.title}.` : role.about);
        if (gone) said.className = "bad";
        const pick = p.suggested[role.name] || (role.name === "tools" ? p.fast : "");
        const use = pick && (gone || !p.models[role.name]) && !input.value.trim()
          ? h("button.btn.ghost", { type: "button", onclick: () => { input.value = pick; said.className = ""; said.textContent = `Suggested: ${pick}. Press Try to check it answers.`; } }, "Use suggested")
          : null;
        const tryIt = h("button.btn.ghost", { type: "button" }, "Try");
        tryIt.onclick = async () => {
          if (!input.value.trim()) return;
          tryIt.disabled = true;
          said.className = "";
          said.textContent = "Asking it...";
          try {
            const r = await api.post("/models/test", { provider: p.name, model: input.value.trim(), role: role.name });
            said.className = r.ok ? "ok" : "bad";
            said.textContent = r.ok ? `It works. It said: ${r.said} (${(r.ms / 1000).toFixed(1)} s)` : r.error;
          } catch (e) { said.className = "bad"; said.textContent = e.message; }
          tryIt.disabled = false;
        };
        return h("div.model-row", h("b", role.name), input, h("div.actions", use, tryIt), said);
      });
      const pull = p.name === "ollama" && block.enabled ? ollamaPull(p, () => openModels(hooks)) : null;
      return h(`div.prov${block.enabled ? "" : ".off"}`,
        h("h4", h("label", toggle, h("b", p.title)), h(`span${p.reachable ? ".ok" : block.enabled ? ".warn" : ""}`, sub),
          index > 0 && block.enabled ? h("button.btn.ghost", { type: "button", title: "Try this one before the one above it",
            onclick: () => { [blocks[index - 1], blocks[index]] = [blocks[index], blocks[index - 1]]; draw(); } }, "Move up") : null),
        h("p", p.error && block.enabled ? `${p.about} ${p.error}` : p.about),
        h("datalist", { id: listId }, p.available.map((m) => h("option", { value: m }))),
        ...rows, pull);
    });
    $("#sheet-body").replaceChildren(
      h("p", "Anexis tries the providers from the top down and moves to the next when one is down. Type in a box to search that provider's models. ", h("b", "Try"), " asks the model one word, so you know it works before you save."),
      ...body,
      h("div.sheet-foot", status, h("button.btn.ghost", { type: "button", onclick: () => closeSheet() }, "Cancel"),
        h("button.btn.primary", { type: "button", onclick: save }, "Save and restart")));
  };

  const save = async () => {
    const providers = blocks.map((block) => ({
      name: block.p.name, enabled: block.enabled,
      models: Object.fromEntries(state.roles.map((r) => [r.name, block.inputs[r.name] ? block.inputs[r.name].value.trim() : block.p.models[r.name] || ""])),
    }));
    try {
      await api.post("/models", { providers });
    } catch (e) { status.textContent = e.message; return; }
    setLocked(true);
    const ok = await restartBrain((line) => { status.textContent = line; });
    setLocked(false);
    if (ok) { closeSheet(); toast("Models saved."); hooks.onSaved?.(); }
  };
  draw();
}

/** Ollama on this computer: download another model, with progress. */
function ollamaPull(p, done) {
  const input = h("input", { type: "text", placeholder: "a model to download, like qwen3:8b", "aria-label": "Model to download" });
  input.setAttribute("list", "ollama-starters");
  const said = h("small", p.installed ? "Downloads through Ollama. Any name from ollama.com/library works." : "Ollama is not installed yet. Downloading a model installs it first.");
  const go = h("button.btn", { type: "button" }, p.installed ? "Download" : "Install and download");
  go.onclick = async () => {
    const model = input.value.trim();
    if (!model) return;
    go.disabled = true;
    let ok = false;
    try {
      await api.stream("POST", "/setup/install", { ollama: true, models: [model] }, (event) => {
        if (event.line) said.textContent = event.line;
        if (event.state === "failed") said.textContent = event.message;
        if (event.state === "finished") ok = event.ok;
      });
    } catch (e) { said.textContent = e.message; }
    go.disabled = false;
    if (ok) { toast(`${model} is ready.`); done(); }
  };
  return h("div.model-row", h("b", "get"), input, h("div.actions", go), said,
    h("datalist", { id: "ollama-starters" }, (p.starters || []).map((m) => h("option", { value: m }))));
}

// ---- checkup -------------------------------------------------------------

export async function openDoctor() {
  const lines = h("div.checks", h("div.empty", "Checking every part..."));
  const again = h("button.btn", { type: "button" }, "Check again");
  const run = async () => {
    again.disabled = true;
    try {
      const checks = await api.get("/doctor");
      const broken = checks.filter((c) => !c.ok && !c.optional).length;
      lines.replaceChildren(...checks.map((c) => h(`div.checkline.${c.ok ? "ok" : c.optional ? "opt" : "bad"}`,
        h("i", c.ok ? "OK" : c.optional ? "OFF" : "FIX"), h("b", c.part), h("span", c.detail), c.fix ? h("small", `Fix: ${c.fix}`) : null)));
      $("#sheet-title").textContent = broken ? `Checkup: ${broken} to fix` : "Checkup: all good";
    } catch (e) {
      lines.replaceChildren(h("div.empty", e.message));
    }
    again.disabled = false;
  };
  again.onclick = run;
  openSheet("Checkup", [lines, h("div.sheet-foot", again, h("button.btn.ghost", { type: "button", onclick: () => closeSheet() }, "Close"))]);
  run();
}

// ---- about me ------------------------------------------------------------

export async function openAbout() {
  let sections, saved;
  try {
    [sections, saved] = await Promise.all([api.get("/aboutme/sections"), api.get("/aboutme")]);
  } catch (e) { return toast(e.message, "bad"); }
  const fields = sections.map((s) => {
    const current = saved[s.key];
    const input = s.many
      ? h("textarea", { rows: 3, placeholder: "one per line" }, Array.isArray(current) ? current.join("\n") : current || "")
      : h("input", { type: "text", value: typeof current === "string" ? current : "" });
    // An answer stored in a richer shape (from a hand written file) is shown, not edited.
    const rich = current && typeof current === "object" && !Array.isArray(current);
    if (rich) { input.value = JSON.stringify(current); input.disabled = true; }
    return { s, input, rich, el: h("label.field", h("span", s.label), input, h("small", s.question)) };
  });
  const status = h("span.left");
  const save = async () => {
    const data = {};
    for (const { s, input, rich } of fields) {
      if (rich) continue;
      data[s.key] = s.many ? input.value.split("\n").map((v) => v.trim()).filter(Boolean) : input.value.trim();
    }
    try {
      const report = await api.post("/aboutme", data);
      document.dispatchEvent(new CustomEvent("anexis:memory-changed"));
      closeSheet();
      toast(`Saved. ${report.added} new, ${report.changed} changed, ${report.removed} removed.`);
    } catch (e) {
      status.textContent = e.message;
    }
  };
  const blank = fields.filter((f) => !f.rich && !f.input.value.trim()).length;
  openSheet("About me", [
    h("p", "Anexis uses this in every reply, so it never has to ask twice. What it already knew is filled in. ",
      blank ? h("b", `${blank} left empty. `) : null, "Leave anything empty. It stays on this computer."),
    h("div.form", fields.map((f) => f.el)),
    h("div.sheet-foot", status, h("button.btn.ghost", { type: "button", onclick: () => closeSheet() }, "Cancel"), h("button.btn.primary", { type: "button", onclick: save }, "Save")),
  ]);
}

// ---- the app screen ------------------------------------------------------

const THEMES = { tron: "#aacfd1", ion: "#4fe3ff", ember: "#ff9d3c", verdant: "#5dff9b", ultra: "#b48cff" };

export async function openApp(hooks) {
  let info, settings;
  try {
    [info, settings] = await Promise.all([api.get("/app"), api.get("/settings")]);
  } catch (e) { return toast(e.message, "bad"); }
  const status = h("span.left");
  const sep = info.folder.includes("\\") ? "\\" : "/";
  const swatch = (name) => h("button.swatch", {
    type: "button", "aria-pressed": String(document.documentElement.dataset.theme === name),
    onclick: (e) => {
      hooks.setTheme(name);
      for (const other of e.currentTarget.parentNode.children) other.setAttribute("aria-pressed", String(other === e.currentTarget));
    },
  }, h("i", { style: `background:${THEMES[name]}` }), name);
  const nameInput = h("input", { type: "text", value: settings.name, maxLength: 40 });
  const levels = { off: "Off: it only answers when you talk to it.", ask: "Ask: it checks in, tells you things, asks questions, and offers tasks it waits for your yes on.",
    act: "Act: the same, but it does the tasks itself and tells you after." };
  const autonomy = h("div.cards", Object.entries(levels).map(([value, about]) => h("button.card", {
    type: "button", "aria-pressed": String(settings.autonomy === value),
    onclick: async (e) => {
      try { await api.post("/settings", { autonomy: value }); } catch (err) { return toast(err.message, "bad"); }
      for (const card of e.currentTarget.parentNode.children) card.setAttribute("aria-pressed", String(card === e.currentTarget));
    },
  }, h("b", value), h("small", about))));
  const checkNow = h("button.btn", { type: "button" }, "Check in now");
  checkNow.onclick = async () => {
    checkNow.disabled = true;
    try {
      const r = await api.post("/initiative/now");
      toast(r.action === "skipped" ? `Not now: ${r.why}.` : r.action === "none" ? "It looked around and found nothing worth saying." : "It said something. See From Anexis under Chats.");
    } catch (err) { toast(err.message, "bad"); }
    checkNow.disabled = false;
  };
  const fx = h("input", { type: "checkbox", checked: document.documentElement.dataset.fx !== "off" });
  fx.onchange = () => hooks.setFx(fx.checked);
  // Only the app window can start with Windows. In a plain browser this is left out.
  let atLogin = null;
  if (window.anexisFrame?.startAtLogin) {
    const box = h("input", { type: "checkbox", checked: await window.anexisFrame.startAtLogin() });
    box.onchange = async () => { box.checked = await window.anexisFrame.startAtLogin(box.checked); };
    atLogin = h("label.check-row", box, h("div", h("b", "Open Anexis when Windows starts"),
      h("small", "It opens minimized and syncs with the school server right away, so both know the same things.")));
  }

  openSheet("App", [
    h("dl.kv",
      h("dt", "version"), h("dd", `${info.version}${info.installed ? " (installed app)" : " (running from source)"}`),
      h("dt", "app folder"), h("dd", info.folder),
      h("dt", "your data"), h("dd", `${settings.home}  (memory, keys, settings)`),
      h("dt", "workspace"), h("dd", settings.workspace),
      h("dt", "runs on"), h("dd", `${info.platform}, Python ${info.python}`),
    ),
    h("p", h("b", "Change this app without rebuilding it."), " Everything it runs is plain files in the app folder:"),
    h("ul.howto",
      h("li", h("code", `ui${sep}`), " is this screen. Save a file there and the window reloads by itself."),
      h("li", h("code", `anexis${sep}`), " is the brain. Save a Python file there and the brain restarts in a second or two. A file with a mistake in it is held back, so a working brain is never replaced by a broken one."),
      h("li", h("code", `desktop${sep}frame.js`), " is the window itself. That one needs the app closed and opened again."),
    ),
    h("div.actions",
      h("button.btn.primary", { type: "button", onclick: () => { closeSheet(); hooks.terminalAt(info.folder, "claude"); } }, "Edit with Claude"),
      h("button.btn", { type: "button", onclick: () => api.post("/files/open", { path: info.folder }).catch((e) => toast(e.message, "bad")) }, "Open app folder"),
      h("button.btn", { type: "button", onclick: () => location.reload() }, "Reload screen"),
      h("button.btn", { type: "button", onclick: async (e) => {
        e.target.disabled = true;
        setLocked(true);
        await restartBrain((line) => { status.textContent = line; });
        setLocked(false);
        e.target.disabled = false;
      } }, "Restart brain"),
    ),
    h("div.form",
      h("div.field", h("span", "Theme"), h("div.swatches", Object.keys(THEMES).map(swatch))),
      h("div.field", h("span", "On its own"), autonomy,
        h("small", "Every hour, outside 10pm to 7am, it looks at what is due, how the computer is doing and what it does not know about you yet. What it says shows up in From Anexis under Chats."),
        h("div.actions", checkNow, h("button.btn.ghost", { type: "button", onclick: () => { closeSheet(); hooks.openChat?.("inbox"); } }, "Open From Anexis"))),
      atLogin,
      h("label.check-row", fx, h("div", h("b", "Scan lines"), h("small", "The faint lines over the screen. Turn off if they bother you."))),
      h("label.field", h("span", "Name"), nameInput, h("small", "What the assistant is called.")),
    ),
    h("div.sheet-foot", status,
      h("button.btn.ghost", { type: "button", onclick: () => closeSheet() }, "Close"),
      h("button.btn.primary", { type: "button", onclick: async () => {
        const name = nameInput.value.trim();
        if (name && name !== settings.name) {
          try { await api.post("/settings", { name }); hooks.onName(name); } catch (e) { status.textContent = e.message; return; }
        }
        closeSheet();
      } }, "Done")),
  ]);
}

/** Shown when the server wants a token this window does not have. */
export function openLock(retry) {
  const input = h("input", { type: "password", placeholder: "paste the token", autocomplete: "off" });
  openSheet("Locked", [
    h("p", "This Anexis can control the whole computer, so it only answers the app. Open it from the Anexis app, or run ", h("code", "anexis ui"), " in a terminal, and this screen opens unlocked."),
    h("p", "Or paste the token from the ", h("code", ".env"), " file in the Anexis home folder (the line that starts with ANEXIS_TOKEN)."),
    h("form.form", { onsubmit: (e) => { e.preventDefault(); if (input.value.trim()) { api.setToken(input.value); closeSheet(true); retry(); } } },
      input, h("div.sheet-foot", h("button.btn.primary", { type: "submit" }, "Unlock"))),
  ], { lock: true });
}
