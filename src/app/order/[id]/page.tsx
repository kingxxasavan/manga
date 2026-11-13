import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";
import { payOrder } from "@/app/actions";
import { Check, Lock } from "@/components/icons";
import { DatabaseNotConfigured } from "@/lib/db";
import { formatDateTime, formatMoney } from "@/lib/money";
import { canPay, getOrder, STATUS_LABEL, WORK_STATUSES, type Order } from "@/lib/orders";
import { paymentsConfigured } from "@/lib/payments";
import { SUPPORT_EMAIL } from "@/lib/site";

// The link is the key to the order: keep it out of search engines and out of referrer headers.
export const metadata: Metadata = { title: "Your order", robots: { index: false, follow: false }, referrer: "no-referrer" };

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ pay?: string }> };

export default function OrderPage(props: Props) {
  return (
    <Suspense fallback={<div className="mt-10 h-96 animate-pulse rounded-3xl bg-surface" />}>
      <OrderView {...props} />
    </Suspense>
  );
}

function Headline({ order }: { order: Order }) {
  const map: Record<Order["status"], [string, string]> = {
    quote_requested: ["We got your request", "We are working out a price. It will appear on this page, so keep this link and check back."],
    quote_ready: ["Your quote is ready", "Happy with the price? Pay below and we get started."],
    awaiting_payment: ["Almost there", "Your order is saved. Pay below and we get started."],
    received: ["Payment received, thank you", "Your order is in the queue. This page updates as we work on it."],
    in_progress: ["We are working on it", "Your order is being made right now."],
    draft_ready: ["Your draft is ready", "Take a look and tell us what to change."],
    done: ["All done", "Your order is finished. Thank you for building with us."],
    cancelled: ["This order was cancelled", "If you paid for it, the refund goes back to your original payment method."],
  };
  const [title, body] = map[order.status];
  return (
    <>
      <h1 className="text-3xl font-extrabold sm:text-4xl">{title}</h1>
      <p className="mt-2 text-muted">{body}</p>
    </>
  );
}

async function OrderView({ params, searchParams }: Props) {
  // Orders are live data: always render per request, never at build time.
  await connection();
  const [{ id }, { pay }] = await Promise.all([params, searchParams]);
  let order: Order | null;
  try {
    order = await getOrder(id);
  } catch (error) {
    if (!(error instanceof DatabaseNotConfigured)) console.error("order page failed", error);
    return (
      <div className="mx-auto max-w-xl pt-16 text-center">
        <h1 className="text-3xl font-extrabold">Orders are not available right now</h1>
        <p className="mt-2 text-muted">Please try again in a few minutes. Your order and any payment are safe.</p>
      </div>
    );
  }
  if (!order) notFound();

  const payable = canPay(order);
  const step = WORK_STATUSES.indexOf(order.status as (typeof WORK_STATUSES)[number]);

  return (
    <div className="rise mx-auto max-w-3xl pt-10">
      <p className="text-xs font-bold uppercase tracking-[0.18em] text-accent">{order.serviceName} · {STATUS_LABEL[order.status]}</p>
      <div className="mt-2"><Headline order={order} /></div>

      {order.paidAt && order.status !== "cancelled" && (
        <ol className="mt-8 grid grid-cols-4 gap-2" aria-label="Order progress">
          {WORK_STATUSES.map((status, i) => {
            const reached = i <= step;
            return (
              <li key={status} aria-current={i === step ? "step" : undefined}>
                <span className="block h-2 overflow-hidden rounded-full bg-surface-2">
                  {reached && <span className="fill-x block h-full rounded-full bg-good" style={{ "--delay": `${i * 220}ms` } as React.CSSProperties} />}
                </span>
                <span className={`mt-2 flex items-center gap-1.5 text-xs font-bold sm:text-sm ${reached ? "text-text" : "text-muted"}`}>
                  {i === step && order.status !== "done" ? <span className="live-dot shrink-0" /> : reached && <Check width={14} height={14} className="shrink-0 text-good" strokeWidth={3} />}
                  {STATUS_LABEL[status]}
                </span>
              </li>
            );
          })}
        </ol>
      )}

      {order.customerNote && (
        <section className="mt-8 rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
          <h2 className="text-sm font-bold uppercase tracking-widest text-muted">Message from us</h2>
          <p className="mt-2 whitespace-pre-wrap break-words leading-relaxed">{order.customerNote}</p>
        </section>
      )}

      {order.deliveryUrl && order.paidAt && order.status !== "cancelled" && (
        <a href={order.deliveryUrl} target="_blank" rel="noreferrer noopener" className="group mt-6 flex items-center justify-between gap-4 rounded-3xl bg-accent p-5 font-bold text-accent-ink shadow-card transition-[filter,transform] duration-200 ease-out-strong hover:brightness-110 active:scale-[0.99] sm:p-6">
          <span>
            <span className="block text-lg">{order.status === "done" ? "Open your finished work" : "Open your draft"}</span>
            <span className="block break-all text-sm font-medium opacity-85">{order.deliveryUrl}</span>
          </span>
          <span aria-hidden="true" className="text-2xl">↗</span>
        </a>
      )}

      {payable && (
        <section className="mt-8 rounded-3xl border border-accent/50 bg-accent-soft p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p>
              <span className="block text-xs font-bold uppercase tracking-widest text-muted">Total</span>
              <span className="font-display text-4xl font-extrabold tabular-nums">{formatMoney(order.amountCents!)}</span>
            </p>
            {paymentsConfigured() ? (
              <form action={payOrder}>
                <input type="hidden" name="id" value={order.id} />
                <button className="btn btn-primary px-7 py-3.5">
                  <Lock width={16} height={16} /> Pay securely
                </button>
              </form>
            ) : (
              <p className="max-w-xs text-sm font-semibold text-warn">Online payment is not switched on yet. Your order is saved, please check back soon.</p>
            )}
          </div>
          {pay === "error" && <p role="alert" className="mt-4 font-semibold text-danger">We could not open the payment page. You were not charged. Please try again.</p>}
        </section>
      )}

      <section className="mt-8">
        <h2 className="text-xl font-bold">What you ordered</h2>
        <dl className="mt-3 divide-y divide-line rounded-3xl border border-line bg-surface">
          {order.lines.map((line) => (
            <div key={line.label} className="flex items-start gap-4 px-5 py-3.5">
              <div className="min-w-0 flex-1">
                <dt className="text-xs font-semibold text-muted">{line.label}</dt>
                <dd className="mt-0.5 whitespace-pre-wrap break-words font-medium">{line.value}</dd>
              </div>
              {(line.amount > 0 || line.multiplier) && (
                <span className="shrink-0 text-sm font-bold text-muted">
                  {line.multiplier ? `+${Math.round((line.multiplier - 1) * 100)}%` : formatMoney(line.amount)}
                </span>
              )}
            </div>
          ))}
          {order.amountCents !== null && (
            <div className="flex items-center justify-between gap-4 px-5 py-4">
              <dt className="font-bold">{order.paidAt ? "Paid" : "Total"}</dt>
              <dd className="font-display text-2xl font-extrabold tabular-nums">{formatMoney(order.amountCents)}</dd>
            </div>
          )}
        </dl>
      </section>

      <p className="mt-6 text-sm text-muted">
        Ordered {formatDateTime(order.createdAt)}{order.paidAt ? ` · paid ${formatDateTime(order.paidAt)}` : ""}.
        {" "}This page is your private order link. Bookmark it, and do not share it publicly.
        {SUPPORT_EMAIL && <> Need help? <a className="font-semibold text-accent hover:underline" href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>.</>}
      </p>
      <p className="mt-4"><Link href="/" className="text-sm font-semibold text-accent hover:underline">Back to home</Link></p>
    </div>
  );
}
