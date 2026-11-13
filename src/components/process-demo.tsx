"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatedPrice } from "./animated-price";
import { Check, Lock, ServiceIcon } from "./icons";

const DURATION = 4500;

const STEPS = [
  { title: "Pick what you need", body: "Every service shows its starting price up front, so you know the ballpark before you begin." },
  { title: "Answer a few questions", body: "Quick taps, no calls. The price moves with every answer, and what you see is what you pay." },
  { title: "Pay securely", body: "Checkout runs on Stripe. Your card details never touch this site." },
  { title: "Track it to done", body: "A private link shows where your order is, with messages and your files when they are ready." },
];

/** Shows its children after a delay, easing in. Used to act out each step. */
function After({ ms, children, className = "" }: { ms: number; children: React.ReactNode; className?: string }) {
  return <div className={`rise ${className}`} style={{ animationDelay: `${ms}ms` }}>{children}</div>;
}

/** Runs a list of [delay, value] changes once, then stays on the last value. */
function useSequence<T>(initial: T, changes: [number, T][]): T {
  const [value, setValue] = useState(initial);
  const plan = useRef(changes);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timers = plan.current.map(([ms, next]) => window.setTimeout(() => setValue(next), reduce ? 0 : ms));
    return () => timers.forEach((id) => window.clearTimeout(id));
  }, []);
  return value;
}

function PickStage() {
  const picked = useSequence(false, [[900, true]]);
  const tiles = [
    { icon: "globe", name: "Website", from: "$149" },
    { icon: "pen", name: "Writing", from: "$19" },
    { icon: "palette", name: "Logos", from: "$12" },
    { icon: "code", name: "Scripts", from: "$49" },
  ] as const;
  return (
    <div className="grid grid-cols-2 gap-3">
      {tiles.map((tile, i) => {
        const on = picked && i === 0;
        return (
          <After key={tile.name} ms={i * 60}>
            <div className={`rounded-2xl border p-4 transition-[border-color,background-color,transform] duration-300 ease-out-strong ${on ? "border-accent bg-accent-soft" : "border-line bg-surface"}`} style={{ transform: on ? "scale(1.03)" : "none" }}>
              <span className="grid size-9 place-items-center rounded-xl bg-accent-soft text-accent"><ServiceIcon name={tile.icon} width={18} height={18} /></span>
              <p className="mt-3 font-bold">{tile.name}</p>
              <p className="text-sm text-muted">from {tile.from}</p>
            </div>
          </After>
        );
      })}
    </div>
  );
}

function AnswerStage() {
  const stage = useSequence(0, [[700, 1], [1700, 2], [2700, 3]]);
  const price = [149_00, 299_00, 359_00, 467_00][stage];
  const options = ["One page", "Multi page", "Online store"];
  return (
    <div>
      <div className="flex items-start justify-between gap-4">
        <p className="font-display text-lg font-extrabold">What kind of website?</p>
        <div className="text-right">
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted">Price so far</p>
          <AnimatedPrice value={price} className="font-display text-3xl font-extrabold" />
        </div>
      </div>
      <div className="mt-4 space-y-2">
        {options.map((option, i) => {
          const on = stage >= 1 ? i === 1 : i === 0;
          return (
            <div key={option} className={`flex items-center gap-3 rounded-xl border px-3.5 py-3 text-sm font-semibold transition-colors duration-300 ${on ? "border-accent bg-accent-soft" : "border-line bg-surface"}`}>
              <span className={`grid size-5 place-items-center rounded-full border-2 transition-colors duration-300 ${on ? "border-accent bg-accent text-accent-ink" : "border-line"}`}>
                {on && <Check width={11} height={11} strokeWidth={3.5} className="pop" />}
              </span>
              {option}
            </div>
          );
        })}
      </div>
      <div className="mt-3 flex min-h-8 flex-wrap gap-2">
        {stage >= 2 && <span className="pop rounded-full bg-surface-2 px-3 py-1.5 text-xs font-bold">+ Blog $60</span>}
        {stage >= 3 && <span className="pop rounded-full bg-surface-2 px-3 py-1.5 text-xs font-bold">+ Rush 30%</span>}
      </div>
    </div>
  );
}

function PayStage() {
  const paid = useSequence(false, [[1900, true]]);
  return (
    <div>
      <After ms={0}>
        <div className="rounded-2xl border border-line bg-surface p-4">
          <div className="flex justify-between text-sm"><span className="text-muted">Website, multi page</span><span className="font-semibold">$359</span></div>
          <div className="mt-2 flex justify-between text-sm"><span className="text-muted">Rush delivery</span><span className="font-semibold">+30%</span></div>
          <div className="mt-3 flex items-end justify-between border-t border-line pt-3">
            <span className="font-bold">Total</span><span className="font-display text-3xl font-extrabold tabular-nums">$467</span>
          </div>
        </div>
      </After>
      <After ms={120}>
        <div className="mt-3 flex items-center gap-3 rounded-xl border border-line bg-surface px-3.5 py-3 text-sm">
          <span className="h-6 w-9 rounded-md bg-gradient-to-br from-accent to-good" />
          <span className="font-mono tracking-widest text-muted">•••• 4242</span>
        </div>
      </After>
      <After ms={240}>
        <div className={`mt-3 flex h-12 items-center justify-center gap-2 rounded-full text-sm font-bold transition-colors duration-300 ${paid ? "bg-good text-[#04130c]" : "bg-accent text-accent-ink"}`}>
          {paid ? <span key="paid" className="pop flex items-center gap-2"><Check width={16} height={16} strokeWidth={3} /> Payment received</span> : <span className="flex items-center gap-2"><Lock width={15} height={15} /> Pay securely</span>}
        </div>
      </After>
    </div>
  );
}

function TrackStage() {
  const reached = useSequence(0, [[600, 1], [1400, 2], [2300, 3]]);
  const labels = ["Received", "In progress", "Draft ready", "Done"];
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-accent">Website · {labels[reached]}</p>
      <div className="mt-3 grid grid-cols-4 gap-2">
        {labels.map((label, i) => (
          <div key={label}>
            <span className="block h-1.5 overflow-hidden rounded-full bg-surface-2">
              <span className="block h-full origin-left rounded-full bg-good transition-transform duration-500 ease-out-strong" style={{ transform: i <= reached ? "scaleX(1)" : "scaleX(0)" }} />
            </span>
            <span className={`mt-1.5 block text-[11px] font-bold transition-colors duration-300 ${i <= reached ? "text-text" : "text-muted"}`}>{label}</span>
          </div>
        ))}
      </div>
      {reached >= 2 && (
        <div className="rise mt-4 rounded-2xl border border-line bg-surface p-4">
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted">Message from us</p>
          <p className="mt-1 text-sm">{reached >= 3 ? "All done. Your files are ready." : "First draft is up. Tell us what to change."}</p>
        </div>
      )}
      {reached >= 3 && (
        <div className="rise mt-3 flex h-12 items-center justify-between rounded-full bg-accent px-5 text-sm font-bold text-accent-ink">
          Open your finished work <span>↗</span>
        </div>
      )}
    </div>
  );
}

const STAGES = [PickStage, AnswerStage, PayStage, TrackStage];

/**
 * The four steps, acted out. It advances by itself while on screen, pauses
 * when hovered or focused, and can be driven by clicking a step.
 * Purpose: explanation. With reduced motion it stays on the chosen step.
 */
export function ProcessDemo() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [inView, setInView] = useState(false);
  const [autoplay, setAutoplay] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const motionOk = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const observer = new IntersectionObserver(
      ([entry]) => {
        setInView(entry.isIntersecting);
        if (entry.isIntersecting) setAutoplay(motionOk);
      },
      { threshold: 0.35 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const running = autoplay && inView && !paused;
  useEffect(() => {
    if (!running) return;
    const id = window.setTimeout(() => setActive((i) => (i + 1) % STEPS.length), DURATION);
    return () => window.clearTimeout(id);
  }, [running, active]);

  const Stage = STAGES[active];

  return (
    <div
      ref={root}
      onPointerEnter={(e) => e.pointerType === "mouse" && setPaused(true)}
      onPointerLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
      className={`grid items-center gap-6 lg:grid-cols-[1fr_1.05fr] lg:gap-12 ${running ? "" : "is-paused"}`}
    >
      <ol className="space-y-2">
        {STEPS.map((step, i) => {
          const on = i === active;
          return (
            <li key={step.title}>
              <button
                type="button" onClick={() => setActive(i)} aria-current={on ? "step" : undefined}
                className={`relative block w-full overflow-hidden rounded-2xl border p-4 text-left transition-[background-color,border-color] duration-300 sm:p-5 ${on ? "border-line bg-surface shadow-card" : "border-transparent hover:bg-surface-2"}`}
              >
                <span className="flex items-start gap-4">
                  <span className={`grid size-9 shrink-0 place-items-center rounded-full font-display text-sm font-extrabold transition-colors duration-300 ${on ? "bg-accent text-accent-ink" : "bg-surface-2 text-muted"}`}>{i + 1}</span>
                  <span className="min-w-0">
                    <span className={`block text-lg font-bold transition-colors duration-300 ${on ? "text-text" : "text-muted"}`}>{step.title}</span>
                    <span className="mt-1 block text-sm leading-relaxed text-muted">{step.body}</span>
                  </span>
                </span>
                {on && autoplay && <span key={active} className="step-timer absolute inset-x-0 bottom-0 h-0.5 bg-accent" style={{ "--duration": `${DURATION}ms` } as React.CSSProperties} />}
              </button>
            </li>
          );
        })}
      </ol>

      {/* The acted out screen. Decorative: the list beside it carries the meaning. */}
      <div aria-hidden="true" className="select-none rounded-[1.75rem] border border-line bg-surface-2/60 p-3 shadow-float">
        <div className="flex items-center gap-1.5 px-2 pb-3 pt-1">
          <span className="size-2.5 rounded-full bg-line" /><span className="size-2.5 rounded-full bg-line" /><span className="size-2.5 rounded-full bg-line" />
          <span className="ml-3 h-5 flex-1 rounded-full bg-surface" />
        </div>
        <div className="min-h-[21.5rem] rounded-2xl bg-bg p-5 sm:p-6">
          <div key={active} className="rise"><Stage /></div>
        </div>
      </div>
    </div>
  );
}
