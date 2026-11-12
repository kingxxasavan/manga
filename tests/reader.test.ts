import { describe, expect, it } from "vitest";
import {
  clampPage, keyAction, resolveDirection, resolveMode, spreadFor, spreads, step, swipeAction, zoneAction,
} from "@/lib/reader/logic";

describe("spreads", () => {
  it("keeps the first page alone and pairs the rest", () => {
    expect(spreads(6)).toEqual([[0], [1, 2], [3, 4], [5]]);
    expect(spreads(5)).toEqual([[0], [1, 2], [3, 4]]);
    expect(spreads(1)).toEqual([[0]]);
    expect(spreads(0)).toEqual([]);
  });
  it("finds the spread holding a page", () => {
    expect(spreadFor(4, 6)).toEqual([3, 4]);
    expect(spreadFor(9, 6)).toEqual([]);
  });
});

describe("step", () => {
  it("moves one page in single mode and reports chapter edges", () => {
    expect(step("single", 2, 5, 1)).toEqual({ kind: "page", page: 3 });
    expect(step("single", 4, 5, 1)).toEqual({ kind: "end" });
    expect(step("single", 0, 5, -1)).toEqual({ kind: "start" });
  });
  it("moves a whole spread in double mode, from either page of it", () => {
    expect(step("double", 1, 6, 1)).toEqual({ kind: "page", page: 3 });
    expect(step("double", 2, 6, 1)).toEqual({ kind: "page", page: 3 });
    expect(step("double", 4, 6, -1)).toEqual({ kind: "page", page: 1 });
    expect(step("double", 5, 6, 1)).toEqual({ kind: "end" });
    expect(step("double", 0, 6, -1)).toEqual({ kind: "start" });
  });
  it("handles an empty chapter", () => {
    expect(step("single", 0, 0, 1)).toEqual({ kind: "end" });
  });
});

describe("input mapping", () => {
  it("flips arrow keys with reading direction", () => {
    expect(keyAction("ArrowRight", "single", "ltr")).toBe("next");
    expect(keyAction("ArrowRight", "single", "rtl")).toBe("prev");
    expect(keyAction("ArrowLeft", "double", "rtl")).toBe("next");
    expect(keyAction(" ", "single", "rtl")).toBe("next");
    expect(keyAction("a", "single", "rtl")).toBeNull();
  });
  it("leaves keys alone in strip mode", () => {
    expect(keyAction("ArrowRight", "strip", "ltr")).toBeNull();
    expect(keyAction(" ", "strip", "ltr")).toBeNull();
  });
  it("maps tap zones", () => {
    expect(zoneAction(0.1, "ltr")).toBe("prev");
    expect(zoneAction(0.1, "rtl")).toBe("next");
    expect(zoneAction(0.9, "rtl")).toBe("prev");
    expect(zoneAction(0.5, "rtl")).toBe("menu");
  });
  it("maps swipes", () => {
    expect(swipeAction(-80, "ltr")).toBe("next");
    expect(swipeAction(-80, "rtl")).toBe("prev");
    expect(swipeAction(80, "rtl")).toBe("next");
  });
});

describe("defaults", () => {
  it("picks strip for webtoons and right to left pages for manga", () => {
    expect(resolveMode("auto", "manhwa")).toBe("strip");
    expect(resolveMode("auto", "manga")).toBe("single");
    expect(resolveMode("double", "manhwa")).toBe("double");
    expect(resolveDirection("auto", "manga")).toBe("rtl");
    expect(resolveDirection("auto", "manhua")).toBe("ltr");
    expect(resolveDirection("ltr", "manga")).toBe("ltr");
  });
  it("clamps saved pages", () => {
    expect(clampPage(99, 10)).toBe(9);
    expect(clampPage(-3, 10)).toBe(0);
    expect(clampPage(NaN, 10)).toBe(0);
    expect(clampPage(2, 0)).toBe(0);
  });
});
