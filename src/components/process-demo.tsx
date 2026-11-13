"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Lock, ServiceIcon } from "./icons";

const DURATION = 4500;

const STEPS = [
  { title: "Pick what you need", body: "Choose the kind of work. There are no price lists to study first." },
  { title: "Tell us about it", body: "A few quick taps about how complex the job is and the level of finish you want." },
  { title: "Get your estimate, then pay", body: "You see an estimated price right away. We confirm the final price, and only then do you pay, securely on Stripe." },
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
    { icon: "globe", name: "Website", note: "Sites and stores" },
    { icon: "pen", name: "Writing", note: "Resumes and copy" },
    { icon: "palette", name: "Logos", note: "Brand graphics" },
    { icon: "code", name: "Scripts", note: "Small tools" },
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
              <p className="text-sm text-muted">{tile.note}</p>
            </div>
          </After>
        );
      })}
    </div>
  );
}

function AnswerStage() {
  const stage = useSequence(0, [[800, 1], [1800, 2], [2700, 3]]);
  const options = ["Simple", "Medium", "Complex"];
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted">Question 2 of 6</p>
      <p className="mt-1 font-display text-lg font-extrabold">How complex is it?</p>
      <div className="mt-4 space-y-2">
        {options.map((option, i) => {
          const on = stage >= 1 && i === 1;
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
        {stage >= 2 && <span className="pop rounded-full bg-surface-2 px-3 py-1.5 text-xs font-bold">Polished finish</span>}
        {stage >= 3 && <span className="pop rounded-full bg-surface-2 px-3 py-1.5 text-xs font-bold">2 rounds of changes</span>}
      </div>
    </div>
  );
}

function PayStage() {
  const stage = useSequence(0, [[900, 1], [2000, 2], [3100, 3]]);
  return (
    <div>
      <After ms={0}>
        <div className="rounded-2xl border border-line bg-surface p-4">
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted">Your estimated price</p>
          {/* A range, drawn rather than numbered: the real one depends on the request */}
          <div className="relative mt-4 h-2 rounded-full bg-surface-2">
            <span className="absolute inset-y-0 left-[28%] w-[44%] origin-left rounded-full bg-accent transition-transform duration-700 ease-out-strong" style={{ transform: stage >= 1 ? "scaleX(1)" : "scaleX(0)" }} />
          </div>
          <div className="mt-2 flex justify-between px-[24%] text-[11px] font-bold text-muted"><span>Low</span><span>High</span></div>
        </div>
      </After>
      <div className="mt-3 min-h-[3.25rem]">
        {stage >= 2 && (
          <div className="rise flex items-center gap-3 rounded-xl border border-good/40 bg-good/10 px-3.5 py-3 text-sm font-semibold">
            <span className="grid size-5 place-items-center rounded-full bg-good text-[#04130c]"><Check width={12} height={12} strokeWidth={3.5} /></span>
            Final price confirmed by us
          </div>
        )}
      </div>
      <After ms={240}>
        <div className={`mt-3 flex h-12 items-center justify-center gap-2 rounded-full text-sm font-bold transition-[background-color,color,opacity] duration-300 ${stage >= 3 ? "bg-good text-[#04130c]" : "bg-accent text-accent-ink"}`} style={{ opacity: stage >= 2 ? 1 : 0.4 }}>
          {stage >= 3 ? <span key="paid" className="pop flex items-center gap-2"><Check width={16} height={16} strokeWidth={3} /> Payment received</span> : <span className="flex items-center gap-2"><Lock width={15} height={15} /> Pay securely</span>}
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
