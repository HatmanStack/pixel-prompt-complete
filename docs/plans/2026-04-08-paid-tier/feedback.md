# Feedback Log

## Active Feedback

<!-- Reviewers append new items here with Status: OPEN -->

## Positive findings (tool evidence)

- `ruff check backend/src/` returned `All checks passed!`.
- `backend/src/billing/webhook.py:41-45` handles base64-encoded bodies
  (`event.get("isBase64Encoded")`) and passes the untouched decoded string
  to `stripe.Webhook.construct_event` at line 142. No JSON parse precedes
  verification. Signature header lookup is case-insensitive (lines 33-38).
- Dispatch covers all five event types required by ADR-5
  (`backend/src/billing/webhook.py:112-118`), and `_on_payment_failed`
  preserves current tier while setting `subscriptionStatus="past_due"`
  (lines 102-109).
- `/me` billing block is populated from the user record in
  `backend/src/lambda_function.py:938-950`, with
  `portalAvailable = bool(user.get("stripeCustomerId"))`.
- With the workaround `PYTHONPATH=backend/src:tests/backend/unit`,
  273 tests pass. Billing coverage: `checkout.py` 100%, `portal.py` 100%,
  `stripe_client.py` 100%, `webhook.py` 94%. Total coverage 90%.
- Commits land in expected order: `8e2d2aa`, `a61e8f5`, `f02e73f`,
  `197c820`, plus plan-checklist commit `0f5dc0b`. `/me` billing block was
  already added in Phase 2 commit `e8bf4bd`.

CHANGES_REQUESTED

## Resolved Feedback

<!-- Generators move resolved items here with a resolution note -->

### CODE_REVIEW Phase 3: Webhook test breaks documented pytest invocation

Status: RESOLVED

Resolution: Changed `tests/backend/unit/test_stripe_webhook.py:14` from
`from fixtures.stripe_events import ...` to
`from .fixtures.stripe_events import ...`, matching the relative-import
convention used by the other tests in `tests/backend/unit/`. Verified with
`PYTHONPATH=backend/src pytest tests/backend/unit/ -v` — all 273 tests
pass, no collection errors.

### CODE_REVIEW Phase 3: Phase-3 verification checkbox is inaccurate

Status: RESOLVED

Resolution: With the import fix above, the documented command
`PYTHONPATH=backend/src pytest tests/backend/unit/ -v ...` now runs to
completion with 273 passing tests, so the `[x]` checkbox in
`docs/plans/2026-04-08-paid-tier/Phase-3.md:234` is accurate.

### PLAN_REVIEW: Phase 3.1 references nonexistent requirements-lock.txt

Status: RESOLVED

Resolution: Phase-3 Task 3.1 updated to state explicitly that the project has no `requirements-lock.txt` and that `backend/src/requirements.txt` is the sole manifest. The lockfile instruction was removed.

### PLAN_REVIEW: Phase 4.8 points at frontend/src/components/Header.tsx which does not exist

Status: RESOLVED

Resolution: Verified via Glob that `frontend/src/components/common/Header.tsx` exists. Phase-4 Task 4.8 now names this exact path and notes it is mounted via `ResponsiveLayout` -> `DesktopLayout`/`MobileLayout`.

### PLAN_REVIEW: Phase 1.2 misses handle_log_endpoint rate_limiter usage

Status: RESOLVED

Resolution: Phase-2 Task 2.6 now enumerates both current `rate_limiter.` call sites (line 135 in `_parse_and_validate_request` and line 741 in `handle_log_endpoint`) and instructs the engineer to grep for any third site before deletion.

### PLAN_REVIEW: Phase 2.6 ValidatedRequest dataclass conflict with existing definition

Status: RESOLVED

Resolution: Verified the existing `ValidatedRequest` is a `@dataclass` with fields `body: dict[str, Any]`, `ip: str`, `prompt: str` (lambda_function.py lines 96-102). Phase-2 Task 2.6 updated to instruct extending the existing dataclass by appending `tier: TierContext` while preserving the original fields and docstring verbatim.

### PLAN_REVIEW: Phase 1.5 splits proxy routes without confirming current shape

Status: RESOLVED

Resolution: Inspected `backend/template.yaml` — routes are already defined as explicit `HttpApi` events (no `ANY /{proxy+}` catch-all). Phase-1 Task 1.5 updated to state this definitively and removes the conditional; the engineer only needs to add the `Auth` block to existing `/iterate` and `/outpaint` event entries.
