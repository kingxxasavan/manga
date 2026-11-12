import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { StarIcon } from "@/components/icons";
import { RowItem, ScrollRow } from "@/components/scroll-row";
import { SeriesCard } from "@/components/series-card";
import { ChapterList, SeriesActions } from "@/components/series-client";
import { formatCount, formatDate } from "@/lib/format";
import { similarTo } from "@/lib/recommend";
import { source } from "@/lib/source";
import { STATUS_LABEL, TYPE_LABEL } from "@/lib/types";

type Props = { params: Promise<{ slug: string }> };

export async function generateStaticParams() {
  return (await source.getAll()).map((s) => ({ slug: s.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const series = await source.getSeries((await params).slug);
  return series ? { title: series.title, description: series.synopsis } : { title: "Not found" };
}

export default function SeriesPage({ params }: Props) {
  return (
    <Suspense fallback={<div className="mt-8 h-96 animate-pulse rounded-[2rem] bg-surface" />}>
      <SeriesView params={params} />
    </Suspense>
  );
}

async function SeriesView({ params }: Props) {
  const { slug } = await params;
  const series = await source.getSeries(slug);
  if (!series) notFound();
  const [chapters, all, meta] = await Promise.all([source.getChapters(slug), source.getAll(), source.getMeta()]);
  const similar = similarTo(all, series);

  const facts = [
    { label: "Rating", value: series.rating.toFixed(1), star: true },
    { label: meta.popularityUnit, value: formatCount(series.views.all) },
    { label: "Chapters", value: series.chapterCountUnknown ? "n/a" : String(series.chapterCount) },
    { label: "Updated", value: formatDate(series.updatedAt) },
  ];

  return (
    <>
      <section className="relative mt-6 overflow-hidden rounded-[2rem] border border-line bg-surface">
        <img src={series.cover} alt="" aria-hidden="true" className="pointer-events-none absolute inset-0 size-full scale-125 object-cover opacity-40 blur-3xl" />
        <div className="absolute inset-0 bg-gradient-to-t from-surface via-surface/80 to-surface/40" />
        <div className="relative grid gap-8 p-6 sm:grid-cols-[auto_1fr] sm:p-10">
          <img
            src={series.cover} alt={`Cover of ${series.title}`} width={600} height={900}
            className="mx-auto aspect-[2/3] w-48 rounded-2xl object-cover shadow-2xl ring-1 ring-white/10 sm:mx-0 sm:w-56 lg:w-64"
          />
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-accent">
              {TYPE_LABEL[series.type]} · {STATUS_LABEL[series.status]} · {series.year}
            </p>
            <h1 className="mt-3 text-4xl font-extrabold leading-[1.05] sm:text-5xl">{series.title}</h1>
            {series.altTitles.length > 0 && <p className="mt-1.5 text-sm text-muted">Also known as {series.altTitles.join(", ")}</p>}
            <p className="mt-2 text-muted">
              by <Link href={`/browse?q=${encodeURIComponent(series.author)}`} className="font-semibold text-text hover:text-accent">{series.author}</Link>
            </p>

            <dl className="mt-5 grid max-w-lg grid-cols-2 gap-2 sm:grid-cols-4">
              {facts.map((fact) => (
                <div key={fact.label} className="rounded-xl border border-line bg-bg/50 px-3 py-2.5">
                  <dt className="text-[11px] font-bold uppercase tracking-wider text-muted">{fact.label}</dt>
                  <dd className="mt-0.5 flex items-center gap-1 font-display text-lg font-bold">
                    {fact.star && <StarIcon width={15} height={15} className="text-accent-2" />}
                    {fact.value}
                  </dd>
                </div>
              ))}
            </dl>

            <p className="mt-5 max-w-2xl leading-relaxed text-muted">{series.synopsis}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {series.genres.map((g) => (
                <Link
                  key={g} href={`/browse?genre=${encodeURIComponent(g)}`}
                  className="rounded-full border border-line bg-bg/40 px-3 py-1 text-xs font-semibold text-muted transition hover:border-accent hover:text-accent"
                >
                  {g}
                </Link>
              ))}
            </div>
            <SeriesActions slug={series.slug} />
            {(series.officialUrl || series.sourceUrl) && (
              <p className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm">
                {series.officialUrl && (
                  <a href={series.officialUrl} target="_blank" rel="noreferrer" className="font-semibold text-accent hover:underline">
                    Read the official release ↗
                  </a>
                )}
                {series.sourceUrl && (
                  <a href={series.sourceUrl} target="_blank" rel="noreferrer" className="text-muted hover:text-text">
                    View on {meta.name} ↗
                  </a>
                )}
              </p>
            )}
          </div>
        </div>
      </section>

      {meta.credit && meta.placeholderPages && (
        <p className="mt-8 rounded-2xl border border-line bg-surface px-4 py-3 text-sm text-muted">
          This site does not host this series. The chapters below open generated placeholder pages that show how the reader works.
          {series.officialUrl && " Use the official release link above to read the real thing."}
        </p>
      )}
      <ChapterList slug={series.slug} chapters={chapters} sample={Boolean(series.chapterCountUnknown)} />

      {similar.length > 0 && (
        <ScrollRow title="You may also like">
          {similar.map((s) => (
            <RowItem key={s.slug}>
              <SeriesCard series={s} />
            </RowItem>
          ))}
        </ScrollRow>
      )}
    </>
  );
}
