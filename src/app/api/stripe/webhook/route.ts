import type Stripe from "stripe";
import { getStripe, recordIfPaid } from "@/lib/payments";

/**
 * Stripe calls this when a payment completes. It is what makes an order paid
 * even if the customer closes the tab before coming back to the site.
 * The signature check proves the call really came from Stripe.
 */
export async function POST(request: Request) {
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  const signature = request.headers.get("stripe-signature");
  if (!secret || !signature) return new Response("Webhook is not configured", { status: 400 });

  let event: Stripe.Event;
  try {
    event = await getStripe().webhooks.constructEventAsync(await request.text(), signature, secret);
  } catch {
    return new Response("Bad signature", { status: 400 });
  }

  if (event.type === "checkout.session.completed" || event.type === "checkout.session.async_payment_succeeded") {
    try {
      await recordIfPaid(event.data.object);
    } catch (error) {
      console.error("webhook could not record payment", error);
      return new Response("Try again later", { status: 500 }); // Stripe retries on 5xx
    }
  }
  return new Response("ok");
}
