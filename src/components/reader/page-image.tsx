"use client";

import { useState } from "react";
import type { Page } from "@/lib/types";

interface Props {
  page: Page;
  className?: string;
  lazy?: boolean;
}

/** One page. If it fails to load it offers a retry and the rest of the chapter stays readable. */
export function PageImage({ page, className = "", lazy = false }: Props) {
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div
        className={`grid place-items-center bg-neutral-500/15 ${className}`}
        style={{ aspectRatio: `${page.width} / ${page.height}` }}
      >
        <div className="p-4 text-center">
          <p className="text-sm font-semibold">Page {page.index + 1} did not load</p>
          <button
            type="button"
            onClick={() => { setFailed(false); setAttempt((n) => n + 1); }}
            className="mt-3 rounded-full bg-accent px-5 py-2 text-sm font-bold text-accent-ink"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <img
      src={attempt ? `${page.src}?retry=${attempt}` : page.src}
      alt={`Page ${page.index + 1}`} width={page.width} height={page.height}
      loading={lazy ? "lazy" : "eager"} decoding="async" draggable={false}
      onError={() => setFailed(true)}
      className={`select-none bg-neutral-500/10 ${className}`}
    />
  );
}
