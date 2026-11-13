"use client";

import { useEffect, useRef } from "react";

/**
 * Eases its children in the first time they scroll into view.
 * Purpose: keeps a long page from arriving all at once. Runs once per element.
 */
export function Reveal({ children, delay = 0, className = "" }: { children: React.ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || el.dataset.visible === "true") return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        el.dataset.visible = "true";
        observer.disconnect();
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={ref} className={`reveal ${className}`} style={delay ? ({ "--delay": `${delay}ms` } as React.CSSProperties) : undefined}>
      {children}
    </div>
  );
}
