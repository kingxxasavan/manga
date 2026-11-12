import type { Metadata } from "next";
import { Suspense } from "react";
import { BrowseClient } from "@/components/browse-client";
import { GENRES, source } from "@/lib/source";

export const metadata: Metadata = { title: "Browse" };

export default async function BrowsePage() {
  const all = await source.getAll();
  return (
    <Suspense fallback={<div className="mt-8 h-96 animate-pulse rounded-3xl bg-surface" />}>
      <BrowseClient all={all} genres={GENRES} />
    </Suspense>
  );
}
