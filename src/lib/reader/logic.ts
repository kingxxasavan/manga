import type { SeriesType } from "@/lib/types";

export type Mode = "strip" | "single" | "double";
export type Direction = "rtl" | "ltr";
export type Fit = "width" | "height" | "original";
export type Background = "black" | "dark" | "sepia" | "white";

export interface ReaderSettings {
  mode: Mode | "auto";
  direction: Direction | "auto";
  fit: Fit;
  /** Width of the strip as a percentage of the reading column, 40 to 100 */
  zoom: number;
  /** Gap between pages in strip mode, in pixels */
  gap: number;
  background: Background;
  autoContinue: boolean;
}

export const DEFAULT_SETTINGS: ReaderSettings = {
  mode: "auto",
  direction: "auto",
  fit: "height",
  zoom: 100,
  gap: 0,
  background: "dark",
  autoContinue: false,
};

export const BACKGROUNDS: Record<Background, { label: string; color: string; dark: boolean }> = {
  black: { label: "Black", color: "#000000", dark: true },
  dark: { label: "Dark grey", color: "#17181c", dark: true },
  sepia: { label: "Sepia", color: "#efe4cb", dark: false },
  white: { label: "White", color: "#ffffff", dark: false },
};

/** Webtoon style series read best as a strip, manga as right to left pages. */
export function resolveMode(setting: ReaderSettings["mode"], type: SeriesType): Mode {
  if (setting !== "auto") return setting;
  return type === "manga" ? "single" : "strip";
}

export function resolveDirection(setting: ReaderSettings["direction"], type: SeriesType): Direction {
  if (setting !== "auto") return setting;
  return type === "manga" ? "rtl" : "ltr";
}

/** Page groups for double page mode. The first page stands alone like a cover. */
export function spreads(total: number): number[][] {
  const out: number[][] = [];
  if (total <= 0) return out;
  out.push([0]);
  for (let i = 1; i < total; i += 2) {
    out.push(i + 1 < total ? [i, i + 1] : [i]);
  }
  return out;
}

export function spreadFor(page: number, total: number): number[] {
  return spreads(total).find((s) => s.includes(page)) ?? [];
}

export type StepResult =
  | { kind: "page"; page: number }
  | { kind: "end" }
  | { kind: "start" };

/** Move forward (+1) or back (-1) from a page. Reports when a chapter edge is crossed. */
export function step(mode: Mode, page: number, total: number, delta: 1 | -1): StepResult {
  if (total <= 0) return { kind: delta === 1 ? "end" : "start" };
  if (mode === "double") {
    const all = spreads(total);
    const index = all.findIndex((s) => s.includes(page)) + delta;
    if (index < 0) return { kind: "start" };
    if (index >= all.length) return { kind: "end" };
    return { kind: "page", page: all[index][0] };
  }
  const next = page + delta;
  if (next < 0) return { kind: "start" };
  if (next >= total) return { kind: "end" };
  return { kind: "page", page: next };
}

export type NavAction = "next" | "prev";

/** Keyboard mapping for the paged modes. Strip mode leaves keys to native scrolling. */
export function keyAction(key: string, mode: Mode, direction: Direction): NavAction | null {
  if (mode === "strip") return null;
  switch (key) {
    case "ArrowRight":
      return direction === "ltr" ? "next" : "prev";
    case "ArrowLeft":
      return direction === "ltr" ? "prev" : "next";
    case " ":
    case "ArrowDown":
    case "PageDown":
      return "next";
    case "ArrowUp":
    case "PageUp":
      return "prev";
    default:
      return null;
  }
}

/** Tap zones: outer thirds turn the page, the middle toggles the menu. */
export function zoneAction(xFraction: number, direction: Direction): NavAction | "menu" {
  if (xFraction < 0.3) return direction === "ltr" ? "prev" : "next";
  if (xFraction > 0.7) return direction === "ltr" ? "next" : "prev";
  return "menu";
}

/** A swipe drags the next page in from the side it lives on. */
export function swipeAction(dx: number, direction: Direction): NavAction {
  const towardsRight = dx < 0;
  return towardsRight === (direction === "ltr") ? "next" : "prev";
}

export function clampPage(page: number, total: number): number {
  if (!Number.isFinite(page) || total <= 0) return 0;
  return Math.max(0, Math.min(total - 1, Math.round(page)));
}
