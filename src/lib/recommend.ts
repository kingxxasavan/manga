import type { Series } from "@/lib/types";

export interface Recommendation {
  series: Series[];
  /** false when there was nothing to learn from and we fell back to top rated */
  personalised: boolean;
}

const READ_WEIGHT = 1;
const BOOKMARK_WEIGHT = 2;

/**
 * Suggests unread series whose genres match what the reader has read and
 * bookmarked. Bookmarks count double. With no signal it returns top rated.
 */
export function recommend(
  all: Series[],
  historySlugs: string[],
  bookmarkSlugs: string[],
  limit = 12,
): Recommendation {
  const bySlug = new Map(all.map((s) => [s.slug, s]));
  const weights = new Map<string, number>();
  const add = (slug: string, weight: number) => {
    for (const genre of bySlug.get(slug)?.genres ?? []) {
      weights.set(genre, (weights.get(genre) ?? 0) + weight);
    }
  };
  historySlugs.forEach((slug) => add(slug, READ_WEIGHT));
  bookmarkSlugs.forEach((slug) => add(slug, BOOKMARK_WEIGHT));

  const byRating = (a: Series, b: Series) => b.rating - a.rating || a.title.localeCompare(b.title);

  if (weights.size === 0) {
    return { series: [...all].sort(byRating).slice(0, limit), personalised: false };
  }

  const seen = new Set([...historySlugs, ...bookmarkSlugs]);
  const scored = all
    .filter((s) => !seen.has(s.slug))
    .map((s) => ({ s, score: s.genres.reduce((sum, g) => sum + (weights.get(g) ?? 0), 0) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score || byRating(a.s, b.s));

  return { series: scored.slice(0, limit).map((entry) => entry.s), personalised: true };
}

/** Series that share the most genres with the given one. */
export function similarTo(all: Series[], target: Series, limit = 8): Series[] {
  return all
    .filter((s) => s.slug !== target.slug)
    .map((s) => ({
      s,
      score: s.genres.filter((g) => target.genres.includes(g)).length + (s.type === target.type ? 0.5 : 0),
    }))
    .filter((entry) => entry.score >= 1)
    .sort((a, b) => b.score - a.score || b.s.rating - a.s.rating)
    .slice(0, limit)
    .map((entry) => entry.s);
}
