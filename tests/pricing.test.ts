import { describe, expect, it } from "vitest";
import { checkEmail, estimate, quote } from "@/lib/pricing";
import { getService, SERVICES, type Service } from "@/lib/services";
import { MAX_ORDER_CENTS } from "@/lib/site";

const website = getService("website")!;
const DETAILS = "A site for my bakery with a menu.";
const base = { type: "landing", pages: 1, features: [], details: DETAILS, links: "", revisions: 1, speed: "standard" };

const total = (service: Service, input: Record<string, unknown>) => {
  const r = quote(service, input);
  if (!r.ok) throw new Error(JSON.stringify(r.errors));
  return r.quote;
};

describe("quote", () => {
  it("prices the cheapest website at its base price", () => {
    expect(total(website, base).total).toBe(149_00);
  });
  it("adds options, extra units and extra revisions", () => {
    // 299 + 2 extra pages (70) + form (20) + blog (60) + 1 extra revision (12) = 461
    const q = total(website, { ...base, type: "multi", pages: 5, features: ["blog", "form"], revisions: 2 });
    expect(q.total).toBe(461_00);
    expect(q.needsManualQuote).toBe(false);
  });
  it("applies the rush multiplier to everything and rounds to a whole dollar", () => {
    // 149 * 1.3 = 193.7 -> 194
    expect(total(website, { ...base, speed: "rush" }).total).toBe(194_00);
  });
  it("gives the same result whatever order multi picks arrive in, and ignores duplicates", () => {
    const a = quote(website, { ...base, features: ["blog", "form"] });
    const b = quote(website, { ...base, features: ["form", "blog", "blog"] });
    expect(a).toEqual(b);
  });
  it("sends orders above the cap to a manual quote instead of a price", () => {
    const q = total(website, {
      ...base, type: "store", pages: 20, features: ["form", "blog", "booking", "payments", "copy"], revisions: 6, speed: "rush",
    });
    expect(q.total).toBeGreaterThan(MAX_ORDER_CENTS);
    expect(q).toMatchObject({ needsManualQuote: true, reason: "over_cap" });
  });
  it("never prices the custom service", () => {
    const custom = getService("custom")!;
    const q = total(custom, { details: "A study guide for my biology exam.", budget: "under50", deadline: "week", links: "" });
    expect(q).toMatchObject({ total: 0, needsManualQuote: true, reason: "quote_only" });
  });
  it("rejects missing, unknown and out of range answers", () => {
    const r = quote(website, { ...base, type: "castle", pages: 99, features: ["nope"], details: "short", speed: undefined });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(Object.keys(r.errors).sort()).toEqual(["details", "features", "pages", "speed", "type"]);
  });
  it("rejects prices smuggled in as numbers that are not whole or not numbers", () => {
    expect(quote(website, { ...base, pages: 1.5 }).ok).toBe(false);
    expect(quote(website, { ...base, pages: "3" }).ok).toBe(false);
    expect(quote(website, { ...base, pages: -4 }).ok).toBe(false);
    expect(quote(website, { ...base, revisions: Number.NaN }).ok).toBe(false);
  });
  it("drops answers to questions that do not exist", () => {
    const r = quote(website, { ...base, total: 1, discount: 100 });
    expect(r.ok && Object.keys(r.answers).sort()).toEqual(["details", "features", "links", "pages", "revisions", "speed", "type"]);
  });
  it("trims text and enforces its length", () => {
    const r = quote(website, { ...base, details: `   ${DETAILS}   ` });
    expect(r.ok && r.answers.details).toBe(DETAILS);
    expect(quote(website, { ...base, details: "x".repeat(2001) }).ok).toBe(false);
  });
});

describe("service config", () => {
  it("has unique ids and unique question ids", () => {
    expect(new Set(SERVICES.map((s) => s.id)).size).toBe(SERVICES.length);
    for (const s of SERVICES) expect(new Set(s.questions.map((q) => q.id)).size).toBe(s.questions.length);
  });
  it("shows a starting price that is really the cheapest possible order", () => {
    for (const s of SERVICES.filter((x) => !x.quoteOnly)) {
      const cheapest: Record<string, unknown> = {};
      for (const q of s.questions) {
        if (q.kind === "choice") {
          cheapest[q.id] = [...q.options].sort((a, b) => (a.price ?? 0) * (a.multiplier ?? 1) - (b.price ?? 0) * (b.multiplier ?? 1) || (a.multiplier ?? 1) - (b.multiplier ?? 1))[0].id;
        } else if (q.kind === "multi") cheapest[q.id] = [];
        else if (q.kind === "number") cheapest[q.id] = q.min;
        else cheapest[q.id] = q.required ? "Enough detail to pass." : "";
      }
      expect(total(s, cheapest).total, s.id).toBe(s.startingAt);
    }
  });
  it("never produces a paid price below 5 dollars", () => {
    for (const s of SERVICES.filter((x) => !x.quoteOnly)) expect(s.startingAt).toBeGreaterThanOrEqual(5_00);
  });
});

describe("estimate", () => {
  it("counts only what has been answered so far", () => {
    expect(estimate(website, {})).toBe(0);
    expect(estimate(website, { type: "multi" })).toBe(299_00);
    expect(estimate(website, { type: "multi", speed: "rush", features: ["blog"] })).toBe(467_00);
  });
  it("matches quote once everything is answered", () => {
    const input = { ...base, type: "multi", pages: 6, features: ["payments"], revisions: 3, speed: "rush" };
    expect(estimate(website, input)).toBe(total(website, input).total);
  });
});

describe("checkEmail", () => {
  it("accepts and normalises real addresses, rejects the rest", () => {
    expect(checkEmail("  Me@Example.com ")).toBe("me@example.com");
    for (const bad of ["", "nope", "a@b", "a b@c.com", 5, null, `${"a".repeat(250)}@b.com`]) expect(checkEmail(bad)).toBeNull();
  });
});
