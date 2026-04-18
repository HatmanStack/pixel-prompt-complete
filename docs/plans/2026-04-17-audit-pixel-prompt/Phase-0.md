# Phase 0: Foundation

## Project Conventions

### Package Manager and Runtime

- **Backend:** Python 3.13, install with `uv pip install -r backend/src/requirements.txt`
- **Frontend:** Node.js 18+, install with `npm install` in `frontend/`
- **Never** use bare `pip` — always `uv pip`

### Build and Test Commands

```bash
# Backend tests (run from repo root)
PYTHONPATH=backend/src pytest tests/backend/unit/ -v

# Frontend tests
cd frontend && npm test

# Linting
ruff check backend/src/
cd frontend && npm run lint

# Type checking
cd frontend && npm run typecheck
```

### Commit Format

Conventional commits enforced by commitlint + Husky:

```text
type(scope): brief description

- Detail 1
- Detail 2
```

Types: `fix`, `feat`, `test`, `docs`, `refactor`, `build`, `chore`

### Code Style

- **Python:** Ruff (line-length 100, rules E/F/W/I). Type hints are used throughout but there is no mypy CI step — Ruff handles linting.
- **TypeScript:** ESLint flat config, strict tsconfig, Prettier
- **No `any` types** in TypeScript, no `# type: ignore` in Python without justification

## Architecture Decisions

### ADR: Audit Remediation Approach

All remediation follows the principle of minimal change. Each fix addresses a specific finding with the smallest possible diff. No refactoring beyond what the finding requires.

### ADR: Thread Pool Lifecycle in Lambda

Lambda containers are recycled without predictable shutdown. Module-level `ThreadPoolExecutor` instances must register `atexit` cleanup handlers to prevent thread leaks. The `atexit` handler calls `shutdown(wait=False)` because Lambda may kill the process before threads complete.

### ADR: Timeout Consolidation

All LLM/API client timeouts should be sourced from `config.py` environment variables rather than hardcoded in individual modules. This ensures a single source of truth and makes operational tuning possible without code changes.

## Testing Strategy

### Backend

- Unit tests use `moto` for S3 mocking and `unittest.mock` for external API calls
- Tests live in `tests/backend/unit/`
- Run: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
- Coverage gate: 80% (enforced by CI)
- Fixtures in `tests/backend/unit/fixtures/`
- Conftest auto-resets handler singletons between tests

### Frontend

- Vitest + React Testing Library
- Tests in `frontend/tests/__tests__/`
- Run: `cd frontend && npm test`
- Coverage thresholds in `vite.config.ts`

### Test Patterns for This Remediation

- **Error handling changes:** Test both the happy path and the specific error condition being hardened
- **Timeout changes:** Mock the timeout config value and verify it's passed to the correct client call
- **Thread pool changes:** Test via `unittest.mock.patch` on `atexit.register` to verify registration
- **Documentation changes:** No tests needed; verify by reading the updated docs

## Shared Patterns

### Error Handling in Lambda Handlers

The existing pattern wraps provider calls in try-except and returns sanitized error messages via `_common.py:sanitize_error_message()`. When changing error handling, preserve this pattern:

1. Catch the specific exception
2. Sanitize the message (strip API keys)
3. Log with correlation_id via `StructuredLogger`
4. Return standardized error response via `error_responses`

### Config Pattern

Environment variables are read in `config.py` at module load time using `_safe_int()` / `_safe_float()` helpers that warn on invalid values and fall back to defaults. New config values follow this pattern.
