import Link from "next/link";

export default function NotFound() {
  return (
    <main className="grid min-h-dvh place-items-center px-6 text-center">
      <div>
        <p className="font-display text-7xl font-extrabold text-accent">404</p>
        <h1 className="mt-3 text-2xl font-bold">This page went missing</h1>
        <p className="mt-2 text-muted">The series or chapter you were looking for is not in the library.</p>
        <Link href="/" className="mt-6 inline-block rounded-full bg-accent px-6 py-3 font-semibold text-accent-ink">
          Back to home
        </Link>
      </div>
    </main>
  );
}
