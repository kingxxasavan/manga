import type { Series } from "@/lib/types";
import { DEMO_META, demoSource } from "./demo";
import { DEMO_SERIES } from "./demo-data";
import { catalogueSource, loadMangaDexCatalogue, MANGADEX_META } from "./mangadex";
import type { Source, SourceMeta } from "./types";

/**
 * The active content source.
 *
 * CONTENT_SOURCE=mangadex (default): real series information and covers from MangaDex.
 * CONTENT_SOURCE=demo: the built in invented catalogue, no network needed.
 *
 * If MangaDex cannot be reached the site quietly serves the demo catalogue
 * instead of breaking, and tries MangaDex again on the next request.
 */
async function loadLive(): Promise<{ series: Series[]; meta: SourceMeta }> {
  try {
    return { series: await loadMangaDexCatalogue(), meta: MANGADEX_META };
  } catch (error) {
    console.warn("MangaDex is unavailable, serving the demo catalogue.", error);
    return { series: DEMO_SERIES, meta: DEMO_META };
  }
}

const liveSource = catalogueSource(
  async () => (await loadLive()).series,
  async () => (await loadLive()).meta,
);

export const source: Source = process.env.CONTENT_SOURCE === "demo" ? demoSource : liveSource;

export type { Source, SourceMeta } from "./types";
export { GENRES } from "./demo-data";
