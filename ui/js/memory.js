// The memory panel: what Anexis remembers about you. Search it, add to it,
// delete from it, and see which memories shaped the last reply.

import * as api from "./api.js";
import { $, h, toast } from "./dom.js";

const KINDS = ["all", "fact", "preference", "habit", "project", "class", "person", "task", "lesson"];
let kind = "all", query = "", used = new Set(), list = null, timer = 0;

function row(m) {
  const forget = h("button", { type: "button", title: "Delete this memory for good" }, "forget");
  forget.onclick = async () => {
    if (!forget.dataset.sure) {  // first click arms it, second click deletes
      forget.dataset.sure = "1";
      forget.textContent = "sure?";
      setTimeout(() => { delete forget.dataset.sure; forget.textContent = "forget"; }, 3000);
      return;
    }
    await remove(m.id);
  };
  const sure = Math.round(m.confidence * 100);
  return h(`div.mem${used.has(m.id) ? ".used" : ""}`,
    h("span.id", `#${m.id}`), h("span.text", m.text), forget,
    h("span.meta", h("b", m.kind), `  ${sure}% sure${m.pinned ? " · about me" : ""}${m.use_count ? ` · used ${m.use_count}×` : ""}`));
}

export async function refresh() {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  else if (kind !== "all") params.set("kind", kind);
  let rows;
  try {
    rows = await api.get(`/memory?${params}`);
  } catch { return; }
  if (query && kind !== "all") rows = rows.filter((m) => m.kind === kind);
  list.replaceChildren(...(rows.length ? rows.map(row) : [h("div.empty", query ? "Nothing found." : "Nothing remembered yet. It learns as you talk.")]));
}

export async function remember(text) {
  try {
    const saved = await api.post("/memory", { text });
    toast(`Saved as #${saved.id}.`);
    refresh();
  } catch (e) {
    toast(e.message, "bad");
  }
}

export async function remove(id) {
  try {
    const { forgotten } = await api.del(`/memory/${id}`);
    toast(forgotten ? `Forgot #${id}.` : `No memory #${id}.`, forgotten ? "" : "bad");
    refresh();
  } catch (e) {
    toast(e.message, "bad");
  }
}

export function search(words) {
  query = words;
  $("#mem-search").value = words;
  refresh();
}

/** Marks the memories the last reply was built from. */
export function markUsed(ids) {
  used = new Set(ids);
  refresh();
}

export function initMemory() {
  list = h("div.side-list");
  const add = h("input", { type: "text", placeholder: "Remember this about me...", "aria-label": "Something to remember" });
  $("#memory").replaceChildren(h("div.side",
    h("div.side-top",
      h("input", {
        id: "mem-search", type: "search", placeholder: "Search memory", "aria-label": "Search memory",
        oninput: (e) => { clearTimeout(timer); timer = setTimeout(() => { query = e.target.value.trim(); refresh(); }, 220); },
      }),
      h("div.kinds", KINDS.map((k) => h("button.chip", {
        type: "button", "aria-pressed": String(k === kind),
        onclick: (e) => {
          kind = k;
          for (const chip of e.target.parentNode.children) chip.setAttribute("aria-pressed", String(chip === e.target));
          refresh();
        },
      }, k))),
    ),
    list,
    h("form.side-foot", { onsubmit: (e) => { e.preventDefault(); if (add.value.trim()) { remember(add.value.trim()); add.value = ""; } } },
      add, h("button.btn", { type: "submit" }, "Save")),
  ));
  document.addEventListener("anexis:memory-changed", refresh);
  refresh();
}
