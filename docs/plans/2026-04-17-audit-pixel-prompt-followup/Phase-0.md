# Phase 0: Foundation

## Project Conventions

Identical to the initial remediation plan. See `docs/plans/2026-04-17-audit-pixel-prompt/Phase-0.md` for full details.

Key points:

- **Backend:** Python 3.13, `uv pip`, Ruff linting, `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
- **Frontend:** Not modified in this plan
- **Commits:** Conventional commits enforced by commitlint + Husky
- **Config pattern:** Environment variables read in `config.py` via `_safe_int()` / `_safe_float()`
- **Error handling:** Catch, sanitize via `sanitize_error_message()`, log with `StructuredLogger`, return via `error_responses`

## Testing Strategy

- Unit tests with `moto` for S3, `unittest.mock` for external APIs
- Run: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
- Coverage gate: 80%

## Architecture Decisions

### ADR: Firefly Token Caching

The previous implementation fetched a fresh OAuth2 token per request (per ADR-4 which stated "no caching"). This ADR overrides that decision with a module-level cache. Rationale: Adobe IMS tokens have a 24-hour TTL. Caching with a 50-minute TTL saves ~500ms per request and reduces Adobe IMS rate-limit risk. The cache is module-scoped, protected by a `threading.Lock`, lives within a single Lambda container, and resets on cold start.

### ADR: API Timeout Default

Reducing `API_CLIENT_TIMEOUT` from 120s to 60s. Image generation APIs typically respond in 10-30s. A 120s timeout is generous but with 4 parallel providers, a hung provider blocks its thread for the full duration. At 60s, failures surface faster and Lambda has ample headroom within its 900s timeout and 3008 MB memory allocation.
