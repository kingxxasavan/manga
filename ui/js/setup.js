// Setup: the first thing a new install shows, and the Setup button after that.
// Four short pages, then it saves, downloads what was picked and restarts
// the brain so everything is live.

import * as api from "./api.js";
import { h } from "./dom.js";
import { closeSheet, keyFields, openSheet, restartBrain, setLocked } from "./overlays.js";

const TITLES = ["Pick a preset", "Options", "Downloads", "Keys"];
const STEP_NAMES = { ollama: "Ollama", models: "Models", claude: "Claude Code", tools: "Tool servers", voice: "Voice" };

export async function openSetup() {
  let state;
  try {
    state = await api.get("/setup");
  } catch (e) {
    return openSheet("Setup", h("p", e.message));
  }
  const choice = {
    preset: state.preset || state.best,
    name: state.name,
    control: state.done ? state.control : "full",
    voice: true,   // the JARVIS voice is the main way to use Anexis
    install: { ollama: true, claude: !state.machine.claude, tools: true },
  };
  let page = 0;
  const fields = keyFields(state.keys);
  const preset = () => state.presets.find((p) => p.name === choice.preset);

  const pages = [
    () => [
      h("p", `${state.machine.summary} Pick how Anexis should run. You can change it later.`),
      h("div.cards", state.presets.map((p) => h("button.card", {
        type: "button", "aria-pressed": String(p.name === choice.preset),
        onclick: () => { choice.preset = p.name; choice.voice ||= p.voice; draw(); },
      }, h("b", p.title), p.name === state.best ? h("em", "best fit for this PC") : null, h("small", p.blurb),
      p.models.length ? h("small", `Local models: ${p.models.join(", ")}`) : null))),
    ],
    () => {
      const name = h("input", { type: "text", value: choice.name, maxLength: 40, oninput: (e) => { choice.name = e.target.value; } });
      const control = (value, title, about) => h("button.card", {
        type: "button", "aria-pressed": String(choice.control === value), onclick: () => { choice.control = value; draw(); },
      }, h("b", title), h("small", about));
      const voice = h("input", { type: "checkbox", checked: choice.voice, onchange: (e) => { choice.voice = e.target.checked; } });
      return [
        h("div.form",
          h("label.field", h("span", "Name"), name, h("small", "What you want to call it.")),
          h("div.field", h("span", "Control of this computer"), h("div.cards",
            control("full", "Full control", "Runs commands, opens apps, changes files, uses the keyboard and mouse without asking. Every action shows in the Activity panel and STOP ends it."),
            control("ask", "Ask first", "Reading and searching just run. Anything that changes the computer waits for your yes."))),
          h("label.check-row", voice, h("div", h("b", "Voice"), h("small", state.machine.voice ? "The JARVIS voice is installed. JARVIS listens for its name." : "The JARVIS voice: say \"Jarvis\" and talk. Runs on this computer. A download of a few GB, once."))),
        ),
      ];
    },
    () => {
      const models = preset().models;
      const box = (key, title, about, disabled) => {
        const input = h("input", { type: "checkbox", checked: Boolean(choice.install[key]) && !disabled, disabled,
          onchange: (e) => { choice.install[key] = e.target.checked; } });
        return h("label.check-row", input, h("div", h("b", title), h("small", about)));
      };
      const rows = [];
      if (models.length) {
        const cannot = !state.machine.ollama && !state.windows;
        rows.push(box("ollama", state.machine.ollama ? "Download the models" : "Install Ollama and download the models",
          cannot ? "Ollama is not installed and on Linux it needs your password. Run: curl -fsSL https://ollama.com/install.sh | sh  and then open Setup again."
                 : `${models.join(", ")}. Several GB, so this is the slow one.`, cannot));
      }
      rows.push(box("claude", "Claude Code", state.machine.claude ? "Already installed." : "So Claude writes your code. Without it Anexis uses its own coder model.", state.machine.claude));
      rows.push(box("tools", "Tool servers", "Files, git, web search, Wikipedia, browser, Word, Excel and more. Downloads the pinned versions."));
      return [h("p", "What to download now. Untick anything you want to skip, Setup can be opened again any time."), h("div.form", rows)];
    },
    () => [
      h("p", choice.preset === "cloud"
        ? "The cloud preset runs on Nvidia, so the Nvidia key is the one you need. The rest are optional."
        : "All optional. Each key turns one thing on. Leave empty to skip. They stay on this computer."),
      fields.el,
    ],
  ];

  function draw() {
    const back = h("button.btn.ghost", { type: "button", onclick: () => { page--; draw(); } }, "Back");
    const next = h("button.btn.primary", { type: "button", onclick: () => { if (page === pages.length - 1) finish(); else { page++; draw(); } } },
      page === pages.length - 1 ? "Save and set up" : "Next");
    openSheet(`Setup · ${TITLES[page]}`, [
      h("div.steps", TITLES.map((_, i) => h(`span${i <= page ? ".on" : ""}`))),
      ...pages[page](),
      h("div.sheet-foot", h("span.left", `Step ${page + 1} of ${pages.length}`), page ? back : null, next),
    ]);
    next.focus();
  }

  async function finish() {
    const models = preset().models;
    const wanted = {
      ollama: Boolean(models.length && choice.install.ollama),
      models: models.length && choice.install.ollama ? models : [],
      claude: Boolean(choice.install.claude) && !state.machine.claude,
      tools: Boolean(choice.install.tools),
      voice: choice.voice && !state.machine.voice,
    };
    const order = ["ollama", "models", "claude", "tools", "voice"].filter((k) => (k === "models" ? wanted.models.length : wanted[k]));
    const rows = new Map(order.map((key) => {
      const detail = h("small", "waiting"), bar = h("i");
      const el = h("div.inst", h("span.mark", "■"), h("b", STEP_NAMES[key]), detail, h("div.bar", bar));
      return [key, { el, detail, bar }];
    }));
    const saving = h("div.inst", { dataset: { state: "start" } }, h("span.mark", "■"), h("b", "Settings and keys"), h("small", "saving"));
    const restart = h("div.inst", h("span.mark", "■"), h("b", "Start the brain with the new settings"), h("small", "after the downloads"));
    const foot = h("div.sheet-foot");
    openSheet("Setup · Working", [
      h("p", "You can leave this running. Nothing here needs you until it says done."),
      saving, ...[...rows.values()].map((r) => r.el), restart, foot,
    ], { lock: true });

    const fail = (row, message) => { row.dataset.state = "failed"; row.querySelector("small").textContent = message; };
    let warnings = {};
    try {
      const reply = await api.post("/setup", {
        preset: choice.preset, name: choice.name.trim() || "Anexis", control: choice.control, voice: choice.voice, keys: fields.values(),
      });
      warnings = reply.warnings;
      for (const [provider, roles] of Object.entries(reply.healed || {})) {
        for (const [role, [old, now]] of Object.entries(roles)) {
          if (now) warnings[`${provider} ${role} model`] = `${old || "none"} is not offered any more, so ${now} is used. Change it under Models.`;
        }
      }
      saving.dataset.state = "done";
      saving.querySelector("small").textContent = reply.backup ? `saved. Your old settings are kept as ${reply.backup}` : "saved";
    } catch (e) {
      fail(saving, e.message);
      setLocked(false);
      foot.replaceChildren(h("button.btn", { type: "button", onclick: draw }, "Back"));
      return;
    }

    let allOk = true;
    if (order.length) {
      try {
        await api.stream("POST", "/setup/install", wanted, (event) => {
          const row = rows.get(event.step);
          if (!row) { if (event.state === "finished") allOk = event.ok; return; }
          row.el.dataset.state = event.state;
          if (event.line) row.detail.textContent = event.line;
          if (event.message) row.detail.textContent = event.message;
          if (event.percent !== undefined) row.bar.style.transform = `scaleX(${event.percent / 100})`;
          if (event.state === "done") row.bar.style.transform = "scaleX(1)";
          if (event.state === "skipped") row.detail.textContent = `skipped: ${event.message}`;
        });
      } catch (e) {
        allOk = false;
        for (const row of rows.values()) if (!["done", "failed", "skipped"].includes(row.el.dataset.state)) fail(row.el, e.message);
      }
    }

    restart.dataset.state = "start";
    const up = await restartBrain((line) => { restart.querySelector("small").textContent = line; });
    restart.dataset.state = up ? "done" : "failed";
    setLocked(false);
    const notes = Object.entries(warnings).map(([env, text]) => h("p", `${env}: ${text}`));
    foot.before(...notes, h("p", allOk && up
      ? "All set. Say hi, or open About me so it knows who you are."
      : "Some parts did not finish. Anexis works with what did. Open Setup again to retry the rest, or Checkup to see what is missing."));
    foot.replaceChildren(h("button.btn.primary", { type: "button", onclick: () => { closeSheet(true); location.reload(); } }, "Done"));
    foot.querySelector("button").focus();
  }

  draw();
}
