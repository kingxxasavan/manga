import { describe, expect, it } from "vitest";
import { cleanDescription, toCatalogue, toSeries, type MdManga } from "@/lib/source/mangadex-map";

const NOW = Date.UTC(2026, 0, 31);

const entry = (over: Partial<MdManga["attributes"]> = {}, id = "11111111-2222-3333-4444-555555555555"): MdManga => ({
  id,
  attributes: {
    title: { en: "Test Series" },
    altTitles: [{ ja: "Tesuto" }],
    description: { en: "A plain description." },
    originalLanguage: "ko",
    status: "ongoing",
    year: 2020,
    lastChapter: "42.5",
    updatedAt: "2026-01-31T00:00:00+00:00",
    links: { engtl: "https://example.com/official" },
    tags: [
      { attributes: { name: { en: "Fantasy" }, group: "genre" } },
      { attributes: { name: { en: "Action" }, group: "genre" } },
      { attributes: { name: { en: "Long Strip" }, group: "format" } },
    ],
    ...over,
  },
  relationships: [
    { type: "author", attributes: { name: "Writer" } },
    { type: "author", attributes: { name: "Writer" } },
    { type: "cover_art", attributes: { fileName: "abc-123.jpg" } },
  ],
});

describe("toSeries", () => {
  it("maps a MangaDex entry", () => {
    const s = toSeries(entry(), { follows: 1000, rating: { bayesian: 8.76 } }, NOW)!;
    expect(s).toMatchObject({
      slug: "test-series", title: "Test Series", type: "manhwa", status: "ongoing",
      author: "Writer", genres: ["Action", "Fantasy"], rating: 8.8, chapterCount: 42, year: 2020,
      cover: "/api/md-cover/11111111-2222-3333-4444-555555555555/abc-123.jpg",
      officialUrl: "https://example.com/official",
    });
    expect(s.views).toEqual({ today: 1000, week: 1000, all: 1000 });
    expect(s.altTitles).toEqual(["Tesuto"]);
  });
  it("ranks stale series lower for today and this week", () => {
    const s = toSeries(entry({ updatedAt: "2025-10-01T00:00:00+00:00" }), { follows: 1000, rating: { bayesian: 8 } }, NOW)!;
    expect(s.views.all).toBe(1000);
    expect(s.views.week).toBeLessThan(1000);
    expect(s.views.today).toBeLessThan(s.views.week);
  });
  it("falls back to an English alt title, then any title", () => {
    expect(toSeries(entry({ title: { "ko-ro": "Romaja" }, altTitles: [{ en: "English Name" }] }), undefined, NOW)!.title).toBe("English Name");
    expect(toSeries(entry({ title: { "ko-ro": "Romaja" }, altTitles: [] }), undefined, NOW)!.title).toBe("Romaja");
  });
  it("drops entries the site cannot show", () => {
    expect(toSeries(entry({ originalLanguage: "fr" }), undefined, NOW)).toBeNull();
    expect(toSeries(entry({ status: "cancelled" }), undefined, NOW)).toBeNull();
    expect(toSeries({ ...entry(), relationships: [] }, undefined, NOW)).toBeNull();
    const badCover = { ...entry(), relationships: [{ type: "cover_art", attributes: { fileName: "../etc/passwd" } }] };
    expect(toSeries(badCover, undefined, NOW)).toBeNull();
  });
  it("keeps series with no chapter count and flags the count as a stand in", () => {
    const s = toSeries(entry({ lastChapter: "" }), undefined, NOW)!;
    expect(s.chapterCountUnknown).toBe(true);
    expect(s.chapterCount).toBeGreaterThan(0);
    expect(toSeries(entry({ lastChapter: null }), undefined, NOW)!.chapterCountUnknown).toBe(true);
    expect(toSeries(entry(), undefined, NOW)!.chapterCountUnknown).toBeUndefined();
  });
  it("ignores an official link that is not https", () => {
    expect(toSeries(entry({ links: { engtl: "javascript:alert(1)" } }), undefined, NOW)!.officialUrl).toBeUndefined();
    expect(toSeries(entry({ links: null }), undefined, NOW)!.officialUrl).toBeUndefined();
  });
});

describe("toCatalogue", () => {
  it("removes duplicate slugs and unusable entries", () => {
    const out = toCatalogue([entry(), entry({}, "99999999-2222-3333-4444-555555555555"), entry({ originalLanguage: "fr" })], {}, NOW);
    expect(out).toHaveLength(1);
  });
});

describe("cleanDescription", () => {
  it("keeps the opening prose and strips markdown", () => {
    expect(cleanDescription("A **bold** [link](https://x.y) story.\n\n---\n**Links:**\n- [a](b)")).toBe("A bold link story.");
  });
  it("shortens very long text on a word boundary", () => {
    const out = cleanDescription("word ".repeat(300));
    expect(out.length).toBeLessThanOrEqual(521);
    expect(out.endsWith("…")).toBe(true);
  });
});
