import { describe, expect, it } from "vitest";
import { checkEmail, estimateRange, quote } from "@/lib/pricing";
import { getService, SERVICES, type Service } from "@/lib/services";
import { MAX_ORDER_CENTS, MIN_ORDER_CENTS } from "@/lib/site";

const website = getService("website")!;
const DETAILS = "A site for my bakery with a menu.";
const base = { type: "landing", pages: 1, features: [], level: "basic", details: DETAILS, links: "", revisions: 1, speed: "standard" };

const scripts = getService("scripts")!;
const scriptBase = { type: "script", complexity: "simple", level: "basic", extras: [], details: "Rename all my files by date.", revisions: 1, speed: "standard" };

const priced = (service: Service, input: Record<string, unknown>) => {
  const r = quote(service, input);
  if (!r.ok) throw new Error(JSON.stringify(r.errors));
  return r.quote;
};

describe("quote", () => {
  it("bases the cheapest website on its starting amount", () => {
    expect(priced(website, base).total).toBe(45_00);
  });
  it("adds options, extra units and extra revisions", () => {
    // 90 + 2 extra pages (12) + form (5) + blog (15) + 1 extra revision (5) = 127
    expect(priced(website, { ...base, type: "multi", pages: 5, features: ["blog", "form"], revisions: 2 }).total).toBe(127_00);
  });
  it("scales with the level of finish and with rush, rounding to a whole dollar", () => {
    expect(priced(website, { ...base, level: "polished" }).total).toBe(54_00); // 45 x 1.2
    expect(priced(website, { ...base, level: "premium", speed: "rush" }).total).toBe(72_00); // 45 x 1.4 x 1.15 = 72.45
    expect(priced(website, { ...base, type: "multi", pages: 5, features: ["blog", "form"], level: "polished", revisions: 2, speed: "rush" }).total).toBe(175_00); // 127 x 1.2 x 1.15 = 175.26
  });
  it("scales with complexity where a service asks for it", () => {
    expect(priced(scripts, scriptBase).total).toBe(25_00);
    expect(priced(scripts, { ...scriptBase, complexity: "complex" }).total).toBe(50_00);
    expect(priced(scripts, { ...scriptBase, complexity: "huge" }).total).toBe(100_00);
  });
  it("gives the same result whatever order multi picks arrive in, and ignores duplicates", () => {
    expect(quote(website, { ...base, features: ["blog", "form"] })).toEqual(quote(website, { ...base, features: ["form", "blog", "blog"] }));
  });
  it("returns an estimate range around the calculated amount", () => {
    const q = priced(website, { ...base, type: "multi" }); // 90
    expect(q.estimate).toEqual({ low: 75_00, high: 105_00 });
    expect(q.reason).toBeUndefined();
  });
  it("gives no estimate above the cap, so those are priced by hand", () => {
    const giant: Service = {
      id: "giant", name: "Giant", tagline: "", icon: "code", delivery: "", examples: [],
      questions: [{ id: "size", kind: "choice", label: "Size", options: [{ id: "big", label: "Big", price: MAX_ORDER_CENTS + 100 }] }],
    };
    const q = priced(giant, { size: "big" });
    expect(q.total).toBeGreaterThan(MAX_ORDER_CENTS);
    expect(q).toMatchObject({ estimate: null, reason: "over_cap" });
  });
  it("never estimates the custom service", () => {
    const q = priced(getService("custom")!, { details: "A study guide for my biology exam.", budget: "unsure", deadline: "week", links: "" });
    expect(q).toMatchObject({ total: 0, estimate: null, reason: "quote_only" });
  });
  it("rejects missing, unknown and out of range answers", () => {
    const r = quote(website, { ...base, type: "castle", pages: 99, features: ["nope"], level: "gold", details: "short", speed: undefined });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(Object.keys(r.errors).sort()).toEqual(["details", "features", "level", "pages", "speed", "type"]);
  });
  it("rejects numbers that are not whole or not numbers", () => {
    expect(quote(website, { ...base, pages: 1.5 }).ok).toBe(false);
    expect(quote(website, { ...base, pages: "3" }).ok).toBe(false);
    expect(quote(website, { ...base, pages: -4 }).ok).toBe(false);
    expect(quote(website, { ...base, revisions: Number.NaN }).ok).toBe(false);
  });
  it("drops answers to questions that do not exist", () => {
    const r = quote(website, { ...base, total: 1, discount: 100, estimate: { low: 1, high: 2 } });
    expect(r.ok && Object.keys(r.answers).sort()).toEqual(["details", "features", "level", "links", "pages", "revisions", "speed", "type"]);
  });
  it("trims text and enforces its length", () => {
    const r = quote(website, { ...base, details: `   ${DETAILS}   ` });
    expect(r.ok && r.answers.details).toBe(DETAILS);
    expect(quote(website, { ...base, details: "x".repeat(2001) }).ok).toBe(false);
  });
});

describe("estimateRange", () => {
  it("spreads 15 percent either side, rounded outward to 5 dollars", () => {
    expect(estimateRange(100_00)).toEqual({ low: 85_00, high: 115_00 });
    expect(estimateRange(461_00)).toEqual({ low: 390_00, high: 535_00 });
  });
  it("always stays inside the allowed prices with low below high", () => {
    for (const total of [1_00, 5_00, 12_00, 19_00, 999_00, 1750_00, MAX_ORDER_CENTS]) {
      const { low, high } = estimateRange(total);
      expect(low).toBeGreaterThanOrEqual(MIN_ORDER_CENTS);
      expect(high).toBeLessThanOrEqual(MAX_ORDER_CENTS);
      expect(low).toBeLessThan(high);
      expect(low % 500).toBe(0);
      expect(high % 500).toBe(0);
    }
  });
});

describe("service config", () => {
  it("has unique ids and unique question ids", () => {
    expect(new Set(SERVICES.map((s) => s.id)).size).toBe(SERVICES.length);
    for (const s of SERVICES) expect(new Set(s.questions.map((q) => q.id)).size).toBe(s.questions.length);
  });
  it("asks about level on every estimated service, and about size or complexity", () => {
    for (const s of SERVICES.filter((x) => !x.quoteOnly)) {
      const ids = s.questions.map((q) => q.id);
      expect(ids, s.id).toContain("level");
      expect(ids.includes("complexity") || ids.includes("pages"), s.id).toBe(true);
    }
  });
  // Builds a request by picking one option per choice question and a count per number question.
  const request = (s: Service, pick: (ids: string[], questionId: string) => string, count: (q: { min: number; max: number; included: number }) => number, multi: (ids: string[]) => string[]) => {
    const input: Record<string, unknown> = {};
    for (const q of s.questions) {
      if (q.kind === "choice") input[q.id] = pick(q.options.map((o) => o.id), q.id);
      else if (q.kind === "multi") input[q.id] = multi(q.options.map((o) => o.id));
      else if (q.kind === "number") input[q.id] = count(q);
      else input[q.id] = q.required ? "Enough detail to pass." : "";
    }
    return input;
  };
  const estimated = SERVICES.filter((x) => !x.quoteOnly);

  it("can produce an estimate for the cheapest possible request of each service", () => {
    for (const s of estimated) {
      const q = priced(s, request(s, (ids) => ids[0], (n) => n.min, () => []));
      expect(q.estimate, s.id).not.toBeNull();
      expect(q.estimate!.low, s.id).toBeGreaterThanOrEqual(MIN_ORDER_CENTS);
    }
  });
  it("only offers the very complex tier for software", () => {
    for (const s of SERVICES) {
      const complexity = s.questions.find((q) => q.id === "complexity");
      const hasHuge = complexity?.kind === "choice" && complexity.options.some((o) => o.id === "huge");
      expect(hasHuge, s.id).toBe(s.id === "scripts");
    }
  });
  it("lets a very complex full app or game go well above 500 dollars", () => {
    const q = priced(scripts, { ...scriptBase, type: "app", complexity: "huge", level: "premium" }); // 150 x 4 x 1.4 = 840
    expect(q.total).toBe(840_00);
    expect(q.estimate!.low).toBeGreaterThan(500_00);
    expect(q.estimate!.high).toBeLessThanOrEqual(MAX_ORDER_CENTS);
  });
  it("never needs a hand made price for anything the questions can produce", () => {
    // Even with everything maxed out, each service stays under the cap and gets an estimate.
    for (const s of estimated) {
      const q = priced(s, request(s, (ids, id) => (id === "type" && s.id === "scripts" ? "app" : ids[ids.length - 1]), (n) => n.max, (ids) => ids));
      expect(q.estimate, `${s.id} maxed out`).not.toBeNull();
    }
  });
});

describe("checkEmail", () => {
  it("accepts and normalises real addresses, rejects the rest", () => {
    expect(checkEmail("  Me@Example.com ")).toBe("me@example.com");
    for (const bad of ["", "nope", "a@b", "a b@c.com", 5, null, `${"a".repeat(250)}@b.com`]) expect(checkEmail(bad)).toBeNull();
  });
});
