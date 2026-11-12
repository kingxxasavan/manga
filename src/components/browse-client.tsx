"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { filterSeries } from "@/lib/source/query";
import type { BrowseQuery, Series, SeriesStatus, SeriesType, SortKey } from "@/lib/types";
import { SERIES_STATUSES, SERIES_TYPES, SORT_KEYS, SORT_LABEL, STATUS_LABEL, TYPE_LABEL } from "@/lib/types";
import { CloseIcon, SearchIcon } from "./icons";
import { SeriesCard } from "./series-card";

const oneOf = <T extends string>(value: string | null, options: readonly T[]): T | undefined =>
  options.includes(value as T) ? (value as T) : undefined;

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button" aria-pressed={active} onClick={onClick}
      className={`rounded-full border px-3.5 py-1.5 text-sm font-semibold transition active:scale-[0.97] ${active ? "border-accent bg-accent text-accent-ink" : "border-line bg-surface text-muted hover:border-accent hover:text-accent"}`}
    >
      {children}
    </button>
  );
}

export function BrowseClient({ all, genres }: { all: Series[]; genres: readonly string[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  // The URL is the single source of truth, so results can be shared and the back button works.
  const query: BrowseQuery = useMemo(() => ({
    q: params.get("q") ?? "",
    genres: params.getAll("genre").filter((g) => genres.includes(g)),
    type: oneOf<SeriesType>(params.get("type"), SERIES_TYPES),
    status: oneOf<SeriesStatus>(params.get("status"), SERIES_STATUSES),
    sort: oneOf<SortKey>(params.get("sort"), SORT_KEYS) ?? "popular",
  }), [params, genres]);

  const update = (mutate: (next: URLSearchParams) => void) => {
    // Read the live URL, not the last render's copy, so a delayed search update
    // can never bring back filters that were just cleared.
    const next = new URLSearchParams(window.location.search);
    mutate(next);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };
  const setParam = (key: string, value: string | undefined) =>
    update((next) => (value ? next.set(key, value) : next.delete(key)));
  const toggleGenre = (genre: string) =>
    update((next) => {
      const current = next.getAll("genre");
      next.delete("genre");
      (current.includes(genre) ? current.filter((g) => g !== genre) : [...current, genre]).forEach((g) => next.append("genre", g));
    });

  // The text box keeps its own state so typing is instant; the URL follows shortly after.
  const urlText = query.q ?? "";
  const [text, setText] = useState(urlText);
  const [syncedText, setSyncedText] = useState(urlText);
  if (urlText !== syncedText) {
    setSyncedText(urlText);
    setText(urlText);
  }
  useEffect(() => {
    if (text === urlText) return;
    const id = window.setTimeout(() => setParam("q", text.trim() || undefined), 250);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const results = useMemo(() => filterSeries(all, { ...query, q: text }), [all, query, text]);
  const filtered = Boolean(text || query.genres?.length || query.type || query.status);

  return (
    <div className="mt-8">
      <h1 className="text-3xl font-extrabold sm:text-4xl">Browse</h1>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row">
        <label className="relative block flex-1">
          <span className="sr-only">Search titles and authors</span>
          <SearchIcon className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="search" value={text} onChange={(e) => setText(e.target.value)}
            placeholder="Search titles, authors"
            className="h-12 w-full rounded-2xl border border-line bg-surface pl-12 pr-4 outline-none transition placeholder:text-muted focus:border-accent"
          />
        </label>
        <label className="flex h-12 items-center gap-2 rounded-2xl border border-line bg-surface px-4 text-sm">
          <span className="text-muted">Sort</span>
          <select
            value={query.sort} onChange={(e) => setParam("sort", e.target.value === "popular" ? undefined : e.target.value)}
            className="bg-transparent font-semibold outline-none"
          >
            {SORT_KEYS.map((key) => <option key={key} value={key} className="bg-surface text-text">{SORT_LABEL[key]}</option>)}
          </select>
        </label>
      </div>

      <div className="mt-5 space-y-4 rounded-3xl border border-line bg-surface/50 p-4 sm:p-5">
        <fieldset className="flex flex-wrap items-center gap-2">
          <legend className="mb-2 text-xs font-bold uppercase tracking-widest text-muted">Type</legend>
          <Chip active={!query.type} onClick={() => setParam("type", undefined)}>All</Chip>
          {SERIES_TYPES.map((type) => (
            <Chip key={type} active={query.type === type} onClick={() => setParam("type", query.type === type ? undefined : type)}>
              {TYPE_LABEL[type]}
            </Chip>
          ))}
        </fieldset>
        <fieldset className="flex flex-wrap items-center gap-2">
          <legend className="mb-2 text-xs font-bold uppercase tracking-widest text-muted">Status</legend>
          <Chip active={!query.status} onClick={() => setParam("status", undefined)}>Any</Chip>
          {SERIES_STATUSES.map((status) => (
            <Chip key={status} active={query.status === status} onClick={() => setParam("status", query.status === status ? undefined : status)}>
              {STATUS_LABEL[status]}
            </Chip>
          ))}
        </fieldset>
        <fieldset className="flex flex-wrap items-center gap-2">
          <legend className="mb-2 text-xs font-bold uppercase tracking-widest text-muted">Genres</legend>
          {genres.map((genre) => (
            <Chip key={genre} active={Boolean(query.genres?.includes(genre))} onClick={() => toggleGenre(genre)}>
              {genre}
            </Chip>
          ))}
        </fieldset>
      </div>

      <div className="mt-6 flex items-center justify-between gap-3">
        <p className="text-sm text-muted" aria-live="polite">
          <span className="font-bold text-text">{results.length}</span> series found
        </p>
        {filtered && (
          <button
            type="button" onClick={() => { setText(""); router.replace(pathname, { scroll: false }); }}
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-accent hover:underline"
          >
            <CloseIcon width={14} height={14} />
            Clear filters
          </button>
        )}
      </div>

      {results.length > 0 ? (
        <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {results.map((s) => <SeriesCard key={s.slug} series={s} sub={`${TYPE_LABEL[s.type]} · ${s.genres[0]}`} />)}
        </div>
      ) : (
        <div className="mt-10 rounded-3xl border border-dashed border-line p-10 text-center">
          <p className="font-display text-xl font-bold">Nothing matches those filters</p>
          <p className="mt-1 text-muted">Try removing a genre or searching for something shorter.</p>
        </div>
      )}
    </div>
  );
}
