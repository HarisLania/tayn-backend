# Tayn Meal Plans - Backend (Django REST Framework)

Subscription meal-plan delivery backend for the UAE. JWT auth, Stripe billing,
Swagger docs. SQLite for development/testing, PostgreSQL for production.

## Apps
- **accounts** - `CustomerProfile`, JWT register/login/logout/refresh/me
- **menu** - `Category`, `Meal` (public, read-only)
- **plans** - `Plan`, the per-meal rate card for a category (public, read-only)
- **subscriptions** - `Subscription`, `Invoice`, `WebhookEvent`; Stripe checkout,
  plan and delivery-day changes (with proration preview), cancel-at-period-end,
  and webhook receiver

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit values
python manage.py migrate      # also seeds categories, meals and plans
python manage.py runserver
```

## Billing model
Pricing is **per meal**. A customer picks a category, a start date, and which
weekdays they want meals; the meal count follows from the days chosen.

```
cycle           = 28 days == exactly 4 weeks
meals_per_cycle = 4 x len(delivery_days)
charge          = plan.price_per_meal x meals_per_cycle
```

28 days is deliberate: any 28-day window contains exactly four of every weekday,
so every cycle holds the same number of meals whatever day the customer starts
on. The charge is therefore identical every cycle and there is no partial period
to prorate at signup. A 30-day or calendar-month cycle would drift through the
week and make the bill vary month to month.

The **first cycle is charged in full at checkout**, before any deliveries. A bad
card then fails at signup rather than on the morning of the first delivery, when
the kitchen has already prepped. Cancelling stops future billing but does not
refund: the customer receives the meals for the cycle they have paid for, so
money is never held against food that will not be delivered.

Deliveries are scheduled from the **first delivery date** — the first chosen
weekday on or after `start_date` — which is computed locally, not by Stripe. So
a customer starting Wednesday who picked only Thursdays gets a cycle running
Thursday to Thursday. Stripe anchors its billing period to checkout time
instead, a day or two earlier; renewals therefore clear shortly before each
delivery cycle ends, which is what you want before prepping the next one.

Which days were chosen never reaches Stripe — only how many. Thu+Fri and Mon+Tue
are both quantity 8. The schedule lives in this database, for the kitchen.

| Category | AED/meal | 2 days/wk | 3 days/wk | 5 days/wk | 7 days/wk |
|---|---|---|---|---|---|
| Standard | 40 | 320 | 480 | 800 | 1,120 |
| Low Cal | 35 | 280 | 420 | 700 | 980 |
| Weight Gain | 50 | 400 | 600 | 1,000 | 1,400 |
| Protein Power | 75 | 600 | 900 | 1,500 | 2,100 |

## Stripe setup
`migrate` seeds the four plans but leaves `stripe_price_id` empty. With
`STRIPE_SECRET_KEY` set, create the matching Stripe products/prices:

```bash
python manage.py sync_stripe_prices --dry-run   # preview
python manage.py sync_stripe_prices             # create + store the price ids
```

**One price per plan** — the per-meal rate, recurring every 4 weeks. The meal
count is the subscription line item's `quantity`, so changing how many days a
customer eats is a quantity update Stripe prorates natively; no second price and
no lookup table. Prices are created in `STRIPE_CURRENCY` (default AED).

The command is idempotent, keyed on a per-plan Stripe `lookup_key`, so it is
safe to re-run after a rate change: the old price is archived and the key
transfers to a new one, while existing subscribers keep theirs.

### Keeping plans and Stripe in sync
The seed migration deliberately does **not** call Stripe. Migrations build the
test database, run in CI, and run on machines with no API keys; they also run
inside a transaction that can roll back the database but cannot un-create a
Stripe product. So the catalogue is seeded offline and reconciled separately,
with three guards against a plan drifting out of sync:

1. **Unsynced plans are hidden.** `/api/plans/` excludes plans with no
   `stripe_price_id` whenever Stripe is configured, so a customer never sees a
   plan they cannot buy. (With Stripe off, nothing is filtered — a blank price
   id is expected in local development.)
2. **A startup warning.** `manage.py check` — and therefore every management
   command — reports `plans.W001` listing any active plan without a price.
3. **A deploy gate.** `manage.py sync_stripe_prices --check` writes nothing and
   exits non-zero if any plan is missing, archived, mispriced, or points at a
   price that no longer exists. Run it in CI or after deploy.

Checkout also rejects an unsynced plan outright, so the failure can never reach
Stripe. `stripe_price_id` is read-only in the admin: it is owned by the sync
command, and hand-editing it is how a plan ends up pointing at the wrong object.

### Webhook
The receiver is `POST /api/webhooks/stripe/` and needs `STRIPE_WEBHOOK_SECRET`.

Local development, via the [Stripe CLI](https://docs.stripe.com/stripe-cli):
```bash
stripe login
stripe listen --forward-to localhost:8000/api/webhooks/stripe/
# copy the printed whsec_... into STRIPE_WEBHOOK_SECRET, then restart runserver
stripe trigger checkout.session.completed   # in a second terminal
```

Deployed: Dashboard -> Developers -> Webhooks -> *Add endpoint*, URL
`https://<your-domain>/api/webhooks/stripe/`, and subscribe to exactly the
events in `subscriptions/webhooks.py::HANDLERS`:
`checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`,
`customer.subscription.updated`, `customer.subscription.deleted`.
Reveal the endpoint's signing secret and put it in the server's environment.
The `whsec_` from `stripe listen` and the one from the Dashboard are different
secrets — each endpoint has its own.

## Environment / DEBUG behaviour
Configuration lives in `.env` (see `.env.example`). Nothing is hard-coded.
- `DEBUG=True`  -> SQLite (`db.sqlite3`), browsable API, media served locally.
- `DEBUG=False` -> PostgreSQL using the `POSTGRES_*` variables.
- Stripe keys are **optional**. When `STRIPE_SECRET_KEY` is blank the checkout and
  webhook endpoints return HTTP 503 instead of calling Stripe, so the rest of the
  API still runs. Set `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` to enable payments.

## Auth
JWT (djangorestframework-simplejwt). Send `Authorization: Bearer <access>`.
- `POST /api/auth/register/`, `POST /api/auth/login/` -> `{ access, refresh }`
- `POST /api/auth/refresh/`, `POST /api/auth/logout/` (blacklists refresh)

## Subscription endpoints
| Method | Path | Notes |
|---|---|---|
| GET | `/api/plans/` | `?category=<slug>`; returns `price_per_meal` |
| POST | `/api/checkout/quote/` | Price a selection, creates nothing |
| POST | `/api/checkout/create-session/` | Checkout URL; also signs up anonymous users |
| GET | `/api/subscriptions/me/` | Current subscription + cycle totals |
| GET | `/api/subscriptions/<id>/deliveries/` | Delivery dates for the current cycle |
| GET | `/api/subscriptions/<id>/invoices/` | |
| POST | `/api/subscriptions/<id>/change-plan/` | `{new_plan_id, preview}` |
| POST | `/api/subscriptions/<id>/delivery-days/` | `{delivery_days, preview}` |
| POST | `/api/subscriptions/<id>/cancel/` | Cancels at period end |

`delivery_days` is 1-7 unique codes from `mon tue wed thu fri sat sun`, accepted
in any case or order and stored sorted. `start_date` must be at least
`MIN_START_LEAD_DAYS` (default 2) ahead — kitchen lead time.

Money is returned as a 2-decimal string (`"480.00"`) on every endpoint.

Subscription `status`: `scheduled` (first cycle paid at checkout, first delivery
still to come), `active` (deliveries under way), `past_due`, `canceled`. Stripe
reports a subscription as `active` from the moment checkout is paid, so the
promotion to `active` waits on `first_delivery_date` instead.

## Docs
- Swagger UI: `/api/docs/`
- Redoc: `/api/redoc/`
- OpenAPI schema: `/api/schema/`

## Tests
```bash
python manage.py test
```
Stripe is fully mocked in tests - no network or API keys required.
