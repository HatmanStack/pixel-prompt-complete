# Operational Safety and Admin Tooling

This plan adds four interlocking features to the Pixel Prompt platform: a per-model cost-ceiling circuit breaker, Cloudflare Turnstile CAPTCHA for guest abuse prevention, an admin dashboard with user management, and Amazon SES email notifications for account lifecycle events. Together these close the operational gaps left after the paid-tier v1 shipped: no platform-level cost protection, no bot prevention, no admin visibility, and no proactive user communication.

All four features are gated behind independent feature flags (`CAPTCHA_ENABLED`, `SES_ENABLED`, `ADMIN_ENABLED`) that default to `false`, preserving the open-source zero-setup experience. The cost-ceiling reuses the existing DynamoDB single-table design and atomic counter pattern. The admin dashboard is a lazy-loaded `/admin` route in the React app, gated by a Cognito `admins` group. Revenue tracking piggybacks on the existing Stripe webhook dispatch.

The plan is split into four phases. Phase 1 handles the backend safety layer (cost ceiling, suspension, CAPTCHA verification). Phase 2 covers email notifications and operational metrics. Phase 3 builds the admin API endpoints. Phase 4 delivers the admin frontend dashboard.

## Prerequisites

- Pixel Prompt paid-tier v1 fully deployed (ADR-1 through ADR-10 from `docs/plans/2026-04-08-paid-tier/Phase-0.md`)
- Node v24 (nvm), Python 3.13 (uv), SAM CLI installed
- For CAPTCHA: a Cloudflare Turnstile site key and secret key
- For SES: a verified SES sending domain (sandbox exit required for production)
- For Admin: at least one Cognito user manually added to the `admins` group

## Phase Summary

| Phase | Goal | Token Estimate |
|-------|------|----------------|
| 0 | Architecture decisions, conventions, test strategy | ~5,000 |
| 1 | Cost ceiling, account suspension, CAPTCHA verification | ~40,000 |
| 2 | SES email notifications, operational metrics, revenue tracking | ~35,000 |
| 3 | Admin API endpoints (users, models, notifications, metrics) | ~40,000 |
| 4 | Admin frontend dashboard (lazy-loaded React routes) | ~45,000 |

## Navigation

- [Phase-0.md](Phase-0.md) - Architecture and conventions
- [Phase-1.md](Phase-1.md) - Cost ceiling, suspension, CAPTCHA
- [Phase-2.md](Phase-2.md) - Email notifications, metrics, revenue
- [Phase-3.md](Phase-3.md) - Admin API endpoints
- [Phase-4.md](Phase-4.md) - Admin frontend dashboard
- [feedback.md](feedback.md) - Review feedback tracker
