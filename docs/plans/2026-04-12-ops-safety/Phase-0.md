# Phase 0: Architecture and Conventions

Source of truth for all architectural decisions in this plan. Every later phase references this document. Do not restate decisions in phase files.

## Project Conventions

Distilled from `CLAUDE.md` and memory files:

- **Python**: 3.13 Lambda runtime. Install with `uv pip`, never bare `pip`. Lint with `ruff check backend/src/`. Line length 100.
- **Backend tests**: pytest with moto for AWS mocks. Run from repo root with `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`. CI enforces 80% backend coverage.
- **Frontend**: React 19 + TypeScript, Vite 8, Vitest 4, Zustand 5, Tailwind 4. `npm run lint`, `npm run typecheck`, `npm test` from `frontend/`.
- **Git rules**: never amend, no `Co-Authored-By` trailers, atomic conventional commits, do not switch branches, do not deploy.
- **Writing style**: direct, factual, no em dashes, no emojis, no filler.
- **SAM**: `sam build` from `backend/`. Do not deploy; deploy is the user's job.
- **Existing env-var pattern**: env var loaded in `backend/src/config.py` as a module constant via `os.environ.get` with `_safe_int` / `_safe_float` helpers. Follow this pattern for all new knobs.
- **Error responses**: factories live in `utils/error_responses.py`. Add new ones there rather than inlining dicts.
- **Feature flag pattern**: boolean loaded from env var in `config.py`, defaults to `false`. Validation at import time (e.g., `BILLING_ENABLED=true` requires `AUTH_ENABLED=true`). See ADR-7 in `docs/plans/2026-04-08-paid-tier/Phase-0.md`.

## ADRs

### ADR-11: Per-Model Cost Ceiling via DynamoDB Counters

Per-model daily generation counters stored in the existing `users` DynamoDB table using partition keys prefixed with `model#`. Example: `model#gemini`, `model#nova`, `model#openai`, `model#firefly`.

Item schema for model counters:

```text
userId          S   "model#<name>" (PK)
dailyCount      N   generations today
dailyResetAt    N   epoch seconds, 24h rolling window start
updatedAt       N   epoch seconds
```

Reuses the existing public method `UserRepository.increment_daily(user_id, window_seconds, limit, now)` (defined at `repository.py` line 192), which wraps `_atomic_increment` with `counter="dailyCount"`, `window_field="dailyResetAt"`, and `create_if_missing=True` by default. Always call `increment_daily`, never `_atomic_increment` directly from outside `UserRepository`. Before each `/generate` call dispatches to a model handler, `enforce_quota` checks the model counter. If `dailyCount >= MODEL_<NAME>_DAILY_CAP`, that model is skipped for this generation (not a 429; other models may still run). If all enabled models are capped, return 429 with `MODEL_COST_CEILING` error code.

Default caps: 500/day per model, overridable via `MODEL_GEMINI_DAILY_CAP`, `MODEL_NOVA_DAILY_CAP`, `MODEL_OPENAI_DAILY_CAP`, `MODEL_FIREFLY_DAILY_CAP`. Window is 24 hours rolling, reusing the `_reset_if_stale` pattern.

Rationale: DynamoDB counters are simpler and more observable than CloudWatch billing alarms. The admin dashboard surfaces them directly. No external dependencies.

### ADR-12: Account Suspension via isSuspended Field

`isSuspended` boolean added to user DynamoDB items. Checked at the top of `enforce_quota` before any counter logic. Returns 403 with `ACCOUNT_SUSPENDED` error code and a descriptive message.

Suspension preserves tier and Stripe subscription state. Unsuspending restores previous access. The field is set/cleared by admin API endpoints only.

### ADR-13: Cloudflare Turnstile CAPTCHA for Guest /generate

Frontend embeds the Turnstile widget on the generation page when `CAPTCHA_ENABLED=true` and the user is not authenticated. The CAPTCHA token is included in the `/generate` request body as `captchaToken`.

Server-side verification in `_parse_and_validate_request`: when `CAPTCHA_ENABLED=true` and the caller is a guest, POST the token to `https://challenges.cloudflare.com/turnstile/v0/siteverify` with the site secret. On failure, return 403 with `CAPTCHA_FAILED` error code. Authenticated users skip CAPTCHA entirely.

Secrets: `TURNSTILE_SITE_KEY` (frontend env var `VITE_TURNSTILE_SITE_KEY`) and `TURNSTILE_SECRET_KEY` (backend env var, stored in SSM SecureString per ADR-6 pattern).

Latency impact: approximately 50-100ms added to `/generate` for guests. Acceptable since generation takes 5-30 seconds.

### ADR-14: Amazon SES for Email Notifications

Lifecycle emails triggered from webhook dispatch in `billing/webhook.py`:

- Welcome (on `checkout.session.completed`)
- Subscription activated (on `customer.subscription.created`)
- Subscription cancelled (on `customer.subscription.deleted`)
- Payment failed warning (on `invoice.payment_failed`)

Admin-triggered emails (suspension notice, warning, custom) sent from admin API endpoints.

All emails use inline HTML templates with plain-text fallback. No SES template resources (keeps it simple and version-controlled). Templates live in `backend/src/notifications/templates.py` as Python string constants.

Gated behind `SES_ENABLED` feature flag. Requires `SES_FROM_EMAIL` env var (the verified sender address). SES sandbox exit is a manual operational step documented in the deployment guide.

IAM: Lambda needs `ses:SendEmail` permission, added to `template.yaml` conditionally when `SES_ENABLED` is relevant (or unconditionally since it is harmless without the feature flag).

### ADR-15: Admin Authorization via Cognito Groups

Admin API endpoints (`/admin/*`) are gated by checking `cognito:groups` in the JWT claims. The JWT already includes this claim when a user belongs to a Cognito group. The backend checks for `"admins"` in the groups list.

The `admins` group is created by SAM via `AWS::Cognito::UserPoolGroup`. The first admin must be manually added via the AWS console.

Admin routes use the same JWT authorizer as `/iterate` and `/me`. The additional group check happens in Lambda, not at the API Gateway level (API Gateway HttpApi JWT authorizer does not support group-based authorization natively).

A new helper `require_admin(event)` lives in `backend/src/auth/claims.py`, a new file to be created (the `auth/` directory currently contains only `__init__.py` and `guest_token.py`). This module imports `extract_claims` from `users.tier` (where it is defined) and adds admin-specific helpers. Returns the claims dict on success, or raises `AdminRequired` (caught by the route handler to return 403).

### ADR-16: Operational Metrics via Scheduled Lambda and CloudWatch

A scheduled Lambda function (EventBridge rule, daily at 00:00 UTC) snapshots operational data into the `users` DynamoDB table under `metrics#YYYY-MM-DD` partition keys:

```text
userId          S   "metrics#2026-04-12" (PK)
modelCounts     M   {"gemini": 450, "nova": 380, ...}
usersByTier     M   {"free": 150, "paid": 45, "guest": 1200}
suspendedCount  N   3
revenue         M   {"activeSubscribers": 45, "mrr": 2250}
createdAt       N   epoch seconds
```

Real-time metrics (request rate, error rate, latency per model) are emitted via CloudWatch `PutMetricData` fire-and-forget from the hot path in `lambda_function.py`. Custom namespace: `PixelPrompt/Operations`. This adds approximately 1ms per request.

The daily snapshot Lambda reuses the same codebase (same SAM function with a different handler, or a conditional branch in `lambda_handler` based on the event source). For simplicity, add a new handler function `handle_daily_snapshot` in a new module `backend/src/ops/metrics.py` and register it as a separate SAM function event.

### ADR-17: Revenue Tracking via Webhook-Fed Aggregates

The existing webhook handler in `billing/webhook.py` is extended to maintain running counters in a `revenue#current` DynamoDB item:

```text
userId              S   "revenue#current" (PK)
activeSubscribers   N   count of active paid users
mrr                 N   monthly recurring revenue in cents
monthlyChurn        N   cancellations this month
updatedAt           N   epoch seconds
```

Updated atomically alongside `set_tier` calls using `_atomic_increment` or direct `UpdateItem`. The daily snapshot Lambda copies `revenue#current` into the daily `metrics#YYYY-MM-DD` item for historical tracking.

### ADR-18: Admin Dashboard Code Splitting

The admin dashboard is a lazy-loaded `/admin` route in the React app. Uses `React.lazy()` and `Suspense` with the same pattern as `AuthCallback`, `BillingSuccess`, and `BillingCancel` in `App.tsx`.

Admin components live under `frontend/src/components/admin/`. Charting uses `recharts` (lightweight, React-native). The admin bundle is fully tree-shaken from the user bundle.

State management: a new `useAdminStore` Zustand store for admin-specific state (user list, model stats, metrics). Follows the same patterns as `useAppStore` and `useBillingStore`.

### ADR-19: DynamoDB GSI Deferred

The `users` table has only a `userId` hash key. Admin user listing requires a Scan. This is acceptable below 10,000 users. A GSI on `tier` or `isSuspended` is deferred to a future plan. The admin user list endpoint uses Scan with pagination (1MB page limit, `LastEvaluatedKey`).

## New Environment Variables

Added to `config.py`:

```text
# Cost ceiling (per-model daily caps)
MODEL_GEMINI_DAILY_CAP=500
MODEL_NOVA_DAILY_CAP=500
MODEL_OPENAI_DAILY_CAP=500
MODEL_FIREFLY_DAILY_CAP=500

# CAPTCHA
CAPTCHA_ENABLED=false
TURNSTILE_SECRET_KEY=

# Email notifications
SES_ENABLED=false
SES_FROM_EMAIL=
SES_REGION=us-west-2

# Admin
ADMIN_ENABLED=false
```

Frontend env vars:

```text
VITE_CAPTCHA_ENABLED=false
VITE_TURNSTILE_SITE_KEY=
VITE_ADMIN_ENABLED=false
```

## New API Routes

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/users | JWT + admin group | List users (paginated Scan) |
| GET | /admin/users/{userId} | JWT + admin group | Get user detail |
| POST | /admin/users/{userId}/suspend | JWT + admin group | Suspend user |
| POST | /admin/users/{userId}/unsuspend | JWT + admin group | Unsuspend user |
| POST | /admin/users/{userId}/notify | JWT + admin group | Send email to user |
| GET | /admin/models | JWT + admin group | Get per-model daily counts and caps |
| POST | /admin/models/{model}/disable | JWT + admin group | Disable a model at runtime |
| POST | /admin/models/{model}/enable | JWT + admin group | Re-enable a model at runtime |
| GET | /admin/metrics | JWT + admin group | Get today's metrics + recent snapshots |
| GET | /admin/revenue | JWT + admin group | Get revenue aggregates |

## New Backend Modules

```text
backend/src/
├── auth/
│   └── claims.py            # CREATE new file: require_admin(), extract_admin_groups(), is_admin()
│                             # Imports extract_claims from users.tier (where it is defined)
├── notifications/
│   ├── __init__.py
│   ├── ses_client.py        # SES client factory (cached)
│   ├── sender.py            # send_email() with feature flag check
│   └── templates.py         # HTML + plain-text email templates
├── ops/
│   ├── __init__.py
│   ├── metrics.py           # Daily snapshot handler, CloudWatch emitter
│   ├── model_counters.py    # Per-model cost ceiling logic
│   └── captcha.py           # Turnstile verification
├── admin/
│   ├── __init__.py
│   ├── users.py             # Admin user list/detail/suspend/unsuspend
│   ├── models.py            # Admin model status/disable/enable
│   ├── notifications.py     # Admin send-notice endpoint
│   ├── metrics.py           # Admin metrics/revenue endpoints
│   └── auth.py              # Admin auth middleware (wraps require_admin)
```

## New Frontend Modules

```text
frontend/src/
├── components/admin/
│   ├── AdminLayout.tsx       # Admin shell with sidebar nav
│   ├── AdminOverview.tsx     # Dashboard overview
│   ├── AdminUsers.tsx        # User list with search/filter
│   ├── AdminUserDetail.tsx   # User detail with suspend/notify actions
│   ├── AdminModels.tsx       # Model status and controls
│   ├── AdminNotifications.tsx # Notification log and send form
│   └── AdminRevenue.tsx      # Revenue charts and metrics
├── stores/
│   └── useAdminStore.ts      # Admin state management
├── api/
│   └── adminClient.ts        # Admin API client
```

## Test Strategy

Unit tests use moto for DynamoDB mocking and `unittest.mock.patch` for external HTTP calls (Turnstile verification, SES).

New test files:

- `tests/backend/unit/test_model_counters.py` - per-model counter increment, cap enforcement, window reset
- `tests/backend/unit/test_captcha.py` - Turnstile verification success/failure, feature flag off
- `tests/backend/unit/test_suspension.py` - suspend/unsuspend flow, quota enforcement with suspension
- `tests/backend/unit/test_ses_sender.py` - email send with moto SES mock, feature flag off
- `tests/backend/unit/test_email_templates.py` - template rendering
- `tests/backend/unit/test_admin_auth.py` - require_admin with/without group claim
- `tests/backend/unit/test_admin_users.py` - user list, suspend, unsuspend, notify endpoints
- `tests/backend/unit/test_admin_models.py` - model status, disable, enable endpoints
- `tests/backend/unit/test_admin_metrics.py` - metrics and revenue endpoints
- `tests/backend/unit/test_daily_snapshot.py` - scheduled snapshot handler
- `tests/backend/unit/test_revenue_tracking.py` - webhook revenue counter updates

Frontend tests:

- `frontend/tests/__tests__/components/admin/` - admin component tests
- `frontend/tests/__tests__/stores/useAdminStore.test.ts` - admin store tests
- `frontend/tests/__tests__/api/adminClient.test.ts` - admin API client tests
- `frontend/tests/__tests__/components/CaptchaWidget.test.tsx` - CAPTCHA widget test

## Deploy Model

This plan does not deploy. All infrastructure changes land in `template.yaml` and SAM synthesizes cleanly, but the actual `sam deploy` is the user's responsibility. Phase verification includes `sam build` succeeding locally.

Feature flags off (`CAPTCHA_ENABLED=false`, `SES_ENABLED=false`, `ADMIN_ENABLED=false`) is the default so a fresh deploy behaves like today.

## Commit Message Conventions

Conventional commits, one commit per task. Types used:

- `feat(ops): ...` for cost ceiling, metrics, model counters
- `feat(captcha): ...` for Turnstile integration
- `feat(notifications): ...` for SES email
- `feat(admin): ...` for admin API and dashboard
- `chore(sam): ...` for `template.yaml` changes
- `test: ...` for test-only commits

No `Co-Authored-By` trailers.
