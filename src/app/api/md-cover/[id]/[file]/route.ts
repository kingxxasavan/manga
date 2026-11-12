/**
 * Serves MangaDex cover thumbnails from this site's own origin. MangaDex asks
 * third party sites not to hotlink its image host from the browser.
 * The id and file name are strictly validated so this can only ever fetch covers.
 */
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const FILE = /^[\w-]+\.(jpe?g|png|gif|webp)$/i;

export async function GET(_request: Request, { params }: { params: Promise<{ id: string; file: string }> }) {
  const { id, file } = await params;
  if (!ID.test(id) || !FILE.test(file)) return new Response("Not found", { status: 404 });
  try {
    const upstream = await fetch(`https://uploads.mangadex.org/covers/${id}/${file}.512.jpg`, {
      headers: { "User-Agent": "manga-site/0.1" },
      signal: AbortSignal.timeout(15_000),
    });
    const type = upstream.headers.get("content-type") ?? "";
    if (!upstream.ok || !type.startsWith("image/")) return new Response("Cover unavailable", { status: 502 });
    return new Response(upstream.body, {
      headers: {
        "Content-Type": type,
        "Cache-Control": "public, max-age=604800, s-maxage=2592000, stale-while-revalidate=2592000",
      },
    });
  } catch {
    return new Response("Cover unavailable", { status: 502 });
  }
}
