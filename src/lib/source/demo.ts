import type { Page } from "@/lib/types";
import { buildChapters, DEMO_SERIES, findSeries, pageCountFor, pageSizeFor } from "./demo-data";
import { filterSeries } from "./query";
import type { Source } from "./types";

const byViews = (range: "today" | "week" | "all") =>
  [...DEMO_SERIES].sort((a, b) => b.views[range] - a.views[range]);

export const demoSource: Source = {
  async getAll() {
    return DEMO_SERIES;
  },
  async getSpotlight() {
    // A mix of types: the best rated ongoing series of each type, then by weekly views.
    return [...DEMO_SERIES]
      .filter((s) => s.status === "ongoing")
      .sort((a, b) => b.rating * 1e7 + b.views.week - (a.rating * 1e7 + a.views.week))
      .slice(0, 6);
  },
  async getPopular(range) {
    return byViews(range).slice(0, 10);
  },
  async getLatest() {
    return filterSeries(DEMO_SERIES, { sort: "newest" }).slice(0, 12);
  },
  async getByType(type) {
    return filterSeries(DEMO_SERIES, { type, sort: "popular" });
  },
  async search(query) {
    return filterSeries(DEMO_SERIES, query);
  },
  async getSeries(slug) {
    return findSeries(slug) ?? null;
  },
  async getChapters(slug) {
    const series = findSeries(slug);
    return series ? buildChapters(series) : [];
  },
  async getChapterPages(slug, chapter) {
    const series = findSeries(slug);
    if (!series || !Number.isInteger(chapter) || chapter < 1 || chapter > series.chapterCount) return [];
    const { width, height } = pageSizeFor(series);
    const pages: Page[] = [];
    for (let i = 0; i < pageCountFor(series, chapter); i++) {
      pages.push({ index: i, src: `/api/page/${slug}/${chapter}/${i}`, width, height });
    }
    return pages;
  },
};
