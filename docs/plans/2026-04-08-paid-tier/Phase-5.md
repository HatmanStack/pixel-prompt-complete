# Phase 5: Documentation and Cleanup

## Phase Goal

Update project documentation to match the new reality, confirm CI gates pass end-to-end, and capture the cost-ceiling follow-up so it is not lost.

**Success criteria:**

- `CLAUDE.md` accurately describes the new endpoints, env vars, and tier system.
- `backend/.env.example` is authoritative.
- A follow-up doc exists for the cost-ceiling work so Phase-0 ADR-8's flag is not orphaned.
- CI (lint + typecheck + tests + coverage + markdownlint) passes on the branch.

**Token estimate:** ~15k

## Prerequisites

- Phases 1–4 complete.

## Task 5.1: Update CLAUDE.md

### Files to Modify

- `CLAUDE.md`

### Implementation Steps

1. Update the API endpoints table: add `/me`, `/billing/checkout`, `/billing/portal`, `/stripe/webhook`. Mark `/iterate` and `/outpaint` as requiring JWT.
1. Update the Environment Variables section:
    - Remove `GLOBAL_LIMIT`, `IP_LIMIT`, `IP_INCLUDE`.
    - Add the Tier system table (feature flags, Cognito, DynamoDB, guest, free, paid, Stripe) matching `Phase-0.md` exactly.
1. Update "Backend Module Structure" to include `auth/`, `billing/`, `users/` modules. Remove `utils/rate_limit.py`.
1. Update "Important Constraints": note the new DynamoDB table and JWT authorizer.
1. Add a short "Open-Source Mode" callout explaining the `AUTH_ENABLED=false, BILLING_ENABLED=false` default.

### Commit Message Template

```text
docs(claude): document tier system, new endpoints and env vars
```

## Task 5.2: Verify .env.example Consistency

### Files to Modify

- `backend/.env.example` (double-check after Phase 1)
- `frontend/.env.example`

### Implementation Steps

1. Diff `Phase-0.md` env var list against `backend/.env.example`. Add any missing entries. Add a comment block at the top explaining the feature flags.
1. Confirm `frontend/.env.example` matches Task 4.1.

### Commit Message Template

```text
docs(env): sync example env files with plan
```

## Task 5.3: Create Cost-Ceiling Follow-Up Doc

### Goal

Capture the sibling work flagged in Phase-0 ADR-8 so it does not vanish.

### Files to Create

- `docs/follow-ups/cost-ceiling.md`

### Implementation Steps

1. Short doc (one page) describing the problem (tier quotas don't bound catastrophic spend), candidate mitigations (per-model daily budgets enforced in Lambda, CloudWatch billing alarms, provider-side spend caps), and a recommendation to run `/brainstorm` for it as a new feature.

### Commit Message Template

```text
docs: capture cost-ceiling follow-up from paid-tier plan
```

## Task 5.4: Run Full CI Locally

### Implementation Steps

1. From repo root:

    ```bash
    ruff check backend/src/
    PYTHONPATH=backend/src pytest tests/backend/unit/ -v --cov=backend/src --cov-fail-under=80
    cd frontend && npm run lint && npm run typecheck && npm test && cd ..
    markdownlint docs/plans/2026-04-08-paid-tier/ CLAUDE.md
    cd backend && sam build && cd ..
    ```

1. Any failure that is not a plan-specific bug is fixed here before handing off.
1. No commit unless fixes are needed.

### Verification Checklist

- [x] All commands succeed.

## Phase Verification

- [x] Tasks 5.1–5.3 committed.
- [x] Task 5.4 verification clean.
- [x] `grep -r "rate_limit\|RateLimiter\|GLOBAL_LIMIT\|IP_LIMIT" backend/ docs/ CLAUDE.md` returns only planned references (e.g., this plan's brainstorm.md which quotes the old names historically).
- [x] `feedback.md` has no OPEN items from any iteration.
