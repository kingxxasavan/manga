// The two side columns: the machine on the left (clock, CPU, memory, programs)
// and the network on the right (link, globe, traffic). Redrawn every two seconds
// from one request, so both always show the same moment.

import * as api from "./api.js";
import { $, bytes, duration, h } from "./dom.js";
import { initGlobe } from "./globe.js";

const KEEP = 60; // two minutes of history in the graphs
const past = { a: [], b: [], down: [], up: [] };
let ui = null, order = [];

const accent = () => getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();

function fit(canvas) {
  const ratio = devicePixelRatio || 1, w = canvas.clientWidth, hgt = canvas.clientHeight;
  if (!w || !hgt) return null;
  if (canvas.width !== Math.round(w * ratio)) { canvas.width = Math.round(w * ratio); canvas.height = Math.round(hgt * ratio); }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, w, hgt);
  return { ctx, w, hgt };
}

function spark(canvas, series, top) {
  const area = fit(canvas);
  if (!area) return;
  const { ctx, w, hgt } = area, colour = accent();
  const max = Math.max(top || 0, ...series.flat(), 1e-9), step = w / (KEEP - 1);
  series.forEach((values, n) => {
    if (values.length < 2) return;
    const start = w - (values.length - 1) * step;
    ctx.beginPath();
    values.forEach((v, i) => {
      const x = start + i * step, y = hgt - 1.5 - (v / max) * (hgt - 4);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.strokeStyle = colour;
    ctx.globalAlpha = n ? 0.45 : 1;
    ctx.lineWidth = 1.2;
    ctx.stroke();
  });
  ctx.globalAlpha = 1;
}

/** The memory grid: one dot per slice of memory, bright for what programs
 *  use, dim for what the system holds but gives back, faint for empty. The
 *  dots are shuffled once so it reads as a texture, not a bar. */
function dots(canvas, used, cached) {
  const area = fit(canvas);
  if (!area) return;
  const { ctx, w, hgt } = area, cols = 40, rows = 8, total = cols * rows;
  if (order.length !== total) {
    order = [...Array(total).keys()];
    for (let i = total - 1; i > 0; i--) { const j = (i * 7919 + 13) % (i + 1); [order[i], order[j]] = [order[j], order[i]]; }
  }
  const nUsed = Math.round(used * total), nCached = Math.round(cached * total);
  const cw = w / cols, ch = hgt / rows, size = Math.max(1.5, Math.min(cw, ch) * 0.55);
  ctx.fillStyle = accent();
  order.forEach((slot, rank) => {
    ctx.globalAlpha = rank < nUsed ? 1 : rank < nUsed + nCached ? 0.42 : 0.13;
    ctx.fillRect((slot % cols) * cw + (cw - size) / 2, Math.floor(slot / cols) * ch + (ch - size) / 2, size, size);
  });
  ctx.globalAlpha = 1;
}

const mod = (title, sub, ...body) => h("section.mod", h("h3", h("b", title), sub), ...body);
const cell = (label) => { const value = h("b", "…"); return { el: h("div", h("span", label), value), value }; };

function build() {
  const clock = h("div.clock-big");
  const day = cell("date"), up = cell("uptime"), type = cell("type"), power = cell("power");
  const cpuName = h("span"), a = h("canvas.spark"), b = h("canvas.spark");
  const aLabel = h("span"), aAvg = h("small"), bLabel = h("span"), bAvg = h("small");
  const load = cell("load"), cores = cell("cores"), tasks = cell("tasks"), gpu = cell("gpu");
  const memSub = h("span"), memDots = h("canvas.dots"), swapBar = h("div.bar", h("i")), swapText = h("b");
  const extra = h("div"), procSub = h("span"), procs = h("table.procs");
  $("#system").replaceChildren(
    mod("", "", clock),
    h("section.mod", h("div.cells", day.el, up.el, type.el, power.el)),
    mod("CPU usage", cpuName,
      h("div.graph-row", h("div", aLabel, aAvg), a), h("div.graph-row", h("div", bLabel, bAvg), b),
      h("div.cells", { style: "margin-top:6px" }, load.el, cores.el, tasks.el, gpu.el)),
    mod("Memory", memSub, memDots, h("div.line", h("span", "swap"), swapBar, swapText), extra),
    h("section.mod.mod-grow", h("h3", h("b", "Top processes"), procSub), h("div.mod-body.scroll", procs)),
  );
  $("#system > .mod:first-child > h3").remove();

  const state = h("b"), ip = cell("ipv4"), iface = cell("interface");
  const globeSub = h("span"), globe = h("canvas.globe");
  const down = cell("down"), upload = cell("up"), totals = cell("total"), traffic = h("canvas.spark");
  $("#network").replaceChildren(
    mod("Network status", h("span"), h("div.pair", h("div", h("span", "state"), state), ip.el, iface.el)),
    mod("World view", globeSub, globe),
    mod("Network traffic", h("span", "down and up"), h("div.pair", down.el, upload.el, totals.el), traffic),
  );
  return { clock, day, up, type, power, cpuName, a, b, aLabel, aAvg, bLabel, bAvg, load, cores, tasks, gpu,
    memSub, memDots, swapBar, swapText, extra, procSub, procs, state, ip, iface, globeSub,
    spin: initGlobe(globe), down, upload, totals, traffic, meters: {} };
}

function meter(key, label) {
  if (!ui.meters[key]) {
    const bar = h("div.bar", h("i")), value = h("b");
    ui.meters[key] = { bar, value };
    ui.extra.append(h("div.line", h("span", { title: label }, label), bar, value));
  }
  return ui.meters[key];
}

function tick() {
  const now = new Date(), two = (n) => String(n).padStart(2, "0");
  ui.clock.replaceChildren(two(now.getHours()), h("em", ":"), two(now.getMinutes()), h("em", ":"), two(now.getSeconds()));
  ui.day.value.textContent = now.toLocaleDateString("en-US", { month: "short", day: "numeric" }).toUpperCase();
  ui.day.value.title = now.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
}

function push(list, value) {
  list.push(value);
  if (list.length > KEEP) list.shift();
}

function draw(s) {
  const mean = (values) => (values.length ? values.reduce((x, y) => x + y, 0) / values.length : 0);
  const half = Math.ceil(s.cores.length / 2), first = s.cores.slice(0, half), second = s.cores.slice(half);
  push(past.a, mean(first));
  push(past.b, second.length ? mean(second) : mean(first));
  push(past.down, s.net.down);
  push(past.up, s.net.up);

  ui.up.value.textContent = duration(s.uptime);
  ui.type.value.textContent = s.os.split(" ")[0].replace("Windows", "win").toLowerCase();
  ui.type.value.title = `${s.host} · ${s.os}`;
  ui.power.value.textContent = s.battery ? `${Math.round(s.battery.percent)}%${s.battery.plugged ? " on" : ""}` : "on";

  ui.cpuName.textContent = s.cpu_name;
  ui.cpuName.title = s.cpu_name;
  ui.aLabel.textContent = `# 1 - ${half}`;
  ui.aAvg.textContent = `Avg. ${mean(first).toFixed(0)}%`;
  ui.bLabel.textContent = second.length ? `# ${half + 1} - ${s.cores.length}` : "all";
  ui.bAvg.textContent = `Avg. ${(second.length ? mean(second) : mean(first)).toFixed(0)}%`;
  spark(ui.a, [past.a], 100);
  spark(ui.b, [past.b], 100);
  ui.load.value.textContent = `${Math.round(s.cpu)}%`;
  ui.cores.value.textContent = s.cores.length;
  ui.tasks.value.textContent = s.process_count;
  const card = s.gpus[0];
  ui.gpu.value.textContent = card ? `${Math.round(card.percent)}% ${Math.round(card.temp)}°` : "none";
  ui.gpu.value.title = card ? `${card.name}: ${bytes(card.used)} of ${bytes(card.total)} memory` : "No Nvidia card found";

  const gib = (n) => (n / 1024 ** 3).toFixed(1);
  ui.memSub.textContent = `using ${gib(s.memory.used)} out of ${gib(s.memory.total)} GiB`;
  dots(ui.memDots, s.memory.used / s.memory.total, s.memory.cached / s.memory.total);
  const swap = s.swap.total ? s.swap.used / s.swap.total : 0;
  ui.swapBar.firstChild.style.transform = `scaleX(${swap})`;
  ui.swapText.textContent = s.swap.total ? `${gib(s.swap.used)} GiB` : "none";
  if (card) {
    const vram = meter("vram", "gpu mem");
    vram.bar.firstChild.style.transform = `scaleX(${card.used / card.total})`;
    vram.value.textContent = `${gib(card.used)} / ${gib(card.total)}`;
  }
  s.disks.slice(0, 3).forEach((disk) => {
    const m = meter(`disk:${disk.mount}`, `disk ${disk.mount}`);
    m.bar.firstChild.style.transform = `scaleX(${disk.percent / 100})`;
    m.bar.classList.toggle("hot", disk.percent >= 92);
    m.value.textContent = `${bytes(disk.total - disk.used)} free`;
  });

  ui.procSub.textContent = "pid | name | cpu | mem";
  ui.procs.replaceChildren(...s.processes.map((p) =>
    h("tr", h("td", String(p.pid)), h("td", { title: p.name }, p.name), h("td", `${p.cpu.toFixed(1)}%`), h("td", bytes(p.memory)))));

  ui.state.textContent = s.link.online ? "ONLINE" : "OFFLINE";
  ui.state.className = s.link.online ? "up" : "down";
  ui.ip.value.textContent = s.link.ip;
  ui.iface.value.textContent = s.link.iface;
  ui.iface.value.title = s.link.iface;
  ui.globeSub.textContent = s.link.online ? "link up" : "no link";
  ui.spin(s.link.online, Math.min(1, (s.net.down + s.net.up) / 400_000));
  ui.down.value.textContent = `${bytes(s.net.down)}/s`;
  ui.upload.value.textContent = `${bytes(s.net.up)}/s`;
  ui.totals.value.textContent = bytes(s.net.received + s.net.sent);
  ui.totals.value.title = `${bytes(s.net.received)} in, ${bytes(s.net.sent)} out since this computer started`;
  spark(ui.traffic, [past.down, past.up], 20_000);
}

export function initStats() {
  ui = build();
  tick();
  setInterval(tick, 1000);
  const poll = async () => {
    if (document.hidden) return;
    try { draw(await api.get("/system/stats")); } catch { /* the brain is restarting, try again next time */ }
  };
  poll();
  setInterval(poll, 2000);
}
