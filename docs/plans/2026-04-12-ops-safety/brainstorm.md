# Feature: Operational Safety and Admin Tooling

## Overview

The paid-tier v1 shipped with per-user quota enforcement but no platform-level cost protection, no abuse prevention beyond cookie tracking, no admin visibility, and no proactive user communication. This plan closes those gaps with four interlocking features: a cost-ceiling circuit breaker, guest CAPTCHA, an admin dashboard, and custom email notifications via SES.

The cost-ceiling adds per-model daily generation counters to the existing DynamoDB users table (following the single-table design from ADR-3/ADR-4, using `model#<name>` prefixed keys and the same `_atomic_increment` pattern from `repository.py`). When any model hits its configured daily cap, `enforce_quota` blocks further generations for that model until the daily window resets. This is the platform-level safety net that replaced the old `RateLimiter` (removed in ADR-8).

Cloudflare Turnstile CAPTCHA gates the guest `/generate` endpoint to prevent automated abuse of the global guest pool. Verification happens server-side in `_parse_and_validate_request`, gated behind a `CAPTCHA_ENABLED` feature flag following the ADR-7 pattern. Amazon SES handles custom email notifications triggered by the existing webhook dispatch in `billing/webhook.py` (account lifecycle events) and by new admin endpoints (suspension notices, warnings). The admin dashboard is a lazy-loaded `/admin` route in the existing React app, gated by a Cognito `admins` user group via a `cognito:groups` claim check -- a new authorization pattern layered on top of the existing JWT authorizer from ADR-2.

## Decisions

1. **Cost-ceiling mechanism: per-model daily generation counters in DynamoDB.** Same table, `model#<name>` partition keys, `_atomic_increment` with configurable daily caps via env vars (e.g., `MODEL_GEMINI_DAILY_CAP=500`). `enforce_quota` checks the model counter before allowing generation. Auto-resets on 24-hour rolling window. No CloudWatch billing alarms -- the counters are the primary mechanism, and the admin dashboard surfaces them for visibility.
2. **CAPTCHA: Cloudflare Turnstile on `/generate` for guests only.** Frontend widget on the generation page. CAPTCHA token included in the `/generate` request body. Lambda verifies server-side via POST to `https://challenges.cloudflare.com/turnstile/v0/siteverify`. Authenticated users skip CAPTCHA entirely. Gated behind `CAPTCHA_ENABLED` feature flag.
3. **CAPTCHA provider: Cloudflare Turnstile.** Free, low-friction, privacy-friendly. Two secrets: `TURNSTILE_SITE_KEY` (frontend) and `TURNSTILE_SECRET_KEY` (backend, stored in SSM SecureString per ADR-6).
4. **Email notifications: Amazon SES for account lifecycle + admin-triggered notices.** Lifecycle events (welcome, subscription activated, subscription cancelled, payment failed warning) triggered from the existing webhook dispatch in `billing/webhook.py`. Admin-triggered notices (suspension, warning, custom) sent from new admin endpoints. SES requires domain verification and sandbox exit for production.
5. **Admin dashboard: `/admin` route in existing React app.** Gated by Cognito `admins` user group. JWT claims include `cognito:groups` when the user belongs to a group. A new claim check in the backend gates admin API endpoints. Lazy-loaded React routes keep admin code out of the user bundle.
6. **Account suspension: `isSuspended` boolean in DynamoDB user records.** Checked at the top of `enforce_quota` before any counter logic. Returns 403 with a descriptive message. Preserves tier and Stripe subscription state. Unsuspending restores previous access automatically. Trivially queryable for the admin dashboard.
7. **Operational metrics: daily DynamoDB snapshots + CloudWatch custom metrics.** A scheduled Lambda (EventBridge cron, daily) snapshots per-model counters, user counts by tier, suspension counts, and revenue aggregates into a `metrics#YYYY-MM-DD` partition in the users table. CloudWatch `PutMetricData` emitted fire-and-forget from the hot path for real-time request rate, error rate, and latency per model.
8. **Revenue view: webhook-fed DynamoDB aggregates.** The existing webhook handler in `billing/webhook.py` is extended to maintain running counters (`revenue#current` item) for active subscriber count, MRR, and monthly churn. Updated atomically alongside `set_tier` calls. The daily snapshot Lambda doubles as a reconciliation point.
9. **Admin dashboard sections: Overview, Users, Models, Notifications, Revenue.** Overview shows real-time CloudWatch graphs and today's per-model generation counts vs caps. Users is a searchable/filterable table with suspend/unsuspend toggle and send-notice button. Models shows per-model daily count vs cap, manual disable toggle, and historical daily snapshot chart. Notifications shows admin email log and templates for common notices. Revenue shows webhook-fed MRR, active subscribers, and churn.
10. **All new secrets via SSM SecureString (ADR-6).** Turnstile secret key, SES sending identity config. Referenced in SAM template via `{{resolve:ssm-secure:...}}`.
11. **All new features behind feature flags (ADR-7 pattern).** `CAPTCHA_ENABLED`, `SES_ENABLED`, `ADMIN_ENABLED` -- each defaults to `false` in `config.py`. Open-source contributors are unaffected.
12. **Single-table DynamoDB design (ADR-3/ADR-4 extended).** New key prefixes: `model#<name>` for per-model counters, `metrics#YYYY-MM-DD` for daily snapshots, `revenue#current` for live aggregates. All in the existing `users` table. No new tables.

## Open Questions

1. **Per-model daily cap defaults**: What should the initial values be? Planner should set reasonable defaults (e.g., 500/day per model) overridable via env vars. The admin dashboard lets operators see usage and adjust.
2. **SES sandbox exit**: Production email requires an AWS support request. This is an operational step, not code. Should be documented in the deployment guide.
3. **Admin group bootstrap**: The first admin must be manually added to the `admins` Cognito group via the AWS console. The SAM template should create the group itself.
4. **Email template format**: HTML with plain-text fallback is standard. Planner decides on template structure (inline vs SES templates).
5. **DynamoDB scan for admin user list**: The users table has only a `userId` hash key. Listing/filtering requires a Scan. Fine at <10k users. Beyond that, a GSI on `tier` or `isSuspended` would be needed. Planner decides whether to add a GSI now or defer.

## Relevant Codebase Context

- `backend/src/users/quota.py` -- `enforce_quota()` is the integration point for cost-ceiling model checks and suspension. Handles guest/free/paid tiers with DynamoDB atomic counters.
- `backend/src/users/repository.py` -- `increment_global_guest()` and `_atomic_increment()` are the template for per-model global counters. `_reset_if_stale()` handles daily window resets. `isSuspended` field will be added to user items.
- `backend/src/billing/webhook.py` -- `_DISPATCH` dict and handler functions are the integration point for SES lifecycle emails and revenue aggregate updates. Already handles checkout, subscription, and payment events.
- `backend/src/config.py` -- all new env vars (model caps, CAPTCHA keys, SES config, feature flags) follow the existing `_safe_int` / `os.environ.get` pattern. Feature flag validation (ADR-7) is already established.
- `backend/template.yaml` -- new SAM resources: EventBridge rule for daily snapshot, IAM permissions for SES and CloudWatch PutMetricData, Cognito `admins` group, new API routes for admin endpoints. Auth conditional pattern (`AuthEnabledCondition`) already established. Secrets via SSM SecureString (ADR-6).
- `backend/src/lambda_function.py` -- new admin route handlers; CAPTCHA verification in `_parse_and_validate_request` for guest `/generate` requests. `_anon_tier()` and `response()` helper patterns.
- `backend/src/users/tier.py` -- `resolve_tier()` and `extract_claims()` will be extended. `extract_claims` is public (renamed from `_extract_claims` in hardening pass). `cognito:groups` claim is available in the JWT.
- `backend/src/utils/error_responses.py` -- new factories for admin-specific errors. Follows UPPER_SNAKE_CASE convention established in hardening pass.
- `frontend/src/api/config.ts` -- `CAPTCHA_ENABLED`, `VITE_TURNSTILE_SITE_KEY`, `ADMIN_ENABLED` env vars. Cognito env var validation pattern already established.
- `frontend/src/stores/useBillingStore.ts` -- `/me` response may include `isSuspended` for the frontend to show a suspension banner. `requestEpoch` stale-response guard already in place.
- `frontend/src/components/` -- new lazy-loaded admin components under `/admin` route. Existing patterns: `TierBanner.tsx`, `QuotaIndicator.tsx`, `UpgradeModal.tsx` (focus trap, Escape key).
- `docs/plans/2026-04-08-paid-tier/Phase-0.md` -- ADR-1 through ADR-10 are the architectural source of truth. This plan extends ADRs 3, 4, 7, and 8.

## Technical Constraints

- **Lambda concurrency**: 10 reserved. Admin endpoints share this pool with user-facing requests. At current scale this is fine. If admin DynamoDB scans become expensive, consider a dedicated Lambda.
- **DynamoDB scans**: The users table has only a `userId` hash key. Admin user listing requires a Scan (O(table size)). Acceptable below 10k users. A GSI on `isSuspended` or `tier` would be needed at scale.
- **CloudWatch PutMetricData latency**: ~1ms fire-and-forget per request. Max 1000 values per call; batching not needed at current throughput.
- **SES sandbox**: New AWS accounts can only send to verified emails. Production requires a support request. Must be documented in deployment guide.
- **Turnstile verification latency**: Server-side POST to Cloudflare adds ~50-100ms to `/generate`. Acceptable since generation itself takes 5-30 seconds.
- **Admin route code splitting**: React lazy imports prevent admin components from bloating the user bundle. The admin dashboard includes charting (likely recharts or similar) which is heavy.
- **Cognito groups**: The `admins` group must exist in the User Pool. SAM template should create it via `AWS::Cognito::UserPoolGroup`. JWT tokens automatically include `cognito:groups` claim.
- **No Co-Authored-By trailers** in commits (per user git rules).
- **Do not deploy** -- SAM build only. Deploy is the user's responsibility.
- **No em dashes, no emojis, no filler** in plan text (per user writing style).
