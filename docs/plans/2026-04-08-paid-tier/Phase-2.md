# Phase 2: Tier Resolution and Quota Enforcement

## Phase Goal

Replace the IP-based `RateLimiter` with the new tier system. Add guest token handling, DynamoDB-backed user repository, tier resolution, and atomic quota enforcement. Wire into `_parse_and_validate_request`. Ship `/me`. Delete `utils/rate_limit.py`.

**Success criteria:**

- With feature flags off, behavior matches pre-phase (no quota enforcement, no auth).
- With `AUTH_ENABLED=true`, guests get 1 generation and are blocked from refinement; signed-in users get 1 generate + 2 refinements per rolling hour; quotas reset correctly after the window.
- `utils/rate_limit.py` and its test file are deleted.
- 80% backend coverage maintained or exceeded.

**Token estimate:** ~55k

## Prerequisites

- Phase 1 committed and verified.
- Phase-0 ADRs 1–4, 7, 9, 10 understood.

## Task 2.1: Add New Error Response Factories [x]

### Goal

Add standard error bodies for auth/tier failures so handlers can return consistent responses.

### Files to Modify

- `backend/src/utils/error_responses.py`

### Implementation Steps

1. Add functions:

    ```python
    def auth_required() -> dict:
        return {"error": "Authentication required", "code": "auth_required"}

    def tier_quota_exceeded(tier: str, reset_at: int) -> dict:
        return {
            "error": f"Quota exceeded for {tier} tier",
            "code": "tier_quota_exceeded",
            "tier": tier,
            "resetAt": reset_at,
        }

    def subscription_required() -> dict:
        return {"error": "Paid subscription required", "code": "subscription_required"}

    def guest_global_limit() -> dict:
        return {"error": "Guest traffic limit reached, please sign in", "code": "guest_global_limit"}
    ```

1. Unit test each in `tests/backend/unit/test_error_responses.py` (extend existing file if present).

### Commit Message Template

```text
feat(errors): add tier/auth error response factories
```

## Task 2.2: Implement Guest Token Module [x]

### Goal

Self-contained HMAC cookie module with no AWS dependencies.

### Files to Create

- `backend/src/auth/__init__.py` (empty)
- `backend/src/auth/guest_token.py`
- `tests/backend/unit/test_guest_token.py`

### Implementation Steps (TDD)

1. Write `test_guest_token.py` first:
    - `test_issue_and_verify_round_trip`
    - `test_tampered_token_rejected`
    - `test_empty_secret_rejected_at_init`
    - `test_token_id_is_random` (issue two tokens, assert different)
    - `test_parse_cookie_header_multiple_cookies`
1. Implement `GuestTokenService` with:
    - `__init__(secret: str)` — raises `ValueError` on empty secret.
    - `issue() -> str` — generates 16-byte token_id, returns `base64url(token_id) + "." + base64url(hmac_sha256(token_id, secret))`.
    - `verify(token: str) -> str | None` — returns token_id on success, `None` on failure. Use `hmac.compare_digest`.
    - `extract_from_cookie_header(header: str) -> str | None` — parses `pp_guest=...` from a Cookie header.
    - `set_cookie_header(token: str, max_age: int) -> str` — returns the `Set-Cookie` value with `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=...`.
1. Module exposes a lazy singleton `get_guest_token_service()` that reads `config.guest_token_secret`.

### Verification Checklist

- [ ] Tests pass.
- [ ] `ruff check` passes.
- [ ] Coverage on `guest_token.py` is 100%.

### Commit Message Template

```text
feat(auth): add HMAC-signed guest token service
```

## Task 2.3: Implement UserRepository (DynamoDB) [x]

### Goal

Atomic CRUD for the users table with rolling-window counter updates in a single `UpdateItem`.

### Files to Create

- `backend/src/users/__init__.py` (empty)
- `backend/src/users/repository.py`
- `tests/backend/unit/test_user_repository.py`

### Implementation Steps (TDD with moto)

1. Fixture: `@pytest.fixture def users_table()` that uses `moto.mock_aws` to create the table matching `Phase-0.md` schema and returns `(table_name, dynamodb_resource)`.
1. Write failing tests first:
    - `test_get_or_create_user` — first call creates, second returns existing.
    - `test_increment_generate_resets_window` — set `windowStart` in the past, call increment, assert `generateCount == 1` and `windowStart` updated.
    - `test_increment_generate_within_window` — two calls within window, assert `generateCount == 2`.
    - `test_increment_refine_independent_of_generate`
    - `test_set_tier_paid` and `test_set_tier_free`
    - `test_set_stripe_customer_id` (idempotent)
    - `test_guest_item_uses_ttl` — creating a guest item sets `ttl` attribute.
    - `test_global_guest_counter_atomic` — two parallel-ish increments both land.
1. Implement `UserRepository`:

    ```python
    class UserRepository:
        def __init__(self, table_name: str, dynamodb_resource=None): ...
        def get_user(self, user_id: str) -> dict | None: ...
        def get_or_create_user(self, user_id: str, email: str | None = None) -> dict: ...
        def touch_quota_window(self, user_id: str, window_seconds: int, now: int) -> dict:
            """Reset counters if window expired. Returns fresh item."""
        def increment_generate(self, user_id: str, window_seconds: int, limit: int, now: int) -> tuple[bool, dict]:
            """Atomic: reset window if stale, then increment if under limit.
            Returns (allowed, updated_item)."""
        def increment_refine(self, user_id: str, window_seconds: int, limit: int, now: int) -> tuple[bool, dict]: ...
        def increment_daily(self, user_id: str, window_seconds: int, limit: int, now: int) -> tuple[bool, dict]: ...
        def set_tier(self, user_id: str, tier: str, **stripe_fields) -> None: ...
        def upsert_guest(self, token_id: str, ip_hash: str, ttl: int) -> dict: ...
        def increment_guest_generate(self, token_id: str, limit: int, window_seconds: int, now: int) -> tuple[bool, dict]: ...
        def increment_global_guest(self, limit: int, window_seconds: int, now: int) -> tuple[bool, dict]: ...
    ```

1. All counter methods use a single `update_item` with a `ConditionExpression` that both checks the counter is under limit AND bumps the window if stale. Pattern:

    ```python
    table.update_item(
        Key={"userId": user_id},
        UpdateExpression=(
            "SET windowStart = if_not_exists(windowStart, :now), "
            "updatedAt = :now "
            "ADD generateCount :one"
        ),
        ConditionExpression="(attribute_not_exists(generateCount) OR generateCount < :limit) "
                            "AND (attribute_not_exists(windowStart) OR windowStart > :stale)",
        ExpressionAttributeValues={":one": 1, ":limit": limit, ":now": now, ":stale": now - window_seconds},
        ReturnValues="ALL_NEW",
    )
    ```

    If `ConditionalCheckFailedException` fires and the reason is a stale window, the method re-attempts after resetting the counter via a separate conditional update. Cap at 3 retries.

### Verification Checklist

- [ ] All tests pass with moto.
- [ ] Branch coverage on `repository.py` is 90%+.
- [ ] No raw `boto3.client` calls — use injected `dynamodb_resource`.

### Commit Message Template

```text
feat(users): add DynamoDB user repository with atomic quota updates
```

## Task 2.4: Implement Tier Resolution [x]

### Goal

Single function that reads the Lambda event, returns a `TierContext` describing the caller.

### Files to Create

- `backend/src/users/tier.py`
- `tests/backend/unit/test_tier_resolution.py`

### Implementation Steps (TDD)

1. Define:

    ```python
    @dataclass(frozen=True)
    class TierContext:
        tier: Literal["guest", "free", "paid"]
        user_id: str           # cognito sub or "guest#<token_id>"
        email: str | None
        is_authenticated: bool
        guest_token_id: str | None  # only set when tier == "guest"
        issue_guest_cookie: bool    # true when we minted a new token
    ```

1. Implement `resolve_tier(event, repo, guest_service) -> TierContext`:
    - If `config.auth_enabled` is False: return a synthetic `TierContext(tier="paid", user_id="anon", is_authenticated=False, ...)` with effectively unlimited quotas. This is the open-source path.
    - Otherwise: try `event.requestContext.authorizer.jwt.claims` — if present, extract `sub` and `email`, call `repo.get_or_create_user`, consult `repo`'s `tier` attribute, return `free` or `paid`.
    - If no claims: look for `pp_guest` cookie in headers. Verify HMAC. If valid, return `guest` with the existing token_id. If missing or invalid, mint a new token and set `issue_guest_cookie=True`.
1. Tests:
    - `test_flags_off_returns_anon_paid`
    - `test_jwt_claims_return_free_by_default`
    - `test_jwt_claims_returning_paid_user` (seed repo with `tier="paid"`)
    - `test_no_claims_no_cookie_issues_new_token`
    - `test_no_claims_valid_cookie_returns_guest`
    - `test_no_claims_tampered_cookie_issues_new_token`

### Commit Message Template

```text
feat(users): add tier resolution from JWT claims and guest cookie
```

## Task 2.5: Implement Quota Enforcement Layer [x]

### Goal

Single function `enforce_quota(tier_ctx, endpoint, repo) -> QuotaResult` that calls the right repository method based on tier + endpoint, returns a pass/fail decision and the updated counters.

### Files to Create

- `backend/src/users/quota.py`
- `tests/backend/unit/test_quota_enforcement.py`

### Implementation Steps (TDD)

1. Define:

    ```python
    @dataclass(frozen=True)
    class QuotaResult:
        allowed: bool
        reason: str | None          # "guest_per_user" | "guest_global" | "free_generate" | "free_refine" | "paid_daily"
        reset_at: int               # epoch seconds
        usage: dict                 # {"used": int, "limit": int} for the relevant counter
    ```

1. Implement `enforce_quota(ctx: TierContext, endpoint: Literal["generate","refine"], repo: UserRepository, now: int) -> QuotaResult`:
    - If `not config.auth_enabled`: return `QuotaResult(allowed=True, reason=None, reset_at=0, usage={})`.
    - If `ctx.tier == "guest"`:
        - If `endpoint == "refine"`: return disallowed with `reason="guest_per_user"`.
        - Check global cap first via `repo.increment_global_guest`. If blocked, return disallowed with `reason="guest_global"`. (If blocked, do **not** increment the per-guest counter.)
        - Then `repo.increment_guest_generate`. If blocked, return disallowed.
    - If `ctx.tier == "free"`:
        - `generate` → `increment_generate` (limits: `free_generate_limit`, `free_window_seconds`).
        - `refine` → `increment_refine`.
    - If `ctx.tier == "paid"`:
        - `generate` → no quota (allow).
        - `refine` → `increment_daily` (limits: `paid_daily_limit`, `paid_window_seconds`).
1. Tests cover every branch above, including window-reset behavior and global-cap-blocks-before-per-user.

### Commit Message Template

```text
feat(users): add tier-based quota enforcement layer
```

## Task 2.6: Wire Tier + Quota into lambda_function.py [x]

### Goal

Replace `RateLimiter` with the new layer in `_parse_and_validate_request`. Thread the `TierContext` through so handlers can attach `Set-Cookie` on guest responses.

### Files to Modify

- `backend/src/lambda_function.py`

### Implementation Steps

1. Module-level: instantiate `_user_repo = UserRepository(config.users_table_name)` and `_guest_service = get_guest_token_service()` (lazy-safe when `AUTH_ENABLED=false` — repo is still constructed but never called because `resolve_tier` short-circuits).
1. Remove `rate_limiter = RateLimiter(...)` and its import.
1. Extend the existing `ValidatedRequest` dataclass (already defined at `lambda_function.py` line 96-102 as `@dataclass` with fields `body: dict[str, Any]`, `ip: str`, `prompt: str`). Preserve those three fields verbatim and append a new `tier: TierContext` field. Do **not** redefine the class from scratch:

    ```python
    @dataclass
    class ValidatedRequest:
        """Result of successful request validation."""

        body: dict[str, Any]
        ip: str
        prompt: str
        tier: TierContext
    ```

1. In `_parse_and_validate_request`, after JSON parse:
    - Call `resolve_tier(event, _user_repo, _guest_service)`.
    - Determine endpoint kind: `_parse_and_validate_request` grows a new `endpoint_kind` param (`"generate"` or `"refine"` or `"none"` for non-quota-gated endpoints like `/enhance`, `/log`). Callers pass this explicitly.
    - Call `enforce_quota` when `endpoint_kind != "none"`. If not allowed, return an appropriate 402/429 response with the error code from Task 2.1.
    - Attach `tier` to the returned `ValidatedRequest`.
1. Update every caller of `_parse_and_validate_request` to pass the right `endpoint_kind`: `handle_generate` → `"generate"`, `handle_iterate` and `handle_outpaint` → `"refine"`, `handle_enhance` → `"none"`, `handle_log_endpoint` → `"none"`.
1. Update `response()` to optionally accept a `set_cookie: str | None` parameter and emit a `Set-Cookie` header when provided.
1. In `handle_generate`, if `validated.tier.issue_guest_cookie`, pass `set_cookie=...` on the success response.
1. Remove every remaining `rate_limiter.` call site. As of today there are exactly two in `lambda_function.py`: line 135 inside `_parse_and_validate_request` (the main entry path, replaced by `enforce_quota` above) and line 741 inside `handle_log_endpoint`. Grep the file for `rate_limiter` to confirm no third call site has been added since this plan was written. Both must be deleted; `/log` will rely on API Gateway throttling.
1. Update `_parse_and_validate_request` signature in tests accordingly.

### Verification Checklist

- [ ] No references to `RateLimiter` or `rate_limiter` remain.
- [ ] `ruff check` passes.
- [ ] Existing handler tests updated to pass `endpoint_kind` via fresh fixtures that mock `_user_repo` and `resolve_tier`.
- [ ] New test `tests/backend/unit/test_quota_wiring.py` covers: guest hits /generate (ok + cookie), guest hits /iterate (blocked 402), free user exceeds refine quota (429), paid user unlimited generate.

### Commit Message Template

```text
feat(lambda): wire tier resolution and quota enforcement
```

## Task 2.7: Implement /me Endpoint [x]

### Goal

`handle_me` returns the `/me` payload from `Phase-0.md` ADR-10.

### Files to Modify

- `backend/src/lambda_function.py`

### Implementation Steps

1. Add `handle_me(event, correlation_id)` that:
    - Requires `auth_enabled=True`. Otherwise returns 501.
    - Calls `resolve_tier` — must return an authenticated context. Otherwise 401 via `error_responses.auth_required()`.
    - Calls `_user_repo.touch_quota_window` to get fresh counters.
    - Builds the response JSON exactly as specified in Phase-0 ADR-10, choosing the counter relevant to the tier.
1. Register in `lambda_handler` (replace the Task 1.6 stub).
1. Test `tests/backend/unit/test_me_endpoint.py` covers: unauthenticated → 401, free tier → correct counters, paid tier → daily counter, flags-off → 501.

### Commit Message Template

```text
feat(lambda): implement /me tier and quota endpoint
```

## Task 2.8: Delete utils/rate_limit.py [x]

### Goal

Remove the legacy rate limiter entirely.

### Files to Delete

- `backend/src/utils/rate_limit.py`
- `tests/backend/unit/test_rate_limit.py` (if present)

### Implementation Steps

1. `git rm` both files.
1. Grep `backend/src/` and `tests/` for `rate_limit` — confirm no references.
1. Remove any remaining `global_limit` / `ip_limit` mentions from comments and docstrings.

### Verification Checklist

- [ ] `grep -r "rate_limit\|RateLimiter\|global_limit\|ip_limit" backend/src tests/backend` is empty.
- [ ] Full test suite passes.
- [ ] Coverage still ≥ 80%.

### Commit Message Template

```text
refactor: remove legacy IP-based rate limiter

Tier-based quotas are now the single source of truth.
```

## Phase Verification

- [ ] All 8 tasks committed in order.
- [ ] `ruff check backend/src/` passes.
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v --cov=backend/src --cov-fail-under=80` passes.
- [ ] Manual smoke test against `sam local start-api`: `/generate` with no auth works (guest cookie issued), second `/generate` with same cookie blocked, `/iterate` with no auth returns 402, `/me` with no auth returns 401.
- [ ] Flag-off behavior unchanged: all existing integration-style tests pass without modification.
