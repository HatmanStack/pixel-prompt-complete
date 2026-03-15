# Phase 2: [IMPLEMENTER] Error Handling, S3 Pagination, Performance, and Input Validation

## Phase Goal

Fix the two CRITICAL findings (unpaginated S3 listings with silent error swallowing), address HIGH-priority operational debt (client caching, input validation, error safety nets), and fix the frontend request timeout. This phase focuses on correctness and reliability without changing module structure.

**Success criteria:**
- `list_galleries()` and `list_gallery_images()` paginate S3 results and handle errors with specific exception types and logging
- `PromptEnhancer` reuses cached SDK clients instead of creating new ones per call
- `handle_status` validates session_id format (like `handle_gallery_detail` already does)
- `generate_for_model` applies `sanitize_error_message()` in its except block
- `generate_for_model` calls `fail_iteration()` on unhandled exceptions
- `handle_log_endpoint` validates metadata payload size
- Frontend `REQUEST_TIMEOUT` increased to handle long-running operations
- All existing tests pass plus new tests for pagination and validation

**Estimated tokens:** ~30,000

## Prerequisites

- Phase 1 completed (dead code removed)
- Backend tests passing: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
- Frontend tests passing: `cd frontend && npm test`

## Tasks

---

### Task 1: Add S3 pagination to `list_galleries()` and replace bare except

**Goal:** Fix CRITICAL finding #1. `list_objects_v2` returns max 1000 keys per call. Add pagination using `ContinuationToken`. Replace `except Exception: return []` with specific `ClientError` handling and logging.

**Files to Modify:**
- `backend/src/utils/storage.py` -- Fix `list_galleries()` method (lines 172-203)

**Prerequisites:** None

**Implementation Steps:**
- Modify `list_galleries()` to loop on `list_objects_v2` using the `IsTruncated` and `NextContinuationToken` response fields. Continue calling until `IsTruncated` is `False`.
- Replace the bare `except Exception: return []` with `except ClientError as e:` that logs the error via `logger.error(...)` and re-raises. This ensures operational issues (IAM, throttling) surface to the caller rather than being silently hidden.
- Keep the method's return type as `List[str]`.

**Verification Checklist:**
- [ ] `list_galleries()` uses a pagination loop with `ContinuationToken`
- [ ] No bare `except Exception` remains in the method
- [ ] `ClientError` is caught specifically with logging
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/test_storage.py -v` passes

**Testing Instructions:**
- Write a test in `tests/backend/unit/test_storage.py` that creates >1000 gallery prefixes in moto S3 and verifies `list_galleries()` returns all of them. Use the existing `mock_s3` fixture from `conftest.py`.
- Write a test that verifies `ClientError` is logged and re-raised (not swallowed).
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_storage.py -v`

**Commit Message Template:**
```
fix(backend): add S3 pagination to list_galleries and replace silent error swallowing
```

---

### Task 2: Add S3 pagination to `list_gallery_images()` and replace bare except

**Goal:** Fix CRITICAL finding #2. Same pattern as Task 1 but for `list_gallery_images()`.

**Files to Modify:**
- `backend/src/utils/storage.py` -- Fix `list_gallery_images()` method (lines 205-236)

**Prerequisites:** Task 1 (same file, same pattern)

**Implementation Steps:**
- Modify `list_gallery_images()` to loop on `list_objects_v2` using pagination.
- Replace bare `except Exception: return []` with specific `ClientError` handling and logging.
- The method filters for `.json` files -- maintain this filter within the pagination loop.

**Verification Checklist:**
- [ ] `list_gallery_images()` uses a pagination loop
- [ ] No bare `except Exception` remains in the method
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/test_storage.py -v` passes

**Testing Instructions:**
- Write a test that creates >1000 objects in a gallery folder and verifies all are returned.
- Write a test that verifies error handling behavior.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_storage.py -v`

**Commit Message Template:**
```
fix(backend): add S3 pagination to list_gallery_images and replace silent error swallowing
```

---

### Task 3: Cache SDK clients in PromptEnhancer

**Goal:** Fix HIGH finding #7. `PromptEnhancer.enhance()` creates a new `genai.Client` or `OpenAI` client on every invocation. Use the existing cached client factories `_get_openai_client()` and `_get_genai_client()` from `handlers.py`.

**Files to Modify:**
- `backend/src/api/enhance.py` -- Use cached clients instead of creating new ones

**Prerequisites:** None

**Implementation Steps:**
- In `enhance.py`, import the cached client factories: `from models.handlers import _get_openai_client, _get_genai_client`.
- In the `enhance()` method, replace `client = genai.Client(api_key=api_key)` (line 82) with `client = _get_genai_client(api_key)`.
- Replace `client = OpenAI(**client_kwargs)` (line 110) with `client = _get_openai_client(api_key, **{k: v for k, v in client_kwargs.items() if k != 'api_key'})`.
- Alternatively, if importing from `handlers.py` creates a circular import, move the client caching functions to a shared utility module (e.g., `backend/src/utils/clients.py`). Only do this if the import fails.

**Verification Checklist:**
- [ ] `enhance.py` no longer calls `genai.Client()` or `OpenAI()` directly
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/test_enhance.py -v` passes
- [ ] `ruff check backend/src/api/enhance.py` passes

**Testing Instructions:**
- Run existing enhance tests to verify no regressions.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_enhance.py -v`

**Commit Message Template:**
```
fix(backend): reuse cached SDK clients in PromptEnhancer
```

---

### Task 4: Add session_id validation in `handle_status`

**Goal:** Fix MEDIUM finding #11. `handle_status` extracts `session_id` by splitting the raw path without validation. Add regex validation matching the pattern used in `handle_gallery_detail`.

**Files to Modify:**
- `backend/src/lambda_function.py` -- Add validation in `handle_status` function

**Prerequisites:** None

**Implementation Steps:**
- Find `handle_status` in `lambda_function.py` (around line 558).
- After extracting `session_id` from the path, add a regex validation check. Use a UUID pattern or a reasonable alphanumeric pattern (e.g., `re.match(r'^[a-zA-Z0-9-]{1,64}$', session_id)`).
- If validation fails, return a 400 error response using the existing `error_response()` utility.
- Look at how `handle_gallery_detail` (around line 704) validates its input and follow the same pattern.

**Verification Checklist:**
- [ ] `handle_status` validates `session_id` format before using it
- [ ] Invalid session IDs return a 400 error response
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v` passes

**Testing Instructions:**
- Write tests in `test_lambda_function.py` for `handle_status` with valid and invalid session IDs.
- Test with path traversal patterns (e.g., `../../etc/passwd`) and overly long IDs.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v`

**Commit Message Template:**
```
fix(backend): add session_id validation in handle_status endpoint
```

---

### Task 5: Apply `sanitize_error_message()` and `fail_iteration()` safety net in `generate_for_model`

**Goal:** Fix HIGH finding #6 (unsanitized error messages) and MEDIUM finding from eval (iteration left as `in_progress` on crash). Ensure exceptions in `generate_for_model` are sanitized before being stored and that `fail_iteration()` is always called.

**Files to Modify:**
- `backend/src/lambda_function.py` -- Fix `generate_for_model` except block

**Prerequisites:** None

**Implementation Steps:**
- Find `generate_for_model` in `lambda_function.py` (around line 237).
- In the `except Exception as e:` block, import and apply `sanitize_error_message` from `models.handlers` to the error string before storing it.
- Ensure `session_manager.fail_iteration()` is called in the except block so the iteration status is updated to `error` rather than staying as `in_progress`.
- Structure as a try/except/finally or try/except with explicit `fail_iteration` call.

**Verification Checklist:**
- [ ] `generate_for_model` applies `sanitize_error_message()` to exception strings
- [ ] `generate_for_model` calls `fail_iteration()` on unhandled exceptions
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v` passes

**Testing Instructions:**
- Write a test that simulates a handler exception and verifies the error message is sanitized.
- Write a test that verifies `fail_iteration` is called when a handler raises.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v`

**Commit Message Template:**
```
fix(backend): sanitize error messages and ensure fail_iteration on handler exceptions
```

---

### Task 6: Add request body size validation and log endpoint metadata limits

**Goal:** Fix MEDIUM findings #13 (log injection) and stress eval finding (no body size limit). Add size guards to protect against oversized payloads.

**Files to Modify:**
- `backend/src/lambda_function.py` -- Add body size check before `json.loads()`, and limit metadata in `handle_log_endpoint`

**Prerequisites:** None

**Implementation Steps:**
- Near the top of each POST handler (`handle_generate`, `handle_iterate`, `handle_outpaint`, `handle_log_endpoint`), add a body size check before `json.loads()`. Use `len(event.get('body', ''))` and reject with a 413 error if it exceeds a reasonable limit (e.g., 1 MB for generation endpoints, 10 KB for log endpoint).
- In `handle_log_endpoint`, after parsing the body JSON, limit the `metadata` dict: restrict to known keys or cap the total serialized size. Remove any keys that could overwrite structured log fields (e.g., `timestamp`, `level`, `correlation_id`).
- Use `error_response()` from `utils.error_responses` for the 413 response.

**Verification Checklist:**
- [ ] POST handlers reject bodies exceeding size limits with 413 status
- [ ] `handle_log_endpoint` sanitizes metadata keys
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes

**Testing Instructions:**
- Write tests for oversized body rejection.
- Write tests for metadata key sanitization in `handle_log_endpoint`.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v`
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_log_endpoint.py -v`

**Commit Message Template:**
```
fix(backend): add request body size limits and sanitize log metadata
```

---

### Task 7: Increase frontend REQUEST_TIMEOUT

**Goal:** Fix LOW finding #25. `REQUEST_TIMEOUT` is 30 seconds but BFL polling can take 120+ seconds. The `/iterate` and `/outpaint` endpoints are synchronous and will time out.

**Files to Modify:**
- `frontend/src/api/config.ts` -- Increase `REQUEST_TIMEOUT`

**Prerequisites:** None

**Implementation Steps:**
- In `frontend/src/api/config.ts`, change `REQUEST_TIMEOUT` from `30000` (30 seconds) to `180000` (180 seconds / 3 minutes). This provides headroom above the 120s BFL polling maximum.
- Update the comment to explain the rationale: image generation can take up to 120+ seconds for some providers.

**Verification Checklist:**
- [ ] `REQUEST_TIMEOUT` is set to `180000`
- [ ] Comment explains the rationale
- [ ] `cd frontend && npm run typecheck` passes

**Testing Instructions:**
- `cd frontend && npm test`
- `cd frontend && npm run typecheck`

**Commit Message Template:**
```
fix(frontend): increase REQUEST_TIMEOUT to 180s for long-running generation requests
```

---

## Phase Verification

After all tasks are complete:

1. Full backend test suite passes: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
2. Backend lint passes: `ruff check backend/src/`
3. Frontend tests pass: `cd frontend && npm test`
4. Frontend lint + typecheck pass: `cd frontend && npm run lint && npm run typecheck`
5. New pagination tests verify >1000 key handling
6. No bare `except Exception: return []` patterns remain in `storage.py`
7. `handle_status` rejects malformed session IDs
8. `generate_for_model` sanitizes error messages and calls `fail_iteration`
