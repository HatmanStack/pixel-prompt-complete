# Phase 3: [IMPLEMENTER] Architecture Refactoring

## Phase Goal

Extract the shared validation/execution pipeline from `handle_generate`, `handle_iterate`, and `handle_outpaint` to eliminate ~70% code duplication. Improve stage prefix stripping logic. Fix the CORS wildcard to be configurable. This phase restructures internal code without changing external API contracts.

**Success criteria:**
- Shared request validation (body parsing, IP extraction, rate limiting, content filtering) is extracted into a reusable pipeline
- Shared result handling (image upload, iteration completion, context update) is extracted into a helper
- `handle_iterate` and `handle_outpaint` share a common base flow with only their unique logic (preset vs context) differing
- Stage prefix stripping uses proper prefix matching instead of magic numbers
- CORS `Access-Control-Allow-Origin` is configurable via environment variable
- All existing tests pass
- `lambda_function.py` is shorter and each handler function is focused on its unique logic

**Estimated tokens:** ~35,000

## Prerequisites

- Phase 2 completed (error handling and validation fixes in place)
- All backend tests passing: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`

## Tasks

---

### Task 1: Extract shared request validation into a pipeline helper

**Goal:** The three POST handlers (`handle_generate`, `handle_iterate`, `handle_outpaint`) all perform the same initial steps: parse JSON body, extract IP, check rate limits, validate prompt, and run content filter. Extract this into a shared helper function.

**Files to Modify:**
- `backend/src/lambda_function.py` -- Extract helper, refactor handlers to use it

**Prerequisites:** None

**Implementation Steps:**
- Create a helper function (e.g., `_parse_and_validate_request(event, require_prompt=True)`) that performs:
  1. Parse `event.get('body', '{}')` as JSON (raise on failure via `json.JSONDecodeError`)
  2. Extract IP from `requestContext.http.sourceIp` or fall back to `body.ip`
  3. Check rate limit via `rate_limiter.check_rate_limit(ip)` -- return 429 response if limited
  4. Extract and validate prompt (if `require_prompt=True`)
  5. Run content filter on prompt
  6. Return a tuple/dataclass of `(body, ip, prompt)` on success, or an error `ApiResponse` on failure
- Use a return pattern like `(None, error_response)` or `(validated_data, None)` so callers can check for errors. Alternatively, use a simple dataclass `ValidatedRequest` with the parsed fields.
- Refactor `handle_generate`, `handle_iterate`, and `handle_outpaint` to call this helper first and return early on error.
- For `handle_outpaint`, the prompt has a default value (`'continue the scene naturally'`) -- pass this to the helper or handle it after the call.
- **Important:** After extracting JSON parsing into `_parse_and_validate_request`, remove the now-dead `except json.JSONDecodeError` blocks from `handle_generate`, `handle_iterate`, and `handle_outpaint`. Since JSON parsing is handled entirely within `_parse_and_validate_request`, these outer `try/except json.JSONDecodeError` catches become unreachable dead code. Removing them reduces handler line counts and avoids confusion.

**Verification Checklist:**
- [x] A shared validation helper exists and is used by all 3 POST handlers
- [x] Rate limiting, content filtering, and prompt validation logic appears only once
- [x] `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v` passes
- [x] `ruff check backend/src/lambda_function.py` passes

**Testing Instructions:**
- All existing tests should pass without modification since behavior is unchanged.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v`
- `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`

**Commit Message Template:**
```
refactor(backend): extract shared request validation pipeline from POST handlers
```

---

### Task 2: Extract shared result handling into a helper

**Goal:** After a handler returns a successful result, `handle_generate` (inside `generate_for_model`), `handle_iterate`, and `handle_outpaint` all perform the same sequence: upload image, complete iteration, add context entry. Extract this into a reusable helper.

**Files to Modify:**
- `backend/src/lambda_function.py` -- Extract result handling helper

**Prerequisites:** Task 1

**Implementation Steps:**
- Create a helper function (e.g., `_handle_successful_result(session_id, model_name, prompt, result, iteration_index, target, duration)`) that performs:
  1. Upload image via `image_storage.upload_image()`
  2. Complete iteration via `session_manager.complete_iteration()`
  3. Create and add context entry via `context_manager.add_entry()`
  4. Return the image key and CloudFront URL
- Create a corresponding `_handle_failed_result(session_id, model_name, iteration_index, error_msg)` that calls `session_manager.fail_iteration()`.
- Refactor `generate_for_model`, `handle_iterate`, and `handle_outpaint` to use these helpers.
- For `handle_outpaint`, the prompt stored in context differs (`f"outpaint:{preset}"`) -- pass this as a parameter or let the caller specify the context prompt.

**Verification Checklist:**
- [x] Image upload + iteration completion + context update appears only once (in the helper)
- [x] All 3 handlers use the shared helpers for success and failure paths
- [x] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes

**Testing Instructions:**
- All existing tests should pass without modification.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v`

**Commit Message Template:**
```
refactor(backend): extract shared result handling from generate, iterate, and outpaint
```

---

### Task 3: Unify `handle_iterate` and `handle_outpaint` common logic

**Goal:** After Tasks 1-2, `handle_iterate` and `handle_outpaint` still share ~80% identical code for model validation, iteration counting, source image loading, and handler dispatch. Extract this shared flow.

**Files to Modify:**
- `backend/src/lambda_function.py` -- Create unified refinement handler

**Prerequisites:** Tasks 1 and 2

**Implementation Steps:**

The key goal is to eliminate ALL duplicated logic between `handle_iterate` and `handle_outpaint`. After Tasks 1-2, there should already be shared validation (`_parse_and_validate_request`) and shared result handling (`_handle_successful_result` / `_handle_failed_result`). The remaining duplicated code is the dispatch-and-result-handling flow: model validation, iteration counting, source image loading, handler dispatch, try/except around the handler call, and result branching. ALL of this must be extracted.

- Create a unified helper function `_handle_refinement(event, correlation_id, handler_callable, context_prompt)` that:
  1. Calls the shared validation helper (from Task 1)
  2. Validates `sessionId` and `model` from body
  3. Validates `model_name` is in MODELS and enabled
  4. Checks iteration count against `MAX_ITERATIONS`
  5. Loads source image from latest iteration
  6. Adds new iteration to session
  7. Calls `handler_callable(config, source_image, ...)` inside a `try/except`
  8. On success: calls `_handle_successful_result(...)` (from Task 2)
  9. On failure: calls `_handle_failed_result(...)` (from Task 2)
  10. Returns the final API response

- The `handler_callable` parameter is a callable that the thin wrapper provides. This avoids a type flag and keeps the dispatch clean.

- `handle_iterate` becomes a thin wrapper (~10-15 lines) that:
  1. Gets context from `ContextManager`
  2. Resolves the handler via `get_iterate_handler(provider)`
  3. Creates a lambda/partial that calls `iterate_handler(config, source_image, prompt, context)`
  4. Calls `_handle_refinement(event, correlation_id, handler_callable, prompt)`

- `handle_outpaint` becomes a thin wrapper (~10-15 lines) that:
  1. Extracts preset from body
  2. Resolves the handler via `get_outpaint_handler(provider)`
  3. Creates a lambda/partial that calls `outpaint_handler(config, source_image, preset, prompt)`
  4. Calls `_handle_refinement(event, correlation_id, handler_callable, f"outpaint:{preset}")`

- **Critical:** Do NOT leave the `try/except` error handling and result branching duplicated in both wrappers. The entire dispatch-try-except-result flow must live inside `_handle_refinement`. The wrappers should only contain logic that is truly unique to their endpoint (context retrieval for iterate, preset extraction for outpaint).

- **Critical:** Do NOT leave `except json.JSONDecodeError` blocks in the wrappers -- JSON parsing is handled by `_parse_and_validate_request` (see Task 1 of this phase). See also the note about dead `JSONDecodeError` catches in Task 1 below.

**Verification Checklist:**
- [x] `handle_iterate` and `handle_outpaint` are significantly shorter (each <30 lines)
- [x] Shared validation/loading/dispatch logic appears only once
- [x] `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v` passes
- [x] `ruff check backend/src/lambda_function.py` passes

**Testing Instructions:**
- All existing iterate and outpaint tests must pass unchanged.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v`

**Commit Message Template:**
```
refactor(backend): unify handle_iterate and handle_outpaint shared logic
```

---

### Task 4: Fix stage prefix stripping with proper prefix matching

**Goal:** Fix MEDIUM finding #18. Replace hardcoded string slicing (`path[6:]`, `path[9:]`) with proper prefix matching that handles any stage name.

**Files to Modify:**
- `backend/src/lambda_function.py` -- Fix stage prefix logic in `lambda_handler`

**Prerequisites:** None

**Implementation Steps:**
- In `lambda_handler` (around lines 86-93), replace the hardcoded length-based slicing with a general approach. For example:
  ```python
  known_stages = ['/Prod/', '/Staging/', '/Dev/']
  for stage in known_stages:
      if path.startswith(stage):
          path = path[len(stage):]
          break
  ```
- Or use a regex: `path = re.sub(r'^/(Prod|Staging|Dev)/', '', path)`.
- Ensure the path still gets a leading `/` added if missing.

**Verification Checklist:**
- [x] No magic numbers (`path[6:]`, `path[9:]`) remain in stage stripping logic
- [x] Stage stripping works for `/Prod/`, `/Staging/`, and `/Dev/` prefixes
- [x] `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v` passes

**Testing Instructions:**
- Write a test that sends events with different stage prefixes and verifies correct routing.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v`

**Commit Message Template:**
```
refactor(backend): replace magic number stage prefix stripping with proper prefix matching
```

---

### Task 5: Make CORS origin configurable

**Goal:** Fix HIGH finding #5. Replace hardcoded `Access-Control-Allow-Origin: '*'` with an environment-variable-configured value.

**Files to Modify:**
- `backend/src/lambda_function.py` -- Make CORS origin configurable
- `backend/src/config.py` -- Add `cors_allowed_origin` config variable
- `backend/template.yaml` -- Add environment variable for CORS origin

**Prerequisites:** None

**Implementation Steps:**
- In `config.py`, add: `cors_allowed_origin = os.environ.get('CORS_ALLOWED_ORIGIN', '*')` near the other environment variable reads.
- In `lambda_function.py`, find the `response()` function (around line 750-760) that sets CORS headers. Import `cors_allowed_origin` from `config` and use it instead of the hardcoded `'*'`.
- In `template.yaml`, add `CORS_ALLOWED_ORIGIN` to the Lambda environment variables section, defaulting to `'*'` for backward compatibility.
- The default remains `*` so this is a non-breaking change. Operators can restrict it by setting the env var.

**Verification Checklist:**
- [x] `cors_allowed_origin` is defined in `config.py`
- [x] `response()` uses `cors_allowed_origin` instead of hardcoded `'*'`
- [x] `template.yaml` includes `CORS_ALLOWED_ORIGIN` environment variable
- [x] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes

**Testing Instructions:**
- Write a test that sets `CORS_ALLOWED_ORIGIN` env var and verifies the response header matches.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v`

**Commit Message Template:**
```
fix(backend): make CORS allowed origin configurable via environment variable
```

---

## Phase Verification

After all tasks are complete:

1. Full backend test suite passes: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
2. Backend lint passes: `ruff check backend/src/`
3. `lambda_function.py` is significantly shorter than its pre-Phase-3 size
4. No duplicated validation/result-handling patterns across handlers
5. Stage prefix stripping uses no magic numbers
6. CORS origin is configurable
7. All API behavior is unchanged (same request/response contracts)
