# Architecture Decision Records

## The rule

**ADRs that govern live code live in this directory.** A decision anyone has to
know about to read the code correctly belongs here, numbered sequentially, and
every citation of it — in code, tests or documentation — carries the **path**,
not just the number:

```text
see docs/adr/005-dalle3-iteration-uses-gpt-image-1.md
```

**Per-plan `Phase-0.md` files under `docs/plans/` are historical.** They record
what was decided while a plan was being executed, and their ADR numbers are
**local to that plan**. Two plans can each have an ADR-5 meaning entirely
different things, and two of them did: "DALL-E 3 Iteration Strategy"
(`docs/plans/2026-04-06-audit-pixel-prompt/Phase-0.md:57`) and "Presigned URL
Download" (`docs/plans/2026-04-15-ux-enhancements/Phase-0.md:153`). A bare
`ADR-5` in a docstring identified neither.

The numbers in this directory therefore do **not** preserve the numbers a
decision had in its source plan. 003 through 008 were assigned in promotion
order, continuing from 002. That 005 kept its digit is a coincidence.

## Index

| ADR                                             | Decision                                                                                                    |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| [001](001-fixed-four-models.md)                 | Exactly four models, enable/disable only — no dynamic model registry                                        |
| [002](002-s3-session-state.md)                  | Session state is a JSON document in S3 with ETag optimistic locking. Amended 2026-07-27                     |
| [003](003-dynamodb-single-table.md)             | One DynamoDB table with prefixed partition keys for users, guests, counters, spend, metrics and prompts     |
| [004](004-ratelimiter-removed.md)               | `utils/rate_limit.py` deleted; DynamoDB tier quotas are the single volume gate                              |
| [005](005-dalle3-iteration-uses-gpt-image-1.md) | DALL-E 3 cannot edit, so `/iterate` and `/outpaint` use `gpt-image-1` regardless of `OPENAI_MODEL_ID`       |
| [006](006-firefly-token-cache.md)               | Firefly OAuth2 token cached at module scope with a 50-minute TTL. Supersedes the per-request-token decision |
| [007](007-me-endpoint-contract.md)              | `GET /me` returns tier, the binding quota window, billing state, admin groups and model preference          |
| [008](008-async-generate-dispatch.md)           | `POST /generate` answers `202` and hands provider work to an asynchronous self-invocation                   |

## Writing a new one

Follow the shape of the existing files: `## Status`, `## Context` (including the
options rejected), `## Decision`, `## Code Governed`, `## Consequences` with
Positive / Negative / Neutral.

`## Code Governed` is what makes an ADR checkable. Name the files by path. An
ADR that names no code cannot be verified against the repository and will drift
without anyone noticing.

Superseding an earlier ADR is fine. Doing it silently is not: say so in the
`## Status` section of both, as 004 and 006 do. An ADR that reverses an earlier
one without saying so is how `README.md` came to describe a rate limiter that
had been deleted.
