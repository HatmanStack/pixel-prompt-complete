# Paid Tier (Cognito + Stripe)

Plan ID: `2026-04-08-paid-tier`

## Overview

Introduce a three-level tier system (guest / free / paid) to Pixel Prompt Complete, backed by AWS Cognito Hosted UI for auth and Stripe Checkout for billing. The existing IP-based `RateLimiter` is deleted and replaced with a per-user quota layer keyed off Cognito `sub` (for signed-in users) and a signed guest token + IP (for anonymous users). State lives in a new DynamoDB `users` table.

Feature flags `AUTH_ENABLED` and `BILLING_ENABLED` preserve the open-source contributor experience: with both flags off, the app behaves exactly as it does today.

## Prerequisites

- AWS account with SAM CLI deploy access (for Cognito, DynamoDB, API Gateway changes).
- Stripe account with test + live API keys and a configured subscription product/price.
- SSM Parameter Store (SecureString) access for Stripe secrets.
- Read `docs/plans/2026-04-08-paid-tier/brainstorm.md` for the full decision log.
- Read `Phase-0.md` before reading any implementation phase.

## Phase Summary

| Phase | Title | Focus | Est. tokens |
|-------|-------|-------|-------------|
| 0 | Architecture and Conventions | ADRs, data model, env vars, test strategy, project conventions | ~15k |
| 1 | Infrastructure and Config Scaffolding | SAM template (Cognito, DynamoDB, JWT authorizer, routes), `config.py` feature flags, `.env.example` | ~35k |
| 2 | Tier Resolution and Quota Enforcement (Backend Core) | New `utils/tier.py`, `utils/quota.py`, `utils/guest_token.py`; delete `utils/rate_limit.py`; wire into `_parse_and_validate_request`; `/me` endpoint | ~55k |
| 3 | Stripe Billing Integration | `/billing/checkout`, `/billing/portal`, `/stripe/webhook` with signature verification; webhook-driven tier updates | ~50k |
| 4 | Frontend Auth and Billing UX | Cognito Hosted UI redirect, token storage, auth/billing Zustand slices, tier-aware UI, checkout flow | ~55k |
| 5 | Documentation and Cleanup | Update `CLAUDE.md`, `backend/.env.example`, operational runbook, verify CI gates | ~15k |

## Files

- `README.md` (this file)
- `brainstorm.md` — original design discussion (source of truth for decisions)
- `feedback.md` — review feedback log (pipeline protocol)
- `Phase-0.md` — architecture decisions, data model, conventions
- `Phase-1.md` through `Phase-5.md` — implementation phases

## Out of Scope (Tracked Elsewhere)

- Global cost-ceiling circuit breaker (per-model daily budgets, billing alarms). Called out in Phase-0 as a sibling follow-up.
- Multiple paid tiers, credit packs, custom auth UI, social login, email notifications, admin dashboard, tax/refund logic.
