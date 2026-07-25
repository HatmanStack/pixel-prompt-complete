# Sprint 1 — P0-A (revenue correctness) + P0-B (unit economics)

Scope: pure engineering. Estimated **12–15 working days solo**.

P0-C was decided mid-planning (subscription + hard credit allotment — see
`pricing-memo.md`), which turned Track B from "add caps" into "replace the quota
model with a credit ledger." Every price and allotment is an env var, so tuning
them after launch is a config change, not a code change.

Nothing here enables live billing. `BILLING_ENABLED` stays `false` throughout;
all verification is against test-mode fixtures and moto.

---

## Track A — P0-A: cancellations + idempotency (5–6 days)

Order matters: A1 and A2 are independent and can land in either order, but A3
depends on both, and A5 is the gate on the whole track.

### A1. Set subscription metadata at checkout (0.5 day)

`backend/src/billing/checkout.py:66-74` — add to `checkout.Session.create`:

```python
subscription_data={"metadata": {"userId": user_id}},
```

**Caveat that makes A2 mandatory:** this only tags subscriptions created _after_
deploy. Every existing subscription keeps `metadata: {}` forever. A1 alone does
not fix the bug for anyone who has already subscribed.

### A2. `stripeCustomerId` reverse lookup (1.5 days)

- Add a GSI on `stripeCustomerId` to the users table in
  `backend/src/template.yaml` (the existing GSI is for prompt history — this is
  a second one).
- Add `UserRepository.get_user_by_stripe_customer_id(customer_id)` in
  `backend/src/users/repository.py`.
- GSI backfill is automatic for existing rows that already carry the attribute;
  confirm rows written before `set_stripe_customer_id` existed are not missing it.

### A3. Three-tier resolver (0.5 day)

`backend/src/billing/webhook.py:68-79` — resolve in order:

1. `client_reference_id` (checkout sessions)
2. `metadata.userId` (subscriptions created after A1)
3. **GSI lookup on `obj["customer"]`** (everything else, incl. all pre-A1 subs)

If all three miss, do **not** silently return: log at `error` with the event id
and type, and emit a CloudWatch metric. A silent no-op on a cancellation is the
exact failure mode that produced this bug.

### A4. Webhook idempotency (1.5 days)

Dedup on `stripe_event["id"]`, which is already present in the payload and
already threaded through the fixture builder
(`tests/backend/unit/fixtures/stripe_events.py:23-32`).

Design — conditional-put guard in `handle_stripe_webhook` _before_ dispatch:

- Key: `event#<stripe_event_id>` in the existing users table (avoids a second
  table and a second IAM grant), with a TTL of ~30 days.
- `PutItem` with `ConditionExpression="attribute_not_exists(userId)"`.
- On `ConditionalCheckFailedException` → return `200 {"received": true}`
  immediately without dispatching.
- **If the handler then raises, delete the marker** so Stripe's retry can
  re-process. Without this, one transient DynamoDB blip permanently drops a
  cancellation.

### A5. Rewrite the test suite — the gate (1.5 days)

Rewrite `tests/backend/unit/test_stripe_webhook.py` removing every hand-injected
`metadata.userId` (lines 144, 167, 180, 261, 342, 367, 395, 424, 550).

- Fixtures must be verbatim-shaped Stripe objects: subscriptions and invoices
  carry `metadata: {}` and **no** `client_reference_id`.
- Add an explicit regression test: a real `customer.subscription.deleted` for a
  paid user must leave that user at `tier == "free"`.
- Add idempotency tests: same event id twice → counters move exactly once;
  handler failure → marker cleared, retry succeeds.
- Add a guard test asserting no fixture in the module contains a
  `metadata.userId` key, so the concealment cannot silently return.

Working proof-of-bug tests already exist from the verification pass and can be
inverted into the regression tests.

### A6. Reconciliation for already-churned users (1 day)

There is no way to know from local state who cancelled while the bug was live.
Write a one-shot script (`backend/scripts/`) that lists Stripe subscriptions,
diffs status against the users table, and reports (then, on a `--apply` flag,
corrects) every row where DynamoDB says `paid` but Stripe disagrees. Dry-run
output reviewed by a human before any write.

---

## Track B — P0-B: meter, cap, and credit ledger (7–9 days)

### B1. Dollar cost table (0.5 day)

Add per-model, per-operation cost constants to `backend/src/config.py`,
env-overridable (`MODEL_GEMINI_COST_GENERATE`, …). Seed with the estimates in
`verification.md`, then correct them against real invoices — the table is the
single place a price change has to land.

### B2. `$`-denominated meter (1.5 days)

New `backend/src/ops/cost_meter.py`. Record dollars (as integer micro-dollars —
never floats in DynamoDB counters) on every billable operation:

- per-user daily and per-billing-period spend
- global daily spend
- per-model daily spend

Call it from all three billable paths: `/generate`, `/iterate`, `/outpaint`, plus
`/enhance` (which is where P0-D's unmetered gpt-4o exposure shows up as a number).

### B3. Credit ledger — replaces call-counting quota (2.5 days)

P0-C is now decided (subscription + hard credit allotment), so this is no longer
"cap paid generate at some provisional number" — it is a model change from
**counting calls in a rolling window** to **debiting a monthly credit balance**.

- Add credit config per `pricing-memo.md` (`CREDITS_PER_GENERATE`,
  `*_MONTHLY_CREDITS`, `CREDIT_PERIOD_SECONDS`) as integer centi-credits.
- `users/quota.py:141-142` — delete the unconditional paid-generate allow;
  debit `CREDITS_PER_GENERATE` from the balance instead.
- Atomic debit in `repository.py` with a conditional expression so a balance
  can never go negative under concurrency (the same shape as the existing
  `_atomic_increment`).
- Monthly period reset, not the current rolling hourly window.

### B3a. Free tier becomes a budget, not a rate limit (1 day)

This is the largest single exposure created by "free tier = all 4 models."

`config.py:98-100` + `repository.py:68-96` implement free as a rolling 1-hour
rate limit (1 generate/hour). That permits ~720 generates/month ≈ **$144/month
of COGS per free user**, unbounded in aggregate. A rate limit does not bound
monthly spend.

Replace the hourly window for free users with `FREE_MONTHLY_CREDITS` (default 5)
on the same ledger as B3. Keep a short rolling limit _as well_ if you want abuse
protection, but the monthly budget is what bounds spend.

Aggregate free-tier spend needs its own admin line and its own alarm (B6).

### B3b. `GET /pricing` endpoint (0.5 day)

Public, unauthenticated, cacheable. Returns tier names, prices, allotments, and
per-action credit costs from Lambda env. `UpgradeModal.tsx:74` renders whatever
it returns instead of hardcoding.

Rationale: price experimentation must not require a frontend rebuild, and the UI
must not be able to advertise a price the backend doesn't enforce. One source.

### B4. Extend the cost ceiling to refine paths (1 day)

`ops/model_counters.py:57-60` — `check_model_allowed` mutates (it delegates to
`increment_model_count`). Split it into an explicit `check` and `consume` pair,
then call the consume path from `/iterate` and `/outpaint`
(`lambda_function.py:863,886`), not just `/generate` (`:476`).

### B5. Global dollar ceiling + alarms (1 day)

- Hard daily `$` ceiling that short-circuits all billable endpoints when crossed.
- CloudWatch alarms at 50% / 80% / 100% of the daily budget.
- This is the backstop that makes every other cap a defence-in-depth layer
  rather than the only thing standing between the operator and an unbounded bill.

### B6. Surface `$` in the admin dashboard (0.5–1 day)

The audit's framing — "neither landmine is visible from the admin dashboard" —
stays true until spend appears there. Add `$` spend (today, MTD, per-model,
top-N users by spend) to `/admin/metrics` and `/admin/revenue`.

---

## Definition of done

### Track A — revenue correctness

- [ ] Backend suite green with **zero** hand-injected `metadata.userId` fixtures
- [ ] Real `customer.subscription.deleted` downgrades a paid user to free
- [ ] Duplicate event id moves counters exactly once; `activeSubscribers` cannot go negative
- [ ] Pre-A1 subscription (empty metadata) resolves via the GSI fallback
- [ ] Reconciliation script dry-run reviewed by a human

### Track B — economics

- [ ] Every billable path debits credits and records `$`; nothing is unmetered
- [ ] Credit balance cannot go negative under concurrent requests
- [ ] Free tier bounded by a **monthly budget**, not an hourly rate limit
- [ ] Global `$` ceiling short-circuits all billable endpoints; alarms at 50/80/100%
- [ ] `GET /pricing` is the single source for prices; `UpgradeModal` hardcodes nothing
- [ ] Admin dashboard shows `$` spend, including aggregate free-tier spend

### Both tracks

- [ ] `ruff check` + `mypy` clean; frontend 453 still green
- [ ] `BILLING_ENABLED` still `false`; no deploy

## Out of scope for Sprint 1

- **P0-D** (next sprint): flag defaults, `/enhance` gating, guest `ipHash` binding.
  Note `/enhance` gets _metered_ in B2 but not _gated_ until P0-D.
- **Real COGS numbers.** The table ships with list-price estimates. Correcting it
  from measured spend is a post-deploy config change and a prerequisite for any
  public price (see `pricing-memo.md` → "Before any price goes public").
- Team/per-seat tier, credit rollover policy, all P1 items.
