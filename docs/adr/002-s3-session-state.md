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
