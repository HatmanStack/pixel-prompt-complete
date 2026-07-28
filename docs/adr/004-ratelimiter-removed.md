# ADR 004: `utils/rate_limit.py` Removed in Favour of DynamoDB Tier Quotas

## Status

Accepted. **Supersedes** the S3-backed rate limiter described in
[002-s3-session-state.md](002-s3-session-state.md), which listed "Rate limiting
uses the same ETag pattern" as an accepted cost and "Rate limiting is
best-effort" as a reason it was acceptable. Neither statement describes anything
that exists: the module was deleted in `c3fdd4c`, and `backend/src/utils/` now
contains `clients`, `content_filter`, `error_responses`, `http`, `logger`,
`outpaint`, `retry` and `storage`, and nothing else. The amendment on 002
records the same thing from that side.

Promoted from `docs/plans/2026-04-08-paid-tier/Phase-0.md` (ADR-8). The numbers
in that file are local to that plan and do not correspond to the numbers here;
see [README.md](README.md).

## Context

Before the tier system there were two independent limiters:

- `backend/src/utils/rate_limit.py`, a `RateLimiter` holding a global hourly
  count and a per-IP daily count as JSON objects in S3, mutated through the same
  ETag-conditional-write retry loop ADR 002 describes.
- Nothing else. There was no notion of an account, so there was no notion of a
  limit that belonged to one.

Adding tier quotas would have produced two systems answering the same question
with different state, different windows and different failure behaviour on the
same request. Two limiters that disagree is worse than either alone: the one
that is easier to reason about is the one operators tune, and the other keeps
rejecting.

The S3 limiter was also structurally lossy. Its counter was a read, an
increment, and a conditional PUT; on ETag conflict it retried, and on retry
exhaustion it let the request through. Under the concurrency it existed to
bound, it under-counted.

## Decision

Delete `backend/src/utils/rate_limit.py` and its tests
(`tests/backend/unit/test_rate_limit.py`) outright. The DynamoDB-backed quota
layer is the single source of truth for how many calls an identity may make.

Nothing was kept for compatibility. A limiter that is present but unreferenced
is a limiter a future reader will assume is enforcing something.

## Code Governed

The absence is the decision, so what this ADR governs is what replaced it:

- `backend/src/users/quota.py` — tier quota enforcement, and the only module
  that decides whether a call is allowed on volume grounds
- `backend/src/users/repository.py` — the atomic counters behind it
- `backend/src/ops/model_counters.py` — per-model daily caps, which bound
  provider spend rather than per-caller volume and are a separate concern
- `backend/src/utils/` — verifiable by listing it: no `rate_limit.py`

## Consequences

### Positive

- **One answer per request.** `enforce_quota` is the only volume gate on
  `/generate`, `/iterate` and `/outpaint`.
- **Atomic counting.** The DynamoDB conditional `UpdateItem` cannot under-count
  the way the ETag retry loop did.
- **Limits are per identity, not per IP.** Shared-NAT users are no longer
  metered as one caller, except deliberately in the `anon` and `guest#ip#` paths
  where there is no identity to meter instead.

### Negative

- **There is no limiter without DynamoDB.** With the store unreachable, quota
  fails open by documented policy. The S3 limiter would have failed open too, so
  this is not a regression, but it is now the only volume bound and it depends
  on one service. The per-container circuit breaker in
  `backend/src/ops/store_breaker.py` is the bound that does not read DynamoDB.
- **Open-source deployments now touch DynamoDB.** `AUTH_ENABLED=false` disables
  identity, not metering: anonymous callers resolve to the `anon` tier and are
  metered against a hash of their source IP. Metering requires persistence.

### Neutral

- Two quota systems still coexist in the code — the credit ledger
  (`CREDITS_ENABLED`) and call counting — and consolidating them is a product
  decision, not a cleanup. It is recorded in
  [../follow-ups/2026-07-audit-deferred.md](../follow-ups/2026-07-audit-deferred.md).
