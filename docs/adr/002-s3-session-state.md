# ADR 002: S3 for Session State Management

## Status

Accepted

## Context

Session state (prompt, model iterations, image keys, status) must persist across multiple Lambda invocations for the iterate/outpaint/status workflow. Options considered:

1. **DynamoDB** — Low-latency key-value store, natural fit for session data
2. **S3** — Object storage with JSON documents
3. **ElastiCache/Redis** — In-memory, fastest reads

## Decision

Use S3 with JSON documents at `sessions/{sessionId}/status.json` for all session state. Use ETag-based conditional writes for optimistic locking on concurrent updates.

## Consequences

### Positive

- **Simpler infrastructure**: No additional AWS service to provision or monitor
- **S3 lifecycle policies**: Sessions auto-deleted after 30 days via bucket lifecycle rules
- **No provisioned capacity**: No read/write capacity planning, no throttling at our scale
- **Cost**: Effectively free at our request volume (S3 GET/PUT pricing)
- **Context co-location**: Session state and context windows stored in the same bucket under the same prefix

### Negative

- **Higher latency**: S3 GET/PUT (~50-100ms) vs DynamoDB (~5-10ms) per operation
- **No query capability**: Cannot query sessions by prompt or status without scanning
- **Optimistic locking complexity**: ETag-based conditional writes require retry logic (`MAX_RETRIES=3`)
- **No atomic counters**: Rate limiting uses the same ETag pattern, adding retry overhead

### Why acceptable

- Image generation takes 5-30 seconds per model — 100ms of S3 overhead is negligible
- Session queries are only by ID (from the frontend session cookie), never by attribute
- The 3-retry optimistic lock handles the ThreadPoolExecutor concurrency (4 workers updating same session)
- Rate limiting is best-effort; a small window of over-count on ETag conflict is acceptable

## Amendment — 2026-07-27

Everything above is left as written. It is the record of what was known when the
decision was made, and rewriting it would destroy that.

### What changed

**The premise "no additional AWS service to provision or monitor" no longer
holds.** `backend/template.yaml:1109` declares a DynamoDB table, and it carries
users, guest buckets, tier quotas, per-model daily counters, spend accumulators,
metrics snapshots, Stripe webhook dedup claims and prompt history. See
[003-dynamodb-single-table.md](003-dynamodb-single-table.md).

Two of the consequences above were retired by that table rather than by this
decision:

- "No atomic counters: **Rate limiting** uses the same ETag pattern" and "Rate
  limiting is best-effort" describe `utils/rate_limit.py`, which no longer
  exists. Counting moved to DynamoDB's conditional `UpdateItem` precisely
  because the ETag pattern under-counted. See
  [004-ratelimiter-removed.md](004-ratelimiter-removed.md).
- "No provisioned capacity" still holds for S3, and holds for the table too —
  it is `PAY_PER_REQUEST`.

### Does the decision stand?

**Yes, but the argument for it is different now.** Keeping session state in S3
was originally a way to _avoid adding a store_. It is now a choice _between two
stores the stack already has_, and it has to be defended on its own merits:

- Session documents are read and written whole, by id, and never queried by
  attribute. That is object-storage shaped.
- The document is co-located with what it indexes. Up to 28 image objects and
  the `status.json` describing them live in one bucket under one prefix; the
  alternative splits a session across two services for no read the product
  makes.
- S3 lifecycle expiry deletes a session and its images together in one rule. In
  DynamoDB the metadata would expire by TTL and the images would still need the
  bucket rule, so the two could diverge.
- ETag-conditional writes give the optimistic locking the iteration path needs,
  and the concurrency involved is four workers on one document, not the
  high-contention counter case that defeated the rate limiter.

The latency and query-capability costs listed above are unchanged and still
accepted.

### Open question this leaves

`/gallery/list` is an O(sessions) S3 `LIST` because there is no index of
galleries anywhere. Phase 4 of the 2026-07 audit remediation bounded the
per-folder fan-out but could not remove the top-level listing — closing that
properly means writing a gallery index row at session creation, which is a
schema change to the table ADR 003 describes. Recorded, with a retirement
condition, in
[../follow-ups/2026-07-audit-deferred.md](../follow-ups/2026-07-audit-deferred.md).
