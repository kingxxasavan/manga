// The activity feed: every tool call Anexis makes, newest on top, as it happens.

import * as api from "./api.js";
import { $, clock, h, shortArgs } from "./dom.js";

const WORDS = { asking: "waiting for you", running: "running", done: "done", failed: "failed", declined: "declined", stopped: "stopped" };
const rows = new Map(); // one row per tool call, updated as the call moves on
let list = null, total = 0;

export function add(event) {
  const key = `${event.session_id}:${event.call}`;
  let row = rows.get(key);
  if (!row) {
    $(".empty", list)?.remove();
    const state = h("i"), out = h("pre.act-out", { hidden: true });
    const el = h("button.act", { type: "button", onclick: () => out.textContent && (out.hidden = !out.hidden) },
      h("time", clock(event.at * 1000)), h("b", event.tool), h("span", shortArgs(event.args, 200)), state);
    row = { el, state, out };
    rows.set(key, row);
    list.prepend(el, out);
    total++;
    while (list.childElementCount > 400) { list.lastChild.remove(); }
  }
  row.el.dataset.status = event.status;
  row.state.textContent = WORDS[event.status] + (event.ms !== undefined ? ` · ${event.ms < 1000 ? event.ms + " ms" : (event.ms / 1000).toFixed(1) + " s"}` : "");
  if (event.preview) row.out.textContent = event.preview;
  if (event.status === "failed") row.out.hidden = false;
  $("#activity-count").textContent = `${total} ${total === 1 ? "action" : "actions"}`;
}

export async function initActivity() {
  list = h("div.acts", h("div.empty", "Nothing yet. Every command, file change and click shows up here."));
  $("#activity").replaceChildren(list);
  try {
    for (const event of await api.get("/activity")) add(event);
  } catch { /* filled in live from here on */ }
}
