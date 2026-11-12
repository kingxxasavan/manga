"use client";

import Link from "next/link";
import { useRef } from "react";
import { ChevronLeft, ChevronRight } from "./icons";

interface Props {
  title: string;
  note?: string;
  href?: string;
  children: React.ReactNode;
}

/** A titled, horizontally scrolling shelf with arrow buttons on larger screens. */
export function ScrollRow({ title, note, href, children }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const scroll = (dir: 1 | -1) => {
    const el = ref.current;
    if (el) el.scrollBy({ left: dir * el.clientWidth * 0.85, behavior: "smooth" });
  };
  const arrow = "hidden size-9 place-items-center rounded-full border border-line text-muted transition hover:border-accent hover:text-accent sm:grid";
  return (
    <section className="mt-12">
      <div className="mb-4 flex items-end gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-2xl font-extrabold sm:text-[1.7rem]">{title}</h2>
          {note && <p className="mt-0.5 text-sm text-muted">{note}</p>}
        </div>
        {href && (
          <Link href={href} className="shrink-0 text-sm font-semibold text-accent hover:underline">
            See all
          </Link>
        )}
        <button type="button" onClick={() => scroll(-1)} aria-label={`Scroll ${title} back`} className={arrow}>
          <ChevronLeft width={18} height={18} />
        </button>
        <button type="button" onClick={() => scroll(1)} aria-label={`Scroll ${title} forward`} className={arrow}>
          <ChevronRight width={18} height={18} />
        </button>
      </div>
      <div
        ref={ref}
        className="no-scrollbar -mx-4 flex snap-x gap-4 overflow-x-auto scroll-px-4 px-4 pb-2 sm:-mx-6 sm:scroll-px-6 sm:px-6"
      >
        {children}
      </div>
    </section>
  );
}

export function RowItem({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  return <div className={`shrink-0 snap-start ${wide ? "w-72 sm:w-80" : "w-[9.25rem] sm:w-44"}`}>{children}</div>;
}
