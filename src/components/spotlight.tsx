"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Series } from "@/lib/types";
import { STATUS_LABEL, TYPE_LABEL } from "@/lib/types";
import { ChevronLeft, ChevronRight, PlayIcon, StarIcon } from "./icons";

const INTERVAL = 6500;

export function Spotlight({ items }: { items: Series[] }) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const count = items.length;

  useEffect(() => {
    if (paused || count < 2) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => setIndex((i) => (i + 1) % count), INTERVAL);
    return () => window.clearInterval(id);
  }, [paused, count]);

  if (count === 0) return null;
  const go = (delta: number) => setIndex((i) => (i + delta + count) % count);
  const current = items[index];

  return (
    <section
      aria-roledescription="carousel" aria-label="Spotlight"
      onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)} onBlur={() => setPaused(false)}
      className="relative mt-6 overflow-hidden rounded-[2rem] border border-line bg-surface"
    >
      {/* Blurred cover as a colour wash behind the slide */}
      {items.map((s, i) => (
        <img
          key={s.slug} src={s.cover} alt="" aria-hidden="true"
          className={`pointer-events-none absolute inset-0 size-full scale-125 object-cover blur-3xl transition-opacity duration-700 ${i === index ? "opacity-45" : "opacity-0"}`}
        />
      ))}
      <div className="absolute inset-0 bg-gradient-to-r from-surface via-surface/85 to-surface/30" />

      <div key={current.slug} className="rise relative grid items-center gap-8 p-6 sm:p-10 md:grid-cols-[1fr_auto] lg:p-14">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-accent">
            <span className="rounded-full bg-accent-soft px-3 py-1">Spotlight</span>
            <span className="text-muted">{TYPE_LABEL[current.type]} · {STATUS_LABEL[current.status]}</span>
          </p>
          <h1 className="mt-4 text-4xl font-extrabold leading-[1.02] sm:text-5xl lg:text-6xl">{current.title}</h1>
          <p className="mt-4 line-clamp-3 max-w-xl text-base leading-relaxed text-muted sm:text-lg">{current.synopsis}</p>
          <div className="mt-5 flex flex-wrap items-center gap-2 text-sm">
            <span className="inline-flex items-center gap-1.5 font-bold">
              <StarIcon width={16} height={16} className="text-accent-2" />
              {current.rating.toFixed(1)}
            </span>
            {!current.chapterCountUnknown && (
              <>
                <span className="text-muted">·</span>
                <span className="text-muted">{current.chapterCount} chapters</span>
              </>
            )}
            {current.genres.map((g) => (
              <Link
                key={g} href={`/browse?genre=${encodeURIComponent(g)}`}
                className="rounded-full border border-line bg-bg/40 px-3 py-1 text-xs font-semibold text-muted transition hover:border-accent hover:text-accent"
              >
                {g}
              </Link>
            ))}
          </div>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link
              href={`/read/${current.slug}/1`}
              className="inline-flex items-center gap-2 rounded-full bg-accent px-6 py-3 font-bold text-accent-ink transition hover:brightness-110 active:scale-[0.97]"
            >
              <PlayIcon width={16} height={16} />
              Start reading
            </Link>
            <Link
              href={`/series/${current.slug}`}
              className="rounded-full border border-line bg-bg/40 px-6 py-3 font-bold transition hover:border-text active:scale-[0.97]"
            >
              Details
            </Link>
          </div>
        </div>
        <Link
          href={`/series/${current.slug}`} tabIndex={-1} aria-hidden="true"
          className="hidden w-52 rotate-3 overflow-hidden rounded-2xl shadow-2xl ring-1 ring-white/10 transition duration-500 hover:rotate-0 md:block lg:w-64"
        >
          <img src={current.cover} alt="" width={600} height={900} className="aspect-[2/3] w-full object-cover" />
        </Link>
      </div>

      <div className="relative flex items-center gap-3 px-6 pb-6 sm:px-10 lg:px-14">
        <div className="flex flex-1 gap-2">
          {items.map((s, i) => (
            <button
              key={s.slug} type="button" onClick={() => setIndex(i)}
              aria-label={`Show ${s.title}`} aria-current={i === index}
              className="group py-2"
            >
              <span className={`block h-1.5 rounded-full transition-all duration-300 ${i === index ? "w-8 bg-accent" : "w-3 bg-line group-hover:bg-muted"}`} />
            </button>
          ))}
        </div>
        <button type="button" onClick={() => go(-1)} aria-label="Previous spotlight" className="grid size-10 place-items-center rounded-full border border-line bg-bg/40 transition hover:border-accent hover:text-accent">
          <ChevronLeft width={18} height={18} />
        </button>
        <button type="button" onClick={() => go(1)} aria-label="Next spotlight" className="grid size-10 place-items-center rounded-full border border-line bg-bg/40 transition hover:border-accent hover:text-accent">
          <ChevronRight width={18} height={18} />
        </button>
      </div>
    </section>
  );
}
