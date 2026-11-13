"use client";

import { useEffect, useRef, useState } from "react";
import { formatMoney } from "@/lib/money";

const DURATION = 700;
const easeOut = (t: number) => 1 - Math.pow(1 - t, 4);

/**
 * A price that counts to its value instead of just appearing.
 * Purpose: gives the estimate a moment of arrival after the questions. Seen once per request.
 * `value` is in cents. People who prefer reduced motion get the plain number.
 */
export function AnimatedPrice({ value, from: start, className = "" }: { value: number; from?: number; className?: string }) {
  // `from` makes the number count up the first time it appears (used for the estimate reveal).
  const [shown, setShown] = useState(start ?? value);
  const from = useRef(start ?? value);

  useEffect(() => {
    const start = from.current;
    if (start === value) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      from.current = value;
      const id = requestAnimationFrame(() => setShown(value));
      return () => cancelAnimationFrame(id);
    }
    let frame = 0;
    const began = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - began) / DURATION);
      const current = start + (value - start) * easeOut(t);
      from.current = current; // an interrupted count continues from where it is
      setShown(t === 1 ? value : Math.round(current / 100) * 100);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return (
    <span className={`tabular-nums ${className}`}>
      <span aria-hidden="true">{formatMoney(shown)}</span>
      <span className="sr-only">{formatMoney(value)}</span>
    </span>
  );
}
