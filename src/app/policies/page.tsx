import type { Metadata } from "next";
import { MAX_ORDER_CENTS, SITE_NAME, SUPPORT_EMAIL } from "@/lib/site";
import { formatMoney } from "@/lib/money";

export const metadata: Metadata = { title: "Refunds and terms" };

// DRAFT WORDING. The site owner should read this, change it to match how they
// really work, and have it checked against the rules where they do business.
const SECTIONS = [
  { title: "What you are buying", body: `${SITE_NAME} makes digital work to order: websites, writing, graphics and small software tools. Each order is made for you from the answers you give when ordering.` },
  { title: "Estimates and prices", body: `After the questions you see an estimated price range, based on how complex the job is and the level of finish you chose. An estimate is not a bill. We then confirm a final price on your order page, and you are charged nothing until you accept it by paying. If the final price is outside your estimate, we say why. Requests above ${formatMoney(MAX_ORDER_CENTS)} and custom requests get no automatic estimate and are priced by hand.` },
  { title: "Changes", body: "Every order includes at least one round of changes. A round is one list of changes sent after you see a draft. Extra rounds can be added when you order." },
  { title: "Refunds", body: "Sending a request is free and you can walk away at any time before paying. After paying, if we have not started your order, you can cancel for a full refund. If we cannot deliver what was ordered, you get a full refund. Once a draft has been delivered, refunds are decided case by case, because the work has already been done for you." },
  { title: "Delivery times", body: "Delivery times shown on the site are estimates, not guarantees. If an order is running late we will say so on your order page." },
  { title: "What we will not make", body: "We do not take orders for anything illegal, deceptive or harmful, or for legal, medical or financial advice. If an order like that comes in, we cancel it and refund it." },
  { title: "Your order link", body: "Your order page link is private and works like a key. Anyone with the link can see that order, so do not share it publicly." },
];

export default function PoliciesPage() {
  return (
    <article className="mx-auto max-w-2xl pt-12">
      <h1 className="text-4xl font-extrabold">Refunds and terms</h1>
      <p className="mt-2 text-muted">The short, plain version of how ordering works.</p>
      <div className="mt-8 space-y-7">
        {SECTIONS.map((section) => (
          <section key={section.title}>
            <h2 className="text-xl font-bold">{section.title}</h2>
            <p className="mt-1.5 leading-relaxed text-muted">{section.body}</p>
          </section>
        ))}
        {SUPPORT_EMAIL && (
          <section>
            <h2 className="text-xl font-bold">Contact</h2>
            <p className="mt-1.5 text-muted">Questions about an order: <a className="font-semibold text-accent hover:underline" href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a></p>
          </section>
        )}
      </div>
    </article>
  );
}
