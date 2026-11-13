import { NextResponse } from "next/server";
import { reconcileSession } from "@/lib/payments";
import { getBaseUrl } from "@/lib/request";

/**
 * Stripe sends the customer here after paying. Arriving here proves nothing by
 * itself, so the session is looked up at Stripe with the secret key, and the
 * order is only marked paid if Stripe says so.
 */
export async function GET(request: Request) {
  const sessionId = new URL(request.url).searchParams.get("session_id") ?? "";
  const base = await getBaseUrl();
  try {
    const orderId = await reconcileSession(sessionId);
    if (orderId) return NextResponse.redirect(`${base}/order/${orderId}`, 303);
  } catch (error) {
    console.error("checkout return failed", error);
  }
  return NextResponse.redirect(`${base}/?checkout=unknown`, 303);
}
