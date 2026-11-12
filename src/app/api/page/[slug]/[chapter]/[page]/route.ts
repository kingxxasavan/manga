import { renderPage } from "@/lib/source/art";
import { findSeries, pageCountFor } from "@/lib/source/demo-data";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ slug: string; chapter: string; page: string }> },
) {
  const { slug, chapter, page } = await params;
  const series = findSeries(slug);
  const chapterNumber = Number(chapter);
  const index = Number(page);
  const valid =
    series &&
    Number.isInteger(chapterNumber) && chapterNumber >= 1 && chapterNumber <= series.chapterCount &&
    Number.isInteger(index) && index >= 0 && index < pageCountFor(series, chapterNumber);
  if (!valid) return new Response("Not found", { status: 404 });
  return new Response(renderPage(series, chapterNumber, index), {
    headers: {
      "Content-Type": "image/svg+xml; charset=utf-8",
      "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
    },
  });
}
