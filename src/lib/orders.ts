import "server-only";
import { randomBytes } from "node:crypto";
import { query } from "./db";
import type { Answers, Estimate, Line } from "./pricing";
import { MAX_ORDER_CENTS, MIN_ORDER_CENTS } from "./site";

export const STATUSES = [
  "quote_requested", "quote_ready", "awaiting_payment", "received", "in_progress", "draft_ready", "done", "cancelled",
] as const;
export type OrderStatus = (typeof STATUSES)[number];

/** The steps a paid order moves through, in order. */
export const WORK_STATUSES = ["received", "in_progress", "draft_ready", "done"] as const satisfies readonly OrderStatus[];
export type WorkStatus = (typeof WORK_STATUSES)[number];

export const STATUS_LABEL: Record<OrderStatus, string> = {
  quote_requested: "Confirming your price",
  quote_ready: "Price ready",
  awaiting_payment: "Waiting for payment",
  received: "Received",
  in_progress: "In progress",
  draft_ready: "Draft ready",
  done: "Done",
  cancelled: "Cancelled",
};

export interface Order {
  id: string;
  createdAt: string;
  updatedAt: string;
  serviceId: string;
  serviceName: string;
  email: string;
  name: string;
  answers: Answers;
  lines: Line[];
  /** The range the customer was shown after the questions, if one could be given */
  estimate: Estimate | null;
  /** The final price, set by the owner. null until then. */
  amountCents: number | null;
  status: OrderStatus;
  paidAt: string | null;
  stripeSessionId: string | null;
  stripePaymentIntent: string | null;
  customerNote: string | null;
  deliveryUrl: string | null;
  paymentAlert: string | null;
}

const iso = (value: unknown): string => new Date(value as string | Date).toISOString();
const json = <T>(value: unknown): T => (typeof value === "string" ? JSON.parse(value) : value) as T;

function toOrder(row: Record<string, unknown>): Order {
  return {
    id: row.id as string,
    createdAt: iso(row.created_at),
    updatedAt: iso(row.updated_at),
    serviceId: row.service_id as string,
    serviceName: row.service_name as string,
    email: row.email as string,
    name: row.name as string,
    answers: json<Answers>(row.answers),
    lines: json<Line[]>(row.lines),
    estimate:
      typeof row.estimate_low_cents === "number" && typeof row.estimate_high_cents === "number"
        ? { low: row.estimate_low_cents, high: row.estimate_high_cents }
        : null,
    amountCents: (row.amount_cents as number | null) ?? null,
    status: row.status as OrderStatus,
    paidAt: row.paid_at ? iso(row.paid_at) : null,
    stripeSessionId: (row.stripe_session_id as string | null) ?? null,
    stripePaymentIntent: (row.stripe_payment_intent as string | null) ?? null,
    customerNote: (row.customer_note as string | null) ?? null,
    deliveryUrl: (row.delivery_url as string | null) ?? null,
    paymentAlert: (row.payment_alert as string | null) ?? null,
  };
}

/** Order ids double as the private link to the order, so they are long and random. */
export function newOrderId(): string {
  return randomBytes(16).toString("base64url");
}
export const isOrderId = (id: unknown): id is string => typeof id === "string" && /^[A-Za-z0-9_-]{22}$/.test(id);

export const isPayableAmount = (cents: unknown): cents is number =>
  typeof cents === "number" && Number.isInteger(cents) && cents >= MIN_ORDER_CENTS && cents <= MAX_ORDER_CENTS;

export interface NewOrder {
  serviceId: string;
  serviceName: string;
  email: string;
  name: string;
  answers: Answers;
  lines: Line[];
  /** The range shown to the customer, or null when none could be given */
  estimate?: Estimate | null;
  /** null when the owner still has to set the final price (the normal case) */
  amountCents: number | null;
}

export async function createOrder(input: NewOrder): Promise<Order> {
  if (input.amountCents !== null && !isPayableAmount(input.amountCents)) throw new Error("Amount is outside the allowed range");
  const estimate = input.estimate ?? null;
  if (estimate && !(isPayableAmount(estimate.low) && isPayableAmount(estimate.high) && estimate.low < estimate.high)) {
    throw new Error("Estimate is outside the allowed range");
  }
  const rows = await query(
    `INSERT INTO orders (id, service_id, service_name, email, name, answers, lines, amount_cents, status, estimate_low_cents, estimate_high_cents)
     VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10, $11) RETURNING *`,
    [
      newOrderId(), input.serviceId, input.serviceName, input.email, input.name,
      JSON.stringify(input.answers), JSON.stringify(input.lines), input.amountCents,
      input.amountCents === null ? "quote_requested" : "awaiting_payment",
      estimate?.low ?? null, estimate?.high ?? null,
    ],
  );
  return toOrder(rows[0]);
}

export async function getOrder(id: unknown): Promise<Order | null> {
  if (!isOrderId(id)) return null;
  const rows = await query("SELECT * FROM orders WHERE id = $1", [id]);
  return rows[0] ? toOrder(rows[0]) : null;
}

export async function listOrders(limit = 200): Promise<Order[]> {
  const rows = await query("SELECT * FROM orders ORDER BY created_at DESC LIMIT $1", [limit]);
  return rows.map(toOrder);
}

/** An order can be paid when it has a valid price, is waiting for money and has not been paid. */
export function canPay(order: Order): boolean {
  return order.paidAt === null && (order.status === "awaiting_payment" || order.status === "quote_ready") && isPayableAmount(order.amountCents);
}

export async function setStripeSession(id: string, sessionId: string | null): Promise<void> {
  await query("UPDATE orders SET stripe_session_id = $2, updated_at = now() WHERE id = $1 AND paid_at IS NULL", [id, sessionId]);
}

export interface Payment {
  sessionId: string;
  paymentIntent: string | null;
  amountCents: number;
}

/**
 * Records a confirmed payment. Safe to call any number of times for the same
 * payment (the webhook and the return page both call it): only the first call
 * changes anything. A second, different payment for an order that is already
 * paid is flagged for the owner so it can be refunded.
 */
export async function markPaid(id: string, payment: Payment): Promise<"marked" | "already" | "duplicate" | "missing"> {
  const rows = await query(
    `UPDATE orders
        SET status = 'received', paid_at = now(), updated_at = now(), amount_cents = $4,
            stripe_session_id = $2, stripe_payment_intent = $3,
            payment_alert = CASE WHEN amount_cents IS DISTINCT FROM $4
              THEN 'Paid amount differs from the listed price. Check this payment in Stripe.' ELSE payment_alert END
      WHERE id = $1 AND paid_at IS NULL AND status <> 'cancelled'
      RETURNING id`,
    [id, payment.sessionId, payment.paymentIntent, payment.amountCents],
  );
  if (rows.length > 0) return "marked";

  const order = await getOrder(id);
  if (!order) return "missing";
  if (order.stripeSessionId === payment.sessionId && order.paidAt) return "already";
  const why = order.paidAt ? "A second payment arrived for this order" : "A payment arrived after this order was cancelled";
  await query("UPDATE orders SET payment_alert = $2, updated_at = now() WHERE id = $1", [
    id, `${why} (session ${payment.sessionId}). Refund it in Stripe.`,
  ]);
  return "duplicate";
}

/** Owner confirms or changes the final price of a request that has not been paid. */
export async function setQuote(id: string, amountCents: number, note: string | null): Promise<boolean> {
  if (!isPayableAmount(amountCents)) return false;
  const rows = await query(
    `UPDATE orders SET amount_cents = $2, customer_note = $3, status = 'quote_ready', stripe_session_id = NULL, updated_at = now()
      WHERE id = $1 AND paid_at IS NULL AND status IN ('quote_requested', 'quote_ready') RETURNING id`,
    [id, amountCents, note],
  );
  return rows.length > 0;
}

/** Owner moves a paid order along and can leave a note and a delivery link. */
export async function setProgress(id: string, status: WorkStatus, note: string | null, deliveryUrl: string | null): Promise<boolean> {
  if (!WORK_STATUSES.includes(status)) return false;
  const rows = await query(
    `UPDATE orders SET status = $2, customer_note = $3, delivery_url = $4, updated_at = now()
      WHERE id = $1 AND paid_at IS NOT NULL AND status <> 'cancelled' RETURNING id`,
    [id, status, note, deliveryUrl],
  );
  return rows.length > 0;
}

export async function cancelOrder(id: string, note: string | null): Promise<boolean> {
  const rows = await query(
    `UPDATE orders SET status = 'cancelled', customer_note = COALESCE($2, customer_note), updated_at = now()
      WHERE id = $1 AND status <> 'cancelled' RETURNING id`,
    [id, note],
  );
  return rows.length > 0;
}

export async function clearPaymentAlert(id: string): Promise<void> {
  await query("UPDATE orders SET payment_alert = NULL, updated_at = now() WHERE id = $1", [id]);
}
