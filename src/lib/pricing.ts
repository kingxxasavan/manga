import { MAX_ORDER_CENTS, MIN_ORDER_CENTS } from "./site";
import type { Question, Service } from "./services";

export type AnswerValue = string | string[] | number;
export type Answers = Record<string, AnswerValue>;

export interface Line {
  label: string;
  /** What was picked, in words */
  value: string;
  /** Cents added by this answer, 0 when it is free or only multiplies */
  amount: number;
  multiplier?: number;
}

export interface Estimate {
  /** cents */
  low: number;
  /** cents */
  high: number;
}

export interface Quote {
  lines: Line[];
  /** The middle of the estimate, in cents. 0 for quote only services. */
  total: number;
  /** The range shown to the customer, or null when no estimate can be given. */
  estimate: Estimate | null;
  /** why there is no estimate, when there is none */
  reason?: "quote_only" | "over_cap" | "fixed";
  /** Set when reason is "fixed": the flat price in cents, shown and paid right away. */
  fixedPrice?: number;
}

/** A question is asked unless it depends on an earlier choice that was answered differently. */
export function isVisible(q: Question, input: Record<string, unknown>): boolean {
  return !q.showIf || q.showIf.in.includes(input[q.showIf.id] as string);
}

/** The questions that apply to these answers, in order. Hidden ones are never asked, checked or stored. */
export function visibleQuestions(service: Service, input: Record<string, unknown>): Question[] {
  return service.questions.filter((q) => isVisible(q, input));
}

const STEP = 5_00; // estimates are rounded to whole 5 dollar steps
const SPREAD = 0.15;

/**
 * Turns a calculated amount into the range shown to the customer: 15 percent
 * either side, rounded outward to 5 dollars, and kept inside the allowed prices.
 */
export function estimateRange(total: number): Estimate {
  const low = Math.max(MIN_ORDER_CENTS, Math.floor((total * (1 - SPREAD)) / STEP) * STEP);
  const high = Math.min(MAX_ORDER_CENTS, Math.max(low + STEP, Math.ceil((total * (1 + SPREAD)) / STEP) * STEP));
  return { low: Math.min(low, high - STEP), high };
}

export type QuoteResult =
  | { ok: true; quote: Quote; answers: Answers }
  | { ok: false; errors: Record<string, string> };

const plural = (n: number, unit: string) => `${n} ${unit}${n === 1 ? "" : "s"}`;

/** The default answer a question starts on, used by the form. */
export function defaultAnswer(q: Question): AnswerValue {
  switch (q.kind) {
    case "choice":
      // Look pickers start on the first entry so the preview has something to show.
      return q.ui ? q.options[0].id : "";
    case "multi":
      return [];
    case "number":
      return Math.max(q.min, Math.min(q.max, q.included));
    case "text":
      return "";
  }
}

/** Checks one answer. Returns the cleaned value, or an error message. */
export function checkAnswer(q: Question, raw: unknown): { value: AnswerValue } | { error: string } {
  switch (q.kind) {
    case "choice": {
      if (typeof raw !== "string" || !q.options.some((o) => o.id === raw)) return { error: "Pick one option." };
      return { value: raw };
    }
    case "multi": {
      if (!Array.isArray(raw)) return { error: "Pick from the list." };
      const ids = [...new Set(raw)];
      if (!ids.every((id) => typeof id === "string" && q.options.some((o) => o.id === id))) {
        return { error: "Pick from the list." };
      }
      // Keep config order so the same picks always store and price the same way.
      return { value: q.options.filter((o) => ids.includes(o.id)).map((o) => o.id) };
    }
    case "number": {
      if (typeof raw !== "number" || !Number.isInteger(raw) || raw < q.min || raw > q.max) {
        return { error: `Enter a whole number from ${q.min} to ${q.max}.` };
      }
      return { value: raw };
    }
    case "text": {
      if (typeof raw !== "string") return { error: "Enter some text." };
      const text = raw.trim();
      const min = q.minLength ?? 10;
      if (q.required && text.length < min) {
        return { error: min > 5 ? `Please give a bit more detail (at least ${min} characters).` : "Please fill this in." };
      }
      if (text.length > q.maxLength) return { error: `Keep it under ${q.maxLength} characters.` };
      return { value: text };
    }
  }
}

/**
 * Validates every answer and works out the estimate. The same function runs
 * in the browser (to show the estimate) and on the server (to store it), and
 * the server never accepts a number from the browser.
 *
 * Basis = (sum of everything picked) x (every multiplier). The estimate is a
 * range around that. It is never charged: the owner confirms the final price.
 */
export function quote(service: Service, input: Record<string, unknown>): QuoteResult {
  const errors: Record<string, string> = {};
  const answers: Answers = {};
  const lines: Line[] = [];
  let sum = 0;
  let factor = 1;
  let fixed: number | undefined;

  for (const q of visibleQuestions(service, input)) {
    const checked = checkAnswer(q, input[q.id]);
    if ("error" in checked) {
      errors[q.id] = checked.error;
      continue;
    }
    const value = checked.value;
    answers[q.id] = value;

    if (q.kind === "choice") {
      const option = q.options.find((o) => o.id === value)!;
      sum += option.price ?? 0;
      factor *= option.multiplier ?? 1;
      if (option.fixed !== undefined) fixed = option.fixed;
      lines.push({ label: q.label, value: option.label, amount: option.price ?? 0, multiplier: option.multiplier });
    } else if (q.kind === "multi") {
      const picked = q.options.filter((o) => (value as string[]).includes(o.id));
      const amount = picked.reduce((total, o) => total + (o.price ?? 0), 0);
      sum += amount;
      for (const o of picked) factor *= o.multiplier ?? 1;
      lines.push({ label: q.label, value: picked.length ? picked.map((o) => o.label).join(", ") : "None", amount });
    } else if (q.kind === "number") {
      const count = value as number;
      const amount = Math.max(0, count - q.included) * q.unitPrice;
      sum += amount;
      lines.push({ label: q.label, value: plural(count, q.unit), amount });
    } else {
      lines.push({ label: q.label, value: (value as string) || "Not given", amount: 0 });
    }
  }

  if (Object.keys(errors).length > 0) return { ok: false, errors };

  // A flat price comes from the config alone, so it wins over everything else.
  if (fixed !== undefined) {
    return { ok: true, answers, quote: { lines, total: fixed, estimate: null, reason: "fixed", fixedPrice: fixed } };
  }
  if (service.quoteOnly) {
    return { ok: true, answers, quote: { lines, total: 0, estimate: null, reason: "quote_only" } };
  }
  const total = Math.round((sum * factor) / 100) * 100;
  if (total > MAX_ORDER_CENTS) {
    return { ok: true, answers, quote: { lines, total, estimate: null, reason: "over_cap" } };
  }
  return { ok: true, answers, quote: { lines, total, estimate: estimateRange(total) } };
}

export function checkEmail(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const email = raw.trim().toLowerCase();
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return null;
  return email;
}
