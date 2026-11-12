import { cacheLife } from "next/cache";
import type { Chapter, Page, Series } from "@/lib/types";
import { pageCountFor, pageSizeFor } from "./demo-data";
import { toCatalogue, type MdManga, type MdStats } from "./mangadex-map";
import { filterSeries } from "./query";
import type { Source, SourceMeta } from "./types";

/**
 * Real series information and cover thumbnails from the public MangaDex API.
 *
 * Only catalogue data is used: titles, covers, descriptions, genres, scores.
 * Chapter pages are NOT fetched. The reader shows generated placeholder pages,
 * and series pages link out to the licensed release where MangaDex lists one.
 */

const API = "https://api.mangadex.org";
const HEADERS = { "User-Agent": "manga-site/0.1" };

export const MANGADEX_META: SourceMeta = {
  name: "MangaDex",
  popularityUnit: "followers",
  credit: { label: "Series information and covers from MangaDex", href: "https://mangadex.org" },
  placeholderPages: true,
};

// How many of the most followed series to take per original language.
const TAKE: [language: string[], limit: number][] = [
  [["ja"], 36],
  [["ko"], 28],
  [["zh", "zh-hk"], 20],
];

async function get<T>(path: string, params: [string, string][]): Promise<T> {
  const url = new URL(path, API);
  for (const [key, value] of params) url.searchParams.append(key, value);
  const res = await fetch(url, { headers: HEADERS, signal: AbortSignal.timeout(15_000) });
  if (!res.ok) throw new Error(`MangaDex ${path} answered ${res.status}`);
  return (await res.json()) as T;
}

/** One cached snapshot of the catalogue. Every page of the site reads from it. */
export async function loadMangaDexCatalogue(): Promise<Series[]> {
  "use cache";
  cacheLife("hours");

  const lists = await Promise.all(
    TAKE.map(([languages, limit]) =>
      get<{ data: MdManga[] }>("/manga", [
        ["limit", String(limit)],
        ["order[followedCount]", "desc"],
        ["contentRating[]", "safe"],
        ["includes[]", "cover_art"],
        ["includes[]", "author"],
        ["status[]", "ongoing"],
        ["status[]", "completed"],
        ["status[]", "hiatus"],
        ...languages.map((l): [string, string] => ["originalLanguage[]", l]),
      ]),
    ),
  );
  const mangas = lists.flatMap((list) => list.data);
  const { statistics } = await get<{ statistics: Record<string, MdStats> }>(
    "/statistics/manga",
    mangas.map((m): [string, string] => ["manga[]", m.id]),
  );
  const catalogue = toCatalogue(mangas, statistics, Date.now());
  if (catalogue.length === 0) throw new Error("MangaDex returned no usable series");
  return catalogue;
}

function placeholderChapters(series: Series): Chapter[] {
  // The real chapter titles and dates are not fetched, so none are invented here.
  return Array.from({ length: series.chapterCount }, (_, i) => ({
    number: i + 1,
    title: "",
    publishedAt: null,
    pageCount: pageCountFor(series, i + 1),
  }));
}

/** Builds a Source over any loader, so the fallback logic can reuse it. */
export function catalogueSource(load: () => Promise<Series[]>, meta: () => Promise<SourceMeta>): Source {
  const find = async (slug: string) => (await load()).find((s) => s.slug === slug) ?? null;
  return {
    getMeta: meta,
    getAll: load,
    async getSpotlight() {
      return [...(await load())]
        .filter((s) => s.status === "ongoing" && s.synopsis.length > 80)
        .sort((a, b) => b.rating * Math.log10(b.views.all + 10) - a.rating * Math.log10(a.views.all + 10))
        .slice(0, 6);
    },
    async getPopular(range) {
      return [...(await load())].sort((a, b) => b.views[range] - a.views[range]).slice(0, 10);
    },
    async getLatest() {
      return filterSeries(await load(), { sort: "newest" }).slice(0, 12);
    },
    async getByType(type) {
      return filterSeries(await load(), { type, sort: "popular" });
    },
    async search(query) {
      return filterSeries(await load(), query);
    },
    getSeries: find,
    async getChapters(slug) {
      const series = await find(slug);
      return series ? placeholderChapters(series) : [];
    },
    async getChapterPages(slug, chapter) {
      const series = await find(slug);
      if (!series || !Number.isInteger(chapter) || chapter < 1 || chapter > series.chapterCount) return [];
      const { width, height } = pageSizeFor(series);
      const pages: Page[] = [];
      for (let i = 0; i < pageCountFor(series, chapter); i++) {
        pages.push({ index: i, src: `/api/page/${slug}/${chapter}/${i}`, width, height });
      }
      return pages;
    },
  };
}
