import { describe, expect, it } from "vitest";
import { quote } from "@/lib/pricing";
import { SERVICES, type Service } from "@/lib/services";

/**
 * The pricing rule this site promises:
 *
 *   Every normal request estimates at or under 500 dollars. Only a full app or
 *   game, a "very complex" software job, or an unusually large quantity may go above.
 *
 * These tests try every combination of answers a customer could give and hold
 * the numbers in src/lib/services.ts to that rule.
 * Run `SHOW_SPREAD=1 npm test` to print the spread while tuning.
 */
const LIMIT = 500;

interface Combo {
  input: Record<string, unknown>;
  /** false when the request is one of the named exceptions to the rule */
  normal: boolean;
}

function combos(service: Service): Combo[] {
  let all: Combo[] = [{ input: {}, normal: true }];
  for (const q of service.questions) {
    let values: { value: unknown; normal: boolean }[];
    if (q.kind === "choice") {
      values = q.options.map((o) => ({
        value: o.id,
        // The two named exceptions: a full app or game, and the top complexity tier.
        normal: !(q.id === "complexity" && o.id === "huge") && !(q.id === "type" && o.id === "app"),
      }));
    } else if (q.kind === "multi") {
      values = [[], q.options.slice(0, 2).map((o) => o.id), q.options.map((o) => o.id)].map((value) => ({ value, normal: true }));
    } else if (q.kind === "number") {
      // A few more than what is included is normal. The maximum (20 pages, 30 logos) is a bulk order.
      const few = Math.min(q.max, q.included + 3);
      values = [
        { value: q.min, normal: true },
        { value: few, normal: true },
        { value: q.max, normal: q.max === few },
      ];
    } else {
      values = [{ value: q.required ? "Enough detail to pass." : "", normal: true }];
    }
    all = all.flatMap((c) => values.map((v) => ({ input: { ...c.input, [q.id]: v.value }, normal: c.normal && v.normal })));
  }
  return all;
}

function estimateHigh(service: Service, input: Record<string, unknown>): number {
  const r = quote(service, input);
  if (!r.ok) throw new Error(service.id + ": " + JSON.stringify(r.errors));
  return r.quote.estimate ? r.quote.estimate.high / 100 : Infinity;
}

describe("estimate spread", () => {
  for (const service of SERVICES.filter((s) => !s.quoteOnly)) {
    it(service.name + ": every normal request estimates at or under 500 dollars", () => {
      const all = combos(service).map((c) => ({ ...c, high: estimateHigh(service, c.input) }));
      const normal = all.filter((c) => c.normal).map((c) => c.high).sort((a, b) => a - b);
      const exceptions = all.filter((c) => !c.normal).map((c) => c.high).sort((a, b) => a - b);
      const at = (list: number[], p: number) => list[Math.floor((list.length - 1) * p)];

      if (process.env.SHOW_SPREAD) {
        console.log(
          [
            service.name.padEnd(24),
            "normal requests: " + normal.length,
            "cheapest up to " + at(normal, 0),
            "middle up to " + at(normal, 0.5),
            "dearest up to " + at(normal, 1),
            exceptions.length ? "big or very complex jobs up to " + at(exceptions, 1) : "no exceptions",
          ].join(" | "),
        );
      }

      expect(normal.length).toBeGreaterThan(0);
      expect(at(normal, 1), "the dearest normal request").toBeLessThanOrEqual(LIMIT);
      // Even the exceptions must still get an estimate rather than fall off the top.
      for (const high of exceptions) expect(Number.isFinite(high)).toBe(true);
    });
  }

  it("lets the named exceptions go above 500 dollars", () => {
    const scripts = SERVICES.find((s) => s.id === "scripts")!;
    const above = combos(scripts).filter((c) => !c.normal && estimateHigh(scripts, c.input) > LIMIT);
    expect(above.length).toBeGreaterThan(0);
  });
});
