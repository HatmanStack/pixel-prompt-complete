# Phase 1 [HYGIENIST]: Stale Reference Cleanup

## Phase Goal

Fix stale code comments and docstrings that reference the old model names ("flux", "recraft") instead of the current models ("nova", "firefly"). These were left behind when the model lineup changed.

**Success criteria:** All comments and docstrings referencing model names list the correct 4 models: gemini, nova, openai, firefly.

**Estimated tokens:** ~3,000

## Prerequisites

- None (first phase)

## Tasks

### Task 1: Fix Stale Model Name References

**Goal:** Update 3 locations where code comments/docstrings list the old model names.

**Files to Modify:**

- `backend/src/config.py` — line 43 comment
- `backend/src/jobs/manager.py` — line 39 comment, line 125 docstring

**Implementation Steps:**

1. Read `backend/src/config.py` and find the comment on line 43 that says `'flux', 'recraft', 'gemini', 'openai'`
1. Change it to `'gemini', 'nova', 'openai', 'firefly'`
1. Read `backend/src/jobs/manager.py` and find:
   - Line 39: comment `4 model columns (flux, recraft, gemini, openai)` — change to `4 model columns (gemini, nova, openai, firefly)`
   - Line 125: docstring `Model name ('flux', 'recraft', 'gemini', 'openai')` — change to `Model name ('gemini', 'nova', 'openai', 'firefly')`

**Verification Checklist:**

- [x] No references to "flux" or "recraft" remain in `config.py` or `manager.py`
- [x] All 3 locations updated to list gemini, nova, openai, firefly
- [x] `ruff check backend/src/` passes
- [x] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes (no behavioral change)

**Testing Instructions:**

No new tests needed — these are comment-only changes. Run existing tests to confirm no regressions.

**Commit Message Template:**

```text
fix(backend): update stale model name references in comments

- config.py: fix ModelConfig comment to list current models
- manager.py: fix class docstring and add_iteration docstring
```

## Phase Verification

- `grep -rn "flux\|recraft" backend/src/config.py backend/src/jobs/manager.py` returns no results
- All existing backend tests pass
