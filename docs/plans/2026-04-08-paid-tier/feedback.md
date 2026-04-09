# Feedback Log

## Active Feedback

<!-- Reviewers append new items here with Status: OPEN -->

## Resolved Feedback

<!-- Generators move resolved items here with a resolution note -->

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
