# ADR 006: Firefly OAuth2 Token Cached at Module Scope with a 50-Minute TTL

## Status

Accepted. **Supersedes** "Firefly OAuth2 Per-Request Token"
(`docs/plans/2026-04-06-audit-pixel-prompt/Phase-0.md:49`), which decided the
opposite — fetch a fresh token on every handler invocation, no caching.

Promoted from `docs/plans/2026-04-17-audit-pixel-prompt-followup/Phase-0.md:25`.
The numbers in per-plan `Phase-0.md` files are local to that plan and do not
correspond to the numbers here; see [README.md](README.md).

## Context

Adobe Firefly authenticates with an OAuth2 client-credentials exchange against
Adobe IMS: `client_id` + `client_secret` to
`https://ims-na1.adobelogin.com/ims/token/v3`, returning a bearer token.

The superseded decision fetched one per invocation and gave two reasons: Lambda
is stateless, and module-level state is fragile across container reuse. Both are
half-true and neither survived contact with the numbers:

- **Adobe IMS tokens are valid for 24 hours.** Discarding a 24-hour credential
  after one call and immediately asking for another is not statelessness, it is
  waste.
- **The token fetch is not free.** It adds roughly 500ms to every Firefly call.
  On the outpaint chain — token, upload, generate, download — that is one of
  four sequential round trips inside a bounded budget.
- **It is a rate-limit surface.** Every generation, iteration and outpaint hit
  Adobe's token endpoint, so the token endpoint saw the same request volume as
  the image endpoint.

Options considered:

1. **Keep the per-request fetch.** Rejected on the numbers above.
1. **Cache in DynamoDB or S3.** Rejected. A shared cache for a credential that
   any container can mint for itself in one call adds a store round trip, an
   IAM grant and a new failure mode to save a call that is already cheap
   relative to image generation.
1. **Cache at module scope inside the container.** Chosen.

## Decision

Cache the access token in module-level state in
`backend/src/models/providers/firefly.py`, with a **50-minute TTL** against
Adobe's 24-hour validity — refreshing well before expiry rather than at it, so a
clock skew or a slow call never presents an expired token.

The cache is guarded by a `threading.Lock`, because `/generate` dispatches
providers from a `ThreadPoolExecutor` and two workers can miss the cache at
once.

Scope is explicit and deliberately narrow: **one Lambda execution environment**.
It resets on cold start, it is not shared between concurrent containers, and it
assumes one set of Firefly credentials per container.

## Code Governed

- `backend/src/models/providers/firefly.py` — the module docstring states the
  cache and its TTL; `_token_lock`, `_cached_token`, `_cached_token_expiry` and
  `_TOKEN_TTL` implement it, and `_get_firefly_access_token` is the only reader
- `backend/src/utils/clients.py` — `FIREFLY_TOKEN_TIMEOUT` bounds the token
  call itself, and `firefly_call_timeout` divides the request budget across the
  four sequential calls the chain makes

## Consequences

### Positive

- **~500ms saved per Firefly call** after the first in a warm container.
- **Adobe IMS sees roughly one token request per container lifetime** instead of
  one per image operation.
- **No new dependency.** Process memory needs nothing provisioned, granted or
  monitored.

### Negative

- **Cold starts pay the full cost**, and with `ReservedConcurrentExecutions: 10`
  and bursty traffic a meaningful share of calls can be cold.
- **The cache is per container**, so ten warm containers hold ten tokens. That
  is fine for Adobe's model and would not be for a provider that limited
  concurrent tokens.
- **A revoked credential is honoured for up to 50 minutes** in an already-warm
  container. Rotating Firefly credentials is not instant.

### Neutral

- The 50-minute figure is a margin, not a constraint from Adobe. It can be
  raised toward 24 hours; the only reason not to is that the revocation window
  above grows with it.
