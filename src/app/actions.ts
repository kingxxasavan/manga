"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import {
  ADMIN_COOKIE, adminPassword, createSessionToken, isValidSessionToken, passwordMatches, SESSION_SECONDS,
} from "@/lib/admin-auth";
import {
  cancelOrder, clearPaymentAlert, createOrder, getOrder, isOrderId, isPayableAmount, setProgress, setQuote, WORK_STATUSES, type WorkStatus,
} from "@/lib/orders";
import { checkoutUrl, paymentsConfigured, retireOpenSession } from "@/lib/payments";
import { checkEmail, quote } from "@/lib/pricing";
import { allow, getBaseUrl, getClientIp } from "@/lib/request";
import { getService } from "@/lib/services";

// Server actions can be called directly by anyone, so every input is treated as hostile.

export type SubmitResult = { ok: true; url: string } | { ok: false; errors: Record<string, string>; message?: string };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export async function submitOrder(serviceId: unknown, answers: unknown, contact: unknown): Promise<SubmitResult> {
  const service = typeof serviceId === "string" ? getService(serviceId) : undefined;
  if (!service || !isRecord(answers) || !isRecord(contact)) {
    return { ok: false, errors: {}, message: "Something was missing. Please reload the page and try again." };
  }
  // Hidden field real people never fill in. Bots do.
  if (contact.website) return { ok: true, url: "/" };

  if (!allow(`order:${await getClientIp()}`, 8, 10 * 60_000)) {
    return { ok: false, errors: {}, message: "Too many requests from this connection. Please wait a few minutes." };
  }

  const errors: Record<string, string> = {};
  const email = checkEmail(contact.email);
  if (!email) errors.email = "Enter a valid email address.";
  const name = typeof contact.name === "string" ? contact.name.trim() : "";
  if (name.length < 1 || name.length > 80) errors.name = "Enter your name.";

  // The estimate is worked out here from the answers. No number sent by the browser is used.
  const result = quote(service, answers);
  if (!result.ok) Object.assign(errors, result.errors);
  if (!result.ok || !email || Object.keys(errors).length > 0) return { ok: false, errors };

  // A flat price (the surprise option) is known from the config alone, so it
  // can be paid right away. Everything else is saved as a request: the owner
  // confirms a final price first, and only then can it be paid.
  const flat = result.quote.reason === "fixed" ? result.quote.fixedPrice ?? null : null;
  if (flat !== null && !isPayableAmount(flat)) {
    return { ok: false, errors: {}, message: "This option is not available right now. Please pick another." };
  }

  let order;
  try {
    order = await createOrder({
      serviceId: service.id,
      serviceName: service.name,
      email,
      name,
      answers: result.answers,
      lines: result.quote.lines,
      estimate: result.quote.estimate,
      amountCents: flat,
    });
  } catch (error) {
    console.error("submitOrder could not save the request", error);
    return { ok: false, errors: {}, message: "We could not save your request. Nothing was charged. Please try again in a moment." };
  }

  // The order is saved from here on. If Stripe is slow or down, the customer
  // still lands on their order page, which has its own Pay button, rather than
  // being told to start over and ending up with two orders.
  if (order.amountCents !== null && paymentsConfigured()) {
    try {
      const pay = await checkoutUrl(order, await getBaseUrl());
      if ("url" in pay) return { ok: true, url: pay.url };
    } catch (error) {
      console.error("submitOrder could not start checkout", error);
      return { ok: true, url: `/order/${order.id}?pay=error` };
    }
  }
  return { ok: true, url: `/order/${order.id}` };
}

export async function payOrder(formData: FormData): Promise<void> {
  const id = formData.get("id");
  if (!isOrderId(id)) redirect("/");
  let target = `/order/${id}?pay=error`;
  try {
    const order = await getOrder(id);
    if (order) {
      const pay = await checkoutUrl(order, await getBaseUrl());
      if ("url" in pay) target = pay.url;
      else if ("paid" in pay) target = `/order/${id}`;
    }
  } catch (error) {
    console.error("payOrder failed", error);
  }
  redirect(target);
}

/* ---------- owner (admin) actions ---------- */

export async function isAdmin(): Promise<boolean> {
  const password = adminPassword();
  if (!password) return false;
  return isValidSessionToken(password, (await cookies()).get(ADMIN_COOKIE)?.value, Date.now());
}

async function requireAdmin(): Promise<void> {
  if (!(await isAdmin())) redirect("/admin/login");
}

export async function adminLogin(_previous: string | null, formData: FormData): Promise<string | null> {
  const password = adminPassword();
  if (!password) return "Admin login is switched off. Set ADMIN_PASSWORD (12 characters or more) first.";
  if (!allow(`login:${await getClientIp()}`, 6, 15 * 60_000)) return "Too many tries. Wait 15 minutes.";
  await new Promise((resolve) => setTimeout(resolve, 400));
  if (!passwordMatches(formData.get("password"), password)) return "Wrong password.";
  (await cookies()).set(ADMIN_COOKIE, createSessionToken(password, Date.now()), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_SECONDS,
  });
  redirect("/admin");
}

export async function adminLogout(): Promise<void> {
  (await cookies()).delete(ADMIN_COOKIE);
  redirect("/admin/login");
}

const text = (value: FormDataEntryValue | null, max: number): string | null => {
  const trimmed = typeof value === "string" ? value.trim().slice(0, max) : "";
  return trimmed || null;
};
const back = (id: string, message: string): never => redirect(`/admin?msg=${encodeURIComponent(message)}#o-${id}`);

export async function adminSetQuote(formData: FormData): Promise<void> {
  await requireAdmin();
  const id = formData.get("id");
  if (!isOrderId(id)) redirect("/admin");
  const price = String(formData.get("price") ?? "").trim();
  if (!/^\d{1,4}(\.\d{1,2})?$/.test(price)) back(id, "Enter the price as a number, like 80 or 79.50.");
  const cents = Math.round(Number(price) * 100);
  let message: string;
  try {
    // An older payment link for the old price must not stay payable.
    if ((await retireOpenSession(id)) === "paid") message = "The customer already paid, so the price was not changed.";
    else if (await setQuote(id, cents, text(formData.get("note"), 1000))) message = "Final price is now on the customer order page. Let them know it is ready.";
    else message = "Could not set that price. It must be from $5 to $2,000 and the order must be unpaid.";
  } catch (error) {
    console.error("adminSetQuote failed", error);
    message = "Something went wrong talking to Stripe or the database. Nothing was changed.";
  }
  back(id, message);
}

export async function adminSetProgress(formData: FormData): Promise<void> {
  await requireAdmin();
  const id = formData.get("id");
  if (!isOrderId(id)) redirect("/admin");
  const status = formData.get("status") as WorkStatus;
  const link = text(formData.get("deliveryUrl"), 500);
  if (link && !/^https:\/\/[^\s<>"']+$/.test(link)) back(id, "The delivery link must start with https://");
  if (!WORK_STATUSES.includes(status)) back(id, "Pick a status.");
  const ok = await setProgress(id, status, text(formData.get("note"), 1000), link);
  back(id, ok ? "Order updated." : "Only paid orders that are not cancelled can be updated.");
}

export async function adminCancel(formData: FormData): Promise<void> {
  await requireAdmin();
  const id = formData.get("id");
  if (!isOrderId(id)) redirect("/admin");
  let message = "Order cancelled. If it was paid, refund it in your Stripe dashboard.";
  try {
    // Close any open payment link first so a cancelled order cannot be paid.
    if ((await retireOpenSession(id)) === "paid") message = "This order was just paid. It is now cancelled, so refund it in Stripe.";
    await cancelOrder(id, text(formData.get("note"), 1000));
  } catch (error) {
    console.error("adminCancel failed", error);
    message = "Could not cancel. Nothing was changed.";
  }
  back(id, message);
}

export async function adminClearAlert(formData: FormData): Promise<void> {
  await requireAdmin();
  const id = formData.get("id");
  if (!isOrderId(id)) redirect("/admin");
  await clearPaymentAlert(id);
  back(id, "Alert cleared.");
}
