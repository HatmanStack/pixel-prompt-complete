# Feedback Log

## Active Feedback

## Verification

VERIFIED — 13 of 17 health findings addressed in this pipeline (remaining 4 deferred to followup plan `2026-04-17-audit-pixel-prompt-followup`). All eval and doc findings addressed. 491 backend tests passing, 453 frontend tests passing. Zero regressions.

## Phase Approvals

### PHASE_APPROVED - Phase 2 [IMPLEMENTER]

Approved after 1 iteration. All 9 tasks verified against spec:

1. future.result() hardened with timeout and try-catch; outer TimeoutError handles stragglers
1. atexit.register(_shutdown_executors) with shutdown(wait=False) on both pools
1. No bare except-pass remains; all caught exceptions logged with correlation_id
1. enhance_timeout sourced from config.py (flat import, default 30.0s)
1. adapt_per_model accepts correlation_id parameter, warning log includes it
1. _adapt_prompts_for_models extracted with docstring explaining batch optimization
1. CORS wildcard warning emitted via StructuredLogger.warning when AUTH_ENABLED=true
1. All it.skip removed from galleryFlow.test.tsx (0 matches)
1. Coverage thresholds raised to 57/57/52/60 in vite.config.ts

Test results: 491 backend tests pass, 453 frontend tests pass, ruff clean. 11 commits in conventional format.

---

### PHASE_APPROVED - Phase 1 [HYGIENIST]

Approved after 1 iteration. All stale model name references fixed. 481 tests passing, ruff clean. Commit: 4d31cc2.

---

## Resolved Feedback

### PLAN_REVIEW (2026-04-17) - Iteration 1

#### Critical Issues

1. **Wrong import pattern in Phase 2 Task 4**: Plan incorrectly used `config.enhance_timeout` and `from config import config`, but config.py is a flat module.

**Status:** RESOLVED
**Resolution:** Updated Task 4 to use flat import pattern (`from config import enhance_timeout`) matching existing codebase conventions in `openai_provider.py` and `_common.py`.

---

#### Minor Issues

1. **Phase 2 Task 7 line reference inaccurate**: Said "around line 237" but should be after line 251.

**Status:** RESOLVED
**Resolution:** Updated to reference the last RuntimeError check around line 251 (SES validation block).

---

1. **Phase 2 Task 6 implicit dependency on Task 5**: Task 6 passes correlation_id to adapt_per_model but that parameter is added by Task 5.

**Status:** RESOLVED
**Resolution:** Added explicit Prerequisites section to Task 6 stating dependency on Task 5.

---

#### Suggestions

1. **Phase 2 Task 9 coverage gap**: Raising from 52% to 70% may require substantial unplanned work.

**Status:** RESOLVED
**Resolution:** Changed target to 60% statements/lines as intermediate step, with instruction to raise to 70% if already achievable. Updated Phase-3 docs to match.

---

1. **Phase 0 mentions mypy strict mode**: No mypy config or CI step exists.

**Status:** RESOLVED
**Resolution:** Removed mypy strict mode claim from Phase-0. Clarified that Ruff handles linting and type hints are used but not enforced by mypy in CI.
