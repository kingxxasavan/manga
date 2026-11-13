"use client";

import { useEffect, useState } from "react";
import { AnimatedPrice } from "./animated-price";
import { Check, Lock } from "./icons";

// The same sums the real price list produces: (299 + 70 + 80) x 1.3 = 584
const ROWS = [
  { label: "Multi page website", amount: "$299", total: 299_00 },
  { label: "5 pages", amount: "+$70", total: 369_00 },
  { label: "Blog and contact form", amount: "+$80", total: 449_00 },
  { label: "Rush delivery", amount: "+30%", total: 584_00 },
];

/**
 * Decorative: a quote that builds itself once when the page loads, to show
 * what the product does before anyone clicks. Hidden from screen readers,
 * the headline next to it says the same thing in words.
 */
export function HeroQuote() {
  const [shown, setShown] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const id = requestAnimationFrame(() => setShown(ROWS.length));
      return () => cancelAnimationFrame(id);
    }
    if (shown >= ROWS.length) return;
    const id = window.setTimeout(() => setShown((n) => n + 1), shown === 0 ? 700 : 650);
    return () => window.clearTimeout(id);
  }, [shown]);

  const total = shown === 0 ? 0 : ROWS[shown - 1].total;
  const done = shown >= ROWS.length;

  return (
    <div aria-hidden="true" className="relative mx-auto w-full max-w-sm select-none">
      <div className="rounded-[1.75rem] border border-line bg-[#0c1224]/80 p-6 shadow-float backdrop-blur-xl">
        <div className="flex items-center justify-between">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-muted">Your quote</p>
          <p className="flex items-center gap-2 text-xs font-semibold text-muted"><span className="live-dot" /> Live price</p>
        </div>

        <ul className="mt-5 space-y-2.5">
          {ROWS.map((row, i) => (
            <li
              key={row.label}
              className="flex items-center gap-3 rounded-xl border border-line bg-surface px-3.5 py-3 text-sm transition-[opacity,transform] duration-500 ease-out-strong"
              style={{ opacity: i < shown ? 1 : 0, transform: i < shown ? "none" : "translateY(8px)" }}
            >
              <span className="grid size-5 shrink-0 place-items-center rounded-full bg-accent text-accent-ink"><Check width={12} height={12} strokeWidth={3.5} /></span>
              <span className="min-w-0 flex-1 truncate font-medium">{row.label}</span>
              <span className="font-semibold text-muted">{row.amount}</span>
            </li>
          ))}
        </ul>

        <div className="mt-5 flex items-end justify-between border-t border-line pt-4">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-muted">Total</p>
          <AnimatedPrice value={total} className="font-display text-5xl font-extrabold leading-none" />
        </div>

        <div
          className="mt-5 flex h-12 items-center justify-center gap-2 rounded-full bg-white text-sm font-bold text-[#0b1020] transition-opacity duration-500"
          style={{ opacity: done ? 1 : 0.35 }}
        >
          <Lock width={15} height={15} /> Continue to payment
        </div>
      </div>

      {/* A second card hanging below the quote, hinting at the tracking step. It sits clear of the button. */}
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
