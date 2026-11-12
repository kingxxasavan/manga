"use client";

import Link from "next/link";
import { useMemo } from "react";
import { recommend } from "@/lib/recommend";
import { KEYS, type ProgressMap } from "@/lib/storage";
import type { Series } from "@/lib/types";
import { useStored } from "@/lib/use-stored";
import { RowItem, ScrollRow } from "./scroll-row";
import { SeriesCard } from "./series-card";

const NO_PROGRESS: ProgressMap = {};
const NO_BOOKMARKS: string[] = [];

/** Reading history, most recent first, joined with series data. */
export function useHistory(all: Series[]) {
  const [progress] = useStored(KEYS.progress, NO_PROGRESS);
  return useMemo(() => {
    const bySlug = new Map(all.map((s) => [s.slug, s]));
    return Object.entries(progress)
      .map(([slug, p]) => ({ series: bySlug.get(slug), progress: p }))
      .filter((e): e is { series: Series; progress: ProgressMap[string] } => Boolean(e.series))
      .sort((a, b) => b.progress.updatedAt - a.progress.updatedAt);
  }, [all, progress]);
}

export function ContinueCard({ series, chapter, page, total }: { series: Series; chapter: number; page: number; total: number }) {
  const percent = total > 0 ? Math.round(((page + 1) / total) * 100) : 0;
  return (
    <Link
      href={`/read/${series.slug}/${chapter}`}
      className="group flex gap-4 rounded-2xl border border-line bg-surface p-3 transition hover:border-accent/60 hover:bg-surface-2"
    >
      <img src={series.cover} alt="" loading="lazy" width={600} height={900} className="aspect-[2/3] w-20 shrink-0 rounded-xl object-cover" />
      <span className="flex min-w-0 flex-1 flex-col py-1">
        <span className="line-clamp-2 font-semibold leading-snug transition group-hover:text-accent">{series.title}</span>
        <span className="mt-1 text-sm text-muted">Chapter {chapter} · page {page + 1} of {total}</span>
        <span className="mt-auto block h-1.5 overflow-hidden rounded-full bg-line">
          <span className="block h-full rounded-full bg-accent" style={{ width: `${percent}%` }} />
        </span>
      </span>
    </Link>
  );
}

export function ContinueRow({ all }: { all: Series[] }) {
  const history = useHistory(all);
  if (history.length === 0) return null;
  return (
    <ScrollRow title="Continue reading" href="/library?tab=history">
      {history.slice(0, 10).map(({ series, progress }) => (
        <RowItem key={series.slug} wide>
          <ContinueCard series={series} chapter={progress.chapter} page={progress.page} total={progress.total} />
        </RowItem>
      ))}
    </ScrollRow>
  );
}

export function RecommendedRow({ all }: { all: Series[] }) {
  const [progress] = useStored(KEYS.progress, NO_PROGRESS);
  const [bookmarks] = useStored(KEYS.bookmarks, NO_BOOKMARKS);
  const result = useMemo(() => recommend(all, Object.keys(progress), bookmarks), [all, progress, bookmarks]);
  if (result.series.length === 0) return null;
  return (
    <ScrollRow
      title="Recommended for you"
      note={result.personalised ? "Picked from the genres you read and bookmark" : "Top rated picks to get you started. Read or bookmark something and this row learns your taste."}
    >
      {result.series.map((s) => (
        <RowItem key={s.slug}>
          <SeriesCard series={s} />
        </RowItem>
      ))}
    </ScrollRow>
  );
}
