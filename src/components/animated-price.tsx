"use client";

import { useEffect, useRef, useState } from "react";
import { formatMoney } from "@/lib/money";

const DURATION = 420;
const easeOut = (t: number) => 1 - Math.pow(1 - t, 4);

/**
 * A price that counts to its new value instead of jumping.
 * Purpose: makes it obvious that an answer just changed the price, and by how much.
 * `value` is in cents. People who prefer reduced motion get the plain number.
 */
export function AnimatedPrice({ value, className = "" }: { value: number; className?: string }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);

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
