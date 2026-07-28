# ADR 003: Single-Table DynamoDB Design

## Status

Accepted

Promoted from `docs/plans/2026-04-08-paid-tier/Phase-0.md` — ADR-3 (the users
table) and ADR-4 (guest token storage in the same table under a prefixed key).
The numbers in that file are local to that plan and do not correspond to the
numbers here; see [README.md](README.md).

## Context

The paid tier needed per-identity state that outlives a Lambda invocation: tier,
Stripe linkage, and rolling-window call counters. ADR 002 had already chosen S3
for session state, so the obvious question was whether the same store could
carry this too.

Options considered:

1. **Keep it in S3.** Rejected. S3 has no atomic counters. A quota increment
   becomes a read-modify-write behind an ETag-conditional PUT with a retry loop,
   which is exactly what the `RateLimiter` this repository used to carry did —
   and it over-counted under contention by construction. Quota is the one thing
   in the product where a lost update is a billing error.
1. **One DynamoDB table per concern** (users, guests, counters, spend). Rejected.
   Every table is another resource to provision, another IAM statement, another
   TTL configuration and another thing to get wrong in the template, for records
   that are never joined and never queried together.
1. **One DynamoDB table with prefixed partition keys.** Chosen.

## Decision

One DynamoDB table, `USERS_TABLE_NAME` (default `pixel-prompt-users`), declared
at `backend/template.yaml:1109`. Partition key `userId` (String), no sort key,
`PAY_PER_REQUEST` billing, TTL enabled on the `ttl` attribute, point-in-time
recovery on.

Every record type that is not session state lives in that table, distinguished
by a prefix on `userId`:

| Key form                                | Holds                                                              |
| --------------------------------------- | ------------------------------------------------------------------ |
| `<cognito-sub>`                         | account record: tier, email, Stripe ids, rolling-window counters   |
| `guest#<token_id>`                      | guest counter bucket, TTL-expired                                  |
| `guest#__global__`                      | global cap across all guests in a window                           |
| `guest#ip#<ip-hash>`                    | per-source-IP guest counter                                        |
| `anon#<ip-hash>`                        | anonymous-tier counters when `AUTH_ENABLED=false`                  |
| `model#<name>`                          | per-model daily generation counter (the cost ceiling)              |
| `config#model#<name>`                   | runtime model kill switch set from `/admin/models/{model}/disable` |
| `spend#<YYYY-MM-DD>`, `spend#<YYYY-MM>` | dollar-denominated spend accumulators                              |
| `metrics#<YYYY-MM-DD>`                  | daily metrics snapshot written by the EventBridge schedule         |
| `revenue#current`                       | revenue rollup                                                     |
| `event#<stripe-event-id>`               | Stripe webhook dedup claim, leased and TTL-expired                 |
| `prompt#<uuid>`                         | prompt history row                                                 |

Two global secondary indexes: `PromptHistoryIndex` (`promptOwner` HASH,
`createdAt` RANGE, projection ALL) serves `/prompts/history` and the
`GLOBAL#RECENT` feed behind `/prompts/recent`; `StripeCustomerIndex`
(`stripeCustomerId` HASH, projection KEYS_ONLY) is the reverse lookup from a
Stripe customer to a `userId`, needed because real `customer.subscription.*`
payloads carry neither `client_reference_id` nor `metadata.userId` for
subscriptions created before `subscription_data.metadata` was set at checkout.

Guest identity is an HMAC-signed cookie, not a stored credential:
`base64url(token_id).base64url(hmac_sha256(token_id, GUEST_TOKEN_SECRET))`,
transported as an `HttpOnly; Secure; SameSite=Lax` cookie named `pp_guest`. The
server re-validates the HMAC on every request and issues a new token when it is
invalid or expired, so the table row is a counter bucket rather than a session.

All counter updates go through conditional `UpdateItem` calls so that window
reset and increment are one atomic operation. There is no read-then-write.

## Code Governed

- `backend/src/users/repository.py` — the table's only writer for account,
  guest, counter, webhook and revenue records; `_NON_USER_PREFIXES` there is
  the list the admin scan uses to tell records apart
- `backend/src/users/tier.py` — mints the `guest#` and `anon#` keys
- `backend/src/users/quota.py` — rolling-window enforcement
- `backend/src/auth/guest_token.py` — HMAC sign/verify for the `pp_guest` cookie
- `backend/src/ops/model_counters.py`, `backend/src/ops/cost_meter.py`,
  `backend/src/ops/metrics.py` — the `model#`, `spend#` and `metrics#` records
- `backend/src/prompts/repository.py` — the `prompt#` records and both indexes
- `backend/template.yaml:1109` — the table resource

## Consequences

### Positive

- **Atomic counters.** Quota, per-model caps and spend all increment without a
  read-modify-write race.
- **One resource, one IAM statement, one TTL configuration.** Adding a record
  type is a new key prefix, not a new CloudFormation resource.
- **Native expiry.** Guest buckets, IP buckets, webhook claims and spend
  accumulators all set `ttl` and are reaped by DynamoDB rather than by a
  scheduled job.
- **Empty tables cost nothing.** The table is created by SAM even when
  `AUTH_ENABLED=false`, so open-source deployments still get metering without a
  separate provisioning step.

### Negative

- **The key prefix is the schema.** Nothing in DynamoDB enforces that
  `spend#2026-07-27` has spend attributes; only the code that writes it does.
  `_NON_USER_PREFIXES` has to be kept in step with every new prefix or the admin
  user scan starts returning counters as if they were people.
- **Attribute names are shared across unrelated record types.** `windowStart`
  means one thing on an account and another on a global guest bucket.
- **Scans, not queries, for admin listing.** `scan_users` pages a filtered scan;
  there is no index over tier.

### Neutral

- Session state deliberately stays in S3. See
  [002-s3-session-state.md](002-s3-session-state.md), whose "no additional AWS
  service" premise this decision retired — the amendment there records what
  changed.
