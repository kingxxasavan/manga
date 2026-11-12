"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { formatDate } from "@/lib/format";
import { KEYS, type ProgressMap, type ReadMap } from "@/lib/storage";
import type { Chapter } from "@/lib/types";
import { useStored } from "@/lib/use-stored";
import { BookmarkIcon, CheckIcon, PlayIcon, SortIcon } from "./icons";

const NO_PROGRESS: ProgressMap = {};
const NO_READ: ReadMap = {};
const NO_BOOKMARKS: string[] = [];

export function useBookmark(slug: string): [boolean, () => void] {
  const [bookmarks, setBookmarks] = useStored(KEYS.bookmarks, NO_BOOKMARKS);
  const on = bookmarks.includes(slug);
  return [on, () => setBookmarks(on ? bookmarks.filter((s) => s !== slug) : [slug, ...bookmarks])];
}

export function SeriesActions({ slug }: { slug: string }) {
  const [progress] = useStored(KEYS.progress, NO_PROGRESS);
  const [bookmarked, toggle] = useBookmark(slug);
  const saved = progress[slug];
  return (
    <div className="mt-6 flex flex-wrap gap-3">
      <Link
        href={`/read/${slug}/${saved?.chapter ?? 1}`}
        className="inline-flex items-center gap-2 rounded-full bg-accent px-6 py-3 font-bold text-accent-ink transition hover:brightness-110 active:scale-[0.97]"
      >
        <PlayIcon width={16} height={16} />
        {saved ? `Continue chapter ${saved.chapter}` : "Start reading"}
      </Link>
      <button
        type="button" onClick={toggle} aria-pressed={bookmarked}
        className={`inline-flex items-center gap-2 rounded-full border px-6 py-3 font-bold transition active:scale-[0.97] ${bookmarked ? "border-accent bg-accent-soft text-accent" : "border-line bg-bg/40 hover:border-text"}`}
      >
        <BookmarkIcon width={16} height={16} fill={bookmarked ? "currentColor" : "none"} />
        {bookmarked ? "Bookmarked" : "Bookmark"}
      </button>
    </div>
  );
}

export function ChapterList({ slug, chapters }: { slug: string; chapters: Chapter[] }) {
  const [read] = useStored(KEYS.read, NO_READ);
  const [progress] = useStored(KEYS.progress, NO_PROGRESS);
  const [newestFirst, setNewestFirst] = useState(true);
  const done = useMemo(() => new Set(read[slug] ?? []), [read, slug]);
  const current = progress[slug]?.chapter;
  const ordered = useMemo(() => (newestFirst ? [...chapters].reverse() : chapters), [chapters, newestFirst]);

  return (
    <section className="mt-12">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-2xl font-extrabold">
          Chapters <span className="text-base font-semibold text-muted">{chapters.length}</span>
        </h2>
        <button
          type="button" onClick={() => setNewestFirst((v) => !v)}
          className="inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm font-semibold text-muted transition hover:border-accent hover:text-accent"
        >
          <SortIcon width={16} height={16} />
          {newestFirst ? "Newest first" : "Oldest first"}
        </button>
      </div>
      <ol className="grid gap-2 sm:grid-cols-2">
        {ordered.map((chapter) => {
          const isRead = done.has(chapter.number);
          const isCurrent = current === chapter.number;
          return (
            <li key={chapter.number}>
              <Link
                href={`/read/${slug}/${chapter.number}`}
                className={`group flex items-center gap-3 rounded-xl border px-4 py-3 transition hover:border-accent/60 hover:bg-surface-2 ${isCurrent ? "border-accent/60 bg-accent-soft" : "border-line bg-surface"}`}
              >
                <span className={`min-w-0 flex-1 ${isRead && !isCurrent ? "text-muted" : ""}`}>
                  <span className="block truncate font-semibold transition group-hover:text-accent">
                    Chapter {chapter.number}
                    <span className="font-normal text-muted"> · {chapter.title}</span>
                  </span>
                  <span className="block text-xs text-muted">{formatDate(chapter.publishedAt)} · {chapter.pageCount} pages</span>
                </span>
                {isCurrent ? (
                  <span className="shrink-0 rounded-full bg-accent px-2.5 py-1 text-xs font-bold text-accent-ink">Reading</span>
                ) : isRead ? (
                  <span className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-muted">
                    <CheckIcon width={14} height={14} /> Read
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
