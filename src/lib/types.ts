export type SeriesType = "manga" | "manhwa" | "manhua";
export type SeriesStatus = "ongoing" | "completed" | "hiatus";
export type PopularRange = "today" | "week" | "all";
export type SortKey = "popular" | "rating" | "newest" | "az";

export interface Series {
  slug: string;
  title: string;
  /** URL of the cover image */
  cover: string;
  altTitles: string[];
  author: string;
  type: SeriesType;
  status: SeriesStatus;
  genres: string[];
  synopsis: string;
  /** 0 to 10, one decimal */
  rating: number;
  views: Record<PopularRange, number>;
  year: number;
  chapterCount: number;
  /** ISO date of the most recent chapter */
  updatedAt: string;
}

export interface Chapter {
  number: number;
  title: string;
  publishedAt: string;
  pageCount: number;
}

export interface Page {
  index: number;
  src: string;
  width: number;
  height: number;
}

export interface BrowseQuery {
  q?: string;
  genres?: string[];
  type?: SeriesType;
  status?: SeriesStatus;
  sort?: SortKey;
}

export const SERIES_TYPES: SeriesType[] = ["manga", "manhwa", "manhua"];
export const SERIES_STATUSES: SeriesStatus[] = ["ongoing", "completed", "hiatus"];
export const SORT_KEYS: SortKey[] = ["popular", "rating", "newest", "az"];

export const TYPE_LABEL: Record<SeriesType, string> = {
  manga: "Manga",
  manhwa: "Manhwa",
  manhua: "Manhua",
};
export const STATUS_LABEL: Record<SeriesStatus, string> = {
  ongoing: "Ongoing",
  completed: "Completed",
  hiatus: "On hiatus",
};
export const SORT_LABEL: Record<SortKey, string> = {
  popular: "Most popular",
  rating: "Top rated",
  newest: "Recently updated",
  az: "A to Z",
};
