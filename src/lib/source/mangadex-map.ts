import type { Series, SeriesStatus, SeriesType } from "@/lib/types";
import { slugify } from "./demo-data";

/** Shapes of the parts of the MangaDex API response this site reads. */
export interface MdManga {
  id: string;
  attributes: {
    title: Record<string, string>;
    altTitles: Record<string, string>[];
    description: Record<string, string>;
    originalLanguage: string;
    status: string;
    year: number | null;
    lastChapter: string | null;
    updatedAt: string;
    links: Record<string, string> | null;
    tags: { attributes: { name: Record<string, string>; group: string } }[];
  };
  relationships: { type: string; attributes?: { name?: string; fileName?: string } }[];
}

export interface MdStats {
  follows: number;
  rating: { bayesian: number | null };
}

const TYPE_BY_LANGUAGE: Record<string, SeriesType> = {
  ja: "manga",
  ko: "manhwa",
  zh: "manhua",
  "zh-hk": "manhua",
};

const STATUS: Record<string, SeriesStatus> = {
  ongoing: "ongoing",
  completed: "completed",
  hiatus: "hiatus",
};

const DAY = 86_400_000;
const SAMPLE_CHAPTERS = 10;

/** Descriptions arrive as markdown with trailing link lists. Keep the opening prose only. */
export function cleanDescription(text: string): string {
  const prose = text
    .split(/\n\s*---|\n\s*\*\*|\n\s*#{1,6}\s/)[0]
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_`]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (prose.length <= 520) return prose;
  const cut = prose.slice(0, 520);
  return `${cut.slice(0, cut.lastIndexOf(" "))}…`;
}

function pickTitle(attributes: MdManga["attributes"]): string {
  const english = attributes.title.en ?? attributes.altTitles.find((t) => t.en)?.en;
  return (english ?? Object.values(attributes.title)[0] ?? "").trim();
}

/**
 * Turns one MangaDex entry into a Series, or null when it lacks something the
 * site needs (a title, a cover, a known type, a chapter count).
 * `now` is passed in so the result is deterministic for a given moment.
 */
export function toSeries(manga: MdManga, stats: MdStats | undefined, now: number): Series | null {
  const a = manga.attributes;
  const type = TYPE_BY_LANGUAGE[a.originalLanguage];
  const status = STATUS[a.status];
  const title = pickTitle(a);
  const coverFile = manga.relationships.find((r) => r.type === "cover_art")?.attributes?.fileName;
  // Ongoing series often have no chapter count. The placeholder reader then gets a short sample run.
  const lastChapter = Math.floor(Number(a.lastChapter));
  const known = Number.isFinite(lastChapter) && lastChapter >= 1;
  const chapterCount = known ? lastChapter : SAMPLE_CHAPTERS;
  const slug = slugify(title);
  if (!type || !status || !title || !slug || !coverFile) return null;
  if (!/^[\w-]+\.(jpe?g|png|gif|webp)$/i.test(coverFile)) return null;

  const authors = manga.relationships
    .filter((r) => r.type === "author" && r.attributes?.name)
    .map((r) => r.attributes!.name!);
  const follows = stats?.follows ?? 0;
  // MangaDex has no daily or weekly counts. Recent activity stands in for them:
  // the longer since a series was updated, the less of its following counts.
  const idleDays = Math.max(0, (now - new Date(a.updatedAt).getTime()) / DAY);
  const official = a.links?.engtl;

  return {
    slug,
    title,
    cover: `/api/md-cover/${manga.id}/${coverFile}`,
    altTitles: a.altTitles.flatMap((t) => Object.values(t)).filter((t) => t !== title).slice(0, 3),
    author: [...new Set(authors)].slice(0, 2).join(", ") || "Unknown",
    type,
    status,
    genres: a.tags.filter((t) => t.attributes.group === "genre").map((t) => t.attributes.name.en).filter(Boolean).sort(),
    synopsis: cleanDescription(a.description.en ?? ""),
    rating: Math.round((stats?.rating.bayesian ?? 0) * 10) / 10,
    views: {
      today: Math.round(follows * Math.exp(-idleDays / 7)),
      week: Math.round(follows * Math.exp(-idleDays / 45)),
      all: follows,
    },
    year: a.year ?? new Date(a.updatedAt).getUTCFullYear(),
    chapterCount,
    chapterCountUnknown: known ? undefined : true,
    updatedAt: a.updatedAt,
    officialUrl: official && /^https:\/\//.test(official) ? official : undefined,
    sourceUrl: `https://mangadex.org/title/${manga.id}`,
  };
}

/** Maps a full response, dropping unusable entries and duplicate slugs. */
export function toCatalogue(mangas: MdManga[], stats: Record<string, MdStats>, now: number): Series[] {
  const seen = new Set<string>();
  const out: Series[] = [];
  for (const manga of mangas) {
    const series = toSeries(manga, stats[manga.id], now);
    if (!series || seen.has(series.slug)) continue;
    seen.add(series.slug);
    out.push(series);
  }
  return out;
}
