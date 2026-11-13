"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Check } from "./icons";

const ROWS = [
  { label: "What kind of website?", value: "Multi page" },
  { label: "How many pages?", value: "5 pages" },
  { label: "Anything extra?", value: "Blog, contact form" },
  { label: "Level of finish", value: "Polished" },
];

/**
 * Decorative: a brief that fills itself in once when the page loads, then
 * shows an estimate arriving. It shows what the product does before anyone
 * clicks. No prices on purpose. Hidden from screen readers, the headline
 * beside it says the same thing in words.
 */
export function HeroQuote() {
  const [shown, setShown] = useState(0);
  const total = ROWS.length + 1; // the rows, then the estimate

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const id = requestAnimationFrame(() => setShown(total));
      return () => cancelAnimationFrame(id);
    }
    if (shown >= total) return;
    const id = window.setTimeout(() => setShown((n) => n + 1), shown === 0 ? 700 : 650);
    return () => window.clearTimeout(id);
  }, [shown, total]);

  const done = shown >= total;

  return (
    <div aria-hidden="true" className="relative mx-auto w-full max-w-sm select-none">
      <div className="rounded-[1.75rem] border border-line bg-[#0c1224]/80 p-6 shadow-float backdrop-blur-xl">
        <div className="flex items-center justify-between">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-muted">Your brief</p>
          <p className="flex items-center gap-2 text-xs font-semibold text-muted"><span className="live-dot" /> Website</p>
        </div>

        <ul className="mt-5 space-y-2.5">
          {ROWS.map((row, i) => (
            <li
              key={row.label}
              className="flex items-center gap-3 rounded-xl border border-line bg-surface px-3.5 py-2.5 transition-[opacity,transform] duration-500 ease-out-strong"
              style={{ opacity: i < shown ? 1 : 0, transform: i < shown ? "none" : "translateY(8px)" }}
            >
              <span className="grid size-5 shrink-0 place-items-center rounded-full bg-accent text-accent-ink"><Check width={12} height={12} strokeWidth={3.5} /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-[11px] font-semibold text-muted">{row.label}</span>
                <span className="block truncate text-sm font-semibold">{row.value}</span>
              </span>
            </li>
          ))}
        </ul>

        <div
          className="mt-4 flex items-center gap-3 rounded-xl border border-good/40 bg-good/10 px-3.5 py-3 transition-[opacity,transform] duration-500 ease-out-strong"
          style={{ opacity: done ? 1 : 0, transform: done ? "none" : "translateY(8px)" }}
        >
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-good text-[#04130c]"><Check width={16} height={16} strokeWidth={3} /></span>
          <span>
            <span className="block text-sm font-bold">Your estimate is ready</span>
            <span className="block text-xs text-muted">Based on complexity and level</span>
          </span>
        </div>

        <div
          className="mt-4 flex h-12 items-center justify-center gap-2 rounded-full bg-white text-sm font-bold text-[#0b1020] transition-opacity duration-500"
          style={{ opacity: done ? 1 : 0.35 }}
        >
          Send my request <ArrowRight width={16} height={16} />
        </div>
      </div>

      {/* A second card hanging below, hinting at the tracking step. It sits clear of the button. */}
      <div
        className="absolute -bottom-[5.25rem] -left-6 hidden w-56 rounded-2xl border border-line bg-[#0c1224]/90 p-4 shadow-float backdrop-blur-xl transition-[opacity,transform] duration-700 ease-out-strong sm:block"
        style={{ opacity: done ? 1 : 0, transform: done ? "none" : "translateY(12px)" }}
      >
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted">Order status</p>
        <div className="mt-2.5 grid grid-cols-4 gap-1.5">
          {[true, true, false, false].map((on, i) => <span key={i} className={`h-1.5 rounded-full ${on ? "bg-good" : "bg-surface-2"}`} />)}
        </div>
        <p className="mt-2.5 text-sm font-semibold">In progress</p>
      </div>
    </div>
  );
}
