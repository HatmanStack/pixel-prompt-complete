# Phase 0: Architecture and Conventions

Source of truth for all architectural decisions. Every later phase references this document. Do not restate decisions in phase files — link here.

## Project Conventions

Distilled from `/home/christophergalliart/projects/pixel-prompt-complete/CLAUDE.md` and `~/.claude/projects/-home-christophergalliart-projects/memory/MEMORY.md`:

- **Python**: 3.13 Lambda runtime. Install with `uv pip`, never bare `pip`. Lint with `ruff check backend/src/`. Line length 100.
- **Backend tests**: pytest with moto for AWS mocks. Run from repo root with `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`. CI enforces 80% backend coverage.
- **Frontend**: React 19 + TypeScript, Vite 8, Vitest 4, Zustand 5, Tailwind 4. `npm run lint`, `npm run typecheck`, `npm test` from `frontend/`.
- **Git rules** (from user memory): never amend, no `Co-Authored-By` trailers, atomic conventional commits, do not switch branches, do not deploy. Each task in each phase produces one commit.
- **Writing style** (from user memory): direct, factual, no em dashes, no emojis, no filler.
- **SAM**: `sam build && sam deploy` from `backend/`. `samconfig.toml` is not committed. Do not deploy from this plan; deploy is the user's job.
- **Existing env-var pattern**: env var loaded in `backend/src/config.py` as a module constant, imported by `lambda_function.py`. Follow this pattern for all new knobs.
- **Existing S3 locking pattern**: `jobs/manager.py` uses optimistic locking with a `version` field and 3 retries. `utils/rate_limit.py` uses ETag conditional writes. Either is a valid reference for similar concerns.
- **Error responses**: factories live in `utils/error_responses.py`. Add new ones there rather than inlining dicts.

## ADRs

### ADR-1: Cognito Hosted UI for Auth

Use AWS Cognito User Pool with Hosted UI (redirect flow). Rationale: AWS handles password reset, email verification, MFA hooks, and account recovery. Avoids building custom forms. Branding tradeoff accepted for v1.

JWT verification is delegated to API Gateway HttpApi's built-in JWT authorizer. Lambda never re-verifies signatures; it only reads `event.requestContext.authorizer.jwt.claims` on protected routes. This keeps the crypto work at the edge and the Lambda simple.

### ADR-2: Hybrid Authorizer Placement

- `/generate`, `/enhance`, `/gallery/list`, `/gallery/{id}`, `/status/{id}`, `/log`, `/stripe/webhook`: **no** authorizer (public).
- `/iterate`, `/outpaint`, `/me`, `/billing/checkout`, `/billing/portal`: JWT authorizer **required**.

Guests can hit `/generate` once; as soon as they try to refine they must sign in. This matches the "one free taste" product decision and keeps webhook delivery unauthenticated (Stripe signs the request instead).

### ADR-3: DynamoDB users Table (Single-Table)

Partition key: `userId` (String) = Cognito `sub`. No sort key. On-demand billing.

Item schema:

```text
userId               S   Cognito sub (PK)
tier                 S   "free" | "paid"
email                S   from Cognito claim (informational)
stripeCustomerId     S   set after first checkout
stripeSubscriptionId S   set on subscription.created
subscriptionStatus   S   Stripe status string (active, past_due, canceled, ...)
windowStart          N   epoch seconds, rolling-hour window start
generateCount        N   /generate calls in current window
refineCount          N   /iterate + /outpaint calls in current window
dailyResetAt         N   epoch seconds, paid-tier daily window end
dailyCount           N   paid-tier refinement calls today
createdAt            N   epoch seconds
updatedAt            N   epoch seconds
```

All counter updates use `UpdateItem` with conditional expressions that compare `windowStart` / `dailyResetAt` against `:now`. Counters reset atomically inside the same update.

### ADR-4: Guest Token Storage in DynamoDB (Same Table, Prefixed Key)

Guest records live in the same `users` table with `userId = "guest#" + token_id` and a TTL attribute (`ttl`) set to `now + GUEST_WINDOW_SECONDS + 300`. Rationale: one table to provision, one IAM policy, native TTL cleanup, no new S3 key conventions. Attributes used for guests: `userId`, `tier="guest"`, `generateCount`, `windowStart`, `ttl`, `ipHash` (for cross-check), `createdAt`.

Guest token format: HMAC-signed blob `base64url(token_id).base64url(hmac_sha256(token_id, GUEST_TOKEN_SECRET))`. `token_id` is a 16-byte urandom value. The server re-validates the HMAC on every request; if invalid or expired it issues a new token.

Transport: HttpOnly, Secure, SameSite=Lax cookie named `pp_guest`. Cookie is issued via `Set-Cookie` header on the first `/generate` response when `AUTH_ENABLED=true` and no valid cookie is present. On subsequent requests the cookie is read from `event.headers.cookie`.

**Global guest cap** (`GUEST_GLOBAL_LIMIT` per `GUEST_GLOBAL_WINDOW_SECONDS`): stored as a single DynamoDB item `userId = "guest#__global__"` with `count` and `windowStart` attributes. Incremented atomically per guest `/generate`.

### ADR-5: Stripe Webhook Handled by Existing Lambda

`POST /stripe/webhook` routes to the same Lambda as everything else. Signature verification uses the **raw** `event["body"]` string (no JSON parse before verification). Handled events:

- `checkout.session.completed` — set `stripeCustomerId`, mark `tier="paid"`, store `stripeSubscriptionId`, `subscriptionStatus`.
- `customer.subscription.created` / `updated` — sync `subscriptionStatus`; tier stays `paid` while status is `active` or `trialing`.
- `customer.subscription.deleted` — set `tier="free"`, clear `stripeSubscriptionId`.
- `invoice.payment_failed` — record `subscriptionStatus="past_due"`; tier downgrade happens on `subscription.deleted`, not here (Stripe's retry schedule is the grace period).

Webhook response returns 200 on success, 400 on signature failure, 500 on unexpected errors. All event handling is idempotent — rerunning a webhook must not double-apply state.

### ADR-6: Secrets in SSM Parameter Store (SecureString)

Stripe secret key, Stripe webhook signing secret, and `GUEST_TOKEN_SECRET` live in SSM Parameter Store as SecureString. SAM template references them via `{{resolve:ssm-secure:...}}` and passes them in as Lambda environment variables at deploy time. Rationale: Secrets Manager has recurring cost; SSM SecureString is free and sufficient for this scale. Parameter names are configurable via SAM parameters so the open-source default can be "unset".

### ADR-7: Feature Flags AUTH_ENABLED and BILLING_ENABLED

Two independent booleans loaded in `config.py`:

- `AUTH_ENABLED=false, BILLING_ENABLED=false` (default): no auth, no quotas, app behaves exactly like today. The new `users` table is still created by SAM (empty; no cost on on-demand) but never touched.
- `AUTH_ENABLED=true, BILLING_ENABLED=false`: accounts work, all signed-in users are treated as `free` tier, Stripe endpoints return 501.
- `AUTH_ENABLED=true, BILLING_ENABLED=true`: full tier system.
- `AUTH_ENABLED=false, BILLING_ENABLED=true`: invalid; `config.py` raises at import time.

Branching is at clean boundaries in `_parse_and_validate_request` and in the route table. No per-line `if AUTH_ENABLED` sprinkled in business logic.

### ADR-8: Removal of utils/rate_limit.py

`utils/rate_limit.py` and all references are deleted in Phase 2. Tests in `tests/backend/unit/test_rate_limit.py` are deleted. The new quota layer is the single source of truth.

**Follow-up (sibling work, out of scope for this plan)**: cost-ceiling circuit breaker. Per-model daily spend caps, CloudWatch billing alarms, provider-side spend limits. Tracked separately so it is not lost. A reviewer catching this during pipeline should not ask the planner to inline it.

### ADR-9: Rolling Window Semantics

On every quota check, load the user record and compute:

```text
if now >= windowStart + WINDOW_SECONDS:
    generateCount = 0
    refineCount = 0
    windowStart = now
```

Applied via DynamoDB `UpdateItem` with a conditional expression so reset and increment happen atomically. No TOCTOU.

Paid tier has a second counter (`dailyCount` / `dailyResetAt`) with a 24-hour rolling window, enforced on refinement calls only.

### ADR-10: /me Endpoint Contract

`GET /me` (JWT required) returns:

```json
{
  "userId": "cognito-sub",
  "email": "user@example.com",
  "tier": "free",
  "quota": {
    "windowSeconds": 3600,
    "windowStart": 1712600000,
    "generate": {"used": 1, "limit": 1},
    "refine": {"used": 0, "limit": 2}
  },
  "billing": {
    "subscriptionStatus": null,
    "portalAvailable": false
  }
}
```

For `tier="paid"`, `quota` reports the daily counter instead. The frontend uses this to render the quota indicator and the upgrade CTA.

## Quota Table (Defaults, All Env-Configurable)

| Tier | Window | /generate | /iterate + /outpaint | Env vars |
|------|--------|-----------|----------------------|----------|
| guest | 60 min rolling | 1 | 0 | `GUEST_GENERATE_LIMIT`, `GUEST_WINDOW_SECONDS` |
| guest (global) | 60 min rolling | 5 (sum across all guests) | n/a | `GUEST_GLOBAL_LIMIT`, `GUEST_GLOBAL_WINDOW_SECONDS` |
| free | 60 min rolling | 1 | 2 | `FREE_GENERATE_LIMIT`, `FREE_REFINE_LIMIT`, `FREE_WINDOW_SECONDS` |
| paid | 24 h rolling | unlimited (soft) | `PAID_DAILY_LIMIT` (TBD) | `PAID_DAILY_LIMIT`, `PAID_WINDOW_SECONDS` |

`PAID_DAILY_LIMIT` defaults are intentionally left TBD in code (default to a placeholder like `200`); the operator sets the real value at deploy time after cost analysis.

## New Environment Variables

Added to `config.py` and `backend/.env.example`:

```text
# Feature flags
AUTH_ENABLED=false
BILLING_ENABLED=false

# Cognito
COGNITO_USER_POOL_ID=
COGNITO_USER_POOL_CLIENT_ID=
COGNITO_DOMAIN=
COGNITO_REGION=us-west-2

# DynamoDB
USERS_TABLE_NAME=pixel-prompt-users

# Guest tracking
GUEST_TOKEN_SECRET=
GUEST_GENERATE_LIMIT=1
GUEST_WINDOW_SECONDS=3600
GUEST_GLOBAL_LIMIT=5
GUEST_GLOBAL_WINDOW_SECONDS=3600

# Free tier
FREE_GENERATE_LIMIT=1
FREE_REFINE_LIMIT=2
FREE_WINDOW_SECONDS=3600

# Paid tier
PAID_DAILY_LIMIT=200
PAID_WINDOW_SECONDS=86400

# Stripe
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID=
STRIPE_SUCCESS_URL=
STRIPE_CANCEL_URL=
STRIPE_PORTAL_RETURN_URL=
```

`GLOBAL_LIMIT`, `IP_LIMIT`, `IP_INCLUDE` are **deleted** from `config.py` and `.env.example` in Phase 2.

## New API Routes

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /me | JWT | User info + quota |
| POST | /billing/checkout | JWT | Create Stripe Checkout session, return redirect URL |
| POST | /billing/portal | JWT | Create Stripe Customer Portal session, return redirect URL |
| POST | /stripe/webhook | none (signature) | Stripe event webhook |

## Backend Module Layout (After This Plan)

```text
backend/src/
├── lambda_function.py       # +routes for /me, /billing/*, /stripe/webhook; -RateLimiter
├── config.py                # +feature flags, tier/quota env vars, secrets; -GLOBAL_LIMIT etc.
├── auth/
│   ├── __init__.py
│   ├── claims.py            # Extract + validate JWT claims from event
│   └── guest_token.py       # HMAC sign/verify guest cookie
├── billing/
│   ├── __init__.py
│   ├── stripe_client.py     # Cached Stripe client
│   ├── checkout.py          # /billing/checkout handler
│   ├── portal.py            # /billing/portal handler
│   └── webhook.py           # /stripe/webhook handler + event dispatch
├── users/
│   ├── __init__.py
│   ├── repository.py        # UserRepository: DynamoDB CRUD, atomic quota updates
│   └── tier.py              # resolve_tier(event) -> TierContext
├── utils/
│   ├── error_responses.py   # +auth_required, tier_quota_exceeded, subscription_required
│   └── (rate_limit.py DELETED)
```

## Test Strategy

Unit tests use `moto` for DynamoDB and S3 mocking and `pytest` fixtures for:

- A fake Cognito JWT claims dict.
- A Stripe webhook event fixture (signed with a known secret and the library's `Webhook.construct_event` verified end-to-end).
- A fresh DynamoDB table created per test via moto.

New test files:

- `tests/backend/unit/test_guest_token.py` — HMAC round-trip, expiry, tamper detection.
- `tests/backend/unit/test_user_repository.py` — atomic window reset, counter increment, conditional update retries.
- `tests/backend/unit/test_tier_resolution.py` — guest vs free vs paid claim extraction; feature-flag off path.
- `tests/backend/unit/test_quota_enforcement.py` — per-tier limits, window reset, global guest cap.
- `tests/backend/unit/test_stripe_webhook.py` — signature verification, each event type, idempotency.
- `tests/backend/unit/test_billing_endpoints.py` — checkout and portal session creation (mock stripe client).
- `tests/backend/unit/test_me_endpoint.py` — response shape, feature-flag-off behavior.

Tests that must be **deleted**: `tests/backend/unit/test_rate_limit.py` and any rate-limit assertions in existing handler tests.

Coverage gate is 80%. New modules must individually clear the gate; `billing/webhook.py` in particular needs branch coverage for each event type.

Frontend tests:

- `frontend/tests/__tests__/stores/useAuthStore.test.ts`
- `frontend/tests/__tests__/stores/useBillingStore.test.ts`
- `frontend/tests/__tests__/components/TierBanner.test.tsx`
- `frontend/tests/__tests__/components/QuotaIndicator.test.tsx`
- `frontend/tests/__tests__/api/authClient.test.ts` — Authorization header attachment, 401/402/403 handling.

## Deploy Model

This plan does **not** deploy. All infrastructure changes land in `template.yaml` and SAM synthesizes cleanly, but the actual `sam deploy` is the user's responsibility after they provision the Cognito pool and set the SSM parameters. Phase 1 verification includes `sam build` succeeding locally; it does not include `sam deploy`.

Feature flags off (`AUTH_ENABLED=false`, `BILLING_ENABLED=false`) is the default in `template.yaml` so a fresh deploy behaves like today.

## Commit Message Conventions

Conventional commits, one commit per task. Types used in this plan:

- `feat(auth): ...`, `feat(billing): ...`, `feat(users): ...`, `feat(frontend): ...`
- `refactor: ...` for `rate_limit.py` removal
- `chore(sam): ...` for `template.yaml` changes
- `docs: ...` for `CLAUDE.md` and `.env.example`
- `test: ...` for test-only commits (rare; prefer colocated test + code commits via TDD)

No `Co-Authored-By` trailers.
