import type { BrowseQuery, Chapter, Page, PopularRange, Series, SeriesType } from "@/lib/types";

/**
 * Every bit of content the site shows comes through this interface.
 * To use a real catalogue, implement it in a new file and export that
 * implementation from `lib/source/index.ts`.
 */
export interface Source {
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
