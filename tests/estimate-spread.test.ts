import { describe, expect, it } from "vitest";
import { quote, visibleQuestions } from "@/lib/pricing";
import { SERVICES, type Service } from "@/lib/services";

/**
 * The launch pricing rules this site promises:
 *
 *   1. Every normal request estimates at or under 500 dollars.
 *   2. Bulk quantities and "very complex" jobs stay at or under 800 dollars.
 *   3. Only a full app or game, or a full book, may go above that.
 *
 * These tests try every combination of answers that can change an estimate and
 * hold the numbers in src/lib/services.ts to those rules.
 * Run `SHOW_SPREAD=1 npx vitest run tests/estimate-spread.test.ts --disable-console-intercept`
 * to print the spread while tuning.
 */
const NORMAL_LIMIT = 500;
const BIG_LIMIT = 800;

type Size = "normal" | "big" | "epic";
const RANK: Record<Size, number> = { normal: 0, big: 1, epic: 2 };
const bigger = (a: Size, b: Size): Size => (RANK[a] >= RANK[b] ? a : b);

/** The two jobs that are allowed to be expensive. */
const EPIC_TYPES = ["app", "book"];

function inputs(service: Service): Record<string, unknown>[] {
  let all: Record<string, unknown>[] = [{}];
  for (const q of service.questions) {
    let values: unknown[];
    if (q.kind === "choice") {
      // Choices that cannot change the estimate (colors, fonts, tone) need only one value,
      // unless another question depends on them.
      const matters = q.options.some((o) => o.price || o.multiplier || o.fixed !== undefined) || service.questions.some((x) => x.showIf?.id === q.id);
      values = matters ? q.options.map((o) => o.id) : [q.options[0].id];
    } else if (q.kind === "multi") {
      values = [[], q.options.slice(0, 2).map((o) => o.id), q.options.map((o) => o.id)];
    } else if (q.kind === "number") {
      values = [...new Set([q.min, Math.min(q.max, q.included + 3), q.max])];
    } else {
      values = [q.required ? "Enough detail to pass." : ""];
    }
    all = all.flatMap((c) => values.map((v) => ({ ...c, [q.id]: v })));
  }
  return all;
}

/** How big a request is, judged only on the questions that were actually asked. */
function sizeOf(service: Service, input: Record<string, unknown>): Size {
  let size: Size = "normal";
  for (const q of visibleQuestions(service, input)) {
    const value = input[q.id];
    if (q.kind === "choice") {
      if (q.id === "type" && EPIC_TYPES.includes(value as string)) size = bigger(size, "epic");
      if (q.id === "complexity" && value === "huge") size = bigger(size, "big");
    } else if (q.kind === "number") {
      // A few more than what is included is normal. The maximum (20 pages, 30 logos) is a bulk order.
      if ((value as number) > Math.min(q.max, q.included + 3)) size = bigger(size, "big");
    }
  }
  return size;
}

function estimateHigh(service: Service, input: Record<string, unknown>): number {
  const r = quote(service, input);
  if (!r.ok) throw new Error(service.id + ": " + JSON.stringify(r.errors) + " for " + JSON.stringify(input));
  return r.quote.estimate ? r.quote.estimate.high / 100 : Infinity;
}

describe("estimate spread", () => {
  for (const service of SERVICES.filter((s) => !s.quoteOnly)) {
    it(service.name + ": stays inside the launch pricing rules", () => {
      const all = inputs(service).map((input) => ({ size: sizeOf(service, input), high: estimateHigh(service, input) }));
      const of = (size: Size) => all.filter((c) => c.size === size).map((c) => c.high).sort((a, b) => a - b);
      const normal = of("normal"), big = of("big"), epic = of("epic");
      const at = (list: number[], p: number) => list[Math.floor((list.length - 1) * p)];

      if (process.env.SHOW_SPREAD) {
        console.log(
          [
            service.name.padEnd(24),
            "normal: cheapest " + at(normal, 0) + ", middle " + at(normal, 0.5) + ", dearest " + at(normal, 1),
            big.length ? "bulk or very complex: up to " + at(big, 1) : "no bulk jobs",
            epic.length ? "full app, game or book: up to " + at(epic, 1) : "nothing bigger",
          ].join(" | "),
        );
      }

      expect(normal.length).toBeGreaterThan(0);
      expect(at(normal, 1), "the dearest normal request").toBeLessThanOrEqual(NORMAL_LIMIT);
      if (big.length) expect(at(big, 1), "the dearest bulk or very complex request").toBeLessThanOrEqual(BIG_LIMIT);
      // The biggest jobs must still get an estimate rather than fall off the top.
      for (const high of epic) expect(Number.isFinite(high)).toBe(true);
    });
  }

  it("lets a full app, game or book go above 800 dollars", () => {
    for (const id of ["scripts", "writing"]) {
      const service = SERVICES.find((s) => s.id === id)!;
      const above = inputs(service).filter((input) => sizeOf(service, input) === "epic" && estimateHigh(service, input) > BIG_LIMIT);
      expect(above.length, id).toBeGreaterThan(0);
    }
  });
});
