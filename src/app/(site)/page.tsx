import Link from "next/link";
import { ContinueRow, RecommendedRow } from "@/components/personal-rows";
import { PopularTabs } from "@/components/popular-tabs";
import { RowItem, ScrollRow } from "@/components/scroll-row";
import { SeriesCard } from "@/components/series-card";
import { Spotlight } from "@/components/spotlight";
import { formatDate } from "@/lib/format";
import { GENRES, source } from "@/lib/source";
import { SERIES_TYPES, TYPE_LABEL } from "@/lib/types";

export default async function HomePage() {
  const [meta, all, spotlight, today, week, allTime, latest, ...byType] = await Promise.all([
    source.getMeta(),
    source.getAll(),
    source.getSpotlight(),
    source.getPopular("today"),
    source.getPopular("week"),
    source.getPopular("all"),
    source.getLatest(),
    ...SERIES_TYPES.map((type) => source.getByType(type)),
  ]);

  return (
    <>
      <Spotlight items={spotlight} />
      <ContinueRow all={all} />
      <PopularTabs lists={{ today, week, all: allTime }} unit={meta.popularityUnit} />
      <RecommendedRow all={all} />

      <ScrollRow title="Latest updates" href="/browse?sort=newest">
        {latest.map((s) => (
          <RowItem key={s.slug}>
            <SeriesCard series={s} sub={s.chapterCountUnknown ? formatDate(s.updatedAt) : `Ch. ${s.chapterCount} · ${formatDate(s.updatedAt)}`} />
          </RowItem>
        ))}
      </ScrollRow>

      <section className="mt-12">
        <h2 className="mb-4 text-2xl font-extrabold sm:text-[1.7rem]">Browse by genre</h2>
        <div className="flex flex-wrap gap-2">
          {GENRES.map((genre) => (
            <Link
              key={genre} href={`/browse?genre=${encodeURIComponent(genre)}`}
              className="rounded-full border border-line bg-surface px-4 py-2 text-sm font-semibold transition hover:border-accent hover:bg-accent-soft hover:text-accent"
            >
              {genre}
            </Link>
          ))}
        </div>
      </section>

      {SERIES_TYPES.map((type, i) => (
        <ScrollRow key={type} title={TYPE_LABEL[type]} href={`/browse?type=${type}`}>
          {byType[i].map((s) => (
            <RowItem key={s.slug}>
              <SeriesCard series={s} />
            </RowItem>
          ))}
        </ScrollRow>
      ))}
    </>
  );
}
