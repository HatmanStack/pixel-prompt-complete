---
type: repo-health
date: 2026-04-06
goal: General health check — scan all 4 vectors equally
---

# Codebase Health Audit: pixel-prompt-complete

## Configuration
- **Goal:** General health check — scan all 4 vectors equally
- **Scope:** Full repo, no constraints
- **Deployment Target:** Serverless (Lambda, Cloud Functions) — cold starts, execution limits, stateless constraints
- **Existing Tooling:** Full setup — linters, CI pipeline, pre-commit hooks, type checking
- **Constraints:** None

## Summary
- Overall health: GOOD
- Total findings: 2 critical, 7 high, 9 medium, 6 low

## Tech Debt Ledger

### CRITICAL

1. **[Operational Debt]** `backend/src/lambda_function.py:666-707`
   - **The Debt:** `handle_gallery_list` fetches the full base64-encoded image data (`preview_data = preview_metadata["output"]`) for every gallery and embeds it directly in the JSON response. Each base64 image is ~1-2MB. With 15+ galleries, the response exceeds Lambda's 6MB response size limit and API Gateway's 10MB payload limit, causing silent 502 errors.
   - **The Risk:** As gallery count grows, the endpoint will begin returning 502 errors with no diagnostic information, making the gallery feature completely unusable.

2. **[Operational Debt]** `backend/src/models/handlers.py:55-72` (`_poll_bfl_job`)
   - **The Debt:** BFL polling uses synchronous `time.sleep(interval)` (default 3s) in a loop of up to 40 iterations (120 seconds total), running inside a `ThreadPoolExecutor` thread. During `/generate`, up to 4 threads can block simultaneously, and the Lambda has a 900s timeout with only 10 reserved concurrent executions.
   - **The Risk:** A single stuck BFL job consumes a Lambda execution slot for 120+ seconds. Under load, all 10 concurrent slots can be exhausted by polling threads alone, causing all new requests to queue and timeout.

### HIGH

3. **[Operational Debt]** `backend/src/lambda_function.py:400-427` (`_load_source_image`)
   - **The Debt:** This function makes 3 separate S3 `get_object` calls sequentially: `get_iteration_count()` calls `get_session()`, then `get_latest_image_key()` calls `get_session()` again (duplicate fetch), then `get_image()` fetches the full image data. The session status.json is read twice for the same data.
   - **The Risk:** Unnecessary S3 latency (additional ~50-100ms per iterate/outpaint request) and wasted I/O that counts against S3 request quotas. Under high concurrency, this doubles the chance of hitting S3 throttling.

4. **[Structural Debt]** `backend/src/lambda_function.py:1-824` (entire file)
   - **The Debt:** The main handler file is 824 lines containing routing, request validation, 8 endpoint handlers, response formatting, and business orchestration logic. While internal helper extraction (`_parse_and_validate_request`, `_handle_refinement`) is good, the file still owns too many responsibilities.
   - **The Risk:** High merge-conflict frequency when multiple features touch different endpoints simultaneously. Difficulty identifying the scope of a change.

5. **[Architectural Debt]** `backend/src/lambda_function.py:762`
   - **The Debt:** `handle_gallery_detail` directly accesses a private class attribute: `image_storage._GALLERY_FOLDER_RE.match(gallery_id)`. This breaks the encapsulation of `ImageStorage` by reaching into its implementation detail for input validation.
   - **The Risk:** Any refactor of `ImageStorage`'s internal naming convention silently breaks gallery detail validation. The regex pattern is being used for two different semantic purposes (gallery listing vs. input validation) with no shared abstraction.

6. **[Operational Debt]** `backend/src/lambda_function.py:718-750` (`handle_log_endpoint`)
   - **The Debt:** `handle_log()` raises `ValueError` for missing/invalid fields (lines 36, 39, 43 of `api/log.py`), but the calling endpoint catches it as generic `Exception` and returns HTTP 500 instead of 400. Client-side validation errors are reported as server errors.
   - **The Risk:** Frontend developers see 500 errors for malformed log requests, making debugging more difficult. 500 errors trigger the CloudWatch alarm unnecessarily.

7. **[Structural Debt]** `frontend/src/hooks/useIteration.ts:11-12` and `backend/src/config.py:112-113`
   - **The Debt:** `MAX_ITERATIONS = 7` and `WARNING_THRESHOLD = 5` are independently hardcoded in both the frontend (`useIteration.ts:11-12`) and backend (`config.py:112-113`). The backend values are configurable but the frontend values are compile-time constants with no mechanism to sync.
   - **The Risk:** If the backend limit is changed via environment variable, the frontend continues enforcing the old limit, creating inconsistent UX (frontend says "limit reached" while backend would accept more, or vice versa).

8. **[Operational Debt]** `backend/src/lambda_function.py:753-809` (`handle_gallery_detail`)
   - **The Debt:** Gallery detail returns full base64 image data in the `output` field for every image in a gallery. A single gallery with 4 models generates ~4-8MB of base64 data in one response.
   - **The Risk:** Same payload size issue as the gallery list endpoint. Responses intermittently exceed Lambda/API Gateway limits.

9. **[Architectural Debt]** `backend/src/utils/rate_limit.py:45-75`
   - **The Debt:** Rate limiting performs 2 S3 read-write cycles per request (IP counter + global counter), each with up to 3 retries. That is 4-12 S3 operations per inbound request, all on the hot path before any business logic runs.
   - **The Risk:** S3 rate limiting adds 100-300ms of latency to every request. Under S3 throttling (3500 PUT/s per prefix), rate limiting itself becomes the bottleneck, ironically causing the system to slow down precisely when it is under load.

### MEDIUM

10. **[Hygiene Debt]** `frontend/tests/__tests__/components/GenerateButton.test.jsx` and `frontend/tests/__tests__/components/generation/GenerateButton.test.tsx`
    - **The Debt:** Two test files exist for the same component at different paths. The `.jsx` version appears to be a legacy file from before the `generation/` directory restructuring.
    - **The Risk:** Duplicate tests create confusion about which is authoritative and double CI execution time for that component.

11. **[Hygiene Debt]** `frontend/src/fixtures/apiResponses.ts`
    - **The Debt:** Test fixtures file (`apiResponses.ts`) lives inside `src/fixtures/` in the production source tree rather than alongside tests. It contains mock data types (`MockJobStatus`, `MockResult`) that reference the old job-based API (`jobId`, `completedModels`) rather than the current session-based API.
    - **The Risk:** Stale fixture types give a false impression that the old job-based API still exists. The file ships in production bundles unnecessarily (though tree-shaking likely removes it).

12. **[Operational Debt]** `backend/src/models/handlers.py:177-241` (`handle_openai`)
    - **The Debt:** For DALL-E 2/3 models (non gpt-image-1), the `handle_openai` handler calls `client.images.generate()` with no explicit timeout on the OpenAI SDK call itself, then separately downloads the image URL with `image_download_timeout`. The SDK call inherits `api_client_timeout` (120s) from the cached client, but this is implicit and not visible at the call site.
    - **The Risk:** The timeout behavior is correct but implicit. A developer adding a new handler might not realize the cached client carries the timeout, leading to missing timeouts in future handlers.

13. **[Structural Debt]** `backend/src/api/enhance.py:114-136`
    - **The Debt:** Model-specific branching logic (`if "gpt-5" in model_id` / `elif "gpt-4o" in model_id`) for parameter selection in the prompt enhancer. This is string-matching on model IDs to determine API parameter compatibility.
    - **The Risk:** Every new OpenAI model release requires updating this branching logic. Model ID strings are fragile identifiers for capability detection.

14. **[Hygiene Debt]** `backend/src/api/enhance.py:112-113` (blank lines)
    - **The Debt:** Multiple unnecessary blank lines inside the method body (lines 112-113, 146-147) suggesting leftover from removed code or debugging.
    - **The Risk:** Minor readability issue.

15. **[Structural Debt]** `frontend/src/types/api.ts:83-86` (`SessionGenerateResponse`)
    - **The Debt:** `SessionGenerateResponse` has `status: string` as a loose type, while the actual backend response includes `prompt` and `models` fields that are not typed. The frontend ignores the `models` field from the generate response and instead constructs an empty session for polling.
    - **The Risk:** Type contract between frontend and backend is incomplete. Changes to the generate response shape go undetected at compile time.

16. **[Operational Debt]** `backend/src/utils/storage.py:36-61` (`_store_image`)
    - **The Debt:** Full base64 image data is stored as a JSON field inside S3 objects alongside metadata. This means every `get_image()` call downloads the entire base64 payload even when only metadata (model, prompt, timestamp) is needed, as in gallery listing.
    - **The Risk:** Gallery listing downloads full image data for each preview image. Separating image binary from metadata would dramatically reduce gallery list latency and S3 transfer costs.

17. **[Structural Debt]** `backend/src/jobs/manager.py:183-291`
    - **The Debt:** `complete_iteration()` and `fail_iteration()` are nearly identical methods (~50 lines each) differing only in what fields they set on the iteration object (`status=completed, imageKey, duration` vs `status=error, error`). The retry-loop + get-session + find-iteration + update + save pattern is duplicated.
    - **The Risk:** Any bug fix to the optimistic locking retry pattern must be applied to three separate methods (add_iteration, complete_iteration, fail_iteration).

18. **[Hygiene Debt]** `frontend/src/components/generation/GenerationPanel.tsx:253-265`
    - **The Debt:** Keyboard shortcuts use `CustomEvent` dispatch (`document.dispatchEvent(new CustomEvent('random-prompt-trigger'))`) to communicate between sibling components. This is a DOM-level pub/sub pattern that bypasses React's data flow.
    - **The Risk:** Events are invisible to React DevTools and type-checking. No compile-time guarantee that the event name matches between dispatcher and listener.

### LOW

19. **[Hygiene Debt]** `frontend/src/api/client.ts:122` and multiple `console.error` calls across hooks
    - **The Debt:** 18 `console.error`/`console.warn` calls throughout frontend source code. While the app has a structured logging endpoint (`/log`), client-side errors are only logged to browser console, not sent to the backend logging endpoint.
    - **The Risk:** Production errors are invisible unless a developer has the browser console open. The `/log` endpoint exists but is underutilized.

20. **[Hygiene Debt]** `backend/src/utils/retry.py:13`
    - **The Debt:** The retry module uses Python's `logging.getLogger()` directly while the rest of the backend uses `StructuredLogger`. This creates inconsistent log formatting in CloudWatch.
    - **The Risk:** Retry log entries are not JSON-structured and lack correlation IDs, making them harder to find in CloudWatch Logs Insights queries.

21. **[Hygiene Debt]** `backend/src/models/context.py:93` (`self.s3.exceptions.NoSuchKey`)
    - **The Debt:** Uses `self.s3.exceptions.NoSuchKey` (service resource exception style) while `get_session` in `manager.py:105-108` uses `ClientError` with error code check. Inconsistent S3 error handling pattern across the codebase.
    - **The Risk:** The `s3.exceptions.NoSuchKey` style may not work with all boto3 client configurations (it works with service resources but behavior can vary). Inconsistency makes error handling patterns harder to audit.

22. **[Hygiene Debt]** `frontend/tests/__tests__/components/` (5 legacy `.jsx` test files)
    - **The Debt:** Five test files at the top of the `components/` directory use `.jsx` extension while newer tests in subdirectories use `.tsx`. The `.jsx` files (`GalleryBrowser.test.jsx`, `GenerateButton.test.jsx`, `ImageGrid.test.jsx`, `PromptEnhancer.test.jsx`, `PromptInput.test.jsx`, `ImageCard.test.jsx`) appear to be from an earlier structure before the `generation/`, `gallery/`, `common/` reorganization.
    - **The Risk:** Mixed test file extensions and directory locations create confusion about test organization conventions.

23. **[Hygiene Debt]** `backend/src/config.py:9` (`from typing import Dict, List`)
    - **The Debt:** Uses `typing.Dict` and `typing.List` imports on Python 3.13 where `dict` and `list` are directly usable as generic types. Same pattern in several other backend files.
    - **The Risk:** Minor. Legacy typing imports add unnecessary verbosity but have no runtime impact.

24. **[Hygiene Debt]** `backend/src/lambda_function.py:14` (`from typing import Any, Dict, Optional`)
    - **The Debt:** Mixed use of `typing.Optional` (old-style) and `X | None` (new-style union, used elsewhere in the file like line 111). Inconsistent type annotation style within the same file.
    - **The Risk:** Minor readability inconsistency.

## Quick Wins

1. `backend/src/lambda_function.py:718-750` — Add `except ValueError as e: return response(400, {"error": str(e)})` before the generic `except Exception` in `handle_log_endpoint` to properly return 400 for validation errors (estimated effort: < 15 minutes)
2. `backend/src/lambda_function.py:762` — Add a public `validate_gallery_id(id)` method to `ImageStorage` and call that instead of accessing `_GALLERY_FOLDER_RE` directly (estimated effort: < 15 minutes)
3. `backend/src/lambda_function.py:400-427` — Refactor `_load_source_image` to call `get_session()` once and extract both iteration count and latest image key from the same response (estimated effort: < 30 minutes)

## Automated Scan Results

- **Dead code:** `frontend/src/fixtures/apiResponses.ts` contains stale mock types (`MockJobStatus`, `MockResult`) referencing the old job-based API that no longer exists. No production code imports from this file; only one test file uses it.
- **Vulnerability scan:** Not executed. Recommend running `npm audit` in `frontend/` and `pip-audit` against `backend/src/requirements.txt`.
- **Secrets scan:** `.gitignore` properly excludes `.env`, `.env.local`, `.env.deploy`, `samconfig.toml`, `parameters.json`. API keys are injected via SAM parameters with `NoEcho: true`. No hardcoded secrets found in source code. The `sanitize_error_message` function provides defense-in-depth redaction.
- **Duplicate test files:** `GenerateButton.test.jsx` exists at two paths (`components/` and `components/generation/`).
