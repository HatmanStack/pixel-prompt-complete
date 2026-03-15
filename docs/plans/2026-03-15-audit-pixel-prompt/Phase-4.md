# Phase 4: [FORTIFIER] Type Safety, Frozen Configs, CI Guardrails, and Test Quality

## Phase Goal

Add defensive guardrails to prevent regressions: freeze `ModelConfig` dataclasses to prevent accidental mutation, improve Python type rigor in handler return types, fix the eslint-disable suppression in `GenerationPanel.tsx`, migrate `test_context_manager.py` from MagicMock to moto, and add a backend lockfile for reproducible builds.

**Success criteria:**
- `ModelConfig` dataclass is frozen (immutable)
- Handler functions use typed return dicts instead of `Dict[str, Any]`
- The `eslint-disable-next-line` in `GenerationPanel.tsx` is resolved by fixing the dependency array
- `test_context_manager.py` uses moto-backed S3 instead of MagicMock
- A pinned `requirements-lock.txt` exists for the backend
- A backend `.env.example` documents required Lambda environment variables
- All tests pass

**Estimated tokens:** ~20,000

## Prerequisites

- Phase 3 completed (architecture refactoring done)
- All tests passing

## Tasks

---

### Task 1: Freeze `ModelConfig` dataclass

**Goal:** Fix MEDIUM finding #14. `ModelConfig` is mutable, allowing accidental runtime mutation that persists across Lambda invocations.

**Files to Modify:**
- `backend/src/config.py` -- Add `frozen=True` to `@dataclass`

**Prerequisites:** None

**Implementation Steps:**
- Change `@dataclass` on `ModelConfig` (line 36) to `@dataclass(frozen=True)`.
- This prevents setting attributes after construction. If any code mutates `ModelConfig` instances, it will raise `FrozenInstanceError` at runtime. Search for any code that sets attributes on `ModelConfig` instances and fix it.
- Run all tests to verify nothing depends on mutating configs.

**Verification Checklist:**
- [ ] `@dataclass(frozen=True)` is on `ModelConfig`
- [ ] `grep -r "model_config\.\w\+ =" backend/src/` shows no post-construction mutations (except in `__init__`)
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes

**Testing Instructions:**
- Run all backend tests. If any test mutates a `ModelConfig`, fix the test to create a new instance instead.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_config.py -v`
- `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`

**Commit Message Template:**
```
fix(backend): freeze ModelConfig dataclass to prevent accidental mutation
```

---

### Task 2: Add typed return dicts for handler functions

**Goal:** Improve type rigor in handler return types. Replace `Dict[str, Any]` type aliases with TypedDict definitions for handler return values.

**Files to Modify:**
- `backend/src/models/handlers.py` -- Add TypedDict definitions, update type aliases

**Prerequisites:** None (types.py was deleted in Phase 1; we are creating fresh, aligned types)

**Implementation Steps:**
- At the top of `handlers.py`, define TypedDicts for handler return values:
  ```python
  from typing import TypedDict, Literal, NotRequired

  class HandlerSuccess(TypedDict):
      status: Literal['success']
      image: str
      model: NotRequired[str]
      provider: NotRequired[str]

  class HandlerError(TypedDict):
      status: Literal['error']
      error: str
      model: NotRequired[str]
      provider: NotRequired[str]

  HandlerResult = HandlerSuccess | HandlerError
  ```
- Update the existing type aliases `HandlerFunc`, `IterateHandlerFunc`, `OutpaintHandlerFunc` to use `HandlerResult` as their return type instead of `Dict[str, Any]`.
- Update handler function return type annotations to use `HandlerResult`.
- This is a type annotation change only -- no runtime behavior changes.

**Verification Checklist:**
- [ ] `HandlerResult` TypedDict is defined in `handlers.py`
- [ ] Handler function signatures use `HandlerResult` return type
- [ ] No `Dict[str, Any]` remains in handler type aliases
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/test_handlers.py -v` passes
- [ ] `ruff check backend/src/models/handlers.py` passes

**Testing Instructions:**
- Run handler tests to verify no regressions.
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_handlers.py -v`

**Commit Message Template:**
```
refactor(backend): add TypedDict return types for handler functions
```

---

### Task 3: Fix eslint-disable in GenerationPanel.tsx

**Goal:** Fix MEDIUM finding #19. Remove the `eslint-disable-next-line react-hooks/exhaustive-deps` suppression by properly managing the `useEffect` dependency array.

**Files to Modify:**
- `frontend/src/components/generation/GenerationPanel.tsx` -- Fix the useEffect dependency array

**Prerequisites:** None

**Implementation Steps:**
- Find the `useEffect` with the eslint-disable comment (around line 278).
- Read the effect body to understand what it captures from its closure.
- If it references `handleGenerate`, wrap `handleGenerate` in `useCallback` with the correct dependencies and add it to the effect's dependency array.
- Remove the `eslint-disable-next-line` comment.
- If the `handleGenerate` function is already wrapped in `useCallback`, check its dependency array and fix it.
- The key concern is stale closures in keyboard shortcut handlers -- make sure the handler always has access to current values of `prompt`, `isGenerating`, etc.

**Verification Checklist:**
- [ ] No `eslint-disable-next-line react-hooks/exhaustive-deps` remains in the file
- [ ] `cd frontend && npm run lint` passes (the exhaustive-deps rule no longer fires)
- [ ] `cd frontend && npm run typecheck` passes
- [ ] `cd frontend && npm test` passes

**Testing Instructions:**
- `cd frontend && npm run lint`
- `cd frontend && npm run typecheck`
- `cd frontend && npm test`

**Commit Message Template:**
```
fix(frontend): resolve useEffect exhaustive-deps violation in GenerationPanel
```

---

### Task 4: Migrate `test_context_manager.py` from MagicMock to moto

**Goal:** Address Day 2 eval finding about inconsistent mock strategies. `test_context_manager.py` uses `MagicMock` for S3 while `test_session_manager.py` uses moto. Align to moto.

**Files to Modify:**
- `tests/backend/unit/test_context_manager.py` -- Rewrite to use moto S3

**Prerequisites:** None

**Implementation Steps:**
- Read the existing `test_context_manager.py` to understand what behaviors are being tested.
- Rewrite using the `mock_s3` fixture from `conftest.py` (same pattern as `test_session_manager.py`).
- Create real `ContextManager` instances with the moto S3 client and test bucket.
- Assert on observable behavior (what gets stored in and retrieved from S3) rather than mock call counts.
- Test the core flows: `get_context` (empty), `add_entry`, `add_entry` beyond window size (FIFO eviction), `get_context_for_iteration`, concurrent `add_entry` (ETag conflict retry).

**Verification Checklist:**
- [ ] `test_context_manager.py` uses `mock_s3` fixture, not `MagicMock` for S3
- [ ] Tests assert on observable S3 state, not mock call counts
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/test_context_manager.py -v` passes

**Testing Instructions:**
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_context_manager.py -v`

**Commit Message Template:**
```
test(backend): migrate test_context_manager from MagicMock to moto S3
```

---

### Task 5: Add backend lockfile and .env.example

**Goal:** Address Day 2 reproducibility finding. Create a pinned dependency lockfile and a backend `.env.example` documenting required Lambda environment variables.

**Files to Create:**
- `backend/requirements-lock.txt` -- Pinned dependency versions
- `backend/.env.example` -- Documented environment variables

**Prerequisites:** None

**Implementation Steps:**
- Generate a pinned lockfile from the current installed packages. Run `pip freeze > backend/requirements-lock.txt` from a clean install of `backend/src/requirements.txt`. Alternatively, install and use `pip-compile` from `pip-tools`.
- Create `backend/.env.example` listing all environment variables read by `config.py` and `template.yaml`. Group by category (AWS, Models, Rate Limiting, Operational). Use format:
  ```
  # AWS Configuration
  AWS_REGION=us-west-2
  S3_BUCKET=your-bucket-name
  CLOUDFRONT_DOMAIN=your-distribution.cloudfront.net

  # Model API Keys (required)
  FLUX_API_KEY=
  RECRAFT_API_KEY=
  GEMINI_API_KEY=
  OPENAI_API_KEY=
  ```
- Include comments explaining each variable and its default value.

**Verification Checklist:**
- [ ] `backend/requirements-lock.txt` exists with pinned versions (e.g., `boto3==1.x.x`)
- [ ] `backend/.env.example` lists all env vars from `config.py`
- [ ] `pip install -r backend/requirements-lock.txt` succeeds

**Testing Instructions:**
- Verify lockfile works: `pip install -r backend/requirements-lock.txt` in a fresh venv.

**Commit Message Template:**
```
chore(backend): add requirements lockfile and .env.example for reproducibility
```

---

## Phase Verification

After all tasks are complete:

1. Full backend test suite passes: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
2. Backend lint passes: `ruff check backend/src/`
3. Frontend tests pass: `cd frontend && npm test`
4. Frontend lint passes with no suppressions: `cd frontend && npm run lint`
5. `ModelConfig` is frozen (attempts to mutate raise `FrozenInstanceError`)
6. Handler return types use `HandlerResult` TypedDict
7. `test_context_manager.py` uses moto, not MagicMock
8. `backend/requirements-lock.txt` and `backend/.env.example` exist
