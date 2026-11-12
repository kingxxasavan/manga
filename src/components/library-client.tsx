"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { KEYS, store } from "@/lib/storage";
import type { Series } from "@/lib/types";
import { useHydrated, useStored } from "@/lib/use-stored";
import { ContinueCard, useHistory } from "./personal-rows";
import { SeriesCard } from "./series-card";

const NO_BOOKMARKS: string[] = [];
type Tab = "bookmarks" | "history";

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="mt-6 rounded-3xl border border-dashed border-line p-10 text-center">
      <p className="font-display text-xl font-bold">{title}</p>
      <p className="mt-1 text-muted">{body}</p>
      <Link href="/browse" className="mt-5 inline-block rounded-full bg-accent px-6 py-3 font-bold text-accent-ink">
        Find something to read
      </Link>
    </div>
  );
}

export function LibraryClient({ all }: { all: Series[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const hydrated = useHydrated();
  const tab: Tab = params.get("tab") === "history" ? "history" : "bookmarks";
  const [bookmarks] = useStored(KEYS.bookmarks, NO_BOOKMARKS);
  const history = useHistory(all);
  const [confirming, setConfirming] = useState(false);

  const saved = useMemo(() => {
    const bySlug = new Map(all.map((s) => [s.slug, s]));
    return bookmarks.map((slug) => bySlug.get(slug)).filter((s): s is Series => Boolean(s));
  }, [all, bookmarks]);

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: "bookmarks", label: "Bookmarks", count: saved.length },
    { key: "history", label: "History", count: history.length },
  ];

  return (
    <div className="mt-8">
      <h1 className="text-3xl font-extrabold sm:text-4xl">Library</h1>
      <p className="mt-1 text-muted">Saved in this browser. Nothing leaves your device.</p>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div role="tablist" aria-label="Library sections" className="flex rounded-full border border-line bg-surface p-1">
          {tabs.map((t) => (
            <button
              key={t.key} type="button" role="tab" aria-selected={tab === t.key}
              onClick={() => router.replace(t.key === "bookmarks" ? pathname : `${pathname}?tab=${t.key}`, { scroll: false })}
              className={`rounded-full px-5 py-2 text-sm font-semibold transition ${tab === t.key ? "bg-accent text-accent-ink" : "text-muted hover:text-text"}`}
            >
              {t.label} {hydrated && <span className="opacity-70">{t.count}</span>}
            </button>
          ))}
        </div>
        {tab === "history" && history.length > 0 && (
          confirming ? (
            <span className="flex items-center gap-2 text-sm">
              Clear all history?
              <button
                type="button" className="rounded-full bg-accent px-3 py-1.5 font-semibold text-accent-ink"
                onClick={() => { store.remove(KEYS.progress); store.remove(KEYS.read); setConfirming(false); }}
              >
                Yes, clear
              </button>
              <button type="button" className="rounded-full border border-line px-3 py-1.5 font-semibold" onClick={() => setConfirming(false)}>
                Keep
              </button>
            </span>
          ) : (
            <button type="button" onClick={() => setConfirming(true)} className="text-sm font-semibold text-muted hover:text-accent">
              Clear history
            </button>
          )
        )}
      </div>

      {!hydrated ? (
        <div className="mt-6 h-64 animate-pulse rounded-3xl bg-surface" />
      ) : tab === "bookmarks" ? (
        saved.length > 0 ? (
          <div className="mt-6 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
            {saved.map((s) => <SeriesCard key={s.slug} series={s} />)}
          </div>
        ) : (
          <Empty title="No bookmarks yet" body="Bookmark a series from its page and it shows up here." />
        )
      ) : history.length > 0 ? (
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {history.map(({ series, progress }) => (
            <ContinueCard key={series.slug} series={series} chapter={progress.chapter} page={progress.page} total={progress.total} />
          ))}
        </div>
      ) : (
        <Empty title="No reading history yet" body="Open any chapter and your place is remembered here." />
      )}
    </div>
  );
}
