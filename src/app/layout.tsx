import type { Metadata } from "next";
import Link from "next/link";
import { Logo } from "@/components/icons";
import { THEME_KEY, ThemeToggle } from "@/components/theme-toggle";
import { SITE_NAME, SITE_TAGLINE } from "@/lib/site";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: `${SITE_NAME}: websites, writing, design and tools made for you`, template: `%s | ${SITE_NAME}` },
  description: SITE_TAGLINE,
};

// Runs before first paint so the saved (or system) theme never flashes.
const themeScript = `try{var t=localStorage.getItem(${JSON.stringify(THEME_KEY)});if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="flex min-h-full flex-col">
        <header className="sticky top-0 z-40 border-b border-line/70 bg-bg/85 backdrop-blur-xl">
          <div className="mx-auto flex h-16 max-w-6xl items-center gap-2 px-4 sm:px-6">
            <Link href="/" className="flex items-center gap-2.5 font-display text-xl font-extrabold tracking-tight">
              <Logo />
              {SITE_NAME}
            </Link>
            <nav aria-label="Main" className="ml-auto flex items-center gap-1 text-sm font-semibold">
              <Link href="/#services" className="rounded-full px-3 py-2 text-muted transition hover:text-text">Services</Link>
              <Link href="/#how" className="hidden rounded-full px-3 py-2 text-muted transition hover:text-text sm:block">How it works</Link>
              <ThemeToggle />
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-16 sm:px-6">{children}</main>
        <footer className="border-t border-line py-8 text-sm text-muted">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 sm:px-6">
            <p>© {SITE_NAME}. Payments are handled by Stripe.</p>
            <Link href="/policies" className="font-semibold hover:text-text">Refunds and terms</Link>
          </div>
        </footer>
      </body>
    </html>
  );
}
