import { Header } from "@/components/header";
import { SITE_NAME } from "@/lib/site";

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-10 sm:px-6">{children}</main>
      <footer className="border-t border-line pb-24 pt-8 text-center text-sm text-muted md:pb-8">
        <p>{SITE_NAME} is running on demo content. Every title and artwork here is a generated placeholder.</p>
      </footer>
    </>
  );
}
