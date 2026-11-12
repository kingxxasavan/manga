import type { Metadata } from "next";
import { Suspense } from "react";
import { LibraryClient } from "@/components/library-client";
import { source } from "@/lib/source";

export const metadata: Metadata = { title: "Library" };

export default async function LibraryPage() {
  const all = await source.getAll();
  return (
    <Suspense fallback={<div className="mt-8 h-96 animate-pulse rounded-3xl bg-surface" />}>
      <LibraryClient all={all} />
    </Suspense>
  );
}
