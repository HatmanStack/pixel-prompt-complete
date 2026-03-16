# Phase 1: [HYGIENIST] Dead Code Removal and Dependency Cleanup

## Phase Goal

Remove all confirmed dead code, unused configuration, stale functions, and no-op stubs from the codebase. Fix npm audit vulnerabilities in dev dependencies. This is purely subtractive work -- no new functionality is added. The goal is to reduce cognitive load and maintenance surface area before structural changes begin in later phases.

**Success criteria:**
- All confirmed dead Python functions, variables, and modules are removed
- Associated dead tests are removed or updated
- Frontend no-op callback and placeholder test are cleaned up
- `npm audit` shows zero high-severity vulnerabilities
- All existing tests pass (`PYTHONPATH=backend/src pytest tests/backend/unit/ -v` and `cd frontend && npm test`)
- `ruff check backend/src/` passes
- `cd frontend && npm run lint && npm run typecheck` passes

**Estimated tokens:** ~15,000

## Prerequisites

- Phase 0 read and understood
- Repository cloned at `/home/user/pixel-prompt-complete`
- `npm install` completed in `frontend/`
- Python dependencies installed per `backend/src/requirements.txt`

## Tasks

---

### Task 1: Remove unused Python config variables and functions

**Goal:** Remove `is_model_enabled()`, `MODEL_ORDER`, `handler_timeout`, and `max_thread_workers` from `config.py`. These are defined but never used in production code.

**Files to Modify:**
- `backend/src/config.py` -- Remove the 4 dead items
- `tests/backend/unit/test_config.py` -- Remove or update `test_is_model_enabled` test

**Prerequisites:** None

**Implementation Steps:**
- In `backend/src/config.py`, delete the `is_model_enabled()` function (lines 142-146) and the `MODEL_ORDER` list (line 166). Delete `handler_timeout` (line 171) and `max_thread_workers` (line 172).
- In `tests/backend/unit/test_config.py`, remove the `test_is_model_enabled` test method since the function it tests will no longer exist.
- Verify no other test files import these symbols.

**Verification Checklist:**
- [x]`is_model_enabled`, `MODEL_ORDER`, `handler_timeout`, `max_thread_workers` no longer exist in `config.py`
- [x]`grep -r "is_model_enabled\|MODEL_ORDER\|handler_timeout\|max_thread_workers" backend/src/` returns no results
- [x]`PYTHONPATH=backend/src pytest tests/backend/unit/test_config.py -v` passes
- [x]`ruff check backend/src/config.py` passes

**Testing Instructions:**
- No new tests needed. Run existing test suite to verify nothing breaks.
- `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`

**Commit Message Template:**
```
chore(backend): remove unused config variables and is_model_enabled function
```

---

### Task 2: Remove dead backend functions

**Goal:** Remove confirmed dead functions across backend modules: `save_image()` in storage.py (superseded by `upload_image()`), `job_not_found()` in error_responses.py (legacy job concept), `reset_cache()` no-op in rate_limit.py, `clear_context()` and `_save_context()` in context.py (superseded by conditional variants).

**Files to Modify:**
- `backend/src/utils/storage.py` -- Remove `save_image()` method
- `backend/src/utils/error_responses.py` -- Remove `job_not_found()` function
- `backend/src/utils/rate_limit.py` -- Remove `reset_cache()` no-op function
- `backend/src/models/context.py` -- Remove `clear_context()` and `_save_context()` methods

**Prerequisites:** None

**Implementation Steps:**
- In `storage.py`, delete the `save_image` method (lines 68-93). Keep `upload_image` which is the active replacement.
- In `error_responses.py`, delete the `job_not_found` function (lines 121-130).
- In `rate_limit.py`, delete the `reset_cache` function (lines 23-24).
- In `context.py`, delete the `clear_context` method (lines 145-158) and the `_save_context` method (lines 160-190). Keep `_save_context_conditional` which is the active replacement.
- Search for any test files that reference these deleted functions and update accordingly.

**Verification Checklist:**
- [x]`grep -r "save_image\b" backend/src/` returns only doc references, not function definitions
- [x]`grep -r "job_not_found\|reset_cache\|clear_context\|_save_context[^_]" backend/src/` returns no function definitions
- [x]`PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes
- [x]`ruff check backend/src/` passes

**Testing Instructions:**
- Run full backend test suite. If any tests reference deleted functions, remove those test cases.
- `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`

**Commit Message Template:**
```
chore(backend): remove dead functions from storage, error_responses, rate_limit, context
```

---

### Task 3: Remove unused handlers.py dead code (Bedrock, Stability, Imagen, Generic)

**Goal:** Remove handler functions and client singletons for providers not used by the 4 configured models. The active providers are `bfl`, `recraft`, `google_gemini`, and `openai`. The dead handlers are: `handle_bedrock_nova`, `handle_bedrock_sd`, `handle_stability`, `handle_google_imagen`, `handle_generic`, and their client singletons `_bedrock_nova_client`, `_bedrock_sd_client`, `_get_bedrock_nova_client()`, `_get_bedrock_sd_client()`.

**Files to Modify:**
- `backend/src/models/handlers.py` -- Remove dead handler functions and client singletons
- `backend/src/config.py` -- Remove `bedrock_nova_region` and `bedrock_sd_region` (only used by deleted handlers)
- `tests/backend/unit/test_handlers.py` -- Remove tests for deleted handlers

**Prerequisites:** None

**Implementation Steps:**

> **Note:** All line numbers in this task (and throughout this plan) are approximate references based on the file state before earlier tasks. Since Tasks 1 and 2 modify `config.py`, line numbers in that file will have shifted. **Always search by function/variable name rather than relying on exact line numbers.** The function and variable names are the authoritative identifiers.

- In `handlers.py`, remove:
  - `_bedrock_nova_client` and `_bedrock_sd_client` globals (approximately lines 39-40)
  - `_get_bedrock_nova_client()` and `_get_bedrock_sd_client()` functions (approximately lines 64-83)
  - `handle_google_imagen()` function
  - `handle_bedrock_nova()` function
  - `handle_bedrock_sd()` function
  - `handle_stability()` function
  - `handle_generic()` function
  - Remove the corresponding entries from the handler dict in `get_handler()`: `'google_imagen'`, `'bedrock_nova'`, `'bedrock_sd'`, `'stability'`, `'generic'`
  - Remove the fallback to `handle_generic` in `get_handler()` -- instead raise `ValueError` for unknown providers
  - Remove the `import boto3` if no remaining code uses it
- In `config.py`, remove `bedrock_nova_region` and `bedrock_sd_region` (search for these variable names; originally around lines 51-52 but may have shifted after Tasks 1-2) since they are only imported by the deleted handler code.
- Update the `from config import` statement in `handlers.py` to remove `bedrock_nova_region` and `bedrock_sd_region`.
- In `test_handlers.py`, remove any test cases for the deleted handlers.

**Verification Checklist:**
- [x]`grep -r "bedrock\|stability\|handle_generic\|google_imagen" backend/src/` returns no function definitions (config references in docs are acceptable)
- [x]`handlers.py` is significantly shorter (should drop by ~300+ lines)
- [x]`get_handler()` only contains `bfl`, `recraft`, `google_gemini`, `openai` entries
- [x]`PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes
- [x]`ruff check backend/src/` passes

**Testing Instructions:**
- Run full backend test suite after removal.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_handlers.py -v`
- `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`

**Commit Message Template:**
```
chore(backend): remove unused Bedrock, Stability, Imagen, and generic handlers
```

---

### Task 4: Remove or decide on unused types.py module

**Goal:** The `backend/src/models/types.py` module defines Protocol classes and TypedDicts that are never imported anywhere. Remove the module entirely. (Phase 4 will introduce proper type contracts aligned with actual runtime shapes.)

**Files to Modify:**
- `backend/src/models/types.py` -- Delete this file

**Prerequisites:** None

**Implementation Steps:**
- Verify no code imports from `models.types`: `grep -r "from models.types\|from models import.*types\|import models.types" backend/src/ tests/`
- Delete `backend/src/models/types.py`.

**Verification Checklist:**
- [x]`backend/src/models/types.py` no longer exists
- [x]`PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes
- [x]`ruff check backend/src/` passes

**Testing Instructions:**
- Run full backend test suite.
- `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`

**Commit Message Template:**
```
chore(backend): remove unused types.py module
```

---

### Task 5: Clean up frontend dead code and placeholder test

**Goal:** Remove the no-op `handleGallerySelect` in `GenerationPanel.tsx` (replace with inline empty function or remove prop) and replace the `expect(true).toBe(true)` placeholder assertion in `ImageCard.test.jsx`.

**Files to Modify:**
- `frontend/src/components/generation/GenerationPanel.tsx` -- Fix or remove no-op `handleGallerySelect`
- `frontend/tests/__tests__/components/ImageCard.test.jsx` -- Replace placeholder assertion

**Prerequisites:** None

**Implementation Steps:**
- In `GenerationPanel.tsx`, the `handleGallerySelect` function (around line 282) is a no-op passed to `GalleryBrowser`. Since `GalleryBrowser` accepts `onGallerySelect` as optional (`onGallerySelect?:`), remove the `handleGallerySelect` function definition and stop passing the prop to `GalleryBrowser`. Remove the prop entirely from the JSX: change `<GalleryBrowser onGallerySelect={handleGallerySelect} />` to `<GalleryBrowser />`.
- In `ImageCard.test.jsx` around line 197, find the `expect(true).toBe(true)` assertion. Either write a meaningful assertion for whatever the test is supposed to verify (read the test name/description for intent) or remove the entire test case if it has no meaningful purpose.

**Verification Checklist:**
- [x]`grep -r "handleGallerySelect" frontend/src/` returns no results
- [x]`grep -r "expect(true).toBe(true)" frontend/tests/` returns no results
- [x]`cd frontend && npm test` passes
- [x]`cd frontend && npm run lint && npm run typecheck` passes

**Testing Instructions:**
- `cd frontend && npm test`
- `cd frontend && npm run lint`
- `cd frontend && npm run typecheck`

**Commit Message Template:**
```
chore(frontend): remove no-op gallery handler and placeholder test assertion
```

---

### Task 6: Fix npm audit vulnerabilities

**Goal:** Resolve the 8 npm audit vulnerabilities (5 moderate, 3 high) in frontend dev dependencies. These are in rollup, flatted, minimatch, and vitest/vite.

**Files to Modify:**
- `frontend/package.json` -- Version bumps as needed
- `frontend/package-lock.json` -- Regenerated by npm

**Prerequisites:** Tasks 1-5 completed (clean slate)

**Implementation Steps:**
- Run `cd frontend && npm audit` to see current state.
- Run `cd frontend && npm audit fix` to apply automatic fixes.
- If `npm audit fix` does not resolve all issues, run `npm audit fix --force` cautiously or manually update specific packages in `package.json`.
- Run `npm test` after fixing to ensure no regressions.
- Run `npm run build` to verify the production build still works.

**Verification Checklist:**
- [x]`cd frontend && npm audit` shows zero high-severity vulnerabilities
- [x]`cd frontend && npm test` passes
- [x]`cd frontend && npm run build` completes successfully
- [x]`cd frontend && npm run lint && npm run typecheck` passes

**Testing Instructions:**
- `cd frontend && npm test`
- `cd frontend && npm run build`

**Commit Message Template:**
```
chore(frontend): fix npm audit vulnerabilities in dev dependencies
```

---

## Phase Verification

After all tasks are complete:

1. Full backend test suite passes: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
2. Backend lint passes: `PYTHONPATH=backend/src ruff check backend/src/`
3. Frontend tests pass: `cd frontend && npm test`
4. Frontend lint + typecheck pass: `cd frontend && npm run lint && npm run typecheck`
5. Frontend build succeeds: `cd frontend && npm run build`
6. No dead code references remain in production source (verify with grep for removed function names)
7. `handlers.py` line count has decreased by ~300+ lines
