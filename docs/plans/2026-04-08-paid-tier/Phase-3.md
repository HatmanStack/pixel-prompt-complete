# Phase 3: Stripe Billing Integration

## Phase Goal

Implement Stripe Checkout session creation, Customer Portal session creation, and the webhook endpoint that drives tier transitions. Webhook is the only trusted source for paid/free state.

**Success criteria:**

- `POST /billing/checkout` (JWT required) returns a Stripe Checkout redirect URL.
- `POST /billing/portal` returns a Stripe Customer Portal redirect URL (only if the user has a `stripeCustomerId`).
- `POST /stripe/webhook` verifies signatures, handles all 5 event types idempotently, and updates the users table.
- With `BILLING_ENABLED=false`, all three endpoints return 501.
- Coverage for `billing/` module ≥ 90%.

**Token estimate:** ~50k

## Prerequisites

- Phase 2 complete and merged.
- Phase-0 ADRs 5, 6 understood.
- `stripe` Python library added to `backend/src/requirements.txt` (included in Task 3.1).

## Task 3.1: Add Stripe Dependency and Cached Client

### Goal

Add the `stripe` library and a cached client factory consistent with `utils/clients.py`.

### Files to Modify/Create

- `backend/src/requirements.txt`
- `backend/src/billing/__init__.py` (empty)
- `backend/src/billing/stripe_client.py`

### Implementation Steps

1. Add `stripe>=9.0.0` to `requirements.txt` (pin to current latest). Note: this project intentionally has no `requirements-lock.txt` — `backend/src/requirements.txt` is the only dependency manifest. Do not create a lockfile.
1. Implement `stripe_client.py`:

    ```python
    import stripe
    from functools import lru_cache
    import config

    @lru_cache(maxsize=1)
    def get_stripe():
        if not config.stripe_secret_key:
            raise RuntimeError("STRIPE_SECRET_KEY not configured")
        stripe.api_key = config.stripe_secret_key
        return stripe
    ```

1. Unit test mocks `config.stripe_secret_key` and confirms the factory sets the key once.

### Commit Message Template

```text
feat(billing): add cached stripe client factory
```

## Task 3.2: Implement /billing/checkout

### Goal

Create a Stripe Checkout Session for the configured subscription price, return the URL to the caller.

### Files to Create

- `backend/src/billing/checkout.py`
- `tests/backend/unit/test_billing_checkout.py`

### Implementation Steps (TDD)

1. Tests first (using `unittest.mock.patch` on `stripe.checkout.Session.create`):
    - `test_flags_off_returns_501`
    - `test_unauthenticated_returns_401`
    - `test_creates_customer_if_missing` — no `stripeCustomerId` on user record, asserts `stripe.Customer.create` called, then Session.create uses the new id.
    - `test_reuses_existing_customer`
    - `test_returns_url_in_response`
    - `test_stripe_error_returns_502`
1. Implement `handle_billing_checkout(event, correlation_id)`:
    - Guard on `config.billing_enabled`.
    - Extract JWT claims → `user_id`, `email`.
    - Load user from `UserRepository`. If `stripeCustomerId` missing, `stripe.Customer.create(email=..., metadata={"userId": user_id})` and persist.
    - `stripe.checkout.Session.create(mode="subscription", customer=..., line_items=[{"price": config.stripe_price_id, "quantity": 1}], success_url=config.stripe_success_url, cancel_url=config.stripe_cancel_url, client_reference_id=user_id)`.
    - Return `{"url": session.url}` with 200.
1. Register route in `lambda_function.py` replacing the 501 stub from Phase 1.

### Commit Message Template

```text
feat(billing): implement stripe checkout session endpoint
```

## Task 3.3: Implement /billing/portal

### Goal

Return a Stripe Customer Portal URL so users can manage their subscription.

### Files to Create

- `backend/src/billing/portal.py`
- `tests/backend/unit/test_billing_portal.py`

### Implementation Steps (TDD)

1. Tests: flags-off 501; unauthenticated 401; user without `stripeCustomerId` → 409 with `code="no_subscription"`; happy path returns URL; Stripe error → 502.
1. Implement `handle_billing_portal(event, correlation_id)`:
    - Standard guards.
    - Load user. If no `stripeCustomerId`, 409.
    - `stripe.billing_portal.Session.create(customer=..., return_url=config.stripe_portal_return_url)`.
    - Return `{"url": session.url}`.
1. Wire route.

### Commit Message Template

```text
feat(billing): implement stripe customer portal endpoint
```

## Task 3.4: Implement /stripe/webhook

### Goal

Verify Stripe signatures on raw body, dispatch events to idempotent handlers that update the users table.

### Files to Create

- `backend/src/billing/webhook.py`
- `tests/backend/unit/test_stripe_webhook.py`
- `tests/backend/unit/fixtures/stripe_events.py`

### Implementation Steps (TDD)

1. Build fixture generators that produce signed Stripe payloads using `stripe.Webhook.generate_header` (or manually compute HMAC) with a known secret.
1. Tests cover:
    - `test_flags_off_returns_501`
    - `test_missing_signature_returns_400`
    - `test_bad_signature_returns_400`
    - `test_checkout_session_completed_sets_paid` — seeds a user row by `client_reference_id`; asserts `tier="paid"`, `stripeSubscriptionId`, `subscriptionStatus` set.
    - `test_subscription_updated_syncs_status`
    - `test_subscription_deleted_downgrades_to_free`
    - `test_invoice_payment_failed_marks_past_due_but_keeps_paid`
    - `test_unknown_event_type_returns_200_noop`
    - `test_duplicate_event_is_idempotent` — process the same event twice, state is stable. Use a processed-event set keyed by `event["id"]` stored as a DynamoDB item with TTL, or rely on the fact that the updates are already idempotent (setting the same tier twice is a no-op). Plan chooses the latter — no separate idempotency store needed, but the test still verifies replay safety.
1. Implement:

    ```python
    def handle_stripe_webhook(event, correlation_id):
        if not config.billing_enabled:
            return response(501, {"error": "billing disabled"})
        raw_body = event.get("body", "")
        sig_header = event.get("headers", {}).get("stripe-signature", "")
        try:
            stripe_event = stripe.Webhook.construct_event(raw_body, sig_header, config.stripe_webhook_secret)
        except stripe.error.SignatureVerificationError:
            return response(400, {"error": "invalid signature"})
        except ValueError:
            return response(400, {"error": "invalid payload"})

        dispatch = {
            "checkout.session.completed": _on_checkout_completed,
            "customer.subscription.created": _on_subscription_upsert,
            "customer.subscription.updated": _on_subscription_upsert,
            "customer.subscription.deleted": _on_subscription_deleted,
            "invoice.payment_failed": _on_payment_failed,
        }
        handler = dispatch.get(stripe_event["type"])
        if handler:
            handler(stripe_event["data"]["object"], _user_repo)
        return response(200, {"received": True})
    ```

1. Each `_on_*` helper is a pure function taking the Stripe object and the `UserRepository`. They call `repo.set_tier(...)` with the appropriate fields. Look up the user by `client_reference_id` on `checkout.session.completed` and by `customer` (then by `stripeCustomerId` GSI — **or**, simpler, store a reverse pointer at checkout time by writing the `stripeCustomerId` onto the user record before creating the session so the webhook can scan by sub directly via `client_reference_id` / `metadata`).
1. **Important:** because there is no GSI on `stripeCustomerId`, all dispatch functions must rely on the user_id being present. The plan's answer: set `metadata={"userId": user_id}` on the Stripe Customer in Task 3.2 so every subsequent webhook object carries it. The webhook handler reads `customer.metadata.userId` or fetches the customer via the Stripe API if needed.
1. Wire route in `lambda_function.py`.
1. **Do not parse the body before signature verification.** The raw string from `event["body"]` is passed to `construct_event` untouched.

### Commit Message Template

```text
feat(billing): implement signed stripe webhook with event dispatch
```

## Task 3.5: Handle API Gateway Base64 Encoding for Webhook Body

### Goal

API Gateway sometimes base64-encodes request bodies (especially with binary media types). Stripe needs the exact bytes it signed.

### Files to Modify

- `backend/src/billing/webhook.py`

### Implementation Steps

1. In `handle_stripe_webhook`, check `event.get("isBase64Encoded")`. If true, `raw_body = base64.b64decode(event["body"]).decode("utf-8")`. Pass the decoded string to `construct_event`.
1. Add a test case: `test_base64_body_verified_correctly` using a fixture with `isBase64Encoded=True`.

### Commit Message Template

```text
fix(billing): handle base64-encoded webhook bodies
```

## Task 3.6: Expose Billing Status on /me

### Goal

`GET /me` now returns meaningful `billing` block for paid users.

### Files to Modify

- `backend/src/lambda_function.py`
- `tests/backend/unit/test_me_endpoint.py`

### Implementation Steps

1. Populate `billing.subscriptionStatus` from the user record.
1. `billing.portalAvailable = bool(user.get("stripeCustomerId"))`.
1. Add a test for the paid-user billing block.

### Commit Message Template

```text
feat(me): include billing status in /me response
```

## Phase Verification

- [x] All 6 tasks committed.
- [x] `ruff check backend/src/` passes.
- [x] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v --cov=backend/src --cov-fail-under=80` passes.
- [x] Coverage on `backend/src/billing/` specifically >= 90%.
- [ ] `sam build` still succeeds.
- [ ] Smoke path with Stripe test keys documented in feedback note for the reviewer (actual Stripe call not run in CI).
