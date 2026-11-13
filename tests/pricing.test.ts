import { describe, expect, it } from "vitest";
import { checkEmail, defaultAnswer, estimateRange, quote, visibleQuestions } from "@/lib/pricing";
import { getService, SERVICES, type Service } from "@/lib/services";
import { MAX_ORDER_CENTS, MIN_ORDER_CENTS } from "@/lib/site";
import { FONTS, IMAGERY, PALETTES, resolveLook, TEMPLATES } from "@/lib/templates";

const website = getService("website")!;
const writing = getService("writing")!;
const scripts = getService("scripts")!;
const custom = getService("custom")!;

const DETAILS = "A site for my bakery with a menu.";
const look = { template: "business", palette: "midnight", font: "modern", imagery: "photo" };
const base = { type: "landing", siteName: "Crumb", ...look, pages: 3, features: [], level: "basic", details: DETAILS, links: "", revisions: 1, speed: "standard" };
const scriptBase = { type: "script", complexity: "simple", level: "basic", extras: [], details: "Rename all my files by date.", revisions: 1, speed: "standard" };
const essayBase = {
  type: "essay", pages: 3, sources: "", citation: "apa", tone: "academic", font: "times", fontSize: "12",
  complexity: "simple", level: "basic", details: "Why cities should plant more trees.", revisions: 1, speed: "standard",
};

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
  });
  it("scales with complexity where a service asks for it", () => {
    expect(priced(scripts, scriptBase).total).toBe(25_00);
    expect(priced(scripts, { ...scriptBase, complexity: "complex" }).total).toBe(50_00);
    expect(priced(scripts, { ...scriptBase, complexity: "huge" }).total).toBe(88_00); // 25 x 3.5 = 87.5
  });
  it("does not let the look of a website change its estimate", () => {
    const plain = priced(website, base).total;
    for (const template of TEMPLATES) for (const palette of PALETTES) {
      expect(priced(website, { ...base, template: template.id, palette: palette.id, font: "tech", imagery: "none" }).total).toBe(plain);
    }
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
    expect(priced(giant, { size: "big" })).toMatchObject({ estimate: null, reason: "over_cap" });
  });
  it("rejects missing, unknown and out of range answers", () => {
    const r = quote(website, { ...base, type: "multi", pages: 99, features: ["nope"], level: "gold", template: "castle", details: "short", siteName: "", speed: undefined });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(Object.keys(r.errors).sort()).toEqual(["details", "features", "level", "pages", "siteName", "speed", "template"]);
  });
  it("rejects numbers that are not whole or not numbers", () => {
    const multi = { ...base, type: "multi" };
    expect(quote(website, { ...multi, pages: 2.5 }).ok).toBe(false);
    expect(quote(website, { ...multi, pages: "3" }).ok).toBe(false);
    expect(quote(website, { ...multi, pages: -4 }).ok).toBe(false);
    expect(quote(website, { ...base, revisions: Number.NaN }).ok).toBe(false);
  });
  it("drops answers to questions that do not exist", () => {
    const r = quote(website, { ...base, total: 1, discount: 100, estimate: { low: 1, high: 2 }, fixed: 1 });
    expect(r.ok && "total" in r.answers).toBe(false);
    expect(r.ok && "fixed" in r.answers).toBe(false);
  });
  it("trims text and enforces its length", () => {
    const r = quote(website, { ...base, details: `   ${DETAILS}   `, siteName: "  Crumb  " });
    expect(r.ok && r.answers.details).toBe(DETAILS);
    expect(r.ok && r.answers.siteName).toBe("Crumb");
    expect(quote(website, { ...base, details: "x".repeat(2001) }).ok).toBe(false);
    expect(quote(website, { ...base, siteName: "x".repeat(51) }).ok).toBe(false);
    expect(quote(website, { ...base, siteName: "A" }).ok).toBe(false);
  });
});

describe("questions that only apply sometimes", () => {
  it("does not ask a one page site how many pages it has", () => {
    expect(visibleQuestions(website, { type: "landing" }).some((q) => q.id === "pages")).toBe(false);
    expect(visibleQuestions(website, { type: "store" }).some((q) => q.id === "pages")).toBe(true);
  });
  it("ignores, and does not store or charge for, an answer to a hidden question", () => {
    const r = quote(website, { ...base, type: "landing", pages: 20 });
    expect(r.ok && r.quote.total).toBe(45_00);
    expect(r.ok && "pages" in r.answers).toBe(false);
    // even a nonsense value for a hidden question is not an error
    expect(quote(website, { ...base, type: "landing", pages: "lots" }).ok).toBe(true);
  });
  it("asks each kind of writing only its own questions", () => {
    const ids = (type: string) => visibleQuestions(writing, { type }).map((q) => q.id);
    expect(ids("essay")).toEqual(expect.arrayContaining(["pages", "sources", "citation", "tone", "font", "fontSize"]));
    expect(ids("essay")).not.toEqual(expect.arrayContaining(["minutes"]));
    expect(ids("book")).toEqual(expect.arrayContaining(["bookPages", "sources", "font", "fontSize"]));
    expect(ids("book")).not.toEqual(expect.arrayContaining(["citation"]));
    expect(ids("script")).toEqual(expect.arrayContaining(["minutes", "scriptFor", "font"]));
    expect(ids("script")).not.toEqual(expect.arrayContaining(["sources"]));
    expect(ids("product")).toEqual(expect.arrayContaining(["items"]));
    expect(ids("product")).not.toEqual(expect.arrayContaining(["font", "fontSize", "sources", "pages"]));
    expect(ids("resume")).not.toEqual(expect.arrayContaining(["pages", "sources", "citation"]));
  });
  it("estimates the new kinds of writing", () => {
    expect(priced(writing, essayBase).total).toBe(12_00);
    expect(priced(writing, { ...essayBase, pages: 10 }).total).toBe(23_00); // 12 + 7 x 1.5 = 22.5
    const book = { ...essayBase, type: "book", bookPages: 120 };
    expect(priced(writing, book).total).toBe(140_00); // 40 + 100 x 1
    const script = { ...essayBase, type: "script", minutes: 13, scriptFor: "video" };
    expect(priced(writing, script).total).toBe(30_00); // 15 + 10 x 1.5
    expect(quote(writing, { ...essayBase, type: "script", minutes: 13 }).ok).toBe(false); // scriptFor is required for a script
  });
  it("records the formatting choices on the order", () => {
    const q = priced(writing, { ...essayBase, sources: "Smith 2019, the city tree report", citation: "mla", font: "georgia", fontSize: "11" });
    const said = Object.fromEntries(q.lines.map((l) => [l.label, l.value]));
    expect(said["Which citation style?"]).toBe("MLA");
    expect(said["Which font?"]).toBe("Georgia");
    expect(said["What text size?"]).toBe("11 point");
    expect(said["Any specific sources we should use?"]).toBe("Smith 2019, the city tree report");
  });
});

describe("the flat price surprise", () => {
  const random = { mode: "random", vibe: "chaos", form: "any", avoid: "" };
  it("is a flat 15 dollars with no estimate", () => {
    expect(priced(custom, random)).toMatchObject({ total: 15_00, estimate: null, reason: "fixed", fixedPrice: 15_00 });
  });
  it("only asks its own short questions", () => {
    expect(visibleQuestions(custom, { mode: "random" }).map((q) => q.id)).toEqual(["mode", "vibe", "form", "avoid"]);
    expect(visibleQuestions(custom, { mode: "idea" }).map((q) => q.id)).toEqual(["mode", "details", "budget", "deadline", "links"]);
  });
  it("cannot be turned into a flat price for a real project", () => {
    // Asking for the idea path never returns a fixed price, whatever else is sent along.
    const q = priced(custom, { mode: "idea", details: "A full mobile app for my shop.", budget: "unsure", deadline: "week", links: "", vibe: "chaos", fixed: 1500, fixedPrice: 1 });
    expect(q).toMatchObject({ total: 0, estimate: null, reason: "quote_only" });
    expect(q.fixedPrice).toBeUndefined();
  });
  it("still needs its questions answered", () => {
    expect(quote(custom, { mode: "random" }).ok).toBe(false);
    expect(quote(custom, { mode: "nope" }).ok).toBe(false);
  });
  it("is the only flat price in the catalogue, and it is a payable amount", () => {
    const flats = SERVICES.flatMap((s) => s.questions.flatMap((q) => ("options" in q ? q.options : []).filter((o) => o.fixed !== undefined).map((o) => o.fixed!)));
    expect(flats).toEqual([15_00]);
    expect(flats[0]).toBeGreaterThanOrEqual(MIN_ORDER_CENTS);
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
  it("only makes a question depend on an earlier choice question, with answers that exist", () => {
    for (const s of SERVICES) {
      s.questions.forEach((q, i) => {
        if (!q.showIf) return;
        const parent = s.questions.slice(0, i).find((p) => p.id === q.showIf!.id);
        expect(parent?.kind, `${s.id}.${q.id}`).toBe("choice");
        if (parent?.kind === "choice") {
          for (const id of q.showIf.in) expect(parent.options.some((o) => o.id === id), `${s.id}.${q.id} -> ${id}`).toBe(true);
        }
      });
    }
  });
  it("asks about level on every estimated service, and about size or complexity", () => {
    for (const s of SERVICES.filter((x) => !x.quoteOnly)) {
      const ids = s.questions.map((q) => q.id);
      expect(ids, s.id).toContain("level");
      expect(ids.includes("complexity") || ids.includes("pages"), s.id).toBe(true);
    }
  });
  it("only offers the very complex tier for software", () => {
    for (const s of SERVICES) {
      const complexity = s.questions.find((q) => q.id === "complexity");
      const hasHuge = complexity?.kind === "choice" && complexity.options.some((o) => o.id === "huge");
      expect(hasHuge, s.id).toBe(s.id === "scripts");
    }
  });
});

describe("the look catalogue", () => {
  it("offers every template, color set, text style and image style in the website builder", () => {
    const options = (id: string) => {
      const q = website.questions.find((x) => x.id === id);
      return q?.kind === "choice" ? q.options.map((o) => o.id) : [];
    };
    expect(options("template")).toEqual(TEMPLATES.map((t) => t.id));
    expect(options("palette")).toEqual(PALETTES.map((p) => p.id));
    expect(options("font")).toEqual(FONTS.map((f) => f.id));
    expect(options("imagery")).toEqual(IMAGERY.map((i) => i.id));
  });
  it("starts the look pickers on a real choice so the preview is never empty", () => {
    for (const q of website.questions) {
      if (q.kind === "choice" && q.ui) expect(defaultAnswer(q)).toBe(q.options[0].id);
      else if (q.kind === "choice") expect(defaultAnswer(q)).toBe("");
    }
  });
  it("has a template suited to every kind of website", () => {
    const type = website.questions.find((q) => q.id === "type");
    const kinds = type?.kind === "choice" ? type.options.map((o) => o.id) : [];
    for (const kind of kinds) expect(TEMPLATES.some((t) => t.goodFor.includes(kind)), kind).toBe(true);
  });
  it("resolves stored answers into a look, and falls back safely on junk", () => {
    expect(resolveLook({ template: "blog", palette: "forest", font: "classic", imagery: "none" })).toMatchObject({
      template: { id: "blog" }, palette: { id: "forest" }, font: { id: "classic" }, imagery: { id: "none" },
    });
    expect(resolveLook({ template: 7, palette: "<script>", font: null })).toMatchObject({
      template: { id: TEMPLATES[0].id }, palette: { id: PALETTES[0].id }, font: { id: FONTS[0].id }, imagery: { id: IMAGERY[0].id },
    });
  });
  it("only uses plain hex colors, so a palette can never carry anything but a color", () => {
    for (const p of PALETTES) for (const value of [p.bg, p.surface, p.text, p.muted, p.accent, p.accentInk]) expect(value, p.id).toMatch(/^#[0-9a-f]{6}$/);
  });
});

describe("checkEmail", () => {
  it("accepts and normalises real addresses, rejects the rest", () => {
    expect(checkEmail("  Me@Example.com ")).toBe("me@example.com");
    for (const bad of ["", "nope", "a@b", "a b@c.com", 5, null, `${"a".repeat(250)}@b.com`]) expect(checkEmail(bad)).toBeNull();
  });
});
