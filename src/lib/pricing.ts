import { MAX_ORDER_CENTS } from "./site";
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

export interface Quote {
  lines: Line[];
  /** Final price in cents. 0 for quote only services. */
  total: number;
  /** true when the owner has to price this by hand */
  needsManualQuote: boolean;
  /** why, when needsManualQuote is true */
  reason?: "quote_only" | "over_cap";
}

export type QuoteResult =
  | { ok: true; quote: Quote; answers: Answers }
  | { ok: false; errors: Record<string, string> };

const plural = (n: number, unit: string) => `${n} ${unit}${n === 1 ? "" : "s"}`;

/** The default answer a question starts on, used by the form. */
export function defaultAnswer(q: Question): AnswerValue {
  switch (q.kind) {
    case "choice":
      return "";
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
      if (q.required && text.length < 10) return { error: "Please give a bit more detail (at least 10 characters)." };
      if (text.length > q.maxLength) return { error: `Keep it under ${q.maxLength} characters.` };
      return { value: text };
    }
  }
}

/**
 * Validates every answer and works out the price. This one function is used
 * for the live price in the browser AND for the amount charged on the server,
 * and the server never accepts a price from the browser.
 *
 * Price = (sum of everything picked) x (every multiplier), rounded to a whole dollar.
 */
export function quote(service: Service, input: Record<string, unknown>): QuoteResult {
  const errors: Record<string, string> = {};
  const answers: Answers = {};
  const lines: Line[] = [];
  let sum = 0;
  let factor = 1;

  for (const q of service.questions) {
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

  if (service.quoteOnly) {
    return { ok: true, answers, quote: { lines, total: 0, needsManualQuote: true, reason: "quote_only" } };
  }
  const total = Math.round((sum * factor) / 100) * 100;
  if (total > MAX_ORDER_CENTS) {
    return { ok: true, answers, quote: { lines, total, needsManualQuote: true, reason: "over_cap" } };
  }
  return { ok: true, answers, quote: { lines, total, needsManualQuote: false } };
}

/** Price so far while the form is half filled: unanswered questions count as nothing. */
export function estimate(service: Service, input: Record<string, unknown>): number {
  let sum = 0;
  let factor = 1;
  for (const q of service.questions) {
    const checked = checkAnswer(q, input[q.id]);
    if ("error" in checked) continue;
    const value = checked.value;
    if (q.kind === "choice") {
      const option = q.options.find((o) => o.id === value)!;
      sum += option.price ?? 0;
      factor *= option.multiplier ?? 1;
    } else if (q.kind === "multi") {
      for (const o of q.options) {
        if ((value as string[]).includes(o.id)) {
          sum += o.price ?? 0;
          factor *= o.multiplier ?? 1;
        }
      }
    } else if (q.kind === "number") {
      sum += Math.max(0, (value as number) - q.included) * q.unitPrice;
    }
  }
  return Math.round((sum * factor) / 100) * 100;
}

export function checkEmail(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const email = raw.trim().toLowerCase();
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return null;
  return email;
}
