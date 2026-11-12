import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { Reader } from "@/components/reader/reader";
import { source } from "@/lib/source";

type Props = { params: Promise<{ slug: string; chapter: string }> };

export async function generateStaticParams() {
  return (await source.getAll()).map((s) => ({ slug: s.slug, chapter: "1" }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug, chapter } = await params;
  const series = await source.getSeries(slug);
  return series ? { title: `${series.title}, chapter ${chapter}` } : { title: "Not found" };
}

export default function ReadPage({ params }: Props) {
  return (
    <Suspense fallback={<div className="min-h-dvh bg-[#17181c]" />}>
      <ReaderLoader params={params} />
    </Suspense>
  );
}

async function ReaderLoader({ params }: Props) {
  const { slug, chapter } = await params;
  const number = /^\d+$/.test(chapter) ? Number(chapter) : NaN;
  const series = await source.getSeries(slug);
  if (!series || Number.isNaN(number)) notFound();
  const [chapters, pages] = await Promise.all([source.getChapters(slug), source.getChapterPages(slug, number)]);
  if (pages.length === 0) notFound();
  return (
    <Reader
      series={{ slug: series.slug, title: series.title, type: series.type }}
      chapter={number}
      chapters={chapters.map((c) => ({ number: c.number, title: c.title }))}
      pages={pages}
    />
  );
}
