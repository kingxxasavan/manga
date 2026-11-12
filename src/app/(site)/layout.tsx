import { Header } from "@/components/header";
import { SITE_NAME } from "@/lib/site";
import { source } from "@/lib/source";

export default async function SiteLayout({ children }: { children: React.ReactNode }) {
  const meta = await source.getMeta();
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-10 sm:px-6">{children}</main>
      <footer className="border-t border-line pb-24 pt-8 text-center text-sm text-muted md:pb-8">
        {meta.credit ? (
          <p>
            <a href={meta.credit.href} target="_blank" rel="noreferrer" className="font-semibold text-text hover:text-accent">
              {meta.credit.label}
            </a>
            . Covers belong to their publishers. {SITE_NAME} hosts no chapters, reader pages are placeholders.
          </p>
        ) : (
          <p>{SITE_NAME} is running on demo content. Every title and artwork here is a generated placeholder.</p>
        )}
      </footer>
    </>
  );
}
