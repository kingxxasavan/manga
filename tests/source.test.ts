import { describe, expect, it } from "vitest";
import { source } from "@/lib/source";
import { renderCover, renderPage } from "@/lib/source/art";
import { filterSeries } from "@/lib/source/query";

describe("demo source", () => {
  it("has a varied catalogue with unique slugs", async () => {
    const all = await source.getAll();
    expect(all.length).toBeGreaterThanOrEqual(40);
    expect(new Set(all.map((s) => s.slug)).size).toBe(all.length);
    for (const type of ["manga", "manhwa", "manhua"] as const) {
      expect((await source.getByType(type)).length).toBeGreaterThan(5);
    }
  });
  it("ranks popular lists by the chosen range", async () => {
    const week = await source.getPopular("week");
    expect(week).toHaveLength(10);
    for (let i = 1; i < week.length; i++) {
      expect(week[i - 1].views.week).toBeGreaterThanOrEqual(week[i].views.week);
    }
  });
  it("returns chapters and pages, and nothing for bad input", async () => {
    const [first] = await source.getAll();
    const chapters = await source.getChapters(first.slug);
    expect(chapters).toHaveLength(first.chapterCount);
    const pages = await source.getChapterPages(first.slug, 1);
    expect(pages).toHaveLength(chapters[0].pageCount);
    expect(await source.getChapterPages(first.slug, 0)).toEqual([]);
    expect(await source.getChapterPages(first.slug, first.chapterCount + 1)).toEqual([]);
    expect(await source.getChapterPages("missing", 1)).toEqual([]);
    expect(await source.getSeries("missing")).toBeNull();
  });
  it("renders deterministic svg artwork", async () => {
    const all = await source.getAll();
    const manga = all.find((s) => s.type === "manga")!;
    const strip = all.find((s) => s.type === "manhwa")!;
    expect(renderCover(manga)).toBe(renderCover(manga));
    expect(renderCover(manga)).toMatch(/^<svg /);
    expect(renderPage(manga, 1, 0)).toContain('viewBox="0 0 800 1200"');
    expect(renderPage(strip, 1, 1)).toContain('viewBox="0 0 800 1800"');
    expect(renderPage(manga, 1, 1)).not.toBe(renderPage(manga, 1, 2));
  });
});

describe("filterSeries", () => {
  it("filters by text, type, status and every selected genre", async () => {
    const all = await source.getAll();
    expect(filterSeries(all, { q: "lantern" }).map((s) => s.slug)).toEqual(["the-lantern-clerk"]);
    expect(filterSeries(all, { q: "seo minjae" })).toHaveLength(1);
    expect(filterSeries(all, { q: "yu lu ji" })).toHaveLength(1);
    expect(filterSeries(all, { type: "manhua" }).every((s) => s.type === "manhua")).toBe(true);
    expect(filterSeries(all, { status: "completed" }).every((s) => s.status === "completed")).toBe(true);
    const both = filterSeries(all, { genres: ["Fantasy", "Comedy"] });
    expect(both.length).toBeGreaterThan(0);
    expect(both.every((s) => s.genres.includes("Fantasy") && s.genres.includes("Comedy"))).toBe(true);
    expect(filterSeries(all, { q: "zzzz" })).toEqual([]);
  });
  it("sorts", async () => {
    const all = await source.getAll();
    const az = filterSeries(all, { sort: "az" }).map((s) => s.title);
    expect(az).toEqual([...az].sort((a, b) => a.localeCompare(b)));
    const rated = filterSeries(all, { sort: "rating" });
    expect(rated[0].rating).toBe(Math.max(...all.map((s) => s.rating)));
    expect(all[0].slug).toBe("ashfall-courier"); // input is not mutated
  });
});
