# Feedback Log

## Phase Approvals

- **PHASE_APPROVED** -- Phase 1 (2026-04-06) -- 200 tests pass, ruff clean, all 12 tasks verified, 3 atomic commits
- **PHASE_APPROVED** -- Phase 2 (2026-04-06) -- 328 tests pass, typecheck/lint/build clean, all 8 tasks verified, 6 atomic commits
- **PHASE_APPROVED** -- Phase 3 (2026-04-06) -- 200 backend tests at 87.54% coverage, ruff clean, markdownlint configured, all 7 tasks verified, 5 atomic commits

## Active Feedback

### Suggestions (non-blocking)

1. **Phase Token Estimates vs Actual Content**: Phase 1 is listed at ~45,000 tokens with 12 tasks. This is within budget but close to the ceiling. Consider whether Tasks 1 and 2 (Flux removal and Recraft removal) could be combined into a single task since they are structurally identical operations.

1. **Phase 2 Task 4 Column Focus CSS Specs Are Clear**: The CSS/animation specs for column focus are well-specified: `w-[60%]`, `w-[13%]`, `transition-all duration-300 ease-in-out`, `aria-expanded`, accessibility labels. This is sufficient for implementation.

1. **DALL-E 3 Iteration Strategy Is Well Documented**: ADR-5 clearly explains the limitation, the workaround (gpt-image-1 for edit), and the rationale. Phase 1 Task 5 has a specific test (`test_iterate_openai_uses_gpt_image_1`) that verifies the model parameter. This is good.

1. **Hallucinated Model Name in Phase-3 Summary**: Phase-3.md line 504 says "Gemini Nano Banana 2" which is not a real Google model name. The rest of the plan consistently uses "Gemini" as the display name. This appears only in the post-phase summary and does not affect implementation steps, but an implementer may find it confusing. The model ID `gemini-3.1-flash-image-preview` used in Phase-1 Task 4 should also be verified against current Google API documentation at implementation time, as it may not exist. The `GEMINI_MODEL_ID` env var override provides a safe fallback mechanism.

## Resolved Feedback

### PLAN_REVIEW (2026-04-06) -- Resolved 2026-04-06

#### Critical Issues

1. **Cross-Reference Table Task Numbers Are Wrong (Phase-0.md)**: The audit cross-reference table in Phase-0.md mapped findings to incorrect task numbers.
   - **Resolution:** Corrected all task number mappings in the Phase-0.md cross-reference table. Key fixes: CRITICAL-1/HIGH-3/HIGH-5/HIGH-8 now correctly reference Phase 1, Task 9 (gallery fix). HIGH-6 and session ID validation correctly reference Phase 1, Task 10. MED-13/LOW-20/LOW-21 correctly reference Phase 1, Task 11. MED-15 correctly references Phase 2, Task 2. STALE-1 correctly references Phase 3, Task 6. Legacy typing imports correctly reference Phase 1, Task 3 and Task 11. BFL polling correctly references Phase 1, Task 1.

1. **Orphaned Audit Findings -- MED-17, S3 CORS, CORS origin**: Three findings were mapped to tasks that did not address them.
   - **Resolution:** Moved all three to a new "Out of Scope" section in Phase-0.md with rationale. MED-17 (DRY complete/fail_iteration) is deferred due to low benefit vs risk of breaking optimistic locking. S3 CORS wildcard requires per-environment CloudFront domain knowledge. CORS origin warning is low value since operators configure this at deploy time.

1. **Health Audit Finding #9 (rate_limit.py S3 hot path) Missing from Cross-Reference**: HIGH-9 was not in the cross-reference table.
   - **Resolution:** Added to the "Out of Scope" section in Phase-0.md with rationale. Fixing requires moving to DynamoDB or ElastiCache, which is a significant architectural change outside the scope of a provider swap. The brainstorm explicitly scoped out "changes to rate limiting."

#### Moderate Issues

1. **Phase 2 Task 3 References UIStore Type Location Ambiguously**: Task 3 said `frontend/src/types/index.ts (or wherever UIStore type is defined)`.
   - **Resolution:** Updated to definitively state `frontend/src/types/store.ts` (where `UIStore` is defined at line 82) and noted it is re-exported via `frontend/src/types/index.ts`.

1. **Phase 2 Task 5 Creates Directory Without Saying So**: Task 5 said to create `frontend/src/config/constants.ts` but the directory does not exist.
   - **Resolution:** Added explicit `mkdir -p frontend/src/config` step before file creation, with a note that the directory does not exist yet.

1. **Nova Canvas Open Questions Not Fully Resolved in Plan**: Task 6 assumed specific API task types without confirming they are real.
   - **Resolution:** Added "API Shape Verification" section to Phase 1 Task 6 with a link to the AWS Bedrock Nova Canvas API reference documentation. Added fallback strategies: use TEXT_IMAGE for iteration if IMAGE_VARIATION is unavailable, use INPAINTING with expansion mask if OUTPAINTING is unavailable.

1. **Firefly Open Questions Not Fully Resolved in Plan**: Task 7 assumed specific API endpoints without documentation references or fallback strategies.
   - **Resolution:** Added "API Shape Verification" section to Phase 1 Task 7 with links to Adobe Firefly Services API docs for each endpoint (generate, storage upload, generative expand). Added fallback strategies for iteration (prompt-only re-generation), outpaint (new image at target ratio), and auth (link to OAuth2 server-to-server docs).
