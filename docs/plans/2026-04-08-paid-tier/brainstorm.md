# Feature: Paid Tier (Cognito + Stripe)

## Overview

Transition Pixel Prompt Complete from a fully-open, IP-rate-limited service into a tiered product with three access levels: anonymous "guest" (one free taste), signed-in "free" (a small recurring quota), and "paid" (large daily cap, billed via Stripe subscription). Authentication is handled by AWS Cognito (Hosted UI), billing by Stripe Checkout, and per-user state lives in a new DynamoDB `users` table. The existing IP-based `RateLimiter` is removed entirely; the new tier system becomes the single source of truth for quota enforcement.

The feature must remain friendly to open-source contributors. Auth and billing are gated behind `AUTH_ENABLED` and `BILLING_ENABLED` feature flags so that a contributor can clone the repo, drop in four provider API keys, and run the app exactly as it works today — without ever touching Cognito or Stripe. All quota counts and window durations are env-var driven for easy tuning per deployment.

This is a backend-heavy feature: a new Cognito User Pool, a new DynamoDB table, a new Stripe webhook route, JWT verification on protected endpoints, a new quota-enforcement layer in Lambda, and corresponding frontend work for sign-in/checkout redirects and tier-aware UI.

## Decisions

1. **Guest identification: IP + signed cookie / localStorage token (Option B from Q1).** MAC addresses are not accessible from browsers, so that idea is off the table. IP alone is too leaky (NAT, VPN, mobile networks). A signed token issued on first visit and stored client-side, layered with IP as a fallback, raises the bypass bar significantly without resorting to fingerprinting. Heavy fingerprinting felt disproportionate for an open-source project.
2. **Guest quota: 1 generation, 0 iterations per user, with a global cap of 5 guest generations per rolling 60 minutes.** The per-user limit is the product gate; the global cap is a cost brake against viral moments and abuse.
3. **Free (signed-in) quota: 1 `/generate` + 2 refinement calls (`/iterate` or `/outpaint`) per rolling 60 minutes (Q2 option A).** Refinement model is "per session," matching the natural user flow ("try one prompt, refine a couple times, come back later or upgrade"). Easy to communicate in the UI.
4. **Free tier is only offered after the guest hits their limit.** UX flow is guest → wall → "create an account to keep going" prompt → Cognito Hosted UI → free tier.
5. **All quota counts and window durations must be configurable via env vars** (guest count, guest window, free generate count, free refinement count, free window, paid daily cap). No hardcoded magic numbers.
6. **Auth provider: AWS Cognito with Hosted UI (Q6 option C).** Redirect flow for sign-up/sign-in. Avoids building custom auth forms; AWS handles password reset, email verification, etc. Branding tradeoff accepted for v1.
7. **JWT verification: Hybrid API Gateway authorizer (Q3 option C).** API Gateway HttpApi JWT authorizer is **required** on `/iterate` and `/outpaint`, **absent** on `/generate` (so guests can hit it). Lambda inspects `event.requestContext.authorizer.jwt.claims` when present to determine tier and apply quotas.
8. **Billing model: Stripe subscription (recurring monthly), Q5 option A.** Matches the "unlock iterations up to a daily cap" mental model. Single paid tier for v1; tiers/credit packs can be added later.
9. **Stripe checkout: Stripe Checkout hosted page (redirect flow), part of Q6 option C.** No Stripe Elements / custom payment forms in v1.
10. **Stripe webhook lives on the existing Lambda at `POST /stripe/webhook` (Q8 option A).** Signature-verified. Webhook is the source of truth for the user's `tier` field — the client is never trusted for billing state. Events handled: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`.
11. **User state: single DynamoDB `users` table (Q4 option A, Q7 single-table).** Partition key: Cognito `sub`. Attributes: `tier` (`free` | `paid`), `stripeCustomerId`, `stripeSubscriptionId`, `subscriptionStatus`, `windowStart` (epoch), `generateCount`, `refineCount`, `dailyCount`, `dailyResetAt`, `createdAt`, `updatedAt`. Atomic updates via `UpdateItem` conditional expressions.
12. **Window style: rolling 60 minutes** (Q7). On each quota check, if `now > windowStart + windowSeconds`, reset counters and set `windowStart = now`. More fair than fixed hourly windows; trivially more code than fixed.
13. **Existing `RateLimiter` is removed entirely (Q9 option A).** Tier-based quotas are the single source of truth. **Open follow-up for the planner**: a global cost-ceiling against catastrophic spend (viral moment, stuck retry loop, abusive guest signups across many IPs) should be re-implemented at a different layer — per-model daily budgets, CloudWatch billing alarms, and/or provider-side spend caps. This is important and should not be lost.
14. **Open-source story: `AUTH_ENABLED` and `BILLING_ENABLED` feature flags (Q10 option A).** When both are off, the app behaves exactly like today (no accounts, no tiers, no Stripe). When `AUTH_ENABLED=true` and `BILLING_ENABLED=false`, accounts work but everyone is "free" tier. When both are on, full tier system is active. Branching is at clean boundaries (`if AUTH_ENABLED: ...`).
15. **Guest tracking implementation**: a new lightweight module replaces the relevant parts of `rate_limit.py`. Guest token is HMAC-signed using a server-side secret (env var); cookie is HttpOnly + Secure + SameSite=Lax. Per-token state lives in S3 (or DynamoDB — planner to decide; S3 is consistent with the existing pattern, DynamoDB is consistent with the new `users` table).

## Scope: In

- New Cognito User Pool + Hosted UI (created via SAM template).
- New DynamoDB `users` table (created via SAM template) with the schema described above.
- API Gateway HttpApi JWT authorizer on `/iterate` and `/outpaint`.
- New Lambda module for tier resolution: extract claims, look up user in DynamoDB, return tier + remaining quota.
- New quota-enforcement layer that replaces calls to the old `RateLimiter` in `_parse_and_validate_request` and the refinement endpoints.
- Guest identification: signed cookie issuance on first `/generate`, server-side validation, IP fallback, global guest cap.
- Removal of `utils/rate_limit.py` and all references.
- New Stripe webhook endpoint `POST /stripe/webhook` with signature verification.
- New Stripe Checkout session creation endpoint (e.g., `POST /billing/checkout`) — authenticated, returns the redirect URL.
- New "billing portal" endpoint (e.g., `POST /billing/portal`) so users can cancel/update payment method via Stripe Customer Portal.
- New `/me` endpoint returning the current user's tier, quota usage, and reset times (used by frontend to render UI state).
- Frontend: sign-in / sign-out flow via Cognito Hosted UI redirects, tier-aware UI (guest banner, "upgrade" CTAs, quota indicators), Stripe Checkout redirect, post-checkout success/cancel pages.
- Feature flags `AUTH_ENABLED` / `BILLING_ENABLED` and clean fallback behavior when off.
- All new env vars documented in `backend/.env.example` and `CLAUDE.md`.
- Tests: backend unit tests for tier resolution, quota enforcement, webhook handling, guest cookie flow; frontend tests for auth state and tier-gated UI.

## Scope: Out

- **Multiple paid tiers / pricing tiers** — single paid tier for v1.
- **Credit packs / one-time purchases** — subscription only.
- **Custom auth UI / Stripe Elements** — hosted redirects only.
- **Browser fingerprinting** — guests are tracked by IP + cookie, nothing more invasive.
- **Social login providers** (Google, Apple, GitHub) — Cognito supports them but not required for v1.
- **Email notifications** for billing events (welcome, payment failed, cancelation) — Stripe sends its own; no custom emails for v1.
- **Admin dashboard / user management UI** — manage via AWS console + Stripe dashboard.
- **Refunds and proration logic** — handled via Stripe dashboard manually.
- **Tax handling** (Stripe Tax integration) — out of scope for v1.
- **Migration of existing anonymous users** — there are no existing accounts; the cutover is clean.
- **Determining the actual paid daily cap and price point** — left as a config value; the user explicitly said this needs cost analysis first. Plumbing must support changing it; the value itself is TBD.
- **Cost ceiling / global circuit breaker** — flagged as an open follow-up below; not part of this feature's scope but must be tracked separately.

## Open Questions

1. **Where do guest token records live?** S3 (consistent with the old rate-limit pattern, no new infra) or DynamoDB (consistent with the new `users` table, faster, supports TTL). Planner to decide based on simplicity vs. consistency.
2. **Paid daily cap value and Stripe price.** The user explicitly deferred these pending cost analysis. Plumbing must accept them as env vars / Stripe price IDs; the values will be set at deployment time.
3. **Cost ceiling replacement strategy** (per-model daily budgets, CloudWatch billing alarms, provider spend caps). Important enough that it should likely be a sibling brainstorm/plan, not silently dropped.
4. **What happens to in-flight free-tier sessions when the user upgrades mid-session?** Probably the new tier takes effect on the next request; planner to confirm.
5. **What happens when a paid subscription lapses (`invoice.payment_failed` then `customer.subscription.deleted`)?** Likely demote to free tier on the next request; grace period TBD.
6. **Should guests get a CAPTCHA** to slow down automated guest-quota draining? Out of scope for v1 but worth flagging.

## Relevant Codebase Context

- `backend/src/lambda_function.py` — main router, contains `_parse_and_validate_request` (current rate-limit integration point) and all endpoint handlers. The tier-resolution + quota-enforcement layer slots in here, replacing the `rate_limiter.check_rate_limit(ip)` call around line 135.
- `backend/src/utils/rate_limit.py` — to be **deleted**. Existing pattern (S3 + ETag conditional writes) is a useful reference for any future S3-backed counter logic but the module itself goes away.
- `backend/src/utils/error_responses.py` — add new error factories for `auth_required`, `tier_quota_exceeded`, `subscription_required`, etc.
- `backend/src/jobs/manager.py` — uses S3 + optimistic locking via version field; useful pattern reference if guest tokens end up in S3.
- `backend/src/config.py` — new env vars land here as module-level constants alongside `global_limit`, `ip_limit`, etc. Pattern to follow: env var → typed module constant → imported by `lambda_function.py`.
- `backend/template.yaml` (AWS SAM) — new resources: `AWS::Cognito::UserPool`, `AWS::Cognito::UserPoolClient`, `AWS::Cognito::UserPoolDomain`, `AWS::DynamoDB::Table` for users, IAM permissions for the Lambda role to read/write the new table, JWT authorizer on `/iterate` and `/outpaint` routes, new routes `/stripe/webhook`, `/billing/checkout`, `/billing/portal`, `/me`.
- `backend/.env.example` — new vars must be added here (auth + billing + quota knobs).
- `frontend/src/stores/useAppStore.ts` (and sibling stores) — Zustand state needs new slices for `auth` (tokens, user info) and `billing` (tier, quota usage). Tier-gated UI bits live in `ResponsiveLayout` / `ModelColumn` / `IterationCard` / `IterationInput`.
- `frontend/src/api/` — API client needs to attach `Authorization: Bearer <id_token>` to authenticated requests and handle 401/402/403/429 responses gracefully.
- Test patterns: backend uses pytest + moto for AWS mocks (`tests/backend/unit/`); frontend uses Vitest + RTL (`frontend/tests/__tests__/`). Add `tests/backend/unit/test_tier_quota.py`, `test_stripe_webhook.py`, `test_guest_token.py`; add frontend tests for auth store and tier-gated components.
- CI: `.github/workflows/ci.yml` enforces 80% backend coverage and frontend coverage gate — new modules must include tests to clear the gate.

## Technical Constraints

- **Lambda**: 900s timeout, 3008 MB memory, 10 reserved concurrent executions — plenty of headroom for the additional DynamoDB calls and JWT verification.
- **API Gateway HttpApi**: 50 r/s steady, 100 burst — unchanged.
- **Cognito JWT**: Tokens are large (~1–2 KB); they ride in the `Authorization` header and are validated by Gateway before reaching Lambda on protected routes.
- **DynamoDB**: New `users` table is on-demand billing for v1. Single-item reads/writes per request; well within free tier at expected scale.
- **Stripe**: Webhook signature verification requires the raw request body (not parsed JSON). Lambda receives the raw body in `event["body"]` already, so this works, but care is needed not to re-serialize before verifying.
- **Open-source contributor experience**: With `AUTH_ENABLED=false` and `BILLING_ENABLED=false`, no AWS resources beyond the existing S3 bucket should be required. The DynamoDB table can be conditionally created in SAM, or always created and simply unused — planner to decide.
- **Backwards compatibility**: There are no existing user accounts (the app is anonymous today), so cutover is clean. Existing in-flight sessions in S3 are unaffected.
- **Secrets**: Stripe secret key and webhook signing secret must be stored in AWS Secrets Manager or SSM Parameter Store, not in plain env vars in the SAM template. Planner to decide which.
- **CORS**: New endpoints (`/me`, `/billing/*`, `/stripe/webhook`) need to be added to the existing CORS allow-list logic in `response()`.
- **Existing CLAUDE.md** documents the API surface and env vars exhaustively — both must be updated as part of the implementation.
