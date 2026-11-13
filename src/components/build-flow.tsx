"use client";

import Link from "next/link";
import { useMemo, useState, useTransition } from "react";
import { submitOrder } from "@/app/actions";
import { formatMoney } from "@/lib/money";
import { checkAnswer, checkEmail, defaultAnswer, estimate, quote, type AnswerValue } from "@/lib/pricing";
import type { Option, Question, Service } from "@/lib/services";
import { MAX_ORDER_CENTS } from "@/lib/site";
import { AnimatedPrice } from "./animated-price";
import { ArrowLeft, ArrowRight, Check, Lock, Minus, Plus } from "./icons";

const optionPrice = (o: Option) =>
  o.multiplier ? `+${Math.round((o.multiplier - 1) * 100)}%` : o.price ? `+${formatMoney(o.price)}` : null;

function OptionCard({ option, selected, type, name, onPick, showPlus }: {
  option: Option; selected: boolean; type: "radio" | "checkbox"; name: string; onPick: () => void; showPlus: boolean;
}) {
  const price = option.multiplier
    ? optionPrice(option)
    : option.price
      ? `${showPlus ? "+" : ""}${formatMoney(option.price)}`
      : null;
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
      {price && <span className="shrink-0 text-sm font-bold text-muted">{price}</span>}
    </label>
  );
}

function QuestionInput({ question, value, onChange }: { question: Question; value: AnswerValue; onChange: (value: AnswerValue) => void }) {
  if (question.kind === "choice") {
    // The first priced choice sets the base price, so its amounts read as prices, not add ons.
    const isBase = question.options.every((o) => o.price && !o.multiplier);
    return (
      <div role="radiogroup" aria-label={question.label} className="grid gap-3">
        {question.options.map((o) => (
          <OptionCard key={o.id} option={o} type="radio" name={question.id} selected={value === o.id} onPick={() => onChange(o.id)} showPlus={!isBase} />
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
            key={o.id} option={o} type="checkbox" name={question.id} selected={picked.includes(o.id)} showPlus
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
        <p className="mt-3 text-sm text-muted">
          {question.included} included, then {formatMoney(question.unitPrice)} per extra {question.unit}. Up to {question.max}.
        </p>
      </div>
    );
  }
  const text = value as string;
  const shared = "w-full rounded-2xl border border-line bg-surface p-4 outline-none transition placeholder:text-muted/70 focus:border-accent";
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

export function BuildFlow({ service }: { service: Service }) {
  const questions = service.questions;
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>(() =>
    Object.fromEntries(questions.map((q) => [q.id, defaultAnswer(q)])),
  );
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [contact, setContact] = useState({ name: "", email: "", website: "" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, startTransition] = useTransition();

  const last = step === questions.length; // the "your details" step
  const question = last ? null : questions[step];
  const price = useMemo(() => estimate(service, answers), [service, answers]);
  const overCap = !service.quoteOnly && price > MAX_ORDER_CENTS;
  const manual = service.quoteOnly || overCap;
  const full = useMemo(() => quote(service, answers), [service, answers]);

  const setAnswer = (id: string, value: AnswerValue) => {
    setAnswers((current) => ({ ...current, [id]: value }));
    setError(null);
  };

  const next = () => {
    if (question) {
      const checked = checkAnswer(question, answers[question.id]);
      if ("error" in checked) return setError(checked.error);
    }
    setError(null);
    setStep((s) => s + 1);
    window.scrollTo({ top: 0 });
  };
  const back = () => {
    setError(null);
    setStep((s) => Math.max(0, s - 1));
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
        setError("We could not reach the server. Nothing was charged. Check your connection and try again.");
      }
    });
  };

  const percent = Math.round((step / questions.length) * 100);
  const answered = full.ok ? full.quote.lines : [];
  const field = "h-12 w-full rounded-2xl border bg-surface px-4 outline-none transition focus:border-accent";

  const priceBox = (
    <>
      <p className="text-xs font-bold uppercase tracking-widest text-muted">{manual ? "Price" : "Your price so far"}</p>
      {service.quoteOnly ? (
        <p className="mt-1 font-display text-2xl font-extrabold">We will quote it</p>
      ) : overCap ? (
        <p className="mt-1 font-display text-2xl font-extrabold">Custom quote</p>
      ) : (
        <p className="mt-1 font-display text-5xl font-extrabold leading-none"><AnimatedPrice value={price} /></p>
      )}
      <p className="mt-2 text-sm text-muted">
        {service.quoteOnly
          ? "Send your idea, and a price appears on your order page. You pay nothing until you accept it."
          : overCap
            ? `This comes to more than ${formatMoney(MAX_ORDER_CENTS)}, so we price it by hand. You pay nothing until you accept the quote.`
            : price === 0
              ? "Pick an option and the price starts building."
              : "Updates with every answer. This is the full price, no extra fees."}
      </p>
    </>
  );

  return (
    <div className="pt-8">
      <Link href="/#services" className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted hover:text-text">
        <ArrowLeft width={16} height={16} /> All services
      </Link>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-3xl font-extrabold sm:text-4xl">{service.name}</h1>
        <p className="text-sm font-semibold text-muted">{last ? "Last step" : `Step ${step + 1} of ${questions.length + 1}`}</p>
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label="Progress">
        <div className="h-full w-full origin-left rounded-full bg-accent transition-transform duration-500 ease-out-strong" style={{ transform: `scaleX(${Math.max(percent, 4) / 100})` }} />
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_20rem]">
        <div key={step} className="rise min-w-0 pb-28 lg:pb-0">
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
              <h2 className="text-2xl font-extrabold sm:text-3xl">Where should we reach you?</h2>
              <p className="mt-2 text-muted">We use this only for your order.</p>
              <div className="mt-6 grid gap-4 sm:grid-cols-2">
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

              <h3 className="mt-8 text-lg font-bold">Your order</h3>
              <dl className="mt-3 divide-y divide-line rounded-2xl border border-line bg-surface">
                {answered.map((line, i) => (
                  <div key={line.label} className="flex items-start gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <dt className="text-xs font-semibold text-muted">{line.label}</dt>
                      <dd className="mt-0.5 line-clamp-3 break-words font-medium">{line.value}</dd>
                    </div>
                    <button type="button" onClick={() => setStep(i)} className="shrink-0 text-sm font-semibold text-accent hover:underline">Edit</button>
                  </div>
                ))}
              </dl>
            </>
          )}

          {error && <p role="alert" className="rise mt-5 rounded-2xl border border-danger/40 bg-danger/10 px-4 py-3 font-semibold text-danger">{error}</p>}

          <div className="mt-8 flex items-center gap-3">
            {step > 0 && (
              <button type="button" onClick={back} disabled={pending} className="btn btn-ghost px-5 py-3">
                <ArrowLeft width={18} height={18} /> Back
              </button>
            )}
            {last ? (
              <button type="button" onClick={submit} disabled={pending} className="btn btn-primary flex-1 px-6 py-3.5 disabled:opacity-60 sm:flex-none">
                {pending ? "One moment" : manual ? "Request my quote" : <><Lock width={16} height={16} /> Continue to payment · {formatMoney(price)}</>}
              </button>
            ) : (
              <button type="button" onClick={next} className="btn btn-primary flex-1 px-7 py-3.5 sm:flex-none">
                Next <ArrowRight width={18} height={18} className="arrow" />
              </button>
            )}
          </div>
          {last && !manual && <p className="mt-3 text-sm text-muted">You pay on the secure Stripe page. By ordering you agree to the <Link href="/policies" className="font-semibold underline">refunds and terms</Link>.</p>}
        </div>

        <aside className="hidden lg:block">
          <div className="sticky top-24 rounded-3xl border border-line bg-surface p-6 shadow-float">
            {priceBox}
            <p className="mt-5 border-t border-line pt-4 text-sm text-muted">Usual delivery: <span className="font-semibold text-text">{service.delivery}</span></p>
          </div>
        </aside>
      </div>

      {/* Phone: the price rides along the bottom of the screen */}
      {!last && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-bg/95 px-4 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur-xl lg:hidden">
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs font-bold uppercase tracking-widest text-muted">{manual ? "Price" : "Price so far"}</span>
            <span className="font-display text-2xl font-extrabold">{manual ? "Custom quote" : <AnimatedPrice value={price} />}</span>
          </div>
        </div>
      )}
    </div>
  );
}
