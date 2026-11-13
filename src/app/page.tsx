import Link from "next/link";
import { HeroQuote } from "@/components/hero-quote";
import { ArrowRight, Check, Clock, Lock, ServiceIcon } from "@/components/icons";
import { ProcessDemo } from "@/components/process-demo";
import { Reveal } from "@/components/reveal";
import { SERVICES } from "@/lib/services";
import { LAUNCH_PRICING } from "@/lib/site";

const PROMISES = [
  { title: "No charge until you agree", body: "You get an estimate first, then a confirmed price. You pay only after you have seen the final number and are happy with it." },
  { title: "Changes are included", body: "Every order comes with a round of changes, and you can add more rounds when you order." },
  { title: "You always know where it is", body: "Your private order page shows each step from received to done, with our notes along the way." },
  { title: "See it before we build it", body: "Designing a website? Pick a layout, colors and text style and watch a live preview change as you choose." },
];

const FAQ = [
  { q: "How is the price decided?", a: "By how complex the job is and the level of finish you want. Right after the questions you see an estimated price range. We then look at your request and confirm the final price before you pay anything." },
  { q: "When do I pay?", a: "Only after we confirm the final price on your order page and you accept it. Sending a request costs nothing." },
  { q: "What if my project is bigger than the options?", a: 'Choose "Something else" and describe it. We reply with a price on your order page. Very large projects get no automatic estimate and are always priced by hand.' },
  { q: "Do I need an account?", a: "No. After you send a request you get a private link to your order page. Keep that link, it is where your final price appears and how you check progress and collect your files." },
  { q: "How do I pay?", a: "On a Stripe checkout page, by card. This site never sees or stores your card details." },
  { q: "What if I am not happy with it?", a: "Every order includes at least one round of changes, and you can add more when you order. The refunds page has the full details." },
];

const eyebrow = "text-xs font-bold uppercase tracking-[0.18em] text-accent";

export default function HomePage() {
  return (
    <>
      {/* Hero */}
      <section className="panel-dark on-dark mt-4 rounded-[2rem] px-6 py-14 sm:mt-6 sm:rounded-[2.5rem] sm:px-10 sm:py-20 lg:px-14">
        <span className="glow glow-a" /><span className="glow glow-b" />
        <div className="grid items-center gap-14 lg:grid-cols-[1.15fr_1fr]">
          <div>
            <p className="rise inline-flex items-center gap-2.5 rounded-full border border-line bg-surface px-4 py-1.5 text-xs font-semibold text-muted">
              <span className="live-dot" /> {LAUNCH_PRICING ? "Now open, with launch pricing" : "Taking new orders"}
            </p>
            <h1 className="rise mt-6 text-[2.75rem] font-extrabold leading-[1.02] sm:text-6xl lg:text-[4.25rem]" style={{ animationDelay: "60ms" }}>
              Describe it.<br />Get an estimate.<br /><span className="text-gradient">We build it.</span>
            </h1>
            <p className="rise mt-6 max-w-lg text-lg leading-relaxed text-muted" style={{ animationDelay: "120ms" }}>
              Websites, writing, graphics and small tools, made to order. Tell us what you want like you would ask an AI, get an estimated price based on how complex it is, and follow your order to the finish.
            </p>
            <div className="rise mt-8 flex flex-wrap gap-3" style={{ animationDelay: "180ms" }}>
              <Link href="#services" className="btn btn-light px-7 py-3.5">
                Start building <ArrowRight width={18} height={18} className="arrow" />
              </Link>
              <Link href="#process" className="btn border border-line bg-surface px-7 py-3.5 hover:bg-surface-2">
                See how it works
              </Link>
            </div>
            <ul className="rise mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted" style={{ animationDelay: "240ms" }}>
              <li className="inline-flex items-center gap-2"><Lock width={15} height={15} /> No payment until you agree</li>
              <li className="inline-flex items-center gap-2"><Clock width={15} height={15} /> An estimate in about a minute</li>
              <li className="inline-flex items-center gap-2"><Check width={15} height={15} /> No account needed</li>
            </ul>
          </div>
          <div className="rise pb-2 sm:pb-24 lg:pb-16" style={{ animationDelay: "200ms" }}>
            <HeroQuote />
          </div>
        </div>
      </section>

      {/* Services */}
      <section id="services" className="scroll-mt-24 pt-24">
        <Reveal>
          <p className={eyebrow}>Services</p>
          <h2 className="mt-3 text-4xl font-extrabold sm:text-5xl">What can we build for you?</h2>
          <p className="mt-3 max-w-xl text-lg text-muted">Pick one and tell us about it. Your estimate depends on how complex the job is and the level of finish you want.</p>
        </Reveal>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SERVICES.map((service, i) => (
            <Reveal key={service.id} delay={i * 60} className={service.quoteOnly ? "sm:col-span-2" : ""}>
              <Link
                href={`/build/${service.id}`}
                className={`lift group flex h-full flex-col rounded-3xl border border-line p-6 shadow-card ${service.quoteOnly ? "panel-dark on-dark" : "bg-surface"}`}
              >
                <span className="grid size-12 place-items-center rounded-2xl bg-accent-soft text-accent">
                  <ServiceIcon name={service.icon} width={24} height={24} />
                </span>
                <h3 className="mt-5 text-2xl font-extrabold">{service.name}</h3>
                <p className="mt-1.5 text-muted">{service.tagline}</p>
                <ul className="mt-5 flex flex-wrap gap-2">
                  {service.examples.map((example) => (
                    <li key={example} className="rounded-full border border-line px-3 py-1 text-xs font-semibold text-muted">{example}</li>
                  ))}
                </ul>
                {service.id === "custom" && (
                  <p className="mt-5 max-w-lg text-sm leading-relaxed text-muted">
                    Feeling lucky? Pick <span className="font-bold text-text">Surprise me</span> and get something random made just for you, from a cursed image to a gloriously bad little game. Flat <span className="font-bold text-text">$15</span>.
                  </p>
                )}
                <div className="mt-auto flex items-center justify-between gap-3 pt-7">
                  <p className="text-sm text-muted">
                    <span className="block text-[11px] font-bold uppercase tracking-[0.16em]">Usual delivery</span>
                    <span className="font-semibold text-text">{service.delivery}</span>
                  </p>
                  <span className={`btn px-5 py-2.5 text-sm ${service.quoteOnly ? "btn-light" : "btn-primary"}`}>
                    Build it <ArrowRight width={16} height={16} className="arrow" />
                  </span>
                </div>
              </Link>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Process */}
      <section id="process" className="scroll-mt-24 pt-28">
        <Reveal>
          <p className={eyebrow}>How it works</p>
          <h2 className="mt-3 text-4xl font-extrabold sm:text-5xl">From idea to delivered, in four steps</h2>
          <p className="mt-3 max-w-xl text-lg text-muted">Watch it play, or click a step to jump to it.</p>
        </Reveal>
        <Reveal className="mt-10" delay={80}>
          <ProcessDemo />
        </Reveal>
      </section>

      {/* Promises */}
      <section className="pt-28">
        <Reveal>
          <p className={eyebrow}>Why order here</p>
          <h2 className="mt-3 text-4xl font-extrabold sm:text-5xl">Simple on purpose</h2>
        </Reveal>
        <div className="mt-10 grid gap-4 sm:grid-cols-2">
          {PROMISES.map((item, i) => (
            <Reveal key={item.title} delay={i * 60}>
              <div className="flex h-full gap-4 rounded-3xl border border-line bg-surface p-6 shadow-card">
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-good/15 text-good"><Check width={18} height={18} strokeWidth={3} /></span>
                <div>
                  <h3 className="text-xl font-bold">{item.title}</h3>
                  <p className="mt-1.5 leading-relaxed text-muted">{item.body}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="scroll-mt-24 pt-28">
        <div className="grid gap-10 lg:grid-cols-[1fr_1.6fr]">
          <Reveal>
            <p className={eyebrow}>Questions</p>
            <h2 className="mt-3 text-4xl font-extrabold sm:text-5xl">Good to know</h2>
            <p className="mt-3 text-lg text-muted">The short answers. The <Link href="/policies" className="font-semibold text-accent hover:underline">refunds and terms</Link> page has the rest.</p>
          </Reveal>
          <Reveal delay={80}>
            <div className="divide-y divide-line rounded-3xl border border-line bg-surface shadow-card">
              {FAQ.map((item) => (
                <details key={item.q} className="group p-5 sm:p-6">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-lg font-bold">
                    {item.q}
                    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface-2 text-xl leading-none transition-transform duration-200 ease-out-strong group-open:rotate-45">+</span>
                  </summary>
                  <p className="rise mt-3 max-w-2xl leading-relaxed text-muted">{item.a}</p>
                </details>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* Closing banner */}
      <Reveal className="mt-28">
        <section className="panel-dark on-dark rounded-[2rem] px-6 py-16 text-center sm:rounded-[2.5rem] sm:px-10">
          <span className="glow glow-a" /><span className="glow glow-b" />
          <h2 className="mx-auto max-w-2xl text-4xl font-extrabold sm:text-5xl">Have something in mind?</h2>
          <p className="mx-auto mt-3 max-w-md text-lg text-muted">Get your estimate in about a minute. Sending a request costs nothing.</p>
          <Link href="#services" className="btn btn-light mt-8 px-8 py-4">
            Pick a service <ArrowRight width={18} height={18} className="arrow" />
          </Link>
        </section>
      </Reveal>
    </>
  );
}
