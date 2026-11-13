import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";
import { adminCancel, adminClearAlert, adminLogout, adminSetProgress, adminSetQuote, isAdmin } from "@/app/actions";
import { DatabaseNotConfigured } from "@/lib/db";
import { formatDateTime, formatMoney } from "@/lib/money";
import { listOrders, STATUS_LABEL, WORK_STATUSES, type Order } from "@/lib/orders";
import { paymentsConfigured } from "@/lib/payments";

export const metadata: Metadata = { title: "Orders", robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ msg?: string }> };

export default function AdminPage(props: Props) {
  return (
    <Suspense fallback={<div className="mt-10 h-96 animate-pulse rounded-3xl bg-surface" />}>
      <AdminView {...props} />
    </Suspense>
  );
}

const input = "h-11 w-full rounded-xl border border-line bg-bg px-3 text-sm outline-none focus:border-accent";
const button = "rounded-full bg-accent px-5 py-2.5 text-sm font-bold text-accent-ink transition hover:brightness-110";

const NEEDS_YOU: Order["status"][] = ["quote_requested", "received", "in_progress", "draft_ready"];

function OrderCard({ order }: { order: Order }) {
  const paid = order.paidAt !== null;
  const open = NEEDS_YOU.includes(order.status) || order.paymentAlert !== null;
  const canQuote = !paid && (order.status === "quote_requested" || order.status === "quote_ready");
  return (
    <details id={`o-${order.id}`} open={open} className="scroll-mt-24 rounded-3xl border border-line bg-surface">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-4 gap-y-1 p-5">
        <span className={`rounded-full px-3 py-1 text-xs font-bold ${order.status === "cancelled" ? "bg-surface-2 text-muted" : paid ? "bg-good/15 text-good" : "bg-warn/15 text-warn"}`}>
          {STATUS_LABEL[order.status]}
        </span>
        <span className="font-bold">{order.serviceName}</span>
        <span className="text-sm text-muted">{order.name} · {order.email}</span>
        <span className="ml-auto font-display text-lg font-extrabold tabular-nums">{order.amountCents === null ? "No price yet" : formatMoney(order.amountCents)}</span>
        <span className="w-full text-xs text-muted">{formatDateTime(order.createdAt)}{paid ? ` · paid ${formatDateTime(order.paidAt!)}` : " · not paid"}</span>
      </summary>

      <div className="space-y-5 border-t border-line p-5">
        {order.paymentAlert && (
          <form action={adminClearAlert} className="flex flex-wrap items-center gap-3 rounded-2xl border border-accent/50 bg-accent-soft p-4">
            <input type="hidden" name="id" value={order.id} />
            <p className="min-w-0 flex-1 break-words font-semibold text-accent">Payment needs a look: {order.paymentAlert}</p>
            <button className="rounded-full border border-accent px-4 py-2 text-sm font-bold text-accent">I handled it</button>
          </form>
        )}

        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          {order.lines.map((line) => (
            <div key={line.label} className={line.value.length > 80 ? "sm:col-span-2" : ""}>
              <dt className="text-xs font-semibold text-muted">{line.label}</dt>
              <dd className="mt-0.5 whitespace-pre-wrap break-words">{line.value}</dd>
            </div>
          ))}
        </dl>
        <p className="text-sm">
          <Link href={`/order/${order.id}`} className="font-semibold text-accent hover:underline">Open the customer order page</Link>
          {order.stripePaymentIntent && <span className="text-muted"> · Stripe payment <code className="break-all">{order.stripePaymentIntent}</code></span>}
        </p>

        {canQuote && (
          <form action={adminSetQuote} className="grid gap-3 rounded-2xl bg-surface-2 p-4 sm:grid-cols-[9rem_1fr_auto] sm:items-end">
            <input type="hidden" name="id" value={order.id} />
            <label className="block text-sm font-semibold">Price in USD
              <input name="price" inputMode="decimal" required placeholder="80" defaultValue={order.amountCents ? order.amountCents / 100 : ""} className={`${input} mt-1`} />
            </label>
            <label className="block text-sm font-semibold">Note to the customer (optional)
              <input name="note" maxLength={1000} defaultValue={order.customerNote ?? ""} placeholder="What the price covers" className={`${input} mt-1`} />
            </label>
            <button className={button}>{order.status === "quote_ready" ? "Change quote" : "Send quote"}</button>
          </form>
        )}

        {paid && order.status !== "cancelled" && (
          <form action={adminSetProgress} className="grid gap-3 rounded-2xl bg-surface-2 p-4 sm:grid-cols-2 sm:items-end">
            <input type="hidden" name="id" value={order.id} />
            <label className="block text-sm font-semibold">Status
              <select name="status" defaultValue={order.status} className={`${input} mt-1`}>
                {WORK_STATUSES.map((status) => <option key={status} value={status}>{STATUS_LABEL[status]}</option>)}
              </select>
            </label>
            <label className="block text-sm font-semibold">Delivery link (https)
              <input name="deliveryUrl" type="url" maxLength={500} defaultValue={order.deliveryUrl ?? ""} placeholder="https://" className={`${input} mt-1`} />
            </label>
            <label className="block text-sm font-semibold sm:col-span-2">Message shown on the customer order page
              <textarea name="note" maxLength={1000} rows={2} defaultValue={order.customerNote ?? ""} className={`${input} mt-1 h-auto py-2`} />
            </label>
            <div><button className={button}>Save</button></div>
          </form>
        )}

        {order.status !== "cancelled" && (
          <details className="text-sm">
            <summary className="cursor-pointer font-semibold text-muted hover:text-text">Cancel this order</summary>
            <form action={adminCancel} className="mt-3 flex flex-wrap items-end gap-3">
              <input type="hidden" name="id" value={order.id} />
              <label className="block min-w-0 flex-1 font-semibold">Reason shown to the customer (optional)
                <input name="note" maxLength={1000} className={`${input} mt-1`} />
              </label>
              <button className="rounded-full border border-accent px-5 py-2.5 font-bold text-accent">Cancel order</button>
            </form>
            {paid && <p className="mt-2 text-muted">Cancelling does not move money. Refund the payment in your Stripe dashboard.</p>}
          </details>
        )}
      </div>
    </details>
  );
}

async function AdminView({ searchParams }: Props) {
  // Orders are live data: always render per request, never at build time.
  await connection();
  if (!(await isAdmin())) redirect("/admin/login");
  const { msg } = await searchParams;

  let orders: Order[];
  try {
    orders = await listOrders();
  } catch (error) {
    if (!(error instanceof DatabaseNotConfigured)) console.error("admin page failed", error);
    return (
      <div className="mx-auto max-w-xl pt-16">
        <h1 className="text-3xl font-extrabold">The database is not connected</h1>
        <p className="mt-2 text-muted">Add a Postgres database to the project so DATABASE_URL is set, then reload. See the README.</p>
      </div>
    );
  }

  const waiting = orders.filter((o) => NEEDS_YOU.includes(o.status) || o.paymentAlert).length;
  const earned = orders.filter((o) => o.paidAt && o.status !== "cancelled").reduce((sum, o) => sum + (o.amountCents ?? 0), 0);

  return (
    <div className="pt-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl font-extrabold sm:text-4xl">Orders</h1>
        <form action={adminLogout}><button className="rounded-full border border-line px-4 py-2 text-sm font-semibold text-muted hover:text-text">Log out</button></form>
      </div>
      <p className="mt-2 text-muted">
        {orders.length} orders · <span className="font-semibold text-text">{waiting} need you</span> · {formatMoney(earned)} paid on orders not cancelled
      </p>
      {!paymentsConfigured() && <p className="mt-4 rounded-2xl border border-warn/50 bg-warn/10 p-4 font-semibold text-warn">Stripe is not connected (STRIPE_SECRET_KEY is missing), so customers cannot pay yet.</p>}
      {msg && <p role="status" className="mt-4 rounded-2xl border border-line bg-surface p-4 font-semibold">{msg}</p>}
      <div className="mt-6 space-y-3">
        {orders.length === 0 ? <p className="rounded-3xl border border-dashed border-line p-10 text-center text-muted">No orders yet.</p> : orders.map((order) => <OrderCard key={order.id} order={order} />)}
      </div>
    </div>
  );
}
