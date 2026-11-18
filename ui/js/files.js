// The files panel: look around the disk, open things, jump the terminal there.

import * as api from "./api.js";
import { $, ago, bytes, h, icon, toast } from "./dom.js";

let hooks = {};
let here = "";

async function open(path) {
  try {
    await api.post("/files/open", { path });
  } catch (e) {
    toast(e.message, "bad");
  }
}

export async function show(path = here) {
  let listing;
  try {
    listing = await api.get(`/files?path=${encodeURIComponent(path)}`);
  } catch (e) {
    if (e.status) toast(e.message, "bad");
    return;
  }
  here = listing.path;
  localStorage.setItem("anexis-folder", here);
  $("#files-crumbs").replaceChildren(h("span", { title: here }, here));
  $("#files-up").disabled = !listing.parent;
  $("#files-up").onclick = () => show(listing.parent);
  const extra = [listing.more && `${listing.more} more not shown`, listing.denied && "Windows would not let Anexis look in here"].filter(Boolean);
  $("#files-count").textContent = [`${listing.entries.length} items`, ...extra].join(" · ");
  const tiles = listing.entries.map((entry) => {
    const full = here + (here.endsWith("/") || here.endsWith("\\") ? "" : here.includes("\\") ? "\\" : "/") + entry.name;
    return h("button.tile", {
      type: "button", title: entry.dir ? full : `${full}\nDouble click to open`,
      dataset: entry.dir ? { dir: "" } : {},
      onclick: () => entry.dir && show(full),
      ondblclick: () => !entry.dir && open(full),
      onkeydown: (e) => e.key === "Enter" && !entry.dir && open(full),
    }, icon(entry.dir ? "folder" : "file"), h("b", entry.name), h("small", entry.dir ? "folder" : `${bytes(entry.size)} · ${ago(entry.modified)}`));
  });
  $("#files-tiles").replaceChildren(...(tiles.length ? tiles : [h("div.empty", listing.denied ? "Not allowed to look in here." : "Empty folder.")]));
  $("#files-tiles").scrollTop = 0;
}

export async function initFiles(options) {
  hooks = options;
  const roots = h("div.roots");
  $("#files").replaceChildren(h("div.files",
    h("div.files-bar",
      h("button.btn.ghost", { id: "files-up", type: "button", title: "Up one folder" }, "Up"),
      h("div.crumbs", { id: "files-crumbs" }),
      h("button.btn.ghost", { type: "button", title: "Open a terminal in this folder", onclick: () => hooks.terminalAt?.(here) }, "Terminal here"),
      h("button.btn.ghost", { type: "button", title: "Show this folder in the file manager", onclick: () => open(here) }, "Reveal"),
    ),
    roots,
    h("div.tiles", { id: "files-tiles" }),
  ));
  try {
    const places = await api.get("/files/roots");
    roots.replaceChildren(...places.map((place) => h("button.chip", { type: "button", title: place.path, onclick: () => show(place.path) }, place.name)));
  } catch { /* shown again after the next reconnect */ }
  await show(localStorage.getItem("anexis-folder") || "");
  if (!here) await show("");
}
