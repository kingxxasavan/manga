# Craftline

A made to order services site. A visitor picks a service and answers a few questions
about how complex the job is and the level of finish they want. No prices are shown
until the end, where they get an estimated price range and send the request. The
owner confirms the final price from `/admin`, the customer pays it through Stripe
Checkout, and follows the order on a private link.

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

## How an order moves

1. Customer answers the questions and sees an estimate range. Nothing is charged.
   (The flat price Surprise me option is the exception: it is paid right away.)
2. The request lands in `/admin` with that estimate. You set the final price
   (the form starts on the middle of the estimate) and can add a note.
3. The customer opens their order link, sees the final price and pays on Stripe.
4. You move the order through Received, In progress, Draft ready and Done, and
   add a delivery link.

The site sends no emails yet. Each order in `/admin` has an "Email the customer
their link" button that opens your own mail app with the link filled in.

## Changing services and the estimate

Everything sold lives in `src/lib/services.ts`: the services, their questions, and
the amounts behind the estimate, in cents. Customers never see those amounts, only
the range built from them. Shared `COMPLEXITY` and `LEVEL` questions multiply the
basis. The range is 15 percent either side of the calculated amount, rounded to
5 dollars (`estimateRange` in `src/lib/pricing.ts`).

The amounts follow the launch pricing rules, and `npm test` fails if a change
breaks one of them:

1. every normal request estimates at or under $500
2. bulk quantities (like 20 pages or 30 logos) and "very complex" jobs stay at or under $800
3. only a full app or game, or a full book, may go above that

`SHOW_SPREAD=1 npx vitest run tests/estimate-spread.test.ts --disable-console-intercept`
prints the cheapest, middle and dearest estimate per service while you tune.

When the launch period ends, raise the amounts in `src/lib/services.ts`, loosen
the two limits at the top of `tests/estimate-spread.test.ts` to match, and set
`LAUNCH_PRICING` to `false` in `src/lib/site.ts` to drop the "Launch pricing" labels.

A question can be limited to certain answers with `showIf`, for example the
citation style question only appears for essays and reports. Hidden questions are
never asked, checked, stored or counted.

## The website designer

For websites the customer picks a layout, a color set, a text style and an image
style, and a live preview redraws as they choose. Their choice is saved with the
order and shown again on their order page and in `/admin`, so you can see exactly
what to build.

The catalogue is `src/lib/templates.ts`: add a color set or a text style there and
it appears in the builder. A new layout also needs its drawing added in
`src/components/site-preview.tsx`. The look never changes the estimate.

The preview is a sketch drawn with shapes, not a real page, and the catalogue is
hand made. Generating templates with an AI model would be a later addition and
needs an API key.

## Surprise me

Under "Something else" the customer can pick Surprise me: a flat $15 for something
random. It is the one fixed price on the site (`fixed` on the option in
`services.ts`), so it skips the estimate and goes straight to payment. Every other
request still waits for you to confirm a price.

Site name, currency and the price limits are in `src/lib/site.ts`. A request whose
basis is above `MAX_ORDER_CENTS` ($2,000) gets no automatic estimate, and no final
price can be set outside $5 to $2,000.

## How money is kept safe

- Nothing is charged when a request is sent, and a request cannot be paid until the
  owner has set a final price. The only exception is a flat price option, whose
  amount comes from the config file and never from the browser.
- The estimate is calculated on the server from the answers, with the same function
  the browser uses to show it. A number sent by the browser is never used.
- An order becomes paid only when Stripe confirms it: through the signed webhook,
  or by looking the Checkout Session up with the secret key when the customer returns.
- Recording a payment is idempotent. A second payment for the same order, a payment
  after cancellation, or an amount that differs from the final price is flagged on
  the admin page instead of being dropped.
- An open payment link is reused, and old links are expired when the price changes,
  so a customer is not sent to pay twice or at an old price.
- Card details never touch this site. Refunds are done in the Stripe dashboard.

## What is not built yet

Customer accounts, messages and file uploads inside an order, email notifications,
promo codes, referrals, reviews, and AI follow up questions. Customers reach their
order through the private link shown after sending a request, so they need to keep
it. Because the final price now arrives later, automatic emails are the most
useful thing to add next.

The wording on `/policies` is a draft. Read it and change it to match how you
really work before taking real orders.

## Layout

```
src/lib/services.ts   what is sold, the questions and the estimate basis
src/lib/templates.ts  website layouts, color sets, text styles and image styles
src/lib/pricing.ts    answer validation and the estimate formula
src/lib/orders.ts     order storage and status rules
src/lib/payments.ts   everything that talks to Stripe
src/lib/admin-auth.ts owner login
src/app/actions.ts    server actions (order, pay, admin)
src/app/              pages and the Stripe routes
tests/                unit tests
```
