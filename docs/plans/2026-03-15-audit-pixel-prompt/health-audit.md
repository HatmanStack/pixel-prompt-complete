---
type: repo-health
date: 2026-03-15
goal: general health check
---

# Codebase Health Audit: pixel-prompt-complete

## Configuration
- **Goal:** General health check
- **Scope:** Full repo
- **Existing Tooling:** ESLint (flat config), Ruff (pyproject.toml), Vitest, pytest, GitHub Actions CI
- **Constraints:** None

## Summary
- Overall health: FAIR
- Biggest structural risk: `handlers.py` is a 1039-line god module containing all provider handlers (generate, iterate, outpaint) for 8+ providers with heavy code duplication across handler types.
- Biggest operational risk: S3 `list_objects_v2` calls in gallery listing have no pagination, silently swallowing errors and potentially missing objects when results exceed 1000 keys.
- Total findings: 2 critical, 7 high, 10 medium, 7 low

## Tech Debt Ledger

### CRITICAL

1. **[Operational Debt]** `backend/src/utils/storage.py:179-203`
   - **The Debt:** `list_galleries()` calls `list_objects_v2` without pagination (`ContinuationToken`). S3 returns a maximum of 1000 keys per call. If there are more than 1000 gallery folders, results are silently truncated. The bare `except Exception: return []` on line 202 swallows all errors including permissions, network failures, and throttling -- the caller will never know something went wrong.
   - **The Risk:** Data loss for users -- galleries beyond the 1000th will be invisible. Silent error swallowing means operational issues (IAM misconfiguration, S3 throttling) go undetected.

2. **[Operational Debt]** `backend/src/utils/storage.py:205-236`
   - **The Debt:** `list_gallery_images()` has the same unpaginated `list_objects_v2` call and bare `except Exception: return []` pattern. A gallery with more than 1000 images will show incomplete results silently.
   - **The Risk:** Same as above -- silent data truncation and invisible operational failures.

### HIGH

3. **[Structural Debt]** `backend/src/models/handlers.py:1-1040`
   - **The Debt:** This 1040-line file contains all handler logic for 8+ providers across 3 handler types (generate, iterate, outpaint). Each handler follows an identical pattern: try/except, call API, convert to base64, return result dict. The BFL polling logic is duplicated between `handle_bfl` (lines 528-559) and `_poll_bfl_job` (lines 109-126). The file also mixes concerns: API client caching, error sanitization, response building, and provider-specific logic all in one module.
   - **The Risk:** Modifications to any provider risk breaking others. Adding a new provider requires understanding and modifying a single large file. Duplication means BFL polling bug fixes must be applied in multiple places.

4. **[Architectural Debt]** `backend/src/lambda_function.py:1-766`
   - **The Debt:** The Lambda handler at 766 lines is a god module that performs routing, request parsing, validation, business logic orchestration, and response formatting all in one file. `handle_generate`, `handle_iterate`, and `handle_outpaint` share highly similar validation-and-execution patterns (rate limit check, content filter, model lookup, source image loading, handler dispatch, result upload, context update) with only slight variations.
   - **The Risk:** Any change to the request handling pipeline (e.g., adding authentication) requires modifying multiple near-identical code paths. High risk of introducing inconsistencies across endpoints.

5. **[Operational Debt]** `backend/src/lambda_function.py:760`
   - **The Debt:** CORS header `Access-Control-Allow-Origin: '*'` is hardcoded to wildcard on every response.
   - **The Risk:** Any origin can make authenticated requests to the API. In a production environment with any form of session or cookie-based auth, this is a security vulnerability. Even without cookies, it exposes the API surface to abuse from malicious sites.

6. **[Operational Debt]** `backend/src/models/handlers.py:509` and `backend/src/models/handlers.py:628-636`
   - **The Debt:** `handle_bfl` passes `x-key` header with potentially `None` value (`model_config.get('api_key') or None`). `handle_stability` similarly sets `authorization: "Bearer None"` when no key is configured. `handle_generic` creates a new `OpenAI` client on every call (line 636) instead of using the cached `_get_openai_client`.
   - **The Risk:** Missing API keys produce confusing downstream errors rather than clear validation failures. The uncached client in `handle_generic` wastes resources on repeated Lambda invocations.

7. **[Operational Debt]** `backend/src/api/enhance.py:82` and `backend/src/api/enhance.py:110`
   - **The Debt:** `PromptEnhancer.enhance()` creates a new `genai.Client` or `OpenAI` client on every invocation, unlike `handlers.py` which caches clients at module level.
   - **The Risk:** Under load, each prompt enhancement creates a new HTTP connection pool instead of reusing Lambda container-cached clients. This adds latency and risks connection exhaustion.

8. **[Architectural Debt]** `backend/src/models/types.py:1-90`
   - **The Debt:** The `types.py` module defines Protocol classes (`GenerateHandler`, `IterateHandler`, `OutpaintHandler`) and TypedDicts (`SessionData`, `ModelData`, `IterationData`, `ModelConfigDict`) that are never imported or used anywhere in the codebase. Zero files import from `models.types` (confirmed by grep). `handlers.py` defines its own `HandlerFunc`, `IterateHandlerFunc`, `OutpaintHandlerFunc` type aliases independently.
   - **The Risk:** Dead type definitions create confusion about which type contracts are canonical. Developers may try to use these types and find they don't match the actual runtime shapes.

9. **[Operational Debt]** `backend/src/lambda_function.py:71`
   - **The Debt:** Module-level `ThreadPoolExecutor(max_workers=generate_thread_workers)` is created at import time and never shut down. While this is intentional for Lambda container reuse, it is also used for gallery listing operations (lines 646, 727) which could starve generation requests of threads.
   - **The Risk:** Gallery listing operations could exhaust the shared thread pool, blocking concurrent image generation requests.

### MEDIUM

10. **[Structural Debt]** `backend/src/lambda_function.py:266-408` and `backend/src/lambda_function.py:411-548`
    - **The Debt:** `handle_iterate` and `handle_outpaint` share approximately 80% identical code: JSON parsing, IP extraction, rate limiting, validation, model config lookup, source image loading, iteration management, handler dispatch, image upload, context update, and error handling. The only differences are: outpaint has a `preset` parameter and slightly different prompt formatting.
    - **The Risk:** Bug fixes or security improvements applied to one endpoint may be missed in the other.

11. **[Operational Debt]** `backend/src/lambda_function.py:558-559`
    - **The Debt:** `handle_status` extracts `session_id` by splitting the raw path on `/` and taking the last element without any validation or sanitization. An attacker could inject path traversal patterns or excessively long session IDs.
    - **The Risk:** While S3 key construction uses the session_id in a prefix, unsanitized input could cause unexpected S3 lookups. The `handle_gallery_detail` at line 704 properly validates with regex, but `handle_status` does not.

12. **[Hygiene Debt]** `backend/src/models/handlers.py:177`
    - **The Debt:** The `sanitize_error_message` regex on line 177 (`[A-Za-z0-9]{32,}`) redacts any alphanumeric string of 32+ characters. This will redact legitimate error content like long model names, URLs, and file paths, making debugging difficult.
    - **The Risk:** Overly aggressive redaction obscures meaningful error context in logs, making production debugging harder.

13. **[Operational Debt]** `backend/src/lambda_function.py:670-692`
    - **The Debt:** `handle_log_endpoint` accepts arbitrary `metadata` from the client request body and logs it to CloudWatch via `StructuredLogger.log(**metadata)`. There is no validation or sanitization of the metadata keys or values. A malicious client could inject enormous metadata payloads or overwrite structured log fields.
    - **The Risk:** Log injection attacks, CloudWatch cost inflation via large payloads, or confusion from overwritten log fields.

14. **[Structural Debt]** `backend/src/config.py:74-107` (MODELS dict)
    - **The Debt:** Model configuration is assembled at module import time from environment variables. The MODELS dict is a mutable module-level global. The `ModelConfig` dataclass is not frozen, so any code can mutate model configs (e.g., changing `api_key` or `enabled`) at runtime, affecting all subsequent requests in the same Lambda container.
    - **The Risk:** Accidental mutation of model configs would cause subtle, hard-to-reproduce bugs that persist across Lambda invocations until the container is recycled.

15. **[Hygiene Debt]** Frontend -- missing tests for key components
    - **The Debt:** No tests exist for `GenerationPanel.tsx` (380 lines, main orchestration component), `ImageGrid.tsx` (204 lines), `OutpaintControls.tsx` (156 lines), `PromptEnhancer.tsx` (250 lines), `SessionDetail.tsx` (189 lines), `GalleryBrowser.tsx`, or `useGallery.ts` (229 lines). These are among the largest and most complex frontend files.
    - **The Risk:** The most complex UI logic has zero test coverage, meaning regressions in core user workflows will go undetected.

16. **[Operational Debt]** `backend/src/models/handlers.py:109-126` (`_poll_bfl_job`)
    - **The Debt:** BFL polling uses `time.sleep()` in a loop inside a Lambda function. With default config `bfl_max_poll_attempts=40` and `bfl_poll_interval=3`, this blocks a thread for up to 120 seconds. During this time, the Lambda function is consuming billed compute doing nothing.
    - **The Risk:** Lambda billing waste and thread pool starvation. In the worst case with 4 models all using BFL-style polling, all 4 threads are blocked sleeping.

17. **[Hygiene Debt]** `backend/src/models/handlers.py:39-40` and `backend/src/models/handlers.py:64-83`
    - **The Debt:** Bedrock client singletons (`_bedrock_nova_client`, `_bedrock_sd_client`) use `global` keyword with mutable module-level state but are never used by any of the 4 configured models (flux/bfl, recraft, gemini, openai). The `handle_bedrock_nova`, `handle_bedrock_sd`, `handle_stability`, `handle_google_imagen`, and `handle_generic` handlers are registered in `get_handler()` but never called by the current 4-model config.
    - **The Risk:** Dead code paths increase maintenance burden and cognitive load. Unused Bedrock/Stability/Imagen handlers may rot and break without detection.

18. **[Architectural Debt]** `backend/src/lambda_function.py:86-93`
    - **The Debt:** Stage prefix stripping logic uses hardcoded string lengths (`path[6:]` for `/Prod/`, `path[9:]` for `/Staging/`) rather than proper prefix matching. Adding a new stage name like `/Dev/` would require modifying this logic.
    - **The Risk:** Fragile routing that breaks if deployment stages change. The magic numbers make the code harder to understand.

19. **[Structural Debt]** `frontend/src/components/generation/GenerationPanel.tsx:278`
    - **The Debt:** `eslint-disable-next-line react-hooks/exhaustive-deps` suppresses the exhaustive-deps rule for a `useEffect` that depends on `handleGenerate` (which captures `prompt`, `isGenerating`, and store actions). The dependencies array is `[prompt, isGenerating, expandedImage]` but omits `handleGenerate`.
    - **The Risk:** Stale closure bugs -- the keyboard shortcut handler may reference outdated values of store actions or other variables not in the dependency array.

### LOW

20. **[Hygiene Debt]** `backend/src/config.py:142` and `backend/src/config.py:166-172`
    - **The Debt:** Vulture reports `is_model_enabled`, `MODEL_ORDER`, `handler_timeout`, and `max_thread_workers` as unused. These are defined but never referenced in the codebase.
    - **The Risk:** Dead config values add confusion about what is actually configurable.

21. **[Hygiene Debt]** `backend/src/utils/error_responses.py:121`
    - **The Debt:** `job_not_found()` function references a "job" concept from a previous architecture. The codebase now uses sessions, not jobs.
    - **The Risk:** Misleading API for future developers who may use this function expecting it to work with the current session-based architecture.

22. **[Hygiene Debt]** `backend/src/utils/rate_limit.py:23`
    - **The Debt:** `reset_cache()` is a no-op function with comment "kept for test compatibility." This is test infrastructure leaking into production code.
    - **The Risk:** Minor -- confusing for developers; suggests there was once a cache that no longer exists.

23. **[Hygiene Debt]** `frontend/src/components/generation/GenerationPanel.tsx:282-286`
    - **The Debt:** `handleGallerySelect` is a no-op function with comment "Legacy gallery handler -- no-op, kept for GalleryBrowser prop compatibility."
    - **The Risk:** Dead code and prop interface that should be cleaned up if the prop is truly unused.

24. **[Hygiene Debt]** `frontend/src/hooks/useIteration.ts:12`
    - **The Debt:** `MAX_ITERATIONS = 7` is duplicated between frontend (`useIteration.ts:12`) and backend (`config.py:110`). There is no mechanism to keep them in sync.
    - **The Risk:** If the backend limit changes, the frontend will show incorrect remaining iteration counts.

25. **[Operational Debt]** `frontend/src/api/config.ts:43`
    - **The Debt:** `REQUEST_TIMEOUT` is set to 30 seconds, but image generation can take up to 120+ seconds (BFL polling alone can take 120s). The frontend will abort requests that the backend is still processing.
    - **The Risk:** Users will see timeout errors for legitimate long-running generation requests, even though the backend successfully generates images. The session polling mechanism partially mitigates this for `/generate`, but `/iterate` and `/outpaint` are synchronous calls that will time out.

26. **[Hygiene Debt]** npm audit reports 8 vulnerabilities (5 moderate, 3 high) in frontend dependencies
    - **The Debt:** Vulnerabilities in `rollup` (arbitrary file write via path traversal), `flatted` (unbounded recursion DoS), and `minimatch` (ReDoS). All have fixes available via `npm audit fix`.
    - **The Risk:** Development toolchain vulnerabilities. These are build-time dependencies, not runtime, so production risk is low but CI/CD pipelines could be affected.

## Quick Wins

1. `backend/src/utils/storage.py:202,235` -- Replace bare `except Exception: return []` with specific `ClientError` handling and logging (estimated effort: < 30 minutes)
2. `backend/src/config.py:37` -- Add `frozen=True` to `@dataclass` decorator to prevent accidental mutation of model configs (estimated effort: < 15 minutes)
3. `backend/src/models/types.py` -- Either wire up the Protocol/TypedDict types throughout the codebase or remove the file entirely to eliminate confusion (estimated effort: < 30 minutes)
4. `backend/src/config.py:142,166-172` -- Remove unused `is_model_enabled`, `MODEL_ORDER`, `handler_timeout`, `max_thread_workers` (estimated effort: < 15 minutes)
5. `backend/src/utils/error_responses.py:121` -- Remove legacy `job_not_found()` function (estimated effort: < 5 minutes)
6. `frontend/package.json` -- Run `npm audit fix` to resolve the 8 dependency vulnerabilities (estimated effort: < 15 minutes)

## Automated Scan Results

**Dead Code (vulture - Python):**
- 27 findings at 60% confidence. Key confirmed dead: `is_model_enabled()`, `MODEL_ORDER`, `handler_timeout`, `max_thread_workers` in config.py; `save_image()` in storage.py (superseded by `upload_image()`); `job_not_found()` in error_responses.py; `reset_cache()` no-op in rate_limit.py; entire `types.py` module unused. `clear_context()` and `_save_context()` in context.py also unused (superseded by conditional variants).

**Dead Code (knip - JS/TS):**
- Failed to run due to missing TypeScript dependency in npx cache. Manual review found no significant dead exports in frontend code.

**Vulnerability Scan (npm audit):**
- 8 vulnerabilities: 5 moderate, 3 high. All in build/dev dependencies (rollup, flatted, minimatch, vitest/vite). Fixes available via `npm audit fix`.

**Vulnerability Scan (pip-audit):**
- Failed to parse requirements.txt. No `requirements.txt` in standard location; dependencies managed via SAM `template.yaml` or `pyproject.toml`.

**Secrets Scan:**
- No secrets found committed. `.gitignore` properly excludes `.env`, `.env.local`, `.env.deploy`, `.deploy-config.json`, `*.pem`, `*.key`, `samconfig.toml`, `parameters.json`.

**Git Hygiene:**
- Clean commit history with conventional-style messages. Recent commits show active remediation of lint/typecheck/test errors. Pre-commit hooks (husky) and commitlint configured.
