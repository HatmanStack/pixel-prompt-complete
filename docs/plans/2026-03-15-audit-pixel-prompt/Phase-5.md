# Phase 5: [DOC-ENGINEER] Documentation Alignment

## Phase Goal

Fix all documentation drift, gaps, stale references, and broken links identified in the doc-audit. Align CLAUDE.md, README.md, and CONTRIBUTING.md with the actual codebase state (including changes from Phases 1-4). This is the final phase because documentation must reflect the post-remediation codebase.

**Success criteria:**
- All 6 DRIFT findings resolved
- All 5 GAP findings resolved
- All 2 STALE findings resolved
- Broken LICENSE link resolved
- CONTRIBUTING.md references fixed
- CLAUDE.md module tree, model IDs, CI description, hooks list, and test structure match actual code
- No documentation references to code that was removed in Phase 1

**Estimated tokens:** ~15,000

## Prerequisites

- Phases 1-4 completed (codebase changes finalized)
- Familiarity with what was changed in each prior phase

## Tasks

---

### Task 1: Fix CLAUDE.md backend module structure and stale references

**Goal:** Fix DRIFT findings #3 (stale `registry.py`), STALE finding #1 (same), and GAP finding #1 (missing `types.py`). Note: `types.py` was deleted in Phase 1 and `registry.py` never existed -- remove both from the tree. Also update the tree to reflect any structural changes from Phases 1-3.

**Files to Modify:**
- `CLAUDE.md` -- Update backend module structure tree (around lines 56-77)

**Prerequisites:** Phase 1 completed (types.py deleted, dead code removed)

**Implementation Steps:**
- In the `backend/src/` tree in CLAUDE.md:
  - Remove the line `│   ├── registry.py          # ModelRegistry (legacy, still present)` -- this file does not exist.
  - Do NOT add `types.py` -- it was deleted in Phase 1.
  - Verify the remaining tree entries match actual files by running `ls -R backend/src/` and comparing.
  - Update descriptions if any module's purpose changed (e.g., `config.py` now has `frozen=True` ModelConfig).
- Remove or update the comment about the `models/` directory to reflect that it contains only `__init__.py`, `handlers.py`, and `context.py`.

**Verification Checklist:**
- [ ] `registry.py` is not mentioned in CLAUDE.md module tree
- [ ] `types.py` is not mentioned in CLAUDE.md module tree
- [ ] Every file listed in the tree exists on disk
- [ ] Every Python file in `backend/src/` (excluding `__init__.py`) is listed in the tree

**Testing Instructions:**
- Manual verification: compare tree listing in CLAUDE.md with `find backend/src -name "*.py" -not -name "__init__.py" | sort`

**Commit Message Template:**
```
docs: fix CLAUDE.md backend module structure to match actual codebase
```

---

### Task 2: Fix model ID drift between CLAUDE.md, README.md, and code

**Goal:** Fix DRIFT findings #1, #2, and #6. The model default IDs are inconsistent between `config.py`, `template.yaml`, CLAUDE.md, and README.md. Align all documentation to match the `template.yaml` values (which are the deployed defaults).

**Files to Modify:**
- `CLAUDE.md` -- Verify model ID table (already matches template.yaml per audit -- confirm still accurate)
- `README.md` -- Update model ID table to match template.yaml
- `backend/src/config.py` -- Update Python fallback defaults to match template.yaml

**Prerequisites:** None

**Implementation Steps:**
- The authoritative source for model IDs is `template.yaml` (the SAM deployment template). Read `backend/template.yaml` to confirm the current default values for `FLUX_MODEL_ID` and `GEMINI_MODEL_ID`.
- In `config.py`, update the fallback defaults:
  - Change `flux-pro-1.1` to match the `template.yaml` value for `FLUX_MODEL_ID`
  - Change `gemini-2.0-flash-exp` to match the `template.yaml` value for `GEMINI_MODEL_ID`
- In `README.md`, update the model default IDs table to match `template.yaml`.
- In `CLAUDE.md`, verify the table already matches (it should per the audit). Update if needed.

**Verification Checklist:**
- [ ] `config.py` Flux default matches `template.yaml` Flux default
- [ ] `config.py` Gemini default matches `template.yaml` Gemini default
- [ ] CLAUDE.md model table matches `template.yaml`
- [ ] README.md model table matches `template.yaml`
- [ ] All four sources agree on all model default IDs

**Testing Instructions:**
- `PYTHONPATH=backend/src pytest tests/backend/unit/test_config.py -v` (ensure tests don't hardcode old defaults)

**Commit Message Template:**
```
docs: align model default IDs across config.py, template.yaml, CLAUDE.md, and README.md
```

---

### Task 3: Fix CLAUDE.md CI description and hooks listing

**Goal:** Fix DRIFT findings #4 (`useJobPolling` does not exist) and #5 (CI description is incomplete).

**Files to Modify:**
- `CLAUDE.md` -- Fix hooks listing and CI description

**Prerequisites:** None

**Implementation Steps:**
- In the "Key Hooks" section (around line 140-145):
  - Remove `useJobPolling` from the listing. Only `useSessionPolling` exists.
  - Change the line to: `- \`useSessionPolling\` -- Poll /status/{sessionId} until complete`
- In the CI description (around line 48-50):
  - Update to mention `format:check` in frontend lint
  - Add mention of the `e2e-tests` job with LocalStack
  - Add mention of the `status-check` gate job
  - Example: "Runs on push/PR to main/develop: frontend format check + lint + typecheck -> frontend tests -> backend lint + tests -> E2E tests (LocalStack) -> status gate."

**Verification Checklist:**
- [ ] `useJobPolling` does not appear in CLAUDE.md
- [ ] CI description mentions format:check, E2E tests, and status gate
- [ ] Listed hooks match actual files in `frontend/src/hooks/`

**Testing Instructions:**
- Manual verification: compare hooks listed with `ls frontend/src/hooks/`

**Commit Message Template:**
```
docs: fix CLAUDE.md hooks listing and CI description
```

---

### Task 4: Fix CLAUDE.md stale command and test structure

**Goal:** Fix STALE finding #2 (non-existent `events/generate.json`), STALE code example, and GAP finding #5 (E2E tests not documented). Also fix the `samconfig.toml` reference.

**Files to Modify:**
- `CLAUDE.md` -- Fix stale commands and test structure

**Prerequisites:** None

**Implementation Steps:**
- In the Backend commands section (around lines 43-46):
  - Remove `sam local invoke -e events/generate.json` since the `events/` directory does not exist. Replace with a comment noting that event files can be created for local testing, or simply remove the line.
  - Update `sam deploy  # Uses samconfig.toml` comment to note that `samconfig.toml` is generated on first `sam deploy --guided` and is not checked in.
- In the Test Structure section (around lines 149-163):
  - Add `tests/backend/e2e/` directory and describe it: "E2E tests with LocalStack (require Docker, run via `pytest tests/backend/e2e -v -m e2e`)"
  - Add missing frontend test subdirectories: `api/` and `fixtures/`
  - Verify subdirectory listing matches actual `ls frontend/tests/__tests__/`

**Verification Checklist:**
- [ ] No reference to `events/generate.json` in CLAUDE.md
- [ ] `samconfig.toml` reference notes it is generated, not committed
- [ ] `tests/backend/e2e/` is documented in test structure
- [ ] Frontend test subdirectory listing matches actual directories

**Testing Instructions:**
- Manual verification against filesystem

**Commit Message Template:**
```
docs: fix stale commands and update test structure in CLAUDE.md
```

---

### Task 5: Document undocumented environment variables

**Goal:** Fix GAP findings #2, #3, #4 (undocumented env vars). Add comprehensive env var documentation to CLAUDE.md. Note: Phase 4 Task 5 created `backend/.env.example` -- this task adds the same information to CLAUDE.md for discoverability.

**Files to Modify:**
- `CLAUDE.md` -- Add environment variable reference section

**Prerequisites:** Phase 4 Task 5 (`.env.example` exists as reference)

**Implementation Steps:**
- Add a new section "## Environment Variables" to CLAUDE.md after the Model Configuration section.
- Document all environment variables read by the backend (`config.py`), grouped by category:
  - **AWS**: `AWS_REGION`, `S3_BUCKET`, `CLOUDFRONT_DOMAIN`
  - **Model API Keys**: `FLUX_API_KEY`, `RECRAFT_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`
  - **Model Enable/Disable**: `FLUX_ENABLED`, `RECRAFT_ENABLED`, `GEMINI_ENABLED`, `OPENAI_ENABLED`
  - **Model IDs**: `FLUX_MODEL_ID`, `RECRAFT_MODEL_ID`, `GEMINI_MODEL_ID`, `OPENAI_MODEL_ID`
  - **Prompt Enhancement**: `PROMPT_MODEL_PROVIDER`, `PROMPT_MODEL_ID`, `PROMPT_MODEL_API_KEY`
  - **Rate Limiting**: `GLOBAL_LIMIT`, `IP_LIMIT`, `IP_INCLUDE`
  - **Operational**: `API_CLIENT_TIMEOUT`, `IMAGE_DOWNLOAD_TIMEOUT`, `GENERATE_THREAD_WORKERS`, `BFL_MAX_POLL_ATTEMPTS`, `BFL_POLL_INTERVAL`
  - **CORS** (added in Phase 3): `CORS_ALLOWED_ORIGIN`
- Document frontend env vars: `VITE_API_ENDPOINT`, `VITE_CLOUDFRONT_DOMAIN`, `VITE_S3_BUCKET`, `VITE_ENVIRONMENT`
- Include default values where applicable.

**Verification Checklist:**
- [ ] All env vars from `config.py` are documented in CLAUDE.md
- [ ] All `VITE_*` env vars are documented
- [ ] Default values are noted
- [ ] New `CORS_ALLOWED_ORIGIN` from Phase 3 is included

**Testing Instructions:**
- Manual verification: `grep -r "os.environ.get\|import.meta.env" backend/src/config.py frontend/src/api/config.ts frontend/src/vite-env.d.ts` and ensure all are documented.

**Commit Message Template:**
```
docs: add comprehensive environment variable reference to CLAUDE.md
```

---

### Task 6: Fix CONTRIBUTING.md and README.md issues

**Goal:** Fix CONTRIBUTING.md references to `uv pip install` and root-level `npm install`, and fix the broken LICENSE link in README.md.

**Files to Modify:**
- `CONTRIBUTING.md` -- Fix install commands
- `README.md` -- Fix or remove LICENSE link

**Prerequisites:** None

**Implementation Steps:**
- In `CONTRIBUTING.md` line 12: Replace `cd backend && uv pip install -e ".[dev]"` with the actual backend setup command. Since deps are in `backend/src/requirements.txt`, use: `pip install -r backend/src/requirements.txt && pip install pytest pytest-mock pytest-cov moto ruff`
- In `CONTRIBUTING.md` lines 14-15: Replace `npm install` (root level) with `cd frontend && npm install` since there is no root-level `package.json`. Note that husky hooks are managed from the frontend directory or explain the actual setup.
- In `README.md` around line 185: The `[Apache 2.0](LICENSE)` link points to a non-existent `LICENSE` file. Either create a LICENSE file with the Apache 2.0 text, or remove the link and replace with just the license name. Prefer creating the file if the project is indeed Apache 2.0 licensed.

**Verification Checklist:**
- [ ] `CONTRIBUTING.md` backend install command works with actual project structure
- [ ] `CONTRIBUTING.md` does not reference root-level `npm install`
- [ ] README.md LICENSE link is valid (either file exists or link is removed)

**Testing Instructions:**
- Follow CONTRIBUTING.md setup steps in a fresh checkout to verify accuracy.

**Commit Message Template:**
```
docs: fix CONTRIBUTING.md install commands and README.md LICENSE link
```

---

## Phase Verification

After all tasks are complete:

1. All DRIFT findings from doc-audit.md are resolved
2. All GAP findings from doc-audit.md are resolved
3. All STALE findings from doc-audit.md are resolved
4. Broken LICENSE link is resolved
5. CLAUDE.md module tree matches `find backend/src -name "*.py" -not -name "__init__.py"`
6. CLAUDE.md model IDs match `template.yaml` and `config.py`
7. CLAUDE.md CI description matches `.github/workflows/ci.yml`
8. CONTRIBUTING.md commands work in a fresh clone
9. No documentation references code removed in Phase 1 (types.py, registry.py, dead handlers)
