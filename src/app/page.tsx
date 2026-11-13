import Link from "next/link";
import { ArrowRight, Clock, Lock, ServiceIcon } from "@/components/icons";
import { formatMoney } from "@/lib/money";
import { SERVICES } from "@/lib/services";
import { MAX_ORDER_CENTS, SITE_NAME } from "@/lib/site";

const STEPS = [
  { title: "Pick what you need", body: "Choose a service below. Every one shows its starting price up front." },
  { title: "Answer a few questions", body: "Quick taps, no calls. The price updates live with every answer, so there are no surprises." },
  { title: "Pay securely", body: "Checkout runs on Stripe. We never see or store your card details." },
  { title: "Track it to done", body: "You get a private link that shows exactly where your order is, from received to delivered." },
];

const FAQ = [
  { q: "How is the price decided?", a: "From a fixed price list. Each answer you give adds a known amount, and you see the total change as you go. The price you see before paying is the price you pay." },
  { q: "What if my project is bigger than the options?", a: `Use "Something else" and describe it. We reply with a price on your order page before you pay anything. Orders above ${formatMoney(MAX_ORDER_CENTS)} are always quoted by hand.` },
  { q: "Do I need an account?", a: "No. After you order you get a private link to your order page. Keep that link, it is how you check progress and get your files." },
  { q: "What if I am not happy with it?", a: "Every order includes at least one round of changes, and you can add more when you order. See the refunds page for the details." },
];

export default function HomePage() {
  return (
    <>
      <section className="rise pb-6 pt-14 text-center sm:pt-20">
        <p className="mx-auto inline-flex items-center gap-2 rounded-full border border-line bg-surface px-4 py-1.5 text-xs font-bold uppercase tracking-[0.16em] text-muted">
          <span className="size-2 rounded-full bg-accent" /> One studio, one clear price
        </p>
        <h1 className="mx-auto mt-6 max-w-3xl text-5xl font-extrabold leading-[1.02] sm:text-6xl lg:text-7xl">
          Tell us what you need. <span className="text-accent">See the price</span> before you pay.
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-muted">
          Websites, writing, graphics and small tools, made for you. Answer a few questions, watch the price build, and track your order to the finish.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link href="#services" className="inline-flex items-center gap-2 rounded-full bg-accent px-7 py-3.5 font-bold text-accent-ink transition hover:brightness-110 active:scale-[0.97]">
            Start building <ArrowRight width={18} height={18} />
          </Link>
          <Link href="#how" className="rounded-full border border-line bg-surface px-7 py-3.5 font-bold transition hover:border-text active:scale-[0.97]">
            How it works
          </Link>
        </div>
        <p className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-muted">
          <span className="inline-flex items-center gap-1.5"><Lock width={15} height={15} /> Secure checkout by Stripe</span>
          <span className="inline-flex items-center gap-1.5"><Clock width={15} height={15} /> No account needed</span>
        </p>
      </section>

      <section id="services" className="scroll-mt-24 pt-12">
        <h2 className="text-3xl font-extrabold sm:text-4xl">What can we build for you?</h2>
        <p className="mt-2 text-muted">Pick one to start. It takes about a minute.</p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SERVICES.map((service) => (
            <Link
              key={service.id} href={`/build/${service.id}`}
              className={`group flex flex-col rounded-3xl border border-line bg-surface p-6 shadow-card transition hover:-translate-y-1 hover:border-accent/60 ${service.quoteOnly ? "sm:col-span-2 lg:col-span-2" : ""}`}
            >
              <span className="grid size-12 place-items-center rounded-2xl bg-accent-soft text-accent">
                <ServiceIcon name={service.icon} width={24} height={24} />
              </span>
              <h3 className="mt-4 text-2xl font-extrabold">{service.name}</h3>
              <p className="mt-1 text-muted">{service.tagline}</p>
              <ul className="mt-4 flex flex-wrap gap-2">
                {service.examples.map((example) => (
                  <li key={example} className="rounded-full bg-surface-2 px-3 py-1 text-xs font-semibold text-muted">{example}</li>
                ))}
              </ul>
              <div className="mt-6 flex items-end justify-between gap-3 border-t border-line pt-4">
                <p>
                  <span className="block text-xs font-bold uppercase tracking-wider text-muted">{service.quoteOnly ? "Price" : "From"}</span>
                  <span className="font-display text-2xl font-extrabold">{service.quoteOnly ? "Custom quote" : formatMoney(service.startingAt)}</span>
                </p>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-bold text-accent-ink transition group-hover:brightness-110">
                  Build <ArrowRight width={16} height={16} />
                </span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section id="how" className="scroll-mt-24 pt-20">
        <h2 className="text-3xl font-extrabold sm:text-4xl">How it works</h2>
        <ol className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, i) => (
            <li key={step.title} className="rounded-3xl border border-line bg-surface p-6">
              <span className="font-display text-4xl font-extrabold text-accent">{i + 1}</span>
              <h3 className="mt-3 text-lg font-bold">{step.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="pt-20">
        <h2 className="text-3xl font-extrabold sm:text-4xl">Questions</h2>
        <div className="mt-6 divide-y divide-line rounded-3xl border border-line bg-surface">
          {FAQ.map((item) => (
            <details key={item.q} className="group p-5 sm:p-6">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-lg font-bold">
                {item.q}
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface-2 text-xl leading-none transition group-open:rotate-45">+</span>
              </summary>
              <p className="mt-3 max-w-3xl leading-relaxed text-muted">{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="mt-20 rounded-[2rem] bg-accent p-8 text-center text-accent-ink sm:p-12">
        <h2 className="text-3xl font-extrabold sm:text-4xl">Ready when you are</h2>
        <p className="mx-auto mt-2 max-w-md opacity-90">Start with {SITE_NAME} in a minute. You only pay once you have seen the price.</p>
        <Link href="#services" className="mt-6 inline-flex items-center gap-2 rounded-full bg-accent-ink px-7 py-3.5 font-bold text-accent transition hover:opacity-90 active:scale-[0.97]">
          Pick a service <ArrowRight width={18} height={18} />
        </Link>
      </section>
    </>
  );
}
