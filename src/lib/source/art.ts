import type { Series } from "@/lib/types";
import { TYPE_LABEL } from "@/lib/types";
import { createRand, type Rand } from "./rand";

/**
 * Generated placeholder artwork for the demo source. Everything is plain SVG
 * built from a seed, so the repo ships no image files.
 */

interface Box { x: number; y: number; w: number; h: number }

class Doc {
  private defs: string[] = [];
  private body: string[] = [];
  private n = 0;
  constructor(readonly width: number, readonly height: number) {}

  id(): string {
    return `d${this.n++}`;
  }
  def(markup: string) {
    this.defs.push(markup);
  }
  add(markup: string) {
    this.body.push(markup);
  }
  gradient(from: string, to: string, horizontal = false): string {
    const id = this.id();
    const dir = horizontal ? 'x2="1" y2="0"' : 'x2="0" y2="1"';
    this.def(`<linearGradient id="${id}" x1="0" y1="0" ${dir}><stop offset="0" stop-color="${from}"/><stop offset="1" stop-color="${to}"/></linearGradient>`);
    return `url(#${id})`;
  }
  clip(box: Box, radius = 0): string {
    const id = this.id();
    this.def(`<clipPath id="${id}"><rect x="${box.x}" y="${box.y}" width="${box.w}" height="${box.h}" rx="${radius}"/></clipPath>`);
    return `url(#${id})`;
  }
  toString(): string {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${this.width} ${this.height}" width="${this.width}" height="${this.height}" font-family="'Helvetica Neue',Arial,sans-serif"><defs>${this.defs.join("")}</defs>${this.body.join("")}</svg>`;
  }
}

interface Palette { h: number; h2: number; mono: boolean }

function color(p: Palette, which: 1 | 2, s: number, l: number): string {
  if (p.mono) return `hsl(0 0% ${l}%)`;
  return `hsl(${which === 1 ? p.h : p.h2} ${s}% ${l}%)`;
}

function paletteFor(slug: string, mono: boolean): Palette {
  const rand = createRand(`${slug}/palette`);
  const h = rand.int(0, 359);
  return { h, h2: (h + rand.pick([30, 150, 180, 210])) % 360, mono };
}

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const f = (n: number) => Math.round(n * 10) / 10;

const SCENE_COUNT = 6;

/** Draws one illustrative scene clipped to the given box. */
function scene(doc: Doc, rand: Rand, p: Palette, box: Box, kind: number, radius = 0) {
  const { x, y, w, h } = box;
  const clip = doc.clip(box, radius);
  const g: string[] = [];
  const rect = (fill: string) => g.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}"/>`);
  const unit = Math.min(w, h);

  switch (kind % SCENE_COUNT) {
    case 0: {
      // horizon: sun over layered ridges
      rect(doc.gradient(color(p, 1, 70, 72), color(p, 2, 75, 50)));
      g.push(`<circle cx="${f(x + w * (0.25 + rand() * 0.5))}" cy="${f(y + h * 0.36)}" r="${f(unit * 0.2)}" fill="${color(p, 2, 90, 88)}"/>`);
      [34, 24, 13].forEach((l, layer) => {
        const base = y + h * (0.5 + layer * 0.14);
        const pts = [`${x},${y + h}`, `${x},${f(base)}`];
        const steps = 7;
        for (let i = 1; i < steps; i++) {
          pts.push(`${f(x + (w * i) / steps)},${f(base - rand() * h * 0.2 + (i % 2 ? 0 : h * 0.07))}`);
        }
        pts.push(`${x + w},${f(base)}`, `${x + w},${y + h}`);
        g.push(`<polygon points="${pts.join(" ")}" fill="${color(p, 1, 45, l)}"/>`);
      });
      break;
    }
    case 1: {
      // rings: a signal in the dark
      rect(color(p, 1, 45, 11));
      const cx = x + w * (0.3 + rand() * 0.4);
      const cy = y + h * (0.3 + rand() * 0.3);
      for (let i = 7; i >= 1; i--) {
        g.push(`<circle cx="${f(cx)}" cy="${f(cy)}" r="${f(unit * 0.11 * i)}" fill="none" stroke="${color(p, 2, 85, 62)}" stroke-width="${f(unit * 0.008 + i)}" opacity="${f(1 - i * 0.11)}"/>`);
      }
      g.push(`<circle cx="${f(cx)}" cy="${f(cy)}" r="${f(unit * 0.07)}" fill="${color(p, 2, 95, 78)}"/>`);
      break;
    }
    case 2: {
      // city at night
      rect(doc.gradient(color(p, 1, 55, 14), color(p, 2, 60, 40)));
      g.push(`<circle cx="${f(x + w * (0.2 + rand() * 0.6))}" cy="${f(y + h * 0.22)}" r="${f(unit * 0.1)}" fill="${color(p, 2, 40, 92)}"/>`);
      let bx = x - 10;
      while (bx < x + w) {
        const bw = unit * (0.1 + rand() * 0.14);
        const bh = h * (0.2 + rand() * 0.45);
        const by = y + h - bh;
        g.push(`<rect x="${f(bx)}" y="${f(by)}" width="${f(bw)}" height="${f(bh)}" fill="${color(p, 1, 40, 7)}"/>`);
        const cell = Math.max(bw / 4, 6);
        for (let wy = by + cell; wy < y + h - cell; wy += cell * 1.6) {
          for (let wx = bx + cell * 0.6; wx < bx + bw - cell * 0.8; wx += cell * 1.2) {
            if (rand() < 0.4) g.push(`<rect x="${f(wx)}" y="${f(wy)}" width="${f(cell * 0.5)}" height="${f(cell * 0.7)}" fill="${color(p, 2, 95, 74)}"/>`);
          }
        }
        bx += bw + 3;
      }
      break;
    }
    case 3: {
      // waves
      rect(doc.gradient(color(p, 2, 80, 82), color(p, 1, 70, 62)));
      g.push(`<circle cx="${f(x + w * 0.72)}" cy="${f(y + h * 0.24)}" r="${f(unit * 0.12)}" fill="${color(p, 2, 95, 94)}" opacity="0.9"/>`);
      [58, 44, 30, 18].forEach((l, i) => {
        const base = y + h * (0.42 + i * 0.15);
        const amp = h * 0.045;
        const seg = w / 4;
        const shift = rand() * seg;
        let d = `M${x - seg} ${f(base)}`;
        for (let sx = x - seg + shift; sx < x + w + seg; sx += seg) {
          d += ` q${f(seg / 4)} ${f(-amp)} ${f(seg / 2)} 0 t${f(seg / 2)} 0`;
        }
        d += ` V${y + h} H${x - seg} Z`;
        g.push(`<path d="${d}" fill="${color(p, 1, 60, l)}"/>`);
      });
      break;
    }
    case 4: {
      // speed lines converging on a figure
      rect(color(p, 2, 80, 90));
      const cx = x + w * (0.35 + rand() * 0.3);
      const cy = y + h * (0.4 + rand() * 0.2);
      const reach = Math.hypot(w, h);
      const count = 46;
      for (let i = 0; i < count; i++) {
        const a = (i / count) * Math.PI * 2 + rand() * 0.08;
        const spread = 0.012 + rand() * 0.02;
        const inner = unit * (0.24 + rand() * 0.18);
        const p1 = `${f(cx + Math.cos(a) * inner)},${f(cy + Math.sin(a) * inner)}`;
        const p2 = `${f(cx + Math.cos(a - spread) * reach)},${f(cy + Math.sin(a - spread) * reach)}`;
        const p3 = `${f(cx + Math.cos(a + spread) * reach)},${f(cy + Math.sin(a + spread) * reach)}`;
        g.push(`<polygon points="${p1} ${p2} ${p3}" fill="${color(p, 1, 60, 16)}"/>`);
      }
      g.push(`<ellipse cx="${f(cx)}" cy="${f(cy + unit * 0.12)}" rx="${f(unit * 0.11)}" ry="${f(unit * 0.2)}" fill="${color(p, 1, 50, 12)}"/>`);
      g.push(`<circle cx="${f(cx)}" cy="${f(cy - unit * 0.12)}" r="${f(unit * 0.075)}" fill="${color(p, 1, 50, 12)}"/>`);
      break;
    }
    default: {
      // soft lights
      rect(doc.gradient(color(p, 1, 60, 30), color(p, 2, 70, 58), true));
      for (let i = 0; i < 16; i++) {
        g.push(`<circle cx="${f(x + rand() * w)}" cy="${f(y + rand() * h)}" r="${f(unit * (0.04 + rand() * 0.16))}" fill="${color(p, rand() < 0.5 ? 1 : 2, 85, 78)}" opacity="${f(0.12 + rand() * 0.3)}"/>`);
      }
      const fx = x + w * (0.3 + rand() * 0.4);
      g.push(`<ellipse cx="${f(fx)}" cy="${f(y + h * 0.95)}" rx="${f(unit * 0.16)}" ry="${f(h * 0.3)}" fill="${color(p, 1, 40, 10)}"/>`);
      g.push(`<circle cx="${f(fx)}" cy="${f(y + h * 0.56)}" r="${f(unit * 0.085)}" fill="${color(p, 1, 40, 10)}"/>`);
    }
  }
  doc.add(`<g clip-path="${clip}">${g.join("")}</g>`);
}

const LINES = [
  "Wait.", "Not yet.", "Did you hear that?", "Run!", "I knew it.", "Again?", "Too late.",
  "Look up.", "Stay close.", "It's here.", "Trust me.", "One more.", "...", "Who are you?",
];

function bubble(doc: Doc, rand: Rand, box: Box) {
  const text = rand.pick(LINES);
  const size = Math.max(18, Math.min(30, box.w * 0.055));
  const rx = Math.max(text.length * size * 0.32 + size, size * 2.4);
  const ry = size * 1.7;
  if (rx * 2 > box.w - 16 || ry * 2 > box.h - 16) return;
  const cx = box.x + rx + 10 + rand() * (box.w - rx * 2 - 20);
  const cy = box.y + ry + 10 + rand() * Math.min(box.h * 0.35, box.h - ry * 2 - 20);
  const tail = `${f(cx - size * 0.5)},${f(cy + ry * 0.8)} ${f(cx - size * 0.9)},${f(cy + ry + size * 0.9)} ${f(cx + size * 0.3)},${f(cy + ry * 0.9)}`;
  doc.add(
    `<polygon points="${tail}" fill="#fff" stroke="#111" stroke-width="3" stroke-linejoin="round"/>` +
    `<ellipse cx="${f(cx)}" cy="${f(cy)}" rx="${f(rx)}" ry="${f(ry)}" fill="#fff" stroke="#111" stroke-width="3"/>` +
    `<polygon points="${f(cx - size * 0.42)},${f(cy + ry * 0.7)} ${f(cx - size * 0.8)},${f(cy + ry + size * 0.6)} ${f(cx + size * 0.2)},${f(cy + ry * 0.8)}" fill="#fff"/>` +
    `<text x="${f(cx)}" y="${f(cy + size * 0.35)}" text-anchor="middle" font-size="${f(size)}" font-weight="700" fill="#111">${esc(text)}</text>`,
  );
}

function wrap(title: string, maxChars: number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of title.split(" ")) {
    if (line && (line + " " + word).length > maxChars) {
      lines.push(line);
      line = word;
    } else {
      line = line ? `${line} ${word}` : word;
    }
  }
  if (line) lines.push(line);
  return lines;
}

export function renderCover(series: Series): string {
  const W = 600, H = 900;
  const doc = new Doc(W, H);
  const rand = createRand(`${series.slug}/cover`);
  const p = paletteFor(series.slug, false);
  scene(doc, rand, p, { x: 0, y: 0, w: W, h: H }, rand.int(0, SCENE_COUNT - 1));

  const scrimId = doc.id();
  doc.def(`<linearGradient id="${scrimId}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.88"/></linearGradient>`);
  doc.add(`<rect y="${H * 0.42}" width="${W}" height="${H * 0.58}" fill="url(#${scrimId})"/>`);

  const lines = wrap(series.title.toUpperCase(), 13);
  // Size the title so its longest line always fits inside the cover.
  const longest = Math.max(...lines.map((l) => l.length));
  const byLines = lines.length > 3 ? 54 : lines.length === 3 ? 62 : 72;
  const size = Math.floor(Math.min(byLines, (W - 88) / (longest * 0.68)));
  const startY = H - 96 - (lines.length - 1) * size * 1.02;
  lines.forEach((line, i) => {
    doc.add(`<text x="44" y="${f(startY + i * size * 1.02)}" font-size="${size}" font-weight="900" letter-spacing="-1.5" fill="#fff">${esc(line)}</text>`);
  });
  doc.add(`<rect x="44" y="${H - 74}" width="56" height="5" rx="2.5" fill="${color(p, 2, 95, 66)}"/>`);
  doc.add(`<text x="44" y="${H - 38}" font-size="24" font-weight="600" fill="#fff" opacity="0.85">${esc(series.author)}</text>`);
  doc.add(`<text x="44" y="64" font-size="20" font-weight="800" letter-spacing="5" fill="#fff" opacity="0.9">${TYPE_LABEL[series.type].toUpperCase()}</text>`);
  return doc.toString();
}

function titleBlock(doc: Doc, series: Series, chapter: number, box: Box, dark: boolean) {
  const lines = wrap(series.title, 18);
  const size = 54;
  const ink = dark ? "#fff" : "#111";
  const cy = box.y + box.h / 2 - ((lines.length - 1) * size) / 2;
  doc.add(`<text x="${box.x + box.w / 2}" y="${f(cy - size * 1.3)}" text-anchor="middle" font-size="22" font-weight="700" letter-spacing="8" fill="${ink}" opacity="0.7">CHAPTER ${chapter}</text>`);
  lines.forEach((line, i) => {
    doc.add(`<text x="${box.x + box.w / 2}" y="${f(cy + i * size * 1.08)}" text-anchor="middle" font-size="${size}" font-weight="900" letter-spacing="-1" fill="${ink}">${esc(line)}</text>`);
  });
}

function renderBookPage(series: Series, chapter: number, index: number): string {
  const W = 800, H = 1200, M = 36, GAP = 14;
  const doc = new Doc(W, H);
  const rand = createRand(`${series.slug}/${chapter}/${index}`);
  const p = paletteFor(series.slug, true);
  doc.add(`<rect width="${W}" height="${H}" fill="#fdfdfb"/>`);

  if (index === 0) {
    const art = { x: M, y: M, w: W - M * 2, h: H * 0.6 };
    scene(doc, rand, p, art, rand.int(0, SCENE_COUNT - 1));
    doc.add(`<rect x="${art.x}" y="${art.y}" width="${art.w}" height="${art.h}" fill="none" stroke="#111" stroke-width="5"/>`);
    titleBlock(doc, series, chapter, { x: M, y: art.y + art.h, w: W - M * 2, h: H - art.h - M * 2 }, false);
  } else {
    const rows = rand.int(2, 4);
    const weights = Array.from({ length: rows }, () => 0.7 + rand());
    const total = weights.reduce((a, b) => a + b, 0);
    const usable = H - M * 2 - 30 - GAP * (rows - 1);
    let y = M;
    for (const weight of weights) {
      const h = (usable * weight) / total;
      const cols = rand.int(1, rows > 3 ? 2 : 3);
      const split = Array.from({ length: cols }, () => 0.6 + rand());
      const splitTotal = split.reduce((a, b) => a + b, 0);
      let x = M;
      for (const part of split) {
        const w = ((W - M * 2 - GAP * (cols - 1)) * part) / splitTotal;
        const box = { x: f(x), y: f(y), w: f(w), h: f(h) };
        scene(doc, rand, p, box, rand.int(0, SCENE_COUNT - 1));
        doc.add(`<rect x="${box.x}" y="${box.y}" width="${box.w}" height="${box.h}" fill="none" stroke="#111" stroke-width="5"/>`);
        if (rand() < 0.7) bubble(doc, rand, box);
        x += w + GAP;
      }
      y += h + GAP;
    }
  }
  doc.add(`<text x="${W / 2}" y="${H - 22}" text-anchor="middle" font-size="18" font-weight="600" fill="#555">${index + 1}</text>`);
  return doc.toString();
}

function renderStripPage(series: Series, chapter: number, index: number): string {
  const W = 800, H = 1800;
  const doc = new Doc(W, H);
  const rand = createRand(`${series.slug}/${chapter}/${index}`);
  const p = paletteFor(series.slug, false);
  const dark = createRand(`${series.slug}/paper`)() < 0.5;
  doc.add(`<rect width="${W}" height="${H}" fill="${dark ? `hsl(${p.h} 22% 7%)` : "#fbfaf7"}"/>`);

  let y = 60;
  if (index === 0) {
    const art = { x: 0, y: 0, w: W, h: 760 };
    scene(doc, rand, p, art, rand.int(0, SCENE_COUNT - 1));
    titleBlock(doc, series, chapter, { x: 0, y: 760, w: W, h: 300 }, dark);
    y = 1090;
  }
  while (y < H - 220) {
    const inset = rand.pick([0, 0, 40, 70]);
    const h = Math.min(rand.int(300, 620), H - y - 60);
    if (h < 200) break;
    const box = { x: inset, y, w: W - inset * 2, h };
    scene(doc, rand, p, box, rand.int(0, SCENE_COUNT - 1), inset ? 10 : 0);
    if (rand() < 0.75) bubble(doc, rand, box);
    y += h + rand.int(50, 130);
  }
  return doc.toString();
}

export function renderPage(series: Series, chapter: number, index: number): string {
  return series.type === "manga"
    ? renderBookPage(series, chapter, index)
    : renderStripPage(series, chapter, index);
}
