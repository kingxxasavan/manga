"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  BACKGROUNDS, clampPage, DEFAULT_SETTINGS, keyAction, resolveDirection, resolveMode, spreadFor, step,
  swipeAction, zoneAction, type Fit, type NavAction, type ReaderSettings,
} from "@/lib/reader/logic";
import { KEYS, store, type ProgressMap, type ReadMap } from "@/lib/storage";
import type { Page, SeriesType } from "@/lib/types";
import { useHydrated, useStored } from "@/lib/use-stored";
import { ChevronLeft, ChevronRight, ExpandIcon, SettingsIcon } from "../icons";
import { PageImage } from "./page-image";
import { SettingsPanel } from "./settings-panel";

export interface ReaderProps {
  series: { slug: string; title: string; type: SeriesType };
  chapter: number;
  chapters: { number: number; title: string }[];
  pages: Page[];
}

export function Reader(props: ReaderProps) {
  // Saved settings and progress only exist in the browser, so the reader mounts after hydration.
  const hydrated = useHydrated();
  if (!hydrated) {
    return <div className="grid min-h-dvh place-items-center bg-[#17181c] text-sm text-white/60">Opening chapter {props.chapter}</div>;
  }
  return <ReaderView key={`${props.series.slug}/${props.chapter}`} {...props} />;
}

const PAGED_FIT: Record<Fit, { single: string; double: string }> = {
  height: { single: "h-dvh w-auto max-w-full object-contain", double: "h-dvh w-auto max-w-[50vw] object-contain" },
  width: { single: "h-auto w-full max-w-[1100px]", double: "h-auto w-1/2" },
  original: { single: "h-auto max-w-none", double: "h-auto max-w-none" },
};

const isControl = (target: EventTarget | null) =>
  target instanceof Element && Boolean(target.closest("button, a, input, select, label"));

function ReaderView({ series, chapter, chapters, pages }: ReaderProps) {
  const router = useRouter();
  const total = pages.length;
  const [stored, setStored] = useStored<Partial<ReaderSettings>>(KEYS.settings, DEFAULT_SETTINGS);
  const settings = useMemo<ReaderSettings>(() => ({ ...DEFAULT_SETTINGS, ...stored }), [stored]);
  const mode = resolveMode(settings.mode, series.type);
  const direction = resolveDirection(settings.direction, series.type);
  const background = BACKGROUNDS[settings.background] ?? BACKGROUNDS.dark;

  const [page, setPage] = useState(() => {
    const saved = store.read<ProgressMap>(KEYS.progress, {})[series.slug];
    return saved && saved.chapter === chapter ? clampPage(saved.page, total) : 0;
  });
  const [atEnd, setAtEnd] = useState(false);
  const [bars, setBars] = useState(true);
  const [hovering, setHovering] = useState(false);
  const [panel, setPanel] = useState(false);

  const index = chapters.findIndex((c) => c.number === chapter);
  const prevChapter = index > 0 ? chapters[index - 1] : null;
  const nextChapter = index >= 0 && index < chapters.length - 1 ? chapters[index + 1] : null;
  const chapterHref = (n: number) => `/read/${series.slug}/${n}`;
  const seriesHref = `/series/${series.slug}`;

  // In double page mode two pages are on screen, so "last page seen" is the end of the spread.
  const spread = mode === "double" ? spreadFor(page, total) : [page];
  const lastShown = spread[spread.length - 1] ?? page;

  // Remember where the reader is, and tick the chapter off once the last page is reached.
  useEffect(() => {
    const progress = store.read<ProgressMap>(KEYS.progress, {});
    store.write<ProgressMap>(KEYS.progress, {
      ...progress,
      [series.slug]: { chapter, page, total, updatedAt: Date.now() },
    });
    if (lastShown >= total - 1) {
      const read = store.read<ReadMap>(KEYS.read, {});
      const done = read[series.slug] ?? [];
      if (!done.includes(chapter)) store.write<ReadMap>(KEYS.read, { ...read, [series.slug]: [...done, chapter] });
    }
  }, [page, lastShown, chapter, total, series.slug]);

  const pageRef = useRef(page);
  useEffect(() => {
    pageRef.current = page;
  }, [page]);

  // Queries stay inside this reader: Next keeps the previous route mounted but
  // hidden, so a document wide lookup could find another chapter's pages.
  const stageRef = useRef<HTMLElement>(null);
  const scrollToPage = useCallback((target: number) => {
    stageRef.current
      ?.querySelector(`[data-page="${target}"]`)
      ?.scrollIntoView({ block: "start", behavior: "instant" });
  }, []);

  // Entering strip mode (first load or a mode switch) lands on the current page.
  useLayoutEffect(() => {
    if (mode === "strip") {
      if (pageRef.current > 0) scrollToPage(pageRef.current);
    } else {
      window.scrollTo({ top: 0, behavior: "instant" });
    }
  }, [mode, scrollToPage]);

  // Strip mode: the page crossing the middle of the screen is the current page.
  useEffect(() => {
    if (mode !== "strip") return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setPage(Number((entry.target as HTMLElement).dataset.page));
        }
      },
      { rootMargin: "-50% 0px -50% 0px" },
    );
    stageRef.current?.querySelectorAll<HTMLElement>("[data-page]").forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [mode, total]);

  // Strip mode: hide the bars while scrolling down, bring them back when scrolling up.
  useEffect(() => {
    if (mode !== "strip") return;
    let last = window.scrollY;
    const onScroll = () => {
      const y = window.scrollY;
      if (y > last + 12) setBars(false);
      else if (y < last - 12) setBars(true);
      if (Math.abs(y - last) > 12) last = y;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [mode]);

  // Page modes: bars fade away after a moment of reading.
  useEffect(() => {
    if (mode === "strip" || !bars || panel || hovering || atEnd) return;
    const id = window.setTimeout(() => setBars(false), 3500);
    return () => window.clearTimeout(id);
  }, [mode, bars, panel, hovering, atEnd, page]);

  // Page modes: warm up the next few pages so turning feels instant.
  useEffect(() => {
    if (mode === "strip") return;
    for (const next of pages.slice(page + 1, page + 4)) new Image().src = next.src;
  }, [mode, page, pages]);

  const go = useCallback((action: NavAction) => {
    if (action === "next") {
      if (atEnd) {
        if (nextChapter) router.push(`/read/${series.slug}/${nextChapter.number}`);
        return;
      }
      const result = step(mode, page, total, 1);
      if (result.kind === "page") setPage(result.page);
      else if (settings.autoContinue && nextChapter) router.push(`/read/${series.slug}/${nextChapter.number}`);
      else setAtEnd(true);
    } else {
      if (atEnd) {
        setAtEnd(false);
        return;
      }
      const result = step(mode, page, total, -1);
      if (result.kind === "page") setPage(result.page);
      else setBars(true);
    }
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [atEnd, mode, page, total, nextChapter, settings.autoContinue, router, series.slug]);

  const jump = (target: number) => {
    const clamped = clampPage(target, total);
    setAtEnd(false);
    setPage(clamped);
    if (mode === "strip") scrollToPage(clamped);
  };

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void document.documentElement.requestFullscreen?.().catch(() => {});
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "Escape") {
        setPanel(false);
        return;
      }
      if (panel) return;
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName)) return;
      // Space on a focused button should press the button, not turn the page.
      if (e.key === " " && target && target.closest("button, a")) return;
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      if (key === "m") setBars((v) => !v);
      else if (key === "f") toggleFullscreen();
      else if (key === "n" && nextChapter) router.push(`/read/${series.slug}/${nextChapter.number}`);
      else if (key === "p" && prevChapter) router.push(`/read/${series.slug}/${prevChapter.number}`);
      else {
        const action = keyAction(e.key, mode, direction);
        if (!action) return;
        go(action);
      }
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [panel, mode, direction, go, nextChapter, prevChapter, router, series.slug]);

  // Touch swipes in page modes.
  const touch = useRef<{ x: number; y: number } | null>(null);
  const swiped = useRef(false);
  const onTouchStart = (e: React.TouchEvent) => {
    const t = e.touches[0];
    touch.current = e.touches.length === 1 ? { x: t.clientX, y: t.clientY } : null;
  };
  const onTouchEnd = (e: React.TouchEvent) => {
    const start = touch.current;
    touch.current = null;
    if (!start) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - start.x;
    const dy = t.clientY - start.y;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      swiped.current = true;
      window.setTimeout(() => (swiped.current = false), 400);
      go(swipeAction(dx, direction));
    }
  };

  const onStageClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (swiped.current || isControl(e.target)) return;
    if (window.getSelection()?.toString()) return;
    if (mode === "strip" || atEnd) {
      setBars((v) => !v);
      return;
    }
    const rect = e.currentTarget.getBoundingClientRect();
    const action = zoneAction((e.clientX - rect.left) / rect.width, direction);
    if (action === "menu") setBars((v) => !v);
    else go(action);
  };

  const label = atEnd
    ? "End"
    : spread.length > 1
      ? `${spread[0] + 1}-${spread[1] + 1} / ${total}`
      : `${page + 1} / ${total}`;
  const percent = atEnd ? 100 : total > 0 ? ((lastShown + 1) / total) * 100 : 0;
  const ink = background.dark ? "text-white" : "text-neutral-900";
  const barBase = "fixed inset-x-0 z-40 bg-black/80 text-white backdrop-blur-xl transition-transform duration-300 ease-out";
  const barButton = "inline-flex h-10 min-w-10 items-center justify-center gap-0.5 rounded-full px-2 text-sm font-semibold transition hover:bg-white/15 active:scale-[0.96]";
  const hoverProps = {
    onPointerEnter: (e: React.PointerEvent) => e.pointerType === "mouse" && setHovering(true),
    onPointerLeave: () => setHovering(false),
    onFocusCapture: () => setBars(true),
  };

  const endCard = (
    <div className={`mx-auto w-full max-w-md px-6 py-16 text-center ${ink}`}>
      <p className="text-xs font-bold uppercase tracking-[0.2em] opacity-60">End of chapter {chapter}</p>
      <h2 className="mt-3 text-3xl font-extrabold">{nextChapter ? "Keep going?" : "You are all caught up"}</h2>
      <p className="mt-2 opacity-70">
        {nextChapter ? `Next up: Chapter ${nextChapter.number} · ${nextChapter.title}` : `That was the latest chapter of ${series.title}.`}
      </p>
      <div className="mt-7 flex flex-col gap-3">
        {nextChapter && (
          <Link href={chapterHref(nextChapter.number)} className="rounded-full bg-accent px-6 py-3.5 font-bold text-accent-ink transition hover:brightness-110 active:scale-[0.97]">
            Read chapter {nextChapter.number}
          </Link>
        )}
        <Link href={seriesHref} className="rounded-full border border-current/30 px-6 py-3.5 font-bold transition hover:border-current active:scale-[0.97]">
          Back to series
        </Link>
      </div>
    </div>
  );

  return (
    <div className={`min-h-dvh ${ink}`} style={{ background: background.color }}>
      {/* Always visible reading progress */}
      <div className="fixed inset-x-0 top-0 z-50 h-[3px] bg-white/10" aria-hidden="true">
        <div className="h-full bg-accent transition-[width] duration-200" style={{ width: `${percent}%` }} />
      </div>

      <header {...hoverProps} className={`${barBase} top-0 pt-[3px] ${bars ? "" : "-translate-y-full"}`}>
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-1 px-2 sm:px-4">
          <Link href={seriesHref} aria-label={`Back to ${series.title}`} className={barButton}>
            <ChevronLeft />
          </Link>
          <div className="min-w-0 flex-1 px-1">
            <Link href={seriesHref} className="block truncate text-sm font-bold hover:text-accent">{series.title}</Link>
            <p className="truncate text-xs text-white/60">Chapter {chapter}{index >= 0 ? ` · ${chapters[index].title}` : ""}</p>
          </div>
          <label className="hidden sm:block">
            <span className="sr-only">Jump to chapter</span>
            <select
              value={chapter} onChange={(e) => router.push(chapterHref(Number(e.target.value)))}
              className="h-10 max-w-44 rounded-full border border-white/15 bg-white/10 px-3 text-sm font-semibold outline-none"
            >
              {chapters.map((c) => <option key={c.number} value={c.number} className="bg-neutral-900">Chapter {c.number}</option>)}
            </select>
          </label>
          <button type="button" onClick={toggleFullscreen} aria-label="Toggle fullscreen" className={`${barButton} max-sm:hidden`}>
            <ExpandIcon />
          </button>
          <button type="button" onClick={() => setPanel(true)} aria-label="Reader settings" className={barButton}>
            <SettingsIcon />
          </button>
        </div>
      </header>

      <main
        ref={stageRef}
        onClick={onStageClick}
        onTouchStart={mode === "strip" ? undefined : onTouchStart}
        onTouchEnd={mode === "strip" ? undefined : onTouchEnd}
        style={mode === "strip" ? undefined : { touchAction: "pan-y pinch-zoom" }}
        className={mode === "strip" ? "" : "flex min-h-dvh cursor-pointer items-center justify-center overflow-x-auto"}
      >
        {mode === "strip" ? (
          <div className="mx-auto max-w-[900px]">
            <div className="mx-auto" style={{ width: `${settings.zoom}%` }}>
              {pages.map((p) => (
                <div key={p.index} data-page={p.index} style={{ marginBottom: settings.gap }}>
                  <PageImage page={p} lazy={Math.abs(p.index - page) > 2} className="block h-auto w-full" />
                </div>
              ))}
            </div>
            {endCard}
          </div>
        ) : atEnd ? (
          endCard
        ) : (
          <div className={`flex items-center justify-center ${direction === "rtl" ? "flex-row-reverse" : ""} ${settings.fit === "width" ? "w-full" : ""}`}>
            {spread.map((i) => (
              <PageImage key={pages[i].src} page={pages[i]} className={PAGED_FIT[settings.fit][mode === "double" ? "double" : "single"]} />
            ))}
          </div>
        )}
      </main>

      <footer {...hoverProps} className={`${barBase} bottom-0 pb-[env(safe-area-inset-bottom)] ${bars ? "" : "translate-y-full"}`}>
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-2 px-2 sm:px-4">
          {prevChapter ? (
            <Link href={chapterHref(prevChapter.number)} aria-label={`Previous chapter, chapter ${prevChapter.number}`} className={barButton}>
              <ChevronLeft width={18} height={18} /><span className="hidden pr-1 sm:inline">Prev</span>
            </Link>
          ) : <span className="w-10" />}
          <input
            type="range" min={1} max={Math.max(total, 1)} value={Math.min(page + 1, total)}
            onChange={(e) => jump(Number(e.target.value) - 1)}
            dir={mode === "strip" ? "ltr" : direction}
            aria-label="Page" aria-valuetext={`Page ${page + 1} of ${total}`}
            className="range min-w-0 flex-1"
          />
          <span className="w-[4.5rem] shrink-0 text-center text-sm font-semibold tabular-nums">{label}</span>
          {nextChapter ? (
            <Link href={chapterHref(nextChapter.number)} aria-label={`Next chapter, chapter ${nextChapter.number}`} className={barButton}>
              <span className="hidden pl-1 sm:inline">Next</span><ChevronRight width={18} height={18} />
            </Link>
          ) : <span className="w-10" />}
        </div>
      </footer>

      {panel && (
        <SettingsPanel
          settings={settings} mode={mode} direction={direction}
          onChange={(patch) => setStored({ ...settings, ...patch })}
          onClose={() => setPanel(false)}
        />
      )}
    </div>
  );
}
