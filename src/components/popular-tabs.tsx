"use client";

import Link from "next/link";
import { useState } from "react";
import { formatCount } from "@/lib/format";
import type { PopularRange, Series } from "@/lib/types";
import { TYPE_LABEL } from "@/lib/types";
import { EyeIcon } from "./icons";

const TABS: { key: PopularRange; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "week", label: "This week" },
  { key: "all", label: "All time" },
];

export function PopularTabs({ lists }: { lists: Record<PopularRange, Series[]> }) {
  const [range, setRange] = useState<PopularRange>("week");
  return (
    <section className="mt-12">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-extrabold sm:text-[1.7rem]">Popular</h2>
        <div role="tablist" aria-label="Popular time range" className="flex rounded-full border border-line bg-surface p-1">
          {TABS.map((tab) => (
            <button
              key={tab.key} type="button" role="tab" aria-selected={range === tab.key}
              onClick={() => setRange(tab.key)}
              className={`rounded-full px-4 py-1.5 text-sm font-semibold transition ${range === tab.key ? "bg-accent text-accent-ink" : "text-muted hover:text-text"}`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <ol key={range} className="grid gap-3 sm:grid-cols-2">
        {lists[range].map((s, i) => (
          <li key={s.slug} className="rise" style={{ animationDelay: `${i * 25}ms` }}>
            <Link
              href={`/series/${s.slug}`}
              className="group flex items-center gap-4 rounded-2xl border border-line bg-surface p-3 transition hover:border-accent/60 hover:bg-surface-2"
            >
              <span className={`w-9 shrink-0 text-center font-display text-3xl font-extrabold tabular-nums ${i < 3 ? "text-accent" : "text-muted/60"}`}>
                {i + 1}
              </span>
              <img src={s.cover} alt="" loading="lazy" width={600} height={900} className="aspect-[2/3] w-14 shrink-0 rounded-lg object-cover" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-semibold transition group-hover:text-accent">{s.title}</span>
                <span className="mt-0.5 block truncate text-xs text-muted">{TYPE_LABEL[s.type]} · {s.genres.slice(0, 2).join(" · ")}</span>
                <span className="mt-1.5 inline-flex items-center gap-1.5 text-xs font-semibold text-muted">
                  <EyeIcon width={14} height={14} />
                  {formatCount(s.views[range])} reads
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
