# ADR 007: `GET /me` Response Contract

## Status

Accepted

Promoted from `docs/plans/2026-04-08-paid-tier/Phase-0.md:115` (ADR-10). The
numbers in that file are local to that plan and do not correspond to the numbers
here; see [README.md](README.md). The contract below is what the handler
actually returns today, which has grown since that document was written.

## Context

The frontend has to render a quota indicator, an upgrade call to action, an
admin entry point and a per-user model preference. Each of those needs server
state the client cannot derive: which tier the caller is on, how much of the
window they have spent, whether Stripe has a customer for them, and which
Cognito groups they are in.

Options considered:

1. **One endpoint per concern** (`/tier`, `/quota`, `/billing/status`).
   Rejected. The client needs all of them on first paint and after every
   generation, so it would issue four requests where one suffices, and the four
   answers could disagree with each other.
1. **Put the quota in every response** that consumes quota. Rejected as the sole
   mechanism: the client also needs this before the user does anything, and on a
   page load with no generation in it.
1. **One `GET /me`, polled.** Chosen. `useMePolling` refreshes it, and the
   quota-consuming endpoints do not have to carry quota state.

## Decision

`GET /me` requires a JWT — it is one of the routes the API Gateway authorizer
gates — and returns `401` to an unauthenticated caller, `501` when
`AUTH_ENABLED=false`.

```json
{
  "userId": "cognito-sub",
  "email": "user@example.com",
  "tier": "free",
  "quota": {
    "windowSeconds": 3600,
    "windowStart": 1712600000,
    "generate": { "used": 1, "limit": 1 },
    "refine": { "used": 0, "limit": 2 }
  },
  "billing": {
    "subscriptionStatus": null,
    "portalAvailable": false
  },
  "groups": [],
  "modelChoices": ["gemini", "nova"],
  "preferredModel": "gemini"
}
```

Field rules:

- `quota` reports the **window that binds this caller**, not a fixed one. For
  `tier="paid"` it reports the daily counters (`windowSeconds` from
  `PAID_WINDOW_SECONDS`, `windowStart` from `dailyResetAt`, `generate` from
  `dailyGenerateCount`/`PAID_DAILY_GENERATE_LIMIT`, `refine` from
  `dailyCount`/`PAID_DAILY_LIMIT`). Every other tier reports the rolling free
  window. The shape is identical either way, so the client renders one
  component.
- `generate` is reported for paid users too. It was not, until paid generation
  gained a bound; a limit the user cannot see is a limit they experience as a
  bug.
- `billing.portalAvailable` is `true` exactly when a `stripeCustomerId` exists,
  because the Stripe customer portal cannot be opened without one.
- `groups` carries the caller's admin Cognito groups and is what gates the admin
  UI client-side. It is not what gates the admin API — that is checked
  server-side on every `/admin/*` call.
- `modelChoices` is the caller's refined-model history, highest first;
  `preferredModel` is its first element or `null`. Generating produces four
  images the user did not choose between, so refining one is the only per-user
  preference signal the product collects.

## Code Governed

- `backend/src/lambda_function.py` — `handle_me`, the sole producer
- `frontend/src/api/me.ts` — `MeResponse` and `fetchMe`, the sole consumer
- `frontend/src/hooks/useMePolling.ts` — refresh cadence

`MeResponse` declares a **subset**: it omits `modelChoices` and
`preferredModel`, which the server sends and the client currently ignores.
Extra fields are additive and safe, but the interface is not a complete
description of the payload — this document is.

## Consequences

### Positive

- **One request answers first paint.** Tier, quota, billing state, admin
  visibility and model preference arrive together and are internally consistent.
- **The quota shape is tier-independent**, so the indicator component has no
  tier branch in it.
- **Adding a field is backward compatible**, because the client reads named
  fields off a typed interface rather than a positional payload.

### Negative

- **It is polled**, so quota display lags the underlying counter by up to one
  poll interval. The counter itself is authoritative and enforced server-side,
  so the lag is cosmetic.
- **It fans out to several reads** — the quota window touch, and the model
  choices lookup — on an endpoint the client calls repeatedly.
- **The client type can drift from the payload** and did. Nothing checks the two
  against each other.

### Neutral

- Guest callers never see this endpoint: they have no JWT. Their quota is
  communicated through the `429` response body instead.
