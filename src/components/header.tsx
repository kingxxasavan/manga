import Link from "next/link";
import { Suspense } from "react";
import { SITE_NAME } from "@/lib/site";
import { Logo, SearchIcon } from "./icons";
import { DesktopNav, MobileNav } from "./nav";
import { ThemeToggle } from "./theme-toggle";

export function Header() {
  return (
    <>
      <header className="sticky top-0 z-40 border-b border-line/70 bg-bg/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2.5 font-display text-xl font-extrabold tracking-tight">
            <Logo />
            {SITE_NAME}
          </Link>
          <div className="ml-4">
            <Suspense fallback={null}>
              <DesktopNav />
            </Suspense>
          </div>
          <form action="/browse" role="search" className="ml-auto hidden w-full max-w-xs sm:block">
            <label className="relative block">
              <span className="sr-only">Search titles and authors</span>
              <SearchIcon className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" width={18} height={18} />
              <input
                type="search" name="q" placeholder="Search titles, authors"
                className="h-10 w-full rounded-full border border-line bg-surface pl-10 pr-4 text-sm outline-none transition placeholder:text-muted focus:border-accent"
              />
            </label>
          </form>
          <Link
            href="/browse" aria-label="Search"
            className="ml-auto grid size-10 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-text sm:hidden"
          >
            <SearchIcon />
          </Link>
          <ThemeToggle />
        </div>
      </header>
      <Suspense fallback={null}>
        <MobileNav />
      </Suspense>
    </>
  );
}
