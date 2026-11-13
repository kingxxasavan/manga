import { beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import {
  cancelOrder, canPay, createOrder, getOrder, isOrderId, listOrders, markPaid, setProgress, setQuote, type NewOrder,
} from "@/lib/orders";
import { paidSessionFacts } from "@/lib/payments";

const input = (amountCents: number | null): NewOrder => ({
  serviceId: "website", serviceName: "Website", email: "a@b.co", name: "Ada",
  answers: { type: "landing", pages: 1, features: ["form"] },
  lines: [{ label: "What kind of website?", value: "One page", amount: 149_00 }],
  amountCents,
});
const pay = (sessionId: string, amountCents = 149_00) => ({ sessionId, paymentIntent: "pi_1", amountCents });

beforeAll(async () => {
  await listOrders(1); // boots the in memory database and creates the table
}, 30_000);

describe("orders", () => {
  it("creates a priced order waiting for payment and reads it back intact", async () => {
    const order = await createOrder(input(149_00));
    expect(isOrderId(order.id)).toBe(true);
    expect(order).toMatchObject({ status: "awaiting_payment", amountCents: 149_00, paidAt: null, email: "a@b.co", estimate: null });
    const again = await getOrder(order.id);
    expect(again).toEqual(order);
    expect(again!.answers).toEqual({ type: "landing", pages: 1, features: ["form"] });
    expect(canPay(order)).toBe(true);
  });

  it("stores the estimate the customer was shown, and refuses a broken one", async () => {
    const order = await createOrder({ ...input(null), estimate: { low: 250_00, high: 345_00 } });
    expect(order).toMatchObject({ status: "quote_requested", amountCents: null, estimate: { low: 250_00, high: 345_00 } });
    expect((await getOrder(order.id))!.estimate).toEqual({ low: 250_00, high: 345_00 });
    expect((await createOrder(input(null))).estimate).toBeNull();
    await expect(createOrder({ ...input(null), estimate: { low: 345_00, high: 250_00 } })).rejects.toThrow();
    await expect(createOrder({ ...input(null), estimate: { low: 100_00, high: 9000_00 } })).rejects.toThrow();
    await expect(createOrder({ ...input(null), estimate: { low: 1, high: 10_00 } })).rejects.toThrow();
  });

  it("keeps the estimate when the owner sets a different final price", async () => {
    const order = await createOrder({ ...input(null), estimate: { low: 250_00, high: 345_00 } });
    expect(await setQuote(order.id, 400_00, "Bigger than it looked.")).toBe(true);
    expect(await getOrder(order.id)).toMatchObject({ amountCents: 400_00, status: "quote_ready", estimate: { low: 250_00, high: 345_00 } });
  });

  it("refuses amounts outside 5 to 2000 dollars", async () => {
    await expect(createOrder(input(4_99))).rejects.toThrow();
    await expect(createOrder(input(2000_01))).rejects.toThrow();
    await expect(createOrder(input(10.5))).rejects.toThrow();
    expect((await createOrder(input(2000_00))).amountCents).toBe(2000_00);
  });

  it("rejects malformed ids without touching the database", async () => {
    for (const bad of ["", "abc", "x' OR '1'='1", null, 42, "a".repeat(23)]) expect(await getOrder(bad)).toBeNull();
  });

  it("marks an order paid exactly once", async () => {
    const order = await createOrder(input(149_00));
    expect(await markPaid(order.id, pay("cs_test_aaaaaaaaaa"))).toBe("marked");
    expect(await markPaid(order.id, pay("cs_test_aaaaaaaaaa"))).toBe("already");
    const paid = (await getOrder(order.id))!;
    expect(paid).toMatchObject({ status: "received", stripeSessionId: "cs_test_aaaaaaaaaa", paymentAlert: null });
    expect(paid.paidAt).not.toBeNull();
    expect(canPay(paid)).toBe(false);
  });

  it("flags a second, different payment instead of losing it", async () => {
    const order = await createOrder(input(149_00));
    await markPaid(order.id, pay("cs_test_first00000"));
    expect(await markPaid(order.id, pay("cs_test_second0000"))).toBe("duplicate");
    const after = (await getOrder(order.id))!;
    expect(after.stripeSessionId).toBe("cs_test_first00000");
    expect(after.paymentAlert).toContain("cs_test_second0000");
  });

  it("flags a payment whose amount differs from the listed price and stores what was really paid", async () => {
    const order = await createOrder(input(149_00));
    await markPaid(order.id, pay("cs_test_mismatch00", 99_00));
    const after = (await getOrder(order.id))!;
    expect(after.amountCents).toBe(99_00);
    expect(after.paymentAlert).toContain("differs");
  });

  it("flags a payment that arrives after cancellation", async () => {
    const order = await createOrder(input(149_00));
    await cancelOrder(order.id, null);
    expect(await markPaid(order.id, pay("cs_test_late000000"))).toBe("duplicate");
    const after = (await getOrder(order.id))!;
    expect(after.status).toBe("cancelled");
    expect(after.paymentAlert).toContain("cancelled");
  });

  it("reports a payment for an order that does not exist", async () => {
    expect(await markPaid("AAAAAAAAAAAAAAAAAAAAAA", pay("cs_test_ghost00000"))).toBe("missing");
  });

  it("walks a quote request through pricing and payment", async () => {
    const order = await createOrder(input(null));
    expect(order).toMatchObject({ status: "quote_requested", amountCents: null });
    expect(canPay(order)).toBe(false);
    expect(await setQuote(order.id, 3000_00, null)).toBe(false);
    expect(await setQuote(order.id, 1_00, null)).toBe(false);
    expect(await setQuote(order.id, 80_00, "Includes two drafts.")).toBe(true);
    const quoted = (await getOrder(order.id))!;
    expect(quoted).toMatchObject({ status: "quote_ready", amountCents: 80_00, customerNote: "Includes two drafts." });
    expect(canPay(quoted)).toBe(true);
    await markPaid(order.id, pay("cs_test_quote00000", 80_00));
    expect(await setQuote(order.id, 5_00, null)).toBe(false); // price is locked once paid
    expect((await getOrder(order.id))!.amountCents).toBe(80_00);
  });

  it("only lets paid orders move through the work steps", async () => {
    const order = await createOrder(input(149_00));
    expect(await setProgress(order.id, "in_progress", null, null)).toBe(false);
    await markPaid(order.id, pay("cs_test_progress00"));
    expect(await setProgress(order.id, "bogus" as never, null, null)).toBe(false);
    expect(await setProgress(order.id, "done", "All yours.", "https://example.com/file.zip")).toBe(true);
    expect(await getOrder(order.id)).toMatchObject({ status: "done", customerNote: "All yours.", deliveryUrl: "https://example.com/file.zip" });
    await cancelOrder(order.id, null);
    expect(await setProgress(order.id, "in_progress", null, null)).toBe(false);
  });

  it("lists newest first", async () => {
    const a = await createOrder(input(149_00));
    const list = await listOrders(3);
    expect(list.length).toBe(3);
    expect(list.some((o) => o.id === a.id)).toBe(true);
    expect(list[0].createdAt >= list[2].createdAt).toBe(true);
  });
});

describe("paidSessionFacts", () => {
  const session = (over: object = {}) => ({
    id: "cs_test_abcdefghij", payment_status: "paid" as const, metadata: { order_id: "AAAAAAAAAAAAAAAAAAAAAA" },
    amount_total: 149_00, currency: "usd", payment_intent: "pi_123", ...over,
  });
  it("reads a paid session", () => {
    expect(paidSessionFacts(session())).toEqual({
      orderId: "AAAAAAAAAAAAAAAAAAAAAA", sessionId: "cs_test_abcdefghij", paymentIntent: "pi_123", amountCents: 149_00,
    });
  });
  it("ignores sessions that are unpaid, foreign or malformed", () => {
    expect(paidSessionFacts(session({ payment_status: "unpaid" }))).toBeNull();
    expect(paidSessionFacts(session({ payment_status: "no_payment_required" }))).toBeNull();
    expect(paidSessionFacts(session({ metadata: {} }))).toBeNull();
    expect(paidSessionFacts(session({ metadata: { order_id: "nope" } }))).toBeNull();
    expect(paidSessionFacts(session({ currency: "eur" }))).toBeNull();
    expect(paidSessionFacts(session({ amount_total: 0 }))).toBeNull();
    expect(paidSessionFacts(session({ amount_total: null }))).toBeNull();
  });
});
