import { renderCover } from "@/lib/source/art";
import { source } from "@/lib/source";

export async function GET(_request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const series = await source.getSeries(slug);
  if (!series) return new Response("Not found", { status: 404 });
  return new Response(renderCover(series), {
    headers: {
      "Content-Type": "image/svg+xml; charset=utf-8",
      "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
    },
  });
}
