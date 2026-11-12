import type { BrowseQuery, Chapter, Page, PopularRange, Series, SeriesType } from "@/lib/types";

/**
 * Every bit of content the site shows comes through this interface.
 * To use a real catalogue, implement it in a new file and export that
 * implementation from `lib/source/index.ts`.
 */
export interface SourceMeta {
  name: string;
  /** What the popularity number counts, e.g. "reads" or "followers" */
  popularityUnit: string;
  /** Shown in the footer when the data comes from someone else */
  credit?: { label: string; href: string };
  /** true when chapter pages are generated placeholders, not the real work */
  placeholderPages: boolean;
}

export interface Source {
  getMeta(): Promise<SourceMeta>;
  getAll(): Promise<Series[]>;
  getSpotlight(): Promise<Series[]>;
  getPopular(range: PopularRange): Promise<Series[]>;
  getLatest(): Promise<Series[]>;
  getByType(type: SeriesType): Promise<Series[]>;
  search(query: BrowseQuery): Promise<Series[]>;
  getSeries(slug: string): Promise<Series | null>;
  getChapters(slug: string): Promise<Chapter[]>;
  getChapterPages(slug: string, chapter: number): Promise<Page[]>;
}
