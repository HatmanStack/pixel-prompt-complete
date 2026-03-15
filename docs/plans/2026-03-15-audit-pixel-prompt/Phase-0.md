# Phase 0: Foundation

This phase establishes shared conventions, architecture decisions, and testing strategy that apply across all subsequent phases.

## Architecture Decisions

### ADR-1: Preserve existing module boundaries during cleanup

Dead code removal (Phase 1) will delete files and functions but will not reorganize module boundaries. Architecture refactoring (Phase 3) is the only phase that moves code between modules. This prevents merge conflicts between concurrent phases.

### ADR-2: Use moto for all new backend S3 tests

All new backend tests must use the existing `mock_s3` fixture from `tests/backend/unit/conftest.py` (moto-backed). Do not use `MagicMock` for S3 client interactions. This aligns with the pattern in `test_session_manager.py` and addresses the eval finding about inconsistent mock strategies.

### ADR-3: Prefer targeted exception handling over bare except

Replace all `except Exception: return []` patterns with specific `ClientError` handling. Log errors with `logger.error()` before re-raising or returning fallbacks. Never silently swallow exceptions.

### ADR-4: No new dependencies without justification

Do not add new pip or npm dependencies unless explicitly called for in a task. The goal is to reduce surface area, not expand it.

### ADR-5: Backward-compatible API changes only

All changes to `lambda_function.py` response formats must maintain backward compatibility with the existing frontend. The handler extraction in Phase 3 is an internal refactor -- external API contracts remain unchanged.

## Design Conventions

### Python Backend

- **Line length:** 100 chars (per `pyproject.toml` ruff config)
- **Import style:** Absolute imports from package root (e.g., `from utils.storage import ImageStorage`)
- **Type hints:** Use Python 3.13 syntax (`dict[str, Any]` not `Dict[str, Any]`; `str | None` not `Optional[str]`)
- **Logging:** Use `logging.getLogger(__name__)` per module, structured JSON via `StructuredLogger` for operational events
- **Error handling:** Specific exceptions, logged before re-raise. Use `ClientError` for boto3 errors.

### Frontend (TypeScript/React)

- **State management:** Zustand stores only (no Context API, no Redux)
- **Testing:** Vitest + React Testing Library. Test behavior, not implementation.
- **Formatting:** Prettier via `npm run format:check`

### Testing Strategy

- **Backend unit tests:** `tests/backend/unit/` with `conftest.py` providing `mock_s3` fixture (moto). Run via `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
- **Frontend tests:** `frontend/tests/__tests__/` with Vitest. Run via `cd frontend && npm test`
- **Coverage requirement:** Backend maintains `--cov-fail-under=60` in CI
- **New code:** All new functions and modified functions must have tests. Test the observable behavior (return values, side effects on S3), not mock call counts.

### Commit Message Format

All commits use conventional commits format:

```
type(scope): brief description

- Bullet point details if needed
```

Types: `fix`, `refactor`, `chore`, `test`, `docs`, `ci`
Scopes: `backend`, `frontend`, `ci`, `config`, `docs`

Examples:
- `chore(backend): remove dead code from config.py and types.py`
- `fix(backend): add S3 pagination to gallery listing`
- `refactor(backend): extract shared validation pipeline from lambda handlers`
- `docs: fix CLAUDE.md model ID drift and stale references`

## Verification Commands

```bash
# Backend lint + tests
cd /home/user/pixel-prompt-complete
PYTHONPATH=backend/src ruff check backend/src/
PYTHONPATH=backend/src pytest tests/backend/unit/ -v --tb=short

# Frontend lint + typecheck + tests
cd /home/user/pixel-prompt-complete/frontend
npm run lint
npm run typecheck
npm test

# SAM build (backend packaging)
cd /home/user/pixel-prompt-complete/backend
sam build
```
