// The tools panel: the tool servers and their state, every tool Anexis can
// call, and what is due soon.

import * as api from "./api.js";
import { $, h } from "./dom.js";

const STATE = { running: "ok", starting: "warn", failed: "bad", "needs key": "warn" };
let filter = "", latest = null, due = [];

function draw() {
  if (!latest) return;
  const servers = Object.entries(latest.servers).sort(([a], [b]) => a.localeCompare(b));
  const shown = latest.tools.filter((t) => !filter || `${t.name} ${t.about} ${t.source}`.toLowerCase().includes(filter));
  const builtin = latest.tools.filter((t) => t.source === "builtin").length;
  const body = [];
  if (due.length) body.push(h("div.group.label", "due soon"), ...due.map((line) => h("div.due", line)));
  body.push(h("div.group.label", `tool servers (${servers.filter(([, s]) => s.state === "running").length} of ${servers.length} running)`));
  body.push(h("div.server", h("i.dot.ok"), h("b", "built in"), h("span", `${builtin} tools`), h("small", "shell, files, web, notes, apps, screen, keyboard and mouse")));
  for (const [name, s] of servers) {
    const detail = s.state === "running" ? `${s.tools} tools` : s.state === "needs key" ? `add ${(s.needs || []).join(", ")}` : s.state;
    body.push(h("div.server", h(`i.dot.${STATE[s.state] || ""}`), h("b", name), h("span", detail), h("small", { title: s.error || s.about }, s.error || s.about || "")));
  }
  body.push(h("div.group.label", `tools (${shown.length}${filter ? ` of ${latest.tools.length}` : ""})`));
  for (const tool of shown.slice(0, 300)) {
    body.push(h("div.tool", { title: tool.about }, h("b", tool.name),
      h(`span.tier${tool.tier === "danger" ? ".danger" : ""}`, tool.tier === "safe" ? "reads" : tool.tier === "write" ? "files" : "acts"),
      h("small", `${tool.source.replace(/^mcp:/, "")} · ${tool.about}`)));
  }
  $("#tools-list").replaceChildren(...body);
}

export async function refresh() {
  try {
    latest = await api.get("/tools");
    draw();
  } catch { /* tried again on the next round */ }
}

export function setDue(lines) {
  if (lines.join("|") === due.join("|")) return;
  due = lines;
  draw();
}

export function initTools() {
  $("#tools").replaceChildren(h("div.side",
    h("div.side-top", h("input", {
      type: "search", placeholder: "Find a tool", "aria-label": "Find a tool",
      oninput: (e) => { filter = e.target.value.trim().toLowerCase(); draw(); },
    })),
    h("div.side-list", { id: "tools-list" }),
  ));
  refresh();
  setInterval(() => !document.hidden && refresh(), 15000);
}
