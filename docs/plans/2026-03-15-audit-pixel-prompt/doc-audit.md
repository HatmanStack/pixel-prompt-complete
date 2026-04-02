---
type: doc-health
date: 2026-03-15
prevention_scope: none
ci_platform: GitHub Actions
language_stack: both
---

# Documentation Audit: pixel-prompt-complete

## Configuration
- **Prevention Scope:** None
- **CI Platform:** GitHub Actions
- **Language Stack:** Both (JS/TS + Python)
- **Constraints:** None

## Summary
- Docs scanned: 3 files (CLAUDE.md, README.md, CONTRIBUTING.md)
- Code modules scanned: 19 backend Python files, frontend structure, CI workflow, SAM template
- Findings: 6 drift, 5 gaps, 2 stale, 1 broken link

## Findings

### DRIFT (doc exists, doesn't match code)

1. **`CLAUDE.md:98`** -- Flux default model ID
   - Doc says: `flux-2-pro`
   - Code says (`config.py:80`): `flux-pro-1.1`
   - Note: `template.yaml:76` says `flux-2-pro`. The SAM template and CLAUDE.md agree, but the Python code default differs. The deployed value from SAM will override, but the Python fallback default is wrong in docs or code depending on perspective.

2. **`CLAUDE.md:100`** -- Gemini default model ID
   - Doc says: `gemini-2.5-flash-image`
   - Code says (`config.py:96`): `gemini-2.0-flash-exp`
   - Note: `template.yaml:116` says `gemini-2.5-flash-image`. Same situation as Flux -- CLAUDE.md matches template.yaml but the Python code fallback default is `gemini-2.0-flash-exp`.

3. **`CLAUDE.md:62`** -- Backend module structure lists `models/registry.py`
   - Doc says: `registry.py` exists as "ModelRegistry (legacy, still present)"
   - Code: File `/home/user/pixel-prompt-complete/backend/src/models/registry.py` does **not exist**. The models directory contains `__init__.py`, `handlers.py`, `context.py`, and `types.py`.

4. **`CLAUDE.md:141`** -- Hook listing claims `useJobPolling` exists
   - Doc says: `useSessionPolling` / `useJobPolling`
   - Code: Only `useSessionPolling` exists in `frontend/src/hooks/`. No `useJobPolling` hook exists anywhere in the frontend source.

5. **`CLAUDE.md:48-50`** -- CI description is incomplete
   - Doc says: "Runs on push/PR to main/develop: frontend lint + typecheck -> frontend tests -> backend lint + tests."
   - Code (`.github/workflows/ci.yml`): CI also runs `format:check` in frontend-lint and includes a separate `e2e-tests` job with MiniStack. The description omits format checking and E2E testing.

6. **`README.md:168-171`** -- Model default IDs in README
   - README says Flux default is `flux-pro-1.1` and Gemini default is `gemini-2.0-flash-exp`
   - These match the Python code defaults but **not** the SAM template defaults (`flux-2-pro` and `gemini-2.5-flash-image`). README and CLAUDE.md disagree on Flux and Gemini defaults.

### GAPS (code exists, no doc)

1. **`backend/src/models/types.py`** -- Type definitions module with `HandlerSuccess`, `HandlerError`, `HandlerResult`, `ModelConfigDict`, `IterationData`, `ModelData`, `SessionData`, and Protocol classes for handler contracts. Not mentioned in CLAUDE.md backend module structure.

2. **Frontend env vars undocumented** -- The frontend reads `VITE_API_ENDPOINT`, `VITE_CLOUDFRONT_DOMAIN`, `VITE_S3_BUCKET`, `VITE_ENVIRONMENT` (declared in `frontend/src/vite-env.d.ts`, used in `frontend/src/api/config.ts`). None of these appear in any documentation.

3. **Backend operational env vars undocumented** -- `config.py` reads 7 additional env vars not mentioned in any doc: `API_CLIENT_TIMEOUT`, `IMAGE_DOWNLOAD_TIMEOUT`, `HANDLER_TIMEOUT`, `MAX_THREAD_WORKERS`, `GENERATE_THREAD_WORKERS`, `BFL_MAX_POLL_ATTEMPTS`, `BFL_POLL_INTERVAL`.

4. **Backend env vars partially undocumented** -- `config.py` reads `GLOBAL_LIMIT`, `IP_LIMIT`, `IP_INCLUDE`, `S3_BUCKET`, `CLOUDFRONT_DOMAIN`, `AWS_REGION`, `BEDROCK_NOVA_REGION`, `BEDROCK_SD_REGION`. These are used in template.yaml but not listed in the CLAUDE.md or README model configuration tables.

5. **E2E test infrastructure undocumented in CLAUDE.md** -- `tests/backend/e2e/` directory with `test_full_workflow.py` exists but CLAUDE.md test structure section only mentions `tests/backend/unit/` and `tests/backend/integration/`. README.md documents E2E tests, but CLAUDE.md does not.

### STALE (doc exists, code doesn't)

1. **`CLAUDE.md:62`** -- `models/registry.py` listed as "(legacy, still present)" but the file does not exist at `backend/src/models/registry.py`.

2. **`CLAUDE.md:44`** -- `sam local invoke -e events/generate.json` -- the `events/` directory and file do not exist at `/home/user/pixel-prompt-complete/events/generate.json`.

### BROKEN LINKS

1. **`README.md:185`** -- `[Apache 2.0](LICENSE)` -- No `LICENSE` file exists at `/home/user/pixel-prompt-complete/LICENSE`.

### STALE CODE EXAMPLES

1. **`CLAUDE.md:44`** -- `sam local invoke -e events/generate.json` references a non-existent event file. This command would fail.

### CONFIG DRIFT

1. **Code reads `API_CLIENT_TIMEOUT`** (`config.py:169`) -- not in any doc
2. **Code reads `IMAGE_DOWNLOAD_TIMEOUT`** (`config.py:170`) -- not in any doc
3. **Code reads `HANDLER_TIMEOUT`** (`config.py:171`) -- not in any doc
4. **Code reads `MAX_THREAD_WORKERS`** (`config.py:172`) -- not in any doc
5. **Code reads `GENERATE_THREAD_WORKERS`** (`config.py:173`) -- not in any doc
6. **Code reads `BFL_MAX_POLL_ATTEMPTS`** (`config.py:176`) -- not in any doc
7. **Code reads `BFL_POLL_INTERVAL`** (`config.py:177`) -- not in any doc
8. **Frontend reads `VITE_API_ENDPOINT`** (`frontend/src/api/config.ts:7`) -- not in any doc
9. **Frontend reads `VITE_CLOUDFRONT_DOMAIN`** (`frontend/src/vite-env.d.ts:5`) -- not in any doc
10. **Flux default model ID mismatch**: `config.py:80` defaults to `flux-pro-1.1`, `template.yaml:76` defaults to `flux-2-pro`, CLAUDE.md says `flux-2-pro`, README says `flux-pro-1.1`
11. **Gemini default model ID mismatch**: `config.py:96` defaults to `gemini-2.0-flash-exp`, `template.yaml:116` defaults to `gemini-2.5-flash-image`, CLAUDE.md says `gemini-2.5-flash-image`, README says `gemini-2.0-flash-exp`

### STRUCTURE ISSUES

1. **CLAUDE.md backend module tree is incomplete** -- Missing `models/types.py` and `__init__.py` files. The `types.py` file contains important Protocol definitions and TypedDicts.

2. **CLAUDE.md says `samconfig.toml` is used for deploy** (`CLAUDE.md:33`) -- No `samconfig.toml` exists anywhere in the repository. This file would be generated on first `sam deploy --guided` but its absence means `sam deploy` (without `--guided`) would fail for a fresh clone.

3. **CLAUDE.md test structure lists `frontend/tests/__tests__/` subdirectories** -- Lists `components/`, `hooks/`, `stores/`, `integration/`, `utils/` as subdirectories. The actual structure also contains `api/` (`client.test.ts`) and `fixtures/` (`apiResponses.ts`) directories not mentioned.

4. **CONTRIBUTING.md references `uv pip install -e ".[dev]"`** (`CONTRIBUTING.md:12`) -- Uses `uv` package manager but this is not mentioned as a prerequisite anywhere. README.md mentions "Python 3.13+ (via uv or pyenv)" but only for Python installation, not as a pip replacement.

5. **CONTRIBUTING.md references root-level `npm install` for husky/lint-staged/commitlint** (`CONTRIBUTING.md:14-15`) -- No root-level `package.json` exists at `/home/user/pixel-prompt-complete/package.json` to support this command.
