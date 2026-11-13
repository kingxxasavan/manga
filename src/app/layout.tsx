import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { ArrowRight, Logo } from "@/components/icons";
import { THEME_KEY, ThemeToggle } from "@/components/theme-toggle";
import { SERVICES } from "@/lib/services";
import { SITE_NAME, SITE_TAGLINE } from "@/lib/site";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: `${SITE_NAME}: websites, writing, design and tools made for you`, template: `%s | ${SITE_NAME}` },
  description: SITE_TAGLINE,
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f6f9" },
    { media: "(prefers-color-scheme: dark)", color: "#060913" },
  ],
};

// Runs before first paint: applies the saved (or system) theme with no flash,
// and marks that scripts are on so scroll reveals may start hidden.
const bootScript = `try{var d=document.documentElement;d.classList.add("js");var t=localStorage.getItem(${JSON.stringify(THEME_KEY)});if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";d.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: bootScript }} />
      </head>
      <body className="flex min-h-full flex-col">
        <header className="sticky top-0 z-40 border-b border-line/60 bg-bg/80 backdrop-blur-xl">
          <div className="mx-auto flex h-16 max-w-6xl items-center gap-2 px-4 sm:px-6">
            <Link href="/" className="flex items-center gap-2.5 font-display text-xl font-extrabold tracking-tight">
              <Logo />
              {SITE_NAME}
            </Link>
            <nav aria-label="Main" className="ml-auto flex items-center gap-1 text-sm font-semibold">
              <Link href="/#services" className="hidden rounded-full px-3 py-2 text-muted transition-colors duration-200 hover:text-text sm:block">Services</Link>
              <Link href="/#process" className="hidden rounded-full px-3 py-2 text-muted transition-colors duration-200 hover:text-text sm:block">How it works</Link>
              <Link href="/#faq" className="hidden rounded-full px-3 py-2 text-muted transition-colors duration-200 hover:text-text md:block">FAQ</Link>
              <ThemeToggle />
              <Link href="/#services" className="btn btn-primary ml-1 h-10 px-4 text-sm">
                Start building <ArrowRight width={16} height={16} className="arrow" />
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-20 sm:px-6">{children}</main>
        <footer className="border-t border-line bg-surface">
          <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 sm:grid-cols-[1.4fr_1fr_1fr] sm:px-6">
            <div>
              <p className="flex items-center gap-2.5 font-display text-lg font-extrabold"><Logo /> {SITE_NAME}</p>
              <p className="mt-3 max-w-xs text-sm leading-relaxed text-muted">Made to order digital work with a clear price before you pay.</p>
            </div>
            <nav aria-label="Services">
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted">Services</p>
              <ul className="mt-3 space-y-2 text-sm font-medium">
                {SERVICES.map((s) => <li key={s.id}><Link href={`/build/${s.id}`} className="transition-colors duration-200 hover:text-accent">{s.name}</Link></li>)}
              </ul>
            </nav>
            <nav aria-label="Company">
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted">Company</p>
              <ul className="mt-3 space-y-2 text-sm font-medium">
                <li><Link href="/#process" className="transition-colors duration-200 hover:text-accent">How it works</Link></li>
                <li><Link href="/#faq" className="transition-colors duration-200 hover:text-accent">Questions</Link></li>
                <li><Link href="/policies" className="transition-colors duration-200 hover:text-accent">Refunds and terms</Link></li>
              </ul>
            </nav>
          </div>
          <p className="border-t border-line py-5 text-center text-xs text-muted">© {SITE_NAME}. Payments are handled by Stripe.</p>
        </footer>
      </body>
    </html>
  );
}
