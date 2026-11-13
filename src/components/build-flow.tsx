"use client";

import Link from "next/link";
import { useMemo, useState, useTransition } from "react";
import { submitOrder } from "@/app/actions";
import { checkAnswer, checkEmail, defaultAnswer, quote, type AnswerValue } from "@/lib/pricing";
import type { Option, Question, Service } from "@/lib/services";
import { formatMoney } from "@/lib/money";
import { MAX_ORDER_CENTS } from "@/lib/site";
import { AnimatedPrice } from "./animated-price";
import { ArrowLeft, ArrowRight, Check, Minus, Plus } from "./icons";

function OptionCard({ option, selected, type, name, onPick }: {
  option: Option; selected: boolean; type: "radio" | "checkbox"; name: string; onPick: () => void;
}) {
  return (
    <label className={`flex cursor-pointer items-center gap-4 rounded-2xl border p-4 transition-[border-color,background-color,transform,box-shadow] duration-200 ease-out-strong active:scale-[0.985] ${selected ? "border-accent bg-accent-soft shadow-card" : "border-line bg-surface hover:border-accent/50"}`}>
      <input type={type} name={name} checked={selected} onChange={onPick} className="peer sr-only" />
      <span className={`grid size-6 shrink-0 place-items-center border-2 transition-colors duration-200 peer-focus-visible:ring-2 peer-focus-visible:ring-accent ${type === "radio" ? "rounded-full" : "rounded-md"} ${selected ? "border-accent bg-accent text-accent-ink" : "border-line"}`}>
        {selected && <Check width={14} height={14} strokeWidth={3} className="pop" />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold">{option.label}</span>
        {option.hint && <span className="block text-sm text-muted">{option.hint}</span>}
      </span>
    </label>
  );
}

function QuestionInput({ question, value, onChange }: { question: Question; value: AnswerValue; onChange: (value: AnswerValue) => void }) {
  if (question.kind === "choice") {
    return (
      <div role="radiogroup" aria-label={question.label} className="grid gap-3">
        {question.options.map((o) => (
          <OptionCard key={o.id} option={o} type="radio" name={question.id} selected={value === o.id} onPick={() => onChange(o.id)} />
        ))}
      </div>
    );
  }
  if (question.kind === "multi") {
    const picked = value as string[];
    return (
      <div className="grid gap-3">
        {question.options.map((o) => (
          <OptionCard
            key={o.id} option={o} type="checkbox" name={question.id} selected={picked.includes(o.id)}
            onPick={() => onChange(picked.includes(o.id) ? picked.filter((id) => id !== o.id) : [...picked, o.id])}
          />
        ))}
      </div>
    );
  }
  if (question.kind === "number") {
    const count = value as number;
    const set = (n: number) => onChange(Math.max(question.min, Math.min(question.max, Math.round(n) || question.min)));
    const button = "grid size-12 place-items-center rounded-full border border-line bg-surface transition-[transform,border-color,color] duration-150 ease-out-strong hover:border-accent hover:text-accent active:scale-[0.94] disabled:opacity-40 disabled:hover:border-line disabled:hover:text-text";
    return (
      <div>
        <div className="flex items-center gap-4">
          <button type="button" onClick={() => set(count - 1)} disabled={count <= question.min} aria-label="One fewer" className={button}><Minus /></button>
          <input
            type="number" inputMode="numeric" min={question.min} max={question.max} value={count}
            onChange={(e) => set(Number(e.target.value))} aria-label={question.label}
            className="h-14 w-24 rounded-2xl border border-line bg-surface text-center font-display text-2xl font-extrabold outline-none focus:border-accent"
          />
          <button type="button" onClick={() => set(count + 1)} disabled={count >= question.max} aria-label="One more" className={button}><Plus /></button>
        </div>
        <p className="mt-3 text-sm text-muted">From {question.min} to {question.max}.</p>
      </div>
    );
  }
  const text = value as string;
  const shared = "w-full rounded-2xl border border-line bg-surface p-4 outline-none transition-colors duration-200 placeholder:text-muted/70 focus:border-accent";
  return (
    <div>
      {question.long ? (
        <textarea value={text} onChange={(e) => onChange(e.target.value)} placeholder={question.placeholder} maxLength={question.maxLength} rows={6} aria-label={question.label} className={`${shared} resize-y`} />
      ) : (
        <input value={text} onChange={(e) => onChange(e.target.value)} placeholder={question.placeholder} maxLength={question.maxLength} aria-label={question.label} className={shared} />
      )}
      <p className="mt-2 text-right text-xs text-muted">{text.length} / {question.maxLength}{question.required ? "" : " · optional"}</p>
    </div>
  );
}

/** What an answer looks like in words, for the brief. Empty when not answered yet. */
function answerText(question: Question, value: AnswerValue): string {
  if (question.kind === "choice") return question.options.find((o) => o.id === value)?.label ?? "";
  if (question.kind === "multi") return question.options.filter((o) => (value as string[]).includes(o.id)).map((o) => o.label).join(", ");
  if (question.kind === "number") return `${value} ${question.unit}${value === 1 ? "" : "s"}`;
  return (value as string).trim();
}

export function BuildFlow({ service }: { service: Service }) {
  const questions = service.questions;
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>(() =>
    Object.fromEntries(questions.map((q) => [q.id, defaultAnswer(q)])),
  );
  const [step, setStep] = useState(0);
  // How far the customer has got. The brief only lists steps they have passed.
  const [reached, setReached] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [contact, setContact] = useState({ name: "", email: "", website: "" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, startTransition] = useTransition();

  const last = step === questions.length; // the estimate and "your details" step
  const question = last ? null : questions[step];
  const full = useMemo(() => quote(service, answers), [service, answers]);
  const estimate = full.ok ? full.quote.estimate : null;
  const reason = full.ok ? full.quote.reason : undefined;

  const setAnswer = (id: string, value: AnswerValue) => {
    setAnswers((current) => ({ ...current, [id]: value }));
    setError(null);
  };
  const goTo = (target: number) => {
    setError(null);
    setStep(target);
    setReached((r) => Math.max(r, target));
    window.scrollTo({ top: 0 });
  };
  const next = () => {
    if (question) {
      const checked = checkAnswer(question, answers[question.id]);
      if ("error" in checked) return setError(checked.error);
    }
    goTo(step + 1);
  };

  const submit = () => {
    const errors: Record<string, string> = {};
    if (!contact.name.trim()) errors.name = "Enter your name.";
    if (!checkEmail(contact.email)) errors.email = "Enter a valid email address.";
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    setError(null);
    startTransition(async () => {
      try {
        const result = await submitOrder(service.id, answers, contact);
        if (result.ok) {
          window.location.assign(result.url);
          return;
        }
        setFieldErrors(result.errors);
        const firstBad = questions.findIndex((q) => result.errors[q.id]);
        if (firstBad >= 0) {
          setStep(firstBad);
          setError(result.errors[questions[firstBad].id]);
        } else {
          setError(result.message ?? "Please check the highlighted fields.");
        }
      } catch {
        setError("We could not reach the server. Check your connection and try again.");
      }
    });
  };

  const percent = Math.round((step / questions.length) * 100);
  const field = "h-12 w-full rounded-2xl border bg-surface px-4 outline-none transition-colors duration-200 focus:border-accent";

  return (
    <div className="pt-8">
      <Link href="/#services" className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted transition-colors duration-200 hover:text-text">
        <ArrowLeft width={16} height={16} /> All services
      </Link>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-3xl font-extrabold sm:text-4xl">{service.name}</h1>
        <p className="text-sm font-semibold text-muted">{last ? "Your estimate" : `Question ${step + 1} of ${questions.length}`}</p>
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label="Progress">
        <div className="h-full w-full origin-left rounded-full bg-accent transition-transform duration-500 ease-out-strong" style={{ transform: `scaleX(${Math.max(percent, 4) / 100})` }} />
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_20rem]">
        <div key={step} className="rise min-w-0">
          {question ? (
            <>
              <h2 className="text-2xl font-extrabold sm:text-3xl">{question.label}</h2>
              {question.help && <p className="mt-2 text-muted">{question.help}</p>}
              <div className="mt-6">
                <QuestionInput question={question} value={answers[question.id]} onChange={(v) => setAnswer(question.id, v)} />
              </div>
            </>
          ) : (
            <>
              {/* The estimate: the one place a number appears, after every question is answered */}
              <section className="panel-dark on-dark rounded-3xl p-6 sm:p-8" aria-live="polite">
                <span className="glow glow-a" />
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-muted">{estimate ? "Your estimated price" : "Your price"}</p>
                {estimate ? (
                  <>
                    <p className="mt-3 font-display text-5xl font-extrabold leading-none sm:text-6xl">
                      <AnimatedPrice value={estimate.low} from={0} />
                      <span className="mx-3 text-2xl font-bold text-muted sm:text-3xl">to</span>
                      <AnimatedPrice value={estimate.high} from={0} />
                    </p>
                    <p className="mt-4 max-w-xl leading-relaxed text-muted">
                      Based on the complexity and level you picked. This is an estimate, not a bill. We look at your request, confirm the final price on your order page, and you only pay once you are happy with it.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="mt-3 font-display text-4xl font-extrabold leading-tight sm:text-5xl">We will price this one by hand</p>
                    <p className="mt-4 max-w-xl leading-relaxed text-muted">
                      {reason === "over_cap"
                        ? `This looks like a bigger project, above ${formatMoney(MAX_ORDER_CENTS)}, so a quick estimate would not be fair to you. Send it over and we will reply with a real price on your order page.`
                        : "Every custom idea is different, so there is no automatic estimate. Send it over and a price appears on your order page."}
                      {" "}You pay nothing until you accept it.
                    </p>
                  </>
                )}
              </section>

              <h2 className="mt-10 text-2xl font-extrabold">Where should we reach you?</h2>
              <p className="mt-1.5 text-muted">We use this only for your request.</p>
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1.5 block text-sm font-semibold">Your name</span>
                  <input value={contact.name} onChange={(e) => setContact({ ...contact, name: e.target.value })} maxLength={80} autoComplete="name" className={`${field} ${fieldErrors.name ? "border-danger" : "border-line"}`} />
                  {fieldErrors.name && <span className="mt-1 block text-sm font-semibold text-danger">{fieldErrors.name}</span>}
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-sm font-semibold">Email</span>
                  <input type="email" value={contact.email} onChange={(e) => setContact({ ...contact, email: e.target.value })} maxLength={254} autoComplete="email" className={`${field} ${fieldErrors.email ? "border-danger" : "border-line"}`} />
                  {fieldErrors.email && <span className="mt-1 block text-sm font-semibold text-danger">{fieldErrors.email}</span>}
                </label>
                {/* Honeypot: hidden from people, tempting to bots */}
                <label className="hidden" aria-hidden="true">
                  Website
                  <input tabIndex={-1} autoComplete="off" value={contact.website} onChange={(e) => setContact({ ...contact, website: e.target.value })} />
                </label>
              </div>
            </>
          )}

          {error && <p role="alert" className="rise mt-5 rounded-2xl border border-danger/40 bg-danger/10 px-4 py-3 font-semibold text-danger">{error}</p>}

          <div className="mt-8 flex items-center gap-3">
            {step > 0 && (
              <button type="button" onClick={() => goTo(step - 1)} disabled={pending} className="btn btn-ghost px-5 py-3">
                <ArrowLeft width={18} height={18} /> Back
              </button>
            )}
            {last ? (
              <button type="button" onClick={submit} disabled={pending} className="btn btn-primary flex-1 px-7 py-3.5 disabled:opacity-60 sm:flex-none">
                {pending ? "Sending" : <>Send my request <ArrowRight width={18} height={18} className="arrow" /></>}
              </button>
            ) : (
              <button type="button" onClick={next} className="btn btn-primary flex-1 px-7 py-3.5 sm:flex-none">
                {step === questions.length - 1 ? "See my estimate" : "Next"} <ArrowRight width={18} height={18} className="arrow" />
              </button>
            )}
          </div>
          {last && <p className="mt-3 text-sm text-muted">No payment now. By sending you agree to the <Link href="/policies" className="font-semibold underline">refunds and terms</Link>.</p>}
        </div>

        {/* The brief builds up as questions are answered. No prices here. */}
        <aside>
          <div className="rounded-3xl border border-line bg-surface p-6 shadow-card lg:sticky lg:top-24">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-muted">Your brief</p>
            {reached === 0 ? (
              <p className="mt-3 text-sm leading-relaxed text-muted">Your answers collect here as you go. After the last question you get your estimated price.</p>
            ) : (
              <ol className="mt-3 space-y-1">
                {questions.slice(0, reached).map((q, i) => (
                  <li key={q.id}>
                    <button type="button" onClick={() => goTo(i)} className={`flex w-full items-start gap-3 rounded-xl px-2 py-2 text-left transition-colors duration-200 hover:bg-surface-2 ${i === step ? "bg-surface-2" : ""}`}>
                      <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-good/15 text-good"><Check width={12} height={12} strokeWidth={3.5} /></span>
                      <span className="min-w-0">
                        <span className="block text-xs font-semibold text-muted">{q.label}</span>
                        <span className="line-clamp-2 break-words text-sm font-medium">{answerText(q, answers[q.id]) || "Skipped"}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
            )}
            <p className="mt-4 border-t border-line pt-4 text-sm text-muted">Usual delivery: <span className="font-semibold text-text">{service.delivery}</span></p>
          </div>
        </aside>
      </div>
    </div>
  );
}
