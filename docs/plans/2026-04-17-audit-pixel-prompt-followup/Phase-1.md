# Phase 1 [IMPLEMENTER]: Remaining Health Fixes

## Phase Goal

Address 4 remaining health findings from the 2026-04-17 audit: Firefly token caching, OpenAI download error specificity, API timeout default reduction, and outpaint context validation ordering.

**Success criteria:**

- Firefly OAuth2 token is cached per Lambda container with 50-minute TTL
- OpenAI image download catches `requests.RequestException` with specific error messages
- `API_CLIENT_TIMEOUT` defaults to 60s (down from 120s)
- Outpaint handler validates context before calling `add_iteration`
- All existing tests pass

**Estimated tokens:** ~15,000

## Prerequisites

- Initial audit remediation complete (2026-04-17-audit-pixel-prompt)

## Tasks

### Task 1: Add Firefly OAuth2 Token Caching (HIGH)

**Goal:** Cache the Adobe IMS access token at module level with a 50-minute TTL to avoid fetching a fresh token on every request within the same Lambda container.

**Files to Modify:**

- `backend/src/models/providers/firefly.py` — lines 34-55

**Implementation Steps:**

1. Read `backend/src/models/providers/firefly.py` fully to understand the current token flow
1. Add module-level cache variables after the existing constants (around line 31):

   ```python
   import time as _time

   _cached_token: str | None = None
   _cached_token_expiry: float = 0.0
   _TOKEN_TTL = 50 * 60  # 50 minutes (Adobe tokens last 24h, refresh well before expiry)
   ```

1. Create a new function `_get_or_refresh_token` that wraps `_get_firefly_access_token`:

   ```python
   def _get_or_refresh_token(client_id: str, client_secret: str) -> str:
       """Return a cached access token, refreshing if expired or missing."""
       global _cached_token, _cached_token_expiry
       now = _time.monotonic()
       if _cached_token and now < _cached_token_expiry:
           return _cached_token
       token = _get_firefly_access_token(client_id, client_secret)
       _cached_token = token
       _cached_token_expiry = now + _TOKEN_TTL
       return token
   ```

1. Replace all calls to `_get_firefly_access_token(client_id, client_secret)` with `_get_or_refresh_token(client_id, client_secret)` in `handle_firefly`, `iterate_firefly`, and `outpaint_firefly`. Search for all call sites with Grep first.

1. Keep the original `_get_firefly_access_token` function unchanged (it's the low-level fetch, now called by the caching wrapper).

**Verification Checklist:**

- [x] `_cached_token` and `_cached_token_expiry` exist at module level
- [x] `_get_or_refresh_token` returns cached token when within TTL
- [x] `_get_or_refresh_token` fetches new token when expired
- [x] All 3 handler functions (`handle_firefly`, `iterate_firefly`, `outpaint_firefly`) use `_get_or_refresh_token`
- [x] `_get_firefly_access_token` is still a standalone function (not deleted)
- [x] `PYTHONPATH=backend/src pytest tests/backend/unit/test_firefly_handler.py -v` passes

**Testing Instructions:**

Add tests in `tests/backend/unit/test_firefly_handler.py`:

1. Test cache hit: Mock `_get_firefly_access_token` to return a token. Call `_get_or_refresh_token` twice. Verify the underlying fetch is called only once.
1. Test cache expiry: Set `_cached_token_expiry` to a past time. Call `_get_or_refresh_token`. Verify the underlying fetch is called again.
1. Test cold start: Ensure `_cached_token` starts as `None` and first call fetches.

**Important:** Reset module-level cache state between tests to prevent test-order dependencies. Add an autouse fixture:

```python
@pytest.fixture(autouse=True)
def reset_token_cache():
    import models.providers.firefly as firefly_mod
    firefly_mod._cached_token = None
    firefly_mod._cached_token_expiry = 0.0
    yield
    firefly_mod._cached_token = None
    firefly_mod._cached_token_expiry = 0.0
```

**Commit Message Template:**

```text
perf(backend): add Firefly OAuth2 token caching with 50-min TTL

- Cache Adobe IMS access token at module level
- Saves ~500ms per Firefly request within same Lambda container
- Token refreshed after 50 minutes (well within 24h Adobe TTL)
- Addresses HIGH health finding: firefly.py:34-55
```

---

### Task 2: Improve OpenAI Image Download Error Handling (HIGH)

**Goal:** Add specific `requests.RequestException` handling for OpenAI image downloads to produce clearer error messages for connection failures vs timeouts.

**Files to Modify:**

- `backend/src/models/providers/openai_provider.py` — lines 49-64

**Implementation Steps:**

1. Read `backend/src/models/providers/openai_provider.py` lines 35-65
1. The current code catches `requests.Timeout` specifically (line 56) and then has a generic `except Exception` (line 63). Add a `requests.ConnectionError` catch between them:

   ```python
   except requests.Timeout:
       return _error_result(
           f"Image download timeout after {image_download_timeout} seconds",
           model_config,
           "openai",
       )

   except requests.ConnectionError as e:
       return _error_result(
           f"Image download connection failed: {e}",
           model_config,
           "openai",
       )

   except requests.HTTPError as e:
       return _error_result(
           f"Image download HTTP error: {e.response.status_code if e.response else 'unknown'}",
           model_config,
           "openai",
       )

   except Exception as e:
       return _error_result(e, model_config, "openai")
   ```

1. Note: `_error_result` calls `sanitize_error_message` internally, so no risk of leaking API keys.

**Verification Checklist:**

- [x] `requests.ConnectionError` caught with specific message
- [x] `requests.HTTPError` caught with status code in message
- [x] `requests.Timeout` catch unchanged
- [x] Generic `except Exception` still present as fallback
- [x] `PYTHONPATH=backend/src pytest tests/backend/unit/test_openai_handler.py -v` passes

**Testing Instructions:**

Add tests in `tests/backend/unit/test_openai_handler.py`:

1. Mock `requests.get` to raise `requests.ConnectionError("Connection refused")`. Verify handler returns error result with "connection failed" message.
1. Mock `requests.get` to raise `requests.HTTPError` with a mock response having `status_code=403`. Verify handler returns error result with "HTTP error: 403" message.

**Commit Message Template:**

```text
fix(backend): add specific error handling for OpenAI image downloads

- Catch ConnectionError and HTTPError with clear messages
- Timeout handling unchanged
- Generic Exception fallback preserved
- Addresses HIGH health finding: openai_provider.py:50-52
```

---

### Task 3: Reduce API_CLIENT_TIMEOUT Default (MEDIUM)

**Goal:** Reduce the default `API_CLIENT_TIMEOUT` from 120s to 60s so hung providers surface errors faster within the 900s Lambda timeout.

**Files to Modify:**

- `backend/src/config.py` — the `api_client_timeout` line
- `CLAUDE.md` — the `API_CLIENT_TIMEOUT` row in the Operational Timeouts table

**Implementation Steps:**

1. Read `backend/src/config.py` and find the `api_client_timeout` line
1. Change the default from `120.0` to `60.0`:

   ```python
   api_client_timeout = _safe_float("API_CLIENT_TIMEOUT", 60.0)
   ```

1. Update `CLAUDE.md` — find the `API_CLIENT_TIMEOUT` row in the Operational Timeouts table and change the Default column from `120.0` to `60.0`

**Verification Checklist:**

- [x] `config.py` defaults `API_CLIENT_TIMEOUT` to `60.0`
- [x] `CLAUDE.md` Operational Timeouts table shows `60.0` for `API_CLIENT_TIMEOUT`
- [x] `ruff check backend/src/` passes
- [x] Existing tests pass (tests should not depend on the default timeout value)

**Testing Instructions:**

No new tests needed. The default value is a config constant, not behavior. Run existing tests to confirm no regressions.

**Commit Message Template:**

```text
fix(backend): reduce API_CLIENT_TIMEOUT default from 120s to 60s

- 120s is generous; 60s still exceeds typical provider response times
- 60s still generous for image generation APIs (typically 10-30s)
- Configurable via API_CLIENT_TIMEOUT env var
- Addresses MEDIUM health finding: config.py:254
```

## Phase Verification

1. `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` — all tests pass
1. `ruff check backend/src/` — clean
1. `grep -n "_get_firefly_access_token\|_get_or_refresh_token" backend/src/models/providers/firefly.py` — verify caching wrapper exists and is called
1. `grep -n "ConnectionError\|HTTPError" backend/src/models/providers/openai_provider.py` — verify specific catches exist
1. `grep -n "api_client_timeout.*60" backend/src/config.py` — verify new default

### Health Findings Addressed

| Finding | Original Severity | Status |
|---------|-------------------|--------|
| Firefly OAuth2 token per-call | HIGH | Fixed in Task 1 |
| OpenAI download error handling | HIGH | Fixed in Task 2 |
| API_CLIENT_TIMEOUT 120s default | MEDIUM | Fixed in Task 3 |

### Health Findings Closed (no action needed)

| Finding | Original Severity | Why Closed |
|---------|-------------------|------------|
| Outpaint context validation | MEDIUM | Already handled by existing try-except in `_handle_refinement` (line 857) |
| PromptEnhancer blocking | HIGH | Configurable timeout + fallback already in place |
| DynamoDB retry jitter | MEDIUM | Bounded retries (3), no sleep, fast-fail on limit |
| time.sleep() in retry.py | MEDIUM | Max 7s total, acceptable for Lambda |
| time.sleep() in context.py | MEDIUM | Max 0.3s, negligible |
| Stripe webhook validation | MEDIUM | Already uses stripe.Webhook.construct_event() |
| _parse_and_validate_request size | MEDIUM | Structural preference, well-tested, not a bug |
| Provider name validation | LOW | Already validated at request time via get_handler() |
