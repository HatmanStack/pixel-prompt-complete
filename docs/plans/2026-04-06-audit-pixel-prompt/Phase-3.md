# Phase 3 -- Documentation, CI, and Developer Experience

## Phase Goal

Update all documentation to reflect the new provider lineup, fix all doc-audit drift findings, harden the CI pipeline (coverage gates, markdownlint, lychee), and improve developer experience with dependency pinning and a .devcontainer configuration.

**Success criteria:**

1. CLAUDE.md accurately reflects the new codebase (providers, env vars, architecture)
1. All doc-audit drift and stale findings are resolved
1. Backend CI coverage gate raised from 60% to 80%
1. Frontend CI coverage gate added
1. Dev dependencies pinned in `pyproject.toml`
1. `.devcontainer/` configuration exists
1. Markdownlint config exists and CI runs it
1. All lint and test passes: `make check` equivalent

**Estimated tokens:** ~15,000

## Prerequisites

- Phase 1 and Phase 2 complete
- All backend and frontend tests passing

## Task 1: Update CLAUDE.md

**Goal:** Rewrite CLAUDE.md to reflect the new provider lineup, fix all drift findings from the doc audit, and remove stale references.

**Files to Modify/Create:**

- `CLAUDE.md` (project root) -- Full rewrite of provider-related sections

**Prerequisites:** Phase 1 and Phase 2 complete

**Implementation Steps:**

1. Update the **Project Overview** paragraph to mention the new 4 providers
1. Update the **Architecture** section:
   - Module structure diagram: Replace `handlers.py` with `models/providers/` directory listing showing `__init__.py`, `_common.py`, `gemini.py`, `nova.py`, `openai_provider.py`, `firefly.py`
   - Remove any reference to `handlers.py` as a single file
1. Update the **API Endpoints** table -- no endpoint changes but verify descriptions are accurate
1. Update the **Model Configuration** table:

   | Config Name | Provider | Default Model ID | Env Vars |
   |-------------|----------|-------------------|----------|
   | gemini | google_gemini | gemini-3.1-flash-image-preview | `GEMINI_ENABLED`, `GEMINI_API_KEY`, `GEMINI_MODEL_ID` |
   | nova | bedrock_nova | amazon.nova-canvas-v1:0 | `NOVA_ENABLED`, `NOVA_MODEL_ID` |
   | openai | openai | dall-e-3 | `OPENAI_ENABLED`, `OPENAI_API_KEY`, `OPENAI_MODEL_ID` |
   | firefly | adobe_firefly | firefly-image-5 | `FIREFLY_ENABLED`, `FIREFLY_CLIENT_ID`, `FIREFLY_CLIENT_SECRET`, `FIREFLY_MODEL_ID` |

1. Update the **Environment Variables** tables:
   - Remove Flux and Recraft env vars
   - Add Nova env vars (no API key, IAM auth)
   - Add Firefly env vars (`FIREFLY_CLIENT_ID`, `FIREFLY_CLIENT_SECRET`, `FIREFLY_ENABLED`, `FIREFLY_MODEL_ID`)
   - Remove BFL polling env vars (`BFL_MAX_POLL_ATTEMPTS`, `BFL_POLL_INTERVAL`)
   - Remove phantom frontend env vars (`VITE_DEBUG`, `VITE_API_TIMEOUT`)
   - Update OpenAI default model ID to `dall-e-3`
1. Fix **CI trigger branches** (DRIFT-1): Change "Runs on push/PR to main/develop" to "Runs on push/PR to main"
1. Fix **S3 Structure** (DRIFT-2): Remove the `gallery/{timestamp}/` line. All data is under `sessions/` prefix:

   ```text
   sessions/{sessionId}/status.json           # Session metadata + iteration array per model
   sessions/{sessionId}/context/{model}.json  # Rolling 3-iteration context window
   sessions/{timestamp}/                      # Gallery images with metadata
   ```

1. Fix **version numbers** (DRIFT-3): Update to actual versions from package.json (Vite 8, Vitest 4)
1. Fix **handler signatures** (DRIFT-6/7): Update to match actual current function signatures
1. Update **Important Constraints** section:
   - Remove "Python 3.13" runtime mention that duplicates earlier info
   - Add note about DALL-E 3 iteration using gpt-image-1 (ADR-5)
   - Add note about Firefly OAuth2 per-request token fetch
   - Add note about Nova Canvas using IAM auth (no API key)
1. Update the **Adding a New Handler Type** section to reference `models/providers/` instead of `handlers.py`
1. Update **Test Structure** to reflect the new test files (`test_gemini_handler.py`, `test_nova_handler.py`, etc.)

**Verification Checklist:**

- [ ] No reference to Flux, BFL, or Recraft in CLAUDE.md
- [ ] S3 structure section does not mention `gallery/` prefix
- [ ] CI trigger section says `main` only, not `main/develop`
- [ ] Version numbers match package.json
- [ ] All 4 new providers are documented with correct env vars
- [ ] Handler signatures match actual code

**Testing Instructions:**

- No automated tests. Manual review of CLAUDE.md against the codebase.
- Run `grep -c "flux\|recraft\|bfl\|Flux\|Recraft\|BFL" CLAUDE.md` to verify no old references

**Commit Message Template:**

```text
docs: update CLAUDE.md for new provider lineup

- Replace Flux/Recraft with Nova Canvas and Firefly documentation
- Fix CI branch drift (main only, not main/develop)
- Fix S3 structure (no gallery/ prefix)
- Update version numbers, handler signatures, env var tables
- Resolves 7 doc-audit drift findings
```

---

## Task 2: Raise Coverage Gates in CI

**Goal:** Raise backend coverage gate from 60% to 80% and add a frontend coverage gate. This addresses the eval Test Value finding.

**Files to Modify/Create:**

- `.github/workflows/ci.yml` -- Update backend `--cov-fail-under` and add frontend coverage threshold
- `backend/pyproject.toml` -- Update `[tool.coverage.report] fail_under`

**Prerequisites:** Phase 1 and Phase 2 tests passing at 80%+ coverage

**Implementation Steps:**

1. In `.github/workflows/ci.yml`, backend job:
   - Change `--cov-fail-under=60` to `--cov-fail-under=80`
1. In `backend/pyproject.toml`:
   - Change `fail_under = 60` to `fail_under = 80` under `[tool.coverage.report]`
1. In `.github/workflows/ci.yml`, frontend job:
   - Change `npx vitest run --coverage` to include a threshold. Add vitest coverage configuration to fail on low coverage. This can be done via vitest config:

     ```typescript
     // In vitest.config.ts or vite.config.ts test section:
     coverage: {
       thresholds: {
         statements: 70,
         branches: 60,
         functions: 70,
         lines: 70,
       }
     }
     ```

   Or alternatively via CLI flag if vitest supports it. Check the current vitest config to determine the best approach.

**Verification Checklist:**

- [ ] Backend CI uses `--cov-fail-under=80`
- [ ] `pyproject.toml` has `fail_under = 80`
- [ ] Frontend has a coverage threshold configured (either in vitest config or CI)
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v --cov=backend/src --cov-fail-under=80` passes
- [ ] `cd frontend && npm test` passes with coverage gate

**Testing Instructions:**

- Run the full test suites locally with coverage to verify thresholds are met before raising them
- If coverage is below 80%, identify gaps and add tests before raising the gate

**Commit Message Template:**

```text
chore(ci): raise coverage gates (backend 60->80%, add frontend gate)

- Backend coverage gate raised from 60% to 80%
- Add frontend coverage threshold in vitest config
- Resolves eval Test Value finding
```

---

## Task 3: Pin Dev Dependencies

**Goal:** Pin all dev/test dependencies with exact versions and add a lockfile for reproducible builds. This addresses the eval Reproducibility finding.

**Files to Modify/Create:**

- `backend/pyproject.toml` -- Pin dev dependency versions
- `.github/workflows/ci.yml` -- Install dev deps from pyproject.toml instead of ad-hoc installs

**Prerequisites:** None

**Implementation Steps:**

1. In `backend/pyproject.toml`, update the `[project.optional-dependencies]` section to pin exact versions. First check current installed versions:

   ```bash
   uv pip install -r backend/src/requirements.txt
   uv pip install "pixel-prompt-backend[dev]"
   uv pip freeze | grep -E "mypy|ruff|pytest|moto|requests-mock"
   ```

   Then pin them:

   ```toml
   [project.optional-dependencies]
   dev = [
       "mypy==1.15.0",
       "ruff==0.9.0",
       "pytest==8.3.0",
       "pytest-mock==3.14.0",
       "pytest-cov==6.0.0",
       "moto==5.1.0",
       "requests-mock==1.12.1",
       "responses==0.25.0",
   ]
   ```

   (Use actual current versions discovered by `uv pip freeze`.)

1. Update CI workflow to install dev deps from pyproject.toml:

   ```yaml
   - name: Install dependencies
     run: |
       uv pip install -r backend/src/requirements.txt
       uv pip install -e "backend/.[dev]"
   ```

   This replaces the ad-hoc `pip install pytest pytest-mock pytest-cov requests-mock moto ruff` line. CI must install `uv` first (add `pip install uv` or use the `astral-sh/setup-uv` action).

1. Also update the E2E job's dependency install to use the same pattern.

**Verification Checklist:**

- [ ] All dev dependencies in `pyproject.toml` have pinned versions (e.g., `==X.Y.Z`)
- [ ] CI workflow uses `uv pip install` from `pyproject.toml[dev]`, not ad-hoc pip install
- [ ] CI workflow installs `uv` before using it (via `astral-sh/setup-uv` action or `pip install uv`)
- [ ] Both backend and e2e CI jobs use the same install pattern
- [ ] `uv pip install -e "backend/.[dev]"` succeeds locally

**Testing Instructions:**

- Run `uv pip install -e "backend/.[dev]"` locally and verify all test deps are installed
- Run `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` to verify

**Commit Message Template:**

```text
chore(deps): pin dev dependencies and install from pyproject.toml

- Pin exact versions for all dev/test dependencies
- Update CI to use uv and install from pyproject.toml[dev]
- Resolves eval Reproducibility finding
```

---

## Task 4: Add .devcontainer Configuration

**Goal:** Add a VS Code Dev Container configuration so developers can open the project in Codespaces or a local dev container with all dependencies pre-configured. This addresses the eval Reproducibility finding.

**Files to Modify/Create:**

- `.devcontainer/devcontainer.json` -- Create: Dev container configuration
- `.devcontainer/post-create.sh` -- Create: Post-create setup script

**Prerequisites:** None

**Implementation Steps:**

1. Create `.devcontainer/devcontainer.json`:

   ```json
   {
     "name": "Pixel Prompt Complete",
     "image": "mcr.microsoft.com/devcontainers/python:3.13",
     "features": {
       "ghcr.io/devcontainers/features/node:1": {
         "version": "24"
       },
       "ghcr.io/devcontainers/features/aws-cli:1": {},
       "ghcr.io/devcontainers/features/docker-in-docker:2": {}
     },
     "postCreateCommand": ".devcontainer/post-create.sh",
     "customizations": {
       "vscode": {
         "extensions": [
           "ms-python.python",
           "ms-python.mypy-type-checker",
           "charliermarsh.ruff",
           "dbaeumer.vscode-eslint",
           "bradlc.vscode-tailwindcss"
         ],
         "settings": {
           "python.defaultInterpreterPath": "/usr/local/bin/python",
           "python.analysis.typeCheckingMode": "basic"
         }
       }
     },
     "forwardPorts": [5173, 3000]
   }
   ```

1. Create `.devcontainer/post-create.sh`:

   ```bash
   #!/bin/bash
   set -e

   # Backend setup
   uv pip install -r backend/src/requirements.txt
   uv pip install -e "backend/.[dev]"

   # Frontend setup
   cd frontend && npm ci && cd ..

   # Install pre-commit hooks
   npm install

   echo "Development environment ready!"
   ```

1. Make `post-create.sh` executable: `chmod +x .devcontainer/post-create.sh`

**Verification Checklist:**

- [ ] `.devcontainer/devcontainer.json` exists with Python 3.13 and Node 24
- [ ] `.devcontainer/post-create.sh` exists and is executable
- [ ] Post-create script installs both backend and frontend dependencies

**Testing Instructions:**

- If VS Code is available, open the project with "Reopen in Container" to verify
- Otherwise, verify the post-create script runs without errors in a fresh environment

**Commit Message Template:**

```text
chore(devex): add .devcontainer configuration

- Python 3.13 + Node 24 + AWS CLI + Docker-in-Docker
- Post-create script installs all dependencies
- VS Code extensions for Python, TypeScript, Tailwind
- Resolves eval Reproducibility finding
```

---

## Task 5: Add Markdownlint to CI

**Goal:** Add markdownlint configuration and a CI step to lint markdown files. This addresses the doc-audit structure finding about missing drift prevention tooling.

**Files to Modify/Create:**

- `.markdownlint.json` -- Create: Markdownlint configuration
- `.github/workflows/ci.yml` -- Add markdownlint step
- `package.json` (root) -- Add markdownlint-cli2 as a dev dependency (or install in CI)

**Prerequisites:** None

**Implementation Steps:**

1. Create `.markdownlint.json` at the project root:

   ```json
   {
     "default": true,
     "MD013": false,
     "MD033": false,
     "MD041": false,
     "MD024": { "siblings_only": true }
   }
   ```

   - `MD013` (line length): disabled -- long lines are common in documentation tables
   - `MD033` (inline HTML): disabled -- README may use HTML for formatting
   - `MD041` (first line heading): disabled -- some files start with frontmatter
   - `MD024` (duplicate headings): allowed for siblings

1. Add a docs lint job to CI (or add it to the existing frontend job):

   ```yaml
   docs:
     name: Documentation Lint
     runs-on: ubuntu-latest
     timeout-minutes: 5
     steps:
       - uses: actions/checkout@v6
       - run: npx markdownlint-cli2 "**/*.md" "#node_modules" "#.claude"
   ```

1. Optionally add lychee for link checking (can be a follow-up if too complex):

   ```yaml
   - uses: lycheeverse/lychee-action@v2
     with:
       args: --no-progress '**/*.md'
       fail: true
   ```

**Verification Checklist:**

- [ ] `.markdownlint.json` exists at project root
- [ ] CI has a step or job that runs markdownlint
- [ ] `npx markdownlint-cli2 "**/*.md"` passes locally (fix any existing violations first)

**Testing Instructions:**

- Run `npx markdownlint-cli2 "**/*.md" "#node_modules" "#.claude"` locally
- Fix any violations in existing markdown files before adding the CI gate

**Commit Message Template:**

```text
chore(ci): add markdownlint configuration and CI step

- Create .markdownlint.json with project-appropriate rules
- Add documentation lint job to CI workflow
- Resolves doc-audit structure finding
```

---

## Task 6: Update ADRs and Stale Documentation

**Goal:** Update existing ADRs and remove stale documentation references.

**Files to Modify/Create:**

- `docs/adr/001-fixed-four-models.md` -- Update to reflect new 4 models, remove reference to nonexistent `registry.py`
- `frontend/.env.example` -- Already updated in Phase 2 Task 8, verify final state

**Prerequisites:** Phase 1 and Phase 2 complete

**Implementation Steps:**

1. Update `docs/adr/001-fixed-four-models.md`:
   - Update the model list from Flux/Recraft/Gemini/OpenAI to Gemini/Nova Canvas/DALL-E 3/Firefly
   - Remove the line about "legacy ModelRegistry class" in `models/registry.py` -- this file does not exist
   - Update any code references to match the new module structure
1. Search for any other ADR files that reference old providers and update them:

   ```bash
   grep -r "flux\|recraft\|bfl" docs/adr/
   ```

**Verification Checklist:**

- [ ] No ADR references Flux, Recraft, BFL, or `registry.py`
- [ ] ADR-001 reflects the current 4-model lineup
- [ ] `grep -r "registry.py" docs/` returns no matches

**Testing Instructions:**

- Manual review of ADR files

**Commit Message Template:**

```text
docs(adr): update ADR-001 for new provider lineup

- Replace Flux/Recraft with Nova Canvas and Firefly
- Remove reference to nonexistent models/registry.py (resolves STALE-1)
```

---

## Task 7: Add /log Route to SAM Template (if not done in Phase 1)

**Goal:** Verify the `/log` route was added to SAM template in Phase 1 Task 10. If not, add it here.

**Files to Modify/Create:**

- `backend/template.yaml` -- Add LogApi event (if missing)

**Prerequisites:** Phase 1 Task 10

**Implementation Steps:**

1. Check if `template.yaml` has a `LogApi` event. If yes, this task is a no-op.
1. If not, add:

   ```yaml
   LogApi:
     Type: HttpApi
     Properties:
       Path: /log
       Method: POST
       ApiId: !Ref HttpApi
   ```

**Verification Checklist:**

- [ ] `template.yaml` has a LogApi event for POST /log

**Commit Message Template:**

```text
fix(deploy): add /log POST route to SAM template
```

---

## Phase Verification

After completing all tasks in Phase 3:

1. Run: `ruff check backend/src/` -- passes
1. Run: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v --cov=backend/src --cov-fail-under=80` -- passes
1. Run: `cd frontend && npm run typecheck && npm run lint && npm test` -- passes
1. Run: `npx markdownlint-cli2 "**/*.md" "#node_modules" "#.claude"` -- passes
1. Verify: CLAUDE.md has no references to Flux, Recraft, BFL
1. Verify: CLAUDE.md version numbers match `package.json`
1. Verify: `.devcontainer/` directory exists with both files
1. Verify: `.markdownlint.json` exists
1. Verify: CI workflow has markdownlint step and coverage gates at 80%

**Post-Phase 3 state:**

The codebase should be fully updated:

- 4 new providers operational (Gemini Nano Banana 2, Nova Canvas, DALL-E 3, Firefly)
- Column focus UI working on desktop
- All audit findings addressed or explicitly documented as out of scope
- Documentation accurate and lint-checked
- CI hardened with higher coverage gates
- Developer experience improved with .devcontainer and pinned dependencies
