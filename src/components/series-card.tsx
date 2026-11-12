import Link from "next/link";
import type { Series } from "@/lib/types";
import { StarIcon } from "./icons";

export function Cover({ series, className = "", eager = false }: { series: Series; className?: string; eager?: boolean }) {
  return (
    <img
      src={series.cover} alt="" width={600} height={900}
      loading={eager ? "eager" : "lazy"} decoding="async"
      className={`aspect-[2/3] w-full bg-surface-2 object-cover ${className}`}
    />
  );
}

export function RatingChip({ rating }: { rating: number }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-black/65 px-2 py-1 text-xs font-bold text-white backdrop-blur">
      <StarIcon width={12} height={12} className="text-amber-400" />
      {rating.toFixed(1)}
    </span>
  );
}

export function SeriesCard({ series, sub }: { series: Series; sub?: string }) {
  return (
    <Link href={`/series/${series.slug}`} className="group block">
      <div className="relative overflow-hidden rounded-2xl shadow-card ring-1 ring-line/60">
        <Cover series={series} className="transition duration-500 ease-out group-hover:scale-[1.05]" />
        <span className="absolute right-2 top-2">
          <RatingChip rating={series.rating} />
        </span>
      </div>
      <h3 className="mt-2.5 line-clamp-2 font-sans text-sm font-semibold leading-snug tracking-normal transition group-hover:text-accent">
        {series.title}
      </h3>
      <p className="mt-0.5 truncate text-xs text-muted">{sub ?? series.genres.slice(0, 2).join(" · ")}</p>
    </Link>
  );
}
