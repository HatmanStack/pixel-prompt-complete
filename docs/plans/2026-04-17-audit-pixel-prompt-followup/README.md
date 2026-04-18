# Audit Follow-Up: Remaining Health Findings

## Overview

Follow-up plan addressing health findings from the 2026-04-17 audit that were not included in the initial remediation. After reviewing each remaining finding against the actual code, several were downgraded or closed as already mitigated. This plan covers the 3 findings that warrant action (a 4th — outpaint context validation — was found to already be handled by existing code during plan review).

## Triage of Remaining Findings

### Findings Worth Fixing (in this plan)

| Original Severity | Finding | Rationale |
|-------------------|---------|-----------|
| HIGH | Firefly OAuth2 token per-call | Real perf impact: ~500ms added to every Firefly request. Module-level cache with TTL is straightforward. |
| HIGH | OpenAI download missing specific error handling | Generic `except Exception` catches it but error messages are vague. Adding `requests.RequestException` catch improves diagnostics. |
| MEDIUM | API_CLIENT_TIMEOUT 120s default | 120s is generous for providers that typically respond in 10-30s. Reducing to 60s surfaces failures faster within the 900s Lambda timeout. |
### Findings Closed (already mitigated or low risk)

| Original Severity | Finding | Why Closed |
|-------------------|---------|------------|
| MEDIUM | Outpaint context validation ordering | Already handled by existing try-except in `_handle_refinement` (line 857). Plan review confirmed `_handle_failed_result` is called when `_build_args` throws. |
| HIGH | PromptEnhancer sequential blocking | Timeout now configurable (ENHANCE_TIMEOUT, Phase 2 Task 4). Fallback to original prompt on failure. Remaining risk is acceptable. |
| MEDIUM | DynamoDB retry jitter | Retries bounded to `_MAX_RETRIES=3` with no sleep. Conditional update fails fast on limit hit. Thundering herd risk negligible at this scale. |
| MEDIUM | time.sleep() in retry.py | Max total sleep: ~7s across 3 retries. Acceptable for Lambda billing. Exponential backoff is correct pattern. |
| MEDIUM | time.sleep() in context.py | Max total sleep: 0.3s (3 retries × 0.05-0.15s). Negligible. |
| MEDIUM | Stripe webhook validation | Already validates via `stripe.Webhook.construct_event()` with signature verification. Auditor flagged speculatively. |
| MEDIUM | _parse_and_validate_request size | Structural preference. Function is linear, well-commented, and tested. Not a bug. |
| LOW | Provider name validation at startup | `get_handler()` already raises `ValueError("Unknown provider: {provider}")` at request time. Startup validation would be redundant. |

## Prerequisites

- Initial audit remediation complete (2026-04-17-audit-pixel-prompt pipeline VERIFIED)
- All dependencies installed

## Phase Summary

| Phase | Tag | Goal | Estimated Tokens |
|-------|-----|------|-----------------|
| 0 | -- | Foundation | ~2,000 |
| 1 | [IMPLEMENTER] | Fix 3 remaining health findings | ~12,000 |

## Navigation

- [Phase-0.md](Phase-0.md) — Foundation and conventions
- [Phase-1.md](Phase-1.md) — [IMPLEMENTER] Remaining health fixes
