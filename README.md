# Craftline

A made to order services site. A visitor picks a service, answers a few questions
while the price builds live, pays through Stripe Checkout, and follows the order on
a private link. The owner works the orders from `/admin`.

Next.js, TypeScript, Tailwind CSS, Postgres, Stripe.

## Run it locally

```bash
npm install
cp .env.example .env.local   # fill in what you have, everything is optional locally
npm run dev                  # http://localhost:3000
npm test
npm run lint
npm run build
```

With no `DATABASE_URL`, local development uses PGlite (Postgres running inside
Node, data in `.data/`), so nothing needs installing. Production refuses to start
orders without a real database, because that data would be lost on every restart.

## Going live

Set these environment variables on the host (see `.env.example`):

| Variable | Needed for |
|---|---|
| `DATABASE_URL` | Saving orders. Any Postgres works. The table is created on first use. |
| `STRIPE_SECRET_KEY` | Taking payments. Start with a test key. |
| `STRIPE_WEBHOOK_SECRET` | Marking orders paid even if the customer closes the tab. |
| `ADMIN_PASSWORD` | Logging in at `/admin`. 12 characters or more. |

Stripe webhook: in the Stripe dashboard add an endpoint for
`https://YOUR-DOMAIN/api/stripe/webhook` with the events
`checkout.session.completed` and `checkout.session.async_payment_succeeded`, then
copy its signing secret into `STRIPE_WEBHOOK_SECRET`.

## Changing services and prices

Everything sold lives in `src/lib/services.ts`: the services, their questions, and
every price, in cents. Add or edit entries there. `npm test` checks that each
"from" price really is the cheapest possible order.

Site name, currency and the price limits are in `src/lib/site.ts`. Orders above
`MAX_ORDER_CENTS` ($2,000) are never charged automatically, they become quote
requests that the owner prices by hand.

## How money is kept safe

- The price is calculated on the server from the answers, using the same function
  that drives the live price in the browser. A price sent by the browser is never used.
- An order becomes paid only when Stripe confirms it: through the signed webhook,
  or by looking the Checkout Session up with the secret key when the customer returns.
- Recording a payment is idempotent. A second payment for the same order, a payment
  after cancellation, or an amount that differs from the listed price is flagged on
  the admin page instead of being dropped.
- An open payment link is reused, and old links are expired when a quote changes,
  so a customer is not sent to pay twice.
- Card details never touch this site. Refunds are done in the Stripe dashboard.

## What is not built yet

Customer accounts, messages and file uploads inside an order, email notifications,
promo codes, referrals, reviews, and AI follow up questions. Customers reach their
order through the private link shown after ordering, so they need to keep it.

The wording on `/policies` is a draft. Read it and change it to match how you
really work before taking real orders.

## Layout

```
src/lib/services.ts   what is sold, questions and prices
src/lib/pricing.ts    answer validation and the price formula
src/lib/orders.ts     order storage and status rules
src/lib/payments.ts   everything that talks to Stripe
src/lib/admin-auth.ts owner login
src/app/actions.ts    server actions (order, pay, admin)
src/app/              pages and the Stripe routes
tests/                unit tests
```
