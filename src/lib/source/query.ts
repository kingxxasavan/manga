import type { BrowseQuery, Series, SortKey } from "@/lib/types";

const SORTERS: Record<SortKey, (a: Series, b: Series) => number> = {
  popular: (a, b) => b.views.all - a.views.all,
  rating: (a, b) => b.rating - a.rating,
  newest: (a, b) => b.updatedAt.localeCompare(a.updatedAt),
  az: (a, b) => a.title.localeCompare(b.title),
};

/** Pure filter + sort used by the demo source and by the browse page. */
export function filterSeries(all: Series[], query: BrowseQuery): Series[] {
  const q = query.q?.trim().toLowerCase() ?? "";
  const genres = query.genres ?? [];
  const out = all.filter((s) => {
    if (query.type && s.type !== query.type) return false;
    if (query.status && s.status !== query.status) return false;
    if (!genres.every((g) => s.genres.includes(g))) return false;
    if (q) {
      const haystack = [s.title, s.author, ...s.altTitles].join("\n").toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
  const sorter = SORTERS[query.sort ?? "popular"];
  return out.sort((a, b) => sorter(a, b) || a.title.localeCompare(b.title));
}
