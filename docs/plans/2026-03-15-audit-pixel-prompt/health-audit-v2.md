---
type: repo-health
date: 2026-03-15
goal: re-audit after 5-phase remediation
prior: health-audit.md
---

# Codebase Health Audit v2: pixel-prompt-complete (Post-Remediation)

## Configuration
- **Goal:** Re-audit after 5-phase remediation
- **Scope:** Full repo
- **Existing Tooling:** ESLint (flat config), Ruff (pyproject.toml), Vitest, pytest, GitHub Actions CI
- **Constraints:** None

## EXECUTIVE SUMMARY
- **Overall health: GOOD** (upgraded from FAIR)
- **Biggest structural risk:** `handlers.py` (741 lines) still contains all 4 providers x 3 handler types in one module, though BFL polling duplication was consolidated via `_poll_bfl_job`.
- **Biggest operational risk:** `handle_bfl` (line 252-325) still has inline polling with `time.sleep()` that duplicates the extracted `_poll_bfl_job` helper and uses a stale timeout message.
- **Total findings:** 0 critical, 2 high, 5 medium, 5 low

## PRIOR FINDING REMEDIATION STATUS

| # | Prior Finding | Status | Notes |
|---|--------------|--------|-------|
| 1 | `storage.py` unpaginated `list_galleries()` | **FIXED** | Pagination loop with `ContinuationToken` added (lines 163-177). `ClientError` caught and re-raised with logging (line 184-186). |
| 2 | `storage.py` unpaginated `list_gallery_images()` | **FIXED** | Same pagination pattern applied (lines 209-223). `ClientError` re-raised with logging (lines 227-229). |
| 3 | `handlers.py` 1040-line god module | **PARTIALLY FIXED** | Reduced to 741 lines. Dead providers (Bedrock, Stability, Imagen, Generic) removed. BFL polling consolidated into `_poll_bfl_job`. Shared helpers extracted (`_success_result`, `_error_result`, `_decode_source_image`, etc.). Still a single file with 12 handler functions. |
| 4 | `lambda_function.py` 766-line god module | **PARTIALLY FIXED** | Shared pipeline extracted (`_parse_and_validate_request`, `_handle_refinement`, `_handle_successful_result`). Now 789 lines due to helper additions, but duplication between iterate/outpaint eliminated. |
| 5 | Hardcoded CORS `*` | **FIXED** | Configurable via `CORS_ALLOWED_ORIGIN` env var (config.py:106, lambda_function.py:784). |
| 6 | BFL `None` API key, uncached `handle_generic` client | **FIXED** | Dead `handle_generic` removed. BFL still passes `model_config.get('api_key') or None` but this is now the only provider doing so (line 272). Clients now use cached `get_openai_client`/`get_genai_client` from `utils.clients`. |
| 7 | `enhance.py` uncached clients | **FIXED** | Now uses `get_genai_client` and `get_openai_client` from `utils.clients` (lines 80, 107). |
| 8 | Unused `types.py` module | **FIXED** | File removed. TypedDict types (`HandlerSuccess`, `HandlerError`, `HandlerResult`) now defined in `handlers.py` (lines 94-108). |
| 9 | Shared `ThreadPoolExecutor` for gallery and generation | **NOT FIXED** | Still shared (lambda_function.py:87). Gallery list (line 659) and gallery detail (line 751) still use `_executor`. |
| 10 | `handle_iterate`/`handle_outpaint` duplication | **FIXED** | Unified via `_handle_refinement` helper (lines 417-511). |
| 11 | `handle_status` missing session_id validation | **FIXED** | Regex validation added (line 571): `^[a-zA-Z0-9\-]{1,64}$`. |
| 12 | Overly aggressive `sanitize_error_message` regex | **NOT FIXED** | The `[A-Za-z0-9]{32,}` pattern (handlers.py:138) still redacts any 32+ char alphanumeric string. |
| 13 | `handle_log_endpoint` unsanitized metadata | **FIXED** | Reserved keys filtered (lambda_function.py:697-701). Body size limited to 10 KB (line 686). |
| 14 | Mutable `ModelConfig` dataclass | **FIXED** | `@dataclass(frozen=True)` applied (config.py:36). |
| 15 | Missing frontend tests for key components | **PARTIALLY FIXED** | New tests added: `IterationCard.test.tsx`, `GenerateButton.test.tsx`, `useIteration.test.ts`, `useSessionPolling.test.ts`, `useSound.test.ts`, `useBreakpoint.test.ts`, plus many common component tests. Still missing: `GenerationPanel.tsx` (372 lines), `GalleryBrowser.tsx` (152 lines), `useGallery.ts` (229 lines). |
| 16 | BFL polling `time.sleep()` in Lambda | **NOT FIXED** | `_poll_bfl_job` (line 54-71) and `handle_bfl` inline polling (lines 296-322) both still use `time.sleep()` in loops. Architectural constraint of synchronous Lambda. |
| 17 | Dead Bedrock/Stability/Imagen/Generic handlers | **FIXED** | All removed. Only 4 active providers remain. |
| 18 | Magic number stage prefix stripping | **FIXED** | Replaced with proper prefix matching loop (lambda_function.py:209-211). |
| 19 | `eslint-disable` for exhaustive-deps in GenerationPanel | **FIXED** | The `handleGenerate` is now properly included in the dependency array (line 278). No more eslint-disable. |
| 20 | Dead config values (`is_model_enabled`, `MODEL_ORDER`, etc.) | **FIXED** | All removed from config.py. |
| 21 | Legacy `job_not_found()` in error_responses | **FIXED** | Removed from error_responses.py. |
| 22 | `reset_cache()` no-op in rate_limit.py | **FIXED** | Removed. |
| 23 | `handleGallerySelect` no-op in GenerationPanel | **FIXED** | Removed. |
| 24 | Duplicated `MAX_ITERATIONS` between frontend/backend | **NOT FIXED** | Still hardcoded as `7` in both `frontend/src/hooks/useIteration.ts:12` and `backend/src/config.py:109`. |
| 25 | Frontend `REQUEST_TIMEOUT` too short (30s) | **FIXED** | Increased to 180,000ms (frontend/src/api/config.ts:44). |
| 26 | npm audit vulnerabilities (8) | **PARTIALLY FIXED** | Reduced from 8 (5 moderate + 3 high) to 4 moderate. All remaining are in `esbuild`/`vite` transitive deps of vitest. |

## TECH DEBT LEDGER

### CRITICAL

_(None)_

### HIGH

1. **[Structural Debt]** `backend/src/models/handlers.py:252-322` (inline BFL polling) vs `backend/src/models/handlers.py:54-71` (`_poll_bfl_job`)
   - **The Debt:** `handle_bfl` (the generate handler) contains its own inline polling loop (lines 296-322) that duplicates the logic in `_poll_bfl_job` (lines 54-71). The iterate and outpaint BFL handlers correctly use `_poll_bfl_job`, but `handle_bfl` does not. Additionally, the timeout error message on line 322 uses hardcoded `max_attempts * 3` instead of `max_attempts * poll_interval`, producing incorrect timeout durations when `bfl_poll_interval` is not 3.
   - **The Risk:** Bug fixes to polling logic (e.g., error handling, timeout calculation) must be applied in two places. The stale `* 3` on line 322 already produces incorrect timeout messages when `BFL_POLL_INTERVAL` is changed from the default.

2. **[Operational Debt]** `backend/src/lambda_function.py:87` and `backend/src/lambda_function.py:659,751`
   - **The Debt:** The module-level `ThreadPoolExecutor(max_workers=generate_thread_workers)` is shared between image generation (line 341-347), gallery listing (line 659), and gallery detail (line 751). Default `generate_thread_workers` is 4. A gallery list request that triggers parallel `_build_gallery_entry` calls for many galleries can saturate the pool, blocking concurrent `/generate` requests.
   - **The Risk:** Gallery browsing under load can starve the generation thread pool, causing generation requests to queue behind gallery I/O.

### MEDIUM

3. **[Hygiene Debt]** `backend/src/models/handlers.py:138`
   - **The Debt:** `sanitize_error_message` regex `[A-Za-z0-9]{32,}` redacts any alphanumeric string of 32+ characters, including UUIDs, model names, long file paths, and URL paths.
   - **The Risk:** Over-redaction obscures meaningful error context in production debugging.

4. **[Hygiene Debt]** `backend/src/utils/storage.py:243-284`
   - **The Debt:** `_generate_thumbnail` is never called by any code in the codebase. Vulture confirms it as unused at 60% confidence.
   - **The Risk:** Dead code increases maintenance burden and cognitive load.

5. **[Operational Debt]** `backend/src/lambda_function.py:595-625`
   - **The Debt:** `handle_enhance` does not use the shared `_parse_and_validate_request` pipeline. It manually parses JSON, validates prompt, and checks content filter but skips rate limiting and body size checks.
   - **The Risk:** The `/enhance` endpoint can be called without rate limiting, unlike all other POST endpoints. Inconsistent validation pipeline means security improvements to `_parse_and_validate_request` do not automatically apply to `/enhance`.

6. **[Hygiene Debt]** `tests/backend/unit/test_config.py:113`
   - **The Debt:** Test asserts `flux.model_id == 'flux-pro-1.1'` but the actual default in `config.py:76` is `'flux-2-pro'`. This test fails (confirmed: 1 failure in backend test suite).
   - **The Risk:** Failing test in the test suite erodes CI trust and masks real regressions.

7. **[Hygiene Debt]** `frontend/src/hooks/useIteration.ts:12` and `backend/src/config.py:109`
   - **The Debt:** `MAX_ITERATIONS = 7` is independently hardcoded in both frontend and backend with no synchronization mechanism.
   - **The Risk:** If the backend limit changes, the frontend will show incorrect remaining iteration counts.

### LOW

8. **[Hygiene Debt]** `frontend/src/hooks/useSound.ts:77`
   - **The Debt:** `eslint-disable-line react-hooks/exhaustive-deps` suppresses the exhaustive-deps rule for a cleanup useEffect.
   - **The Risk:** Minor -- the cleanup function captures `soundsRef` which is a ref and stable, so this is likely a false positive, but the suppression obscures the reasoning.

9. **[Hygiene Debt]** `backend/src/models/handlers.py:272`
   - **The Debt:** BFL `handle_bfl` passes `"x-key": model_config.get('api_key') or None` which sends `None` as a header value when no API key is configured.
   - **The Risk:** `requests` will stringify `None` as `"None"` in the header, producing a confusing 401 from the BFL API instead of a clear validation error.

10. **[Operational Debt]** `backend/src/lambda_function.py:335-337`
    - **The Debt:** When `_handle_failed_result` itself raises an exception inside the `generate_for_model` error handler, the inner exception is silently swallowed (`except Exception: pass`).
    - **The Risk:** If S3 is down, session status will never be updated to "failed" for that model, and the error is lost. The `pass` is documented as "best-effort" but produces no log entry.

11. **[Hygiene Debt]** `backend/src/models/handlers.py:268` and `backend/src/models/handlers.py:233`
    - **The Debt:** Blank lines inside function bodies (e.g., line 268 in `handle_bfl`, line 233 in `handle_google_gemini`) that serve no structural purpose.
    - **The Risk:** Minor code style inconsistency.

12. **[Operational Debt]** `backend/src/config.py:53-56`
    - **The Debt:** When `S3_BUCKET` or `CLOUDFRONT_DOMAIN` are not set, a `warnings.warn()` is emitted but execution continues. Module-level objects (`session_manager`, `rate_limiter`, `image_storage`) are then initialized with `None` bucket/domain values, which will fail on first use with unhelpful errors.
    - **The Risk:** Delayed failure with unclear error messages when required env vars are missing.

## QUICK WINS

1. `backend/src/models/handlers.py:252-322` -- Replace inline BFL polling in `handle_bfl` with a call to `_poll_bfl_job` (estimated effort: < 15 minutes)
2. `backend/src/utils/storage.py:243-284` -- Remove unused `_generate_thumbnail` method (estimated effort: < 5 minutes)
3. `tests/backend/unit/test_config.py:113` -- Fix stale assertion `'flux-pro-1.1'` to `'flux-2-pro'` (estimated effort: < 5 minutes)
4. `backend/src/lambda_function.py:595-625` -- Refactor `handle_enhance` to use `_parse_and_validate_request` (estimated effort: < 30 minutes)

## AUTOMATED SCAN RESULTS

**Linting (Ruff - Python):**
- All checks passed. Zero violations.

**Linting (ESLint - TypeScript/React):**
- All checks passed. Zero violations.

**Type Checking (tsc --noEmit):**
- All checks passed. Zero type errors.

**Dead Code (vulture - Python, 60% confidence):**
- 4 findings:
  - `config.py:44` `display_name` (false positive -- used by UI)
  - `config.py:48` `aws_region` (false positive -- used by AWS SDK)
  - `lambda_function.py:203` `lambda_handler` (false positive -- Lambda entry point)
  - `storage.py:243` `_generate_thumbnail` (**confirmed dead** -- never called)

**Backend Tests (pytest):**
- 178 passed, 1 failed (stale model ID assertion in test_config.py), 17 warnings
- All warnings are expected (S3_BUCKET/CLOUDFRONT_DOMAIN not set in test env, prompt enhancement failure in test)

**Frontend Tests (Vitest):**
- 340 passed, 5 skipped (integration tests requiring backend), 30 test files
- Zero failures

**Vulnerability Scan (npm audit):**
- 4 moderate severity vulnerabilities (down from 8)
- All in `esbuild` transitive dependency via `vite`/`vitest` (build-time only)
- Requires `npm audit fix --force` with breaking vitest upgrade to resolve

**Secrets Scan:**
- No secrets found committed. `.gitignore` properly excludes `.env`, `.env.local`, `.env.deploy`, `.deploy-config.json`, `*.pem`, `*.key`, `samconfig.toml`.

**Git Hygiene:**
- Clean commit history with conventional commit messages.
- All remediation phases clearly tracked with descriptive commits.
