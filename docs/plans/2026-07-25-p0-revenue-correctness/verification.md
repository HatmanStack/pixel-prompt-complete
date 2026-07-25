# P0-A / P0-B Verification — pre-fix baseline

**This document is the audit baseline captured at `2f7b2dc`, before any fix
landed.** It records the broken behaviour on purpose; do not read it as the
current state of the code. P0-A has since been fixed on this branch — see
"Post-fix status" at the end.

Verified 2026-07-25 against `2f7b2dc` (pulled; the 4 new commits were frontend
dependency bumps only and touched no billing code).

Baseline before any changes: **backend 496 passed**, **frontend 453 passed**.

## P0-A — CONFIRMED, both halves

### A1. Cancellations never downgrade

Current code, re-verified line by line:

| Claim                                                         | Location at HEAD                                   | Status    |
| ------------------------------------------------------------- | -------------------------------------------------- | --------- |
| Resolver only reads `client_reference_id` → `metadata.userId` | `backend/src/billing/webhook.py:75-79`             | CONFIRMED |
| Checkout never sets `subscription_data`                       | `backend/src/billing/checkout.py:66-74`            | CONFIRMED |
| Only the _Customer_ gets metadata                             | `backend/src/billing/checkout.py:53-58`            | CONFIRMED |
| Handler silently returns on unresolvable user                 | `backend/src/billing/webhook.py:115-117`           | CONFIRMED |
| No `stripeCustomerId` reverse lookup exists                   | `backend/src/users/repository.py` (no such method) | CONFIRMED |

`client_reference_id` is a **Checkout Session** field. It does not exist on a
Subscription object. `metadata` on the Subscription is only populated if
`subscription_data.metadata` was passed at checkout — which never happens. So
every real `customer.subscription.deleted` hits `webhook.py:116` and no-ops.

**Empirical proof.** A test using a verbatim-shaped Stripe subscription object
(`metadata: {}`, no `client_reference_id`), against a user seeded as `paid`:

```text
tier after cancellation = 'paid'
subscriptionStatus      = 'active'
```

The webhook returned `200 {"received": true}`. Stripe sees success, the operator
sees success, the churned user keeps paid access permanently.

### A2. No idempotency

- `webhook.py` reads only `stripe_event["type"]` (`:180`) and
  `stripe_event["data"]["object"]` (`:184`). `stripe_event["id"]` is **never read**.
- No dedup table, no conditional write, no processed-event marker anywhere in
  `backend/src/billing/` or `repository.py`.
- The module docstring at `webhook.py:4` claims "dispatches events to idempotent
  handlers." That claim is false.

**Empirical proof.** Delivering the _same_ `checkout.session.completed`
(`id: evt_same_id`) twice — which Stripe's at-least-once delivery guarantees will
happen — yields:

```text
activeSubscribers after 2x delivery of evt_same_id = 2
```

One subscriber, counted twice. The mirror path (`webhook.py:124`
`decrement_revenue_counter`) can drive `activeSubscribers` negative.

### A3. The tests conceal it — CONFIRMED

`tests/backend/unit/test_stripe_webhook.py` hand-injects
`"metadata": {"userId": ...}` into subscription and invoice fixtures at lines
**144, 167, 180, 261, 342, 367, 395, 424, 550**. Those are exactly the event
types (`customer.subscription.*`, `invoice.payment_failed`) where Stripe sends
`metadata: {}`. The suite is green against a payload shape Stripe never emits.

Note `tests/backend/unit/fixtures/stripe_events.py:23-32` _does_ already thread
an `event_id` into the payload — so the fixture layer is ready for idempotency
tests; the production code simply ignores the field.

## P0-B — CONFIRMED

| Claim                                            | Location at HEAD                                                                      | Status    |
| ------------------------------------------------ | ------------------------------------------------------------------------------------- | --------- |
| Paid generate is an unconditional allow          | `backend/src/users/quota.py:141-142`                                                  | CONFIRMED |
| Paid tier = 200 refines/day                      | `backend/src/config.py:103-104` (`paid_daily_limit=200`, `paid_window_seconds=86400`) | CONFIRMED |
| `check_model_allowed` has exactly one caller     | `backend/src/lambda_function.py:476`, inside `/generate` only                         | CONFIRMED |
| `/iterate` and `/outpaint` skip the cost ceiling | `lambda_function.py:863,886` pass `endpoint_kind="refine"`; no counter call           | CONFIRMED |
| System counts calls, never dollars               | no `$`/cost field anywhere in `ops/` or `repository.py`                               | CONFIRMED |

Two additions found during verification, both worth folding into the fix:

1. **`check_model_allowed` is not a pure check.** `ops/model_counters.py:57-60`
   delegates to `increment_model_count` — it _mutates_ on every call. Extending
   it to `/iterate` and `/outpaint` is correct, but the name is a trap and the
   check/consume split should be made explicit at the same time.
2. **The only spend guard is conditional on auth.** `lambda_function.py:463`
   gates the whole ceiling block on `config.auth_enabled`. With shipped defaults
   (`AUTH_ENABLED=false`) there is _no_ ceiling of any kind — this is where P0-B
   and P0-D compound.

### Cost model (estimates — verify against real provider invoices before pricing)

Per **Generate** click: 1 `gpt-4o` adaptation call (`lambda_function.py:492`,
`adapt_per_model`) + 4 concurrent image generations.

| Component                         | Est. unit cost    |
| --------------------------------- | ----------------- |
| gpt-4o prompt adaptation          | $0.005 – 0.010    |
| Gemini 3 flash image              | ~$0.039           |
| Nova Canvas 1024² standard        | ~$0.040           |
| DALL-E 3 1024² standard           | ~$0.040           |
| Firefly Image 5 (credit-based)    | ~$0.050 – 0.100   |
| **Total per Generate**            | **~$0.17 – 0.23** |
| **Per Refine** (1 model, 1 image) | **~$0.04 – 0.10** |

These are list-price estimates from public rate cards, not measured spend. The
first deliverable of P0-B (the `$` meter) is what replaces them with real numbers.

Exposure at current defaults:

- Paid tier, worst case: unlimited generate + 200 refines/day ≈ **$10/day
  ($300/mo) on refines alone**, unbounded on generate.
- Moderate subscriber (5 gen + 10 refine/day) ≈ **$45/mo COGS**.
- No price point in the $10–30 range survives either number.

## P0-C / P0-D spot-checks (not the assignment, confirmed in passing)

- **No price exists.** `frontend/src/components/UpgradeModal.tsx:74` reads
  "Upgrade to Pro". Grep for `$`/`price` across that file returns nothing else.
- **`_anon_tier()` returns `tier="paid"`** — `lambda_function.py:130-138`. With
  shipped defaults every anonymous caller is a paid user.
- **`/enhance` is unmetered** — `lambda_function.py:955` passes
  `endpoint_kind="none"`; captcha requires `"generate"` (`:188`) and quota
  requires `"generate"|"refine"` (`:213`). It calls gpt-4o with no gate.
- **Content filter checks the raw prompt only** — `lambda_function.py:209`;
  generation uses `adapted_prompts` at `:525`, never re-checked.
- **`/enhance` returns identical strings** for `short_prompt` and `long_prompt`
  — `lambda_function.py:964`.

At the time of this audit, nothing in the P0-A or P0-B findings had been fixed.

## Post-fix status

P0-A is fixed on `feat/p0-revenue-correctness`:

| Baseline finding | Status |
|---|---|
| Cancellations never downgrade | **Fixed** — three-tier resolver + `StripeCustomerIndex` GSI |
| Checkout sets no `subscription_data` | **Fixed** — stamps `metadata.userId` |
| Silent return on unresolved user | **Fixed** — logs at ERROR with event type and customer id |
| No webhook idempotency | **Fixed** — leased claim + explicit completion record |
| Tests hand-inject `metadata.userId` | **Fixed** — real-shaped fixtures + a guard test |
| No recovery path for already-churned users | **Fixed** — `backend/scripts/reconcile_subscriptions.py` |

Two further defects were found in review of the fix itself and are also fixed:
non-atomic revenue counter updates (drove `activeSubscribers` negative on a
mid-handler failure), and a failed claim release permanently swallowing an
event.

Post-fix: **backend 528 passed**, coverage **89.50%**, frontend 453 passed.

**P0-B is unchanged** — every economics finding above still stands and is the
subject of Sprint 1 Track B.
