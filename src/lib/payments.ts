import "server-only";
import Stripe from "stripe";
import { canPay, getOrder, isOrderId, markPaid, setStripeSession, type Order } from "./orders";
import { CURRENCY, SITE_NAME } from "./site";

/**
 * Everything that talks to Stripe.
 *
 * The amount charged always comes from the order row in the database, which
 * the server priced itself. Nothing the browser sends is used as a price.
 * An order only becomes "paid" after Stripe itself says the Checkout Session
 * is paid, either through the signed webhook or by fetching the session with
 * the secret key. The browser arriving on a success page proves nothing.
 */

export class PaymentsNotConfigured extends Error {
  constructor() {
    super("STRIPE_SECRET_KEY is not set.");
    this.name = "PaymentsNotConfigured";
  }
}

let client: Stripe | undefined;
export function getStripe(): Stripe {
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) throw new PaymentsNotConfigured();
  // Short timeout: if Stripe is slow the customer gets a clear retry message instead of a frozen page.
  client ??= new Stripe(key, { timeout: 12_000, maxNetworkRetries: 1 });
  return client;
}
export const paymentsConfigured = () => Boolean(process.env.STRIPE_SECRET_KEY);

type Session = Pick<Stripe.Checkout.Session, "id" | "payment_status" | "metadata" | "amount_total" | "currency" | "payment_intent">;

/** Reads a paid Checkout Session into the facts we store, or null if it is not a completed payment of ours. */
export function paidSessionFacts(session: Session): { orderId: string; sessionId: string; paymentIntent: string | null; amountCents: number } | null {
  const orderId = session.metadata?.order_id;
  if (session.payment_status !== "paid" || !isOrderId(orderId)) return null;
  if (session.currency !== CURRENCY || typeof session.amount_total !== "number" || session.amount_total <= 0) return null;
  const intent = session.payment_intent;
  return {
    orderId,
    sessionId: session.id,
    paymentIntent: typeof intent === "string" ? intent : (intent?.id ?? null),
    amountCents: session.amount_total,
  };
}

/** Records the payment behind a session if Stripe says it is paid. Safe to repeat. */
export async function recordIfPaid(session: Session): Promise<string | null> {
  const facts = paidSessionFacts(session);
  if (!facts) return null;
  const result = await markPaid(facts.orderId, facts);
  if (result === "duplicate" || result === "missing") {
    console.error(`Stripe session ${facts.sessionId} for order ${facts.orderId}: ${result}. Needs a manual check.`);
  }
  return facts.orderId;
}

/** Asks Stripe about a session id and records it if paid. Returns the order id it belongs to. */
export async function reconcileSession(sessionId: string): Promise<string | null> {
  if (!/^cs_[A-Za-z0-9_]{10,200}$/.test(sessionId)) return null;
  const session = await getStripe().checkout.sessions.retrieve(sessionId);
  return recordIfPaid(session);
}

/**
 * Returns a Stripe Checkout link for an order. If the order already has an
 * open session it is reused, and if that session turns out to be paid the
 * payment is recorded instead, so a customer cannot be sent to pay twice.
 */
export async function checkoutUrl(order: Order, baseUrl: string): Promise<{ url: string } | { paid: true } | { error: string }> {
  if (!canPay(order)) return { error: "This order cannot be paid right now." };
  const stripe = getStripe();

  if (order.stripeSessionId) {
    const existing = await stripe.checkout.sessions.retrieve(order.stripeSessionId);
    if (existing.payment_status === "paid") {
      await recordIfPaid(existing);
      return { paid: true };
    }
    if (existing.status === "open" && existing.url && existing.amount_total === order.amountCents) return { url: existing.url };
    if (existing.status === "open") await stripe.checkout.sessions.expire(existing.id);
  }

  const session = await stripe.checkout.sessions.create({
    mode: "payment",
    customer_email: order.email,
    client_reference_id: order.id,
    metadata: { order_id: order.id },
    payment_intent_data: { metadata: { order_id: order.id }, description: `${SITE_NAME}: ${order.serviceName}` },
    line_items: [
      {
        quantity: 1,
        price_data: {
          currency: CURRENCY,
          unit_amount: order.amountCents!,
          product_data: { name: `${order.serviceName} order` },
        },
      },
    ],
    success_url: `${baseUrl}/api/checkout/return?session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${baseUrl}/order/${order.id}`,
  });
  if (!session.url) return { error: "Stripe did not return a payment link. Please try again." };
  await setStripeSession(order.id, session.id);
  return { url: session.url };
}

/** Before the owner changes a quote: make sure no old payment link can still be paid. */
export async function retireOpenSession(orderId: string): Promise<"ok" | "paid"> {
  const order = await getOrder(orderId);
  if (!order?.stripeSessionId || !paymentsConfigured()) return "ok";
  const stripe = getStripe();
  const existing = await stripe.checkout.sessions.retrieve(order.stripeSessionId);
  if (existing.payment_status === "paid") {
    await recordIfPaid(existing);
    return "paid";
  }
  if (existing.status === "open") await stripe.checkout.sessions.expire(existing.id);
  return "ok";
}
