import { describe, expect, it } from "vitest";
import { recommend, similarTo } from "@/lib/recommend";
import type { Series } from "@/lib/types";

const make = (slug: string, genres: string[], rating: number): Series => ({
  slug, title: slug, cover: "", altTitles: [], author: "A", type: "manga", status: "ongoing", genres,
  synopsis: "", rating, views: { today: 0, week: 0, all: 0 }, year: 2020, chapterCount: 1,
  updatedAt: "2026-01-01T00:00:00.000Z",
});

const all = [
  make("a", ["Action", "Fantasy"], 7),
  make("b", ["Action"], 9),
  make("c", ["Romance"], 9.5),
  make("d", ["Fantasy", "Romance"], 8),
  make("e", ["Horror"], 6),
];

describe("recommend", () => {
  it("falls back to top rated with no history", () => {
    const out = recommend(all, [], []);
    expect(out.personalised).toBe(false);
    expect(out.series.map((s) => s.slug)).toEqual(["c", "b", "d", "a", "e"]);
  });
  it("scores unread series by genres already read, and leaves read ones out", () => {
    const out = recommend(all, ["a"], []);
    expect(out.personalised).toBe(true);
    // b (Action) and d (Fantasy) both score 1, rating breaks the tie
    expect(out.series.map((s) => s.slug)).toEqual(["b", "d"]);
  });
  it("weights bookmarks above history", () => {
    const out = recommend(all, ["b"], ["c"]);
    // Romance is worth 2, Action 1: d (Romance) beats a (Action)
    expect(out.series.map((s) => s.slug)).toEqual(["d", "a"]);
  });
  it("ignores unknown slugs and respects the limit", () => {
    expect(recommend(all, ["nope"], []).personalised).toBe(false);
    expect(recommend(all, [], [], 2).series).toHaveLength(2);
  });
});

describe("similarTo", () => {
  it("orders by shared genres and leaves out the series itself", () => {
    expect(similarTo(all, all[0]).map((s) => s.slug)).toEqual(["b", "d"]);
  });
});
