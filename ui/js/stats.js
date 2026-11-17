// The system panel: live numbers about this machine, redrawn every two seconds.

import * as api from "./api.js";
import { $, bytes, duration, h } from "./dom.js";

const KEEP = 60; // two minutes of history in the little graphs
const cpuPast = [], downPast = [];
let parts = null;

function spark(canvas, values, top) {
  const ratio = devicePixelRatio || 1;
  const w = canvas.clientWidth, hgt = canvas.clientHeight;
  if (!w || !hgt) return;
  if (canvas.width !== w * ratio) { canvas.width = w * ratio; canvas.height = hgt * ratio; }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, w, hgt);
  if (values.length < 2) return;
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
  const max = Math.max(top || 0, ...values, 1e-9), step = w / (KEEP - 1), start = w - (values.length - 1) * step;
  ctx.beginPath();
  values.forEach((v, i) => {
    const x = start + i * step, y = hgt - 2 - (v / max) * (hgt - 6);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.strokeStyle = accent;
  ctx.lineWidth = 1.5;
  ctx.shadowColor = accent;
  ctx.shadowBlur = 6;
  ctx.stroke();
  ctx.shadowBlur = 0;
  ctx.lineTo(w, hgt);
  ctx.lineTo(start, hgt);
  ctx.closePath();
  const fill = ctx.createLinearGradient(0, 0, 0, hgt);
  fill.addColorStop(0, accent + "55");
  fill.addColorStop(1, accent + "00");
  ctx.fillStyle = fill;
  ctx.fill();
}

function meter(label) {
  const value = h("span"), bar = h("i");
  const el = h("div.meter", h("span.label", label), value, h("div.bar", bar));
  return { el, set(text, percent) {
    value.textContent = text;
    bar.style.transform = `scaleX(${Math.min(1, Math.max(0, percent / 100))})`;
    el.classList.toggle("hot", percent >= 90);
  } };
}

function build(root) {
  const cpu = h("b"), cpuGraph = h("canvas.spark"), cores = h("div.cores");
  const memory = meter("memory"), swap = meter("swap");
  const gpus = h("div.sys"), disks = h("div.sys");
  const up = h("b"), down = h("b"), netGraph = h("canvas.spark");
  const procs = h("table.procs"), foot = h("div.sys-foot");
  root.replaceChildren(h("div.sys",
    h("div", h("div.sys-head", h("span.label", "cpu"), cpu), cpuGraph, cores),
    memory.el, swap.el, gpus, disks,
    h("div", h("div.net", h("div", h("span.label", "down"), down), h("div", h("span.label", "up"), up)), netGraph),
    h("div", h("div.label", { style: "margin-bottom:4px" }, "busiest programs"), procs),
    foot,
  ));
  return { cpu, cpuGraph, cores, memory, swap, gpus, disks, up, down, netGraph, procs, foot, meters: {} };
}

function named(group, key, label) {
  const store = parts.meters;
  if (!store[key]) {
    store[key] = meter(label);
    group.append(store[key].el);
  }
  return store[key];
}

function draw(s) {
  $("#sys-host").textContent = `${s.host} · ${s.os}`;
  parts.cpu.replaceChildren(String(Math.round(s.cpu)), h("small", "%"));
  cpuPast.push(s.cpu);
  downPast.push(s.net.down);
  if (cpuPast.length > KEEP) cpuPast.shift();
  if (downPast.length > KEEP) downPast.shift();
  spark(parts.cpuGraph, cpuPast, 100);
  spark(parts.netGraph, downPast, 50_000);

  if (parts.cores.childElementCount !== s.cores.length) parts.cores.replaceChildren(...s.cores.map(() => h("i")));
  s.cores.forEach((load, i) => { parts.cores.children[i].style.height = `${Math.max(6, load)}%`; });

  parts.memory.set(`${bytes(s.memory.used)} / ${bytes(s.memory.total)}`, s.memory.percent);
  parts.swap.el.hidden = !s.swap.total;
  if (s.swap.total) parts.swap.set(`${bytes(s.swap.used)} / ${bytes(s.swap.total)}`, (s.swap.used / s.swap.total) * 100);
  s.gpus.forEach((gpu, i) => {
    named(parts.gpus, `gpu${i}`, `gpu ${gpu.name.replace(/^NVIDIA\s+/i, "")}`).set(`${Math.round(gpu.percent)}% · ${Math.round(gpu.temp)}°C`, gpu.percent);
    named(parts.gpus, `vram${i}`, "gpu memory").set(`${bytes(gpu.used)} / ${bytes(gpu.total)}`, (gpu.used / gpu.total) * 100);
  });
  parts.gpus.hidden = !s.gpus.length;
  s.disks.forEach((disk) => named(parts.disks, `disk:${disk.mount}`, `disk ${disk.mount}`).set(`${bytes(disk.total - disk.used)} free`, disk.percent));

  parts.down.textContent = `${bytes(s.net.down)}/s`;
  parts.up.textContent = `${bytes(s.net.up)}/s`;
  parts.procs.replaceChildren(...s.processes.slice(0, 6).map((p) =>
    h("tr", h("td", { title: `pid ${p.pid}` }, p.name), h("td", `${p.cpu.toFixed(1)}%`), h("td", bytes(p.memory)))));
  const battery = s.battery ? `battery ${Math.round(s.battery.percent)}%${s.battery.plugged ? " ⚡" : ""}` : "";
  parts.foot.replaceChildren(h("span", `up ${duration(s.uptime)}`), h("span", battery || `${s.process_count} programs`));
}

export function initStats() {
  parts = build($("#system"));
  const tick = async () => {
    if (!document.hidden) {
      try { draw(await api.get("/system/stats")); } catch { /* the brain is restarting, try again next time */ }
    }
  };
  tick();
  setInterval(tick, 2000);
}
