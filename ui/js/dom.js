// Small helpers every panel uses. No framework: the deck is plain DOM.

/** h("div.card", {onclick}, "text", child) builds an element. */
export function h(spec, attrs, ...children) {
  const [tag, ...classes] = spec.split(".");
  const el = document.createElement(tag || "div");
  if (classes.length) el.className = classes.join(" ");
  if (attrs && (typeof attrs !== "object" || attrs instanceof Node || Array.isArray(attrs))) {
    children.unshift(attrs);
    attrs = null;
  }
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key in el && key !== "list") el[key] = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  el.append(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
  return el;
}

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

export function bytes(n) {
  if (!Number.isFinite(n)) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n >= 100 || i === 0 ? Math.round(n) : n.toFixed(1)} ${units[i]}`;
}

export function duration(seconds) {
  const d = Math.floor(seconds / 86400), hrs = Math.floor((seconds % 86400) / 3600), m = Math.floor((seconds % 3600) / 60);
  return d ? `${d}d ${hrs}h` : hrs ? `${hrs}h ${m}m` : `${m}m`;
}

export function clock(at = Date.now()) {
  return new Date(at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

export function ago(at) {
  const s = Math.max(0, Date.now() / 1000 - at);
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(at * 1000).toLocaleDateString([], { month: "short", day: "numeric", year: s > 3e7 ? "numeric" : undefined });
}

/** A tool call's arguments squeezed onto one line. */
export function shortArgs(args, limit = 140) {
  if (!args || typeof args !== "object") return "";
  const parts = Object.entries(args).map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`);
  const line = parts.join("  ").replace(/\s+/g, " ");
  return line.length > limit ? line.slice(0, limit - 1) + "…" : line;
}

export function toast(message, kind = "") {
  const el = h(`div.toast${kind ? "." + kind : ""}`, message);
  $("#toasts").append(el);
  setTimeout(() => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 300);
  }, kind === "bad" ? 7000 : 3500);
}

const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function inline(text) {
  return escapeHtml(text)
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>")
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noreferrer">$2</a>');
}

/** Enough markdown for chat replies: code blocks, lists, headings, bold,
 *  inline code and links. Everything is escaped first, so a reply can never
 *  put live HTML on the page. */
export function markdown(source) {
  const out = [];
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  let i = 0, para = [];
  const flush = () => { if (para.length) { out.push(`<p>${para.map(inline).join("<br>")}</p>`); para = []; } };
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*```/.test(line)) {
      flush();
      const body = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) body.push(lines[i++]);
      i++;
      out.push(`<pre><code>${escapeHtml(body.join("\n"))}</code></pre>`);
      continue;
    }
    const heading = line.match(/^#{1,6}\s+(.*)/);
    if (heading) { flush(); out.push(`<h3>${inline(heading[1])}</h3>`); i++; continue; }
    const item = /^\s*([-*+]|\d+[.)])\s+/;
    if (item.test(line)) {
      flush();
      const ordered = /^\s*\d/.test(line), items = [];
      while (i < lines.length && item.test(lines[i])) items.push(`<li>${inline(lines[i++].replace(item, ""))}</li>`);
      out.push(ordered ? `<ol>${items.join("")}</ol>` : `<ul>${items.join("")}</ul>`);
      continue;
    }
    if (!line.trim()) flush(); else para.push(line);
    i++;
  }
  flush();
  return out.join("");
}

export const ICONS = {
  folder: '<svg viewBox="0 0 24 24" width="18" height="18"><path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.6l2 2.2h8.4A1.5 1.5 0 0 1 21 8.7v9.8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5v-12Z" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  file: '<svg viewBox="0 0 24 24" width="18" height="18"><path d="M6.5 3h7.2L19 8.3v11.2A1.5 1.5 0 0 1 17.500 21h-11A1.5 1.5 0 0 1 5 19.5v-15A1.5 1.5 0 0 1 6.5 3Zm7 .4V8.5h5" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
};

export function icon(name) {
  const span = h("span");
  span.innerHTML = ICONS[name];
  return span.firstChild;
}
