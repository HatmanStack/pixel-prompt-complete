# Phase 3: Admin API Endpoints

## Phase Goal

Build the admin API layer: authenticated endpoints for user management (list, suspend, unsuspend, notify), model status and controls (view caps, disable/enable), metrics retrieval, and revenue reporting. All endpoints are gated behind the `ADMIN_ENABLED` feature flag and require Cognito `admins` group membership.

**Success criteria:**

- Admin auth middleware validates `cognito:groups` claim and rejects non-admin users with 403
- All 10 admin API endpoints return correct responses
- User suspend/unsuspend/notify endpoints modify DynamoDB and trigger emails
- Model disable/enable endpoints modify runtime config
- All new code has unit tests passing at 80%+ coverage

**Estimated tokens:** ~40,000

## Prerequisites

- Phase 1 complete (config vars, model counters, suspension, CAPTCHA)
- Phase 2 complete (email sender, templates, revenue tracking, metrics)
- All Phase 1 and Phase 2 tests passing

## Task 1: Admin Auth Middleware

**Goal:** Create a `require_admin` function that validates admin group membership from JWT claims.

**Files to Create:**

- `backend/src/auth/claims.py` - New file (the `auth/` directory currently contains only `__init__.py` and `guest_token.py`)
- `backend/src/admin/__init__.py` - Empty init
- `backend/src/admin/auth.py` - Admin auth wrapper

**Prerequisites:** None (uses existing `extract_claims` from `users/tier.py`)

**Implementation Steps:**

1. Create `backend/src/auth/claims.py` (new file; the `auth/` directory currently contains only `__init__.py` and `guest_token.py`). Import `extract_claims` from `users.tier` at the top of the file: `from users.tier import extract_claims`. The `extract_claims` function is defined in `backend/src/users/tier.py` at line 31, not in this new module. Add:
   - `extract_admin_groups(event: dict) -> list[str]`: extract `cognito:groups` from JWT claims at `event["requestContext"]["authorizer"]["jwt"]["claims"]["cognito:groups"]`. The claim value may arrive as a string representation because API Gateway's HttpApi JWT authorizer (which reads claims from `event.requestContext.authorizer.jwt.claims`) serializes JSON array claims into their string form, e.g., `"[admins, editors]"`. This is a defensive measure: handle both string format (strip brackets, split on comma, strip whitespace from each element) and native list format (in case future API Gateway versions pass the array directly). Return empty list if no claims or no groups.
   - `is_admin(event: dict) -> bool`: calls `extract_admin_groups` and checks if `"admins"` is in the list.
1. Create `backend/src/admin/__init__.py` (empty file).
1. Create `backend/src/admin/auth.py`:
   - `require_admin_request(event: dict) -> tuple[dict | None, dict | None]`: returns `(claims, None)` on success or `(None, error_response)` on failure. Checks:
     1. `config.admin_enabled` is True (else return 501 "admin disabled")
     1. `config.auth_enabled` is True (else return 501 "auth disabled")
     1. `extract_claims(event)` returns non-None (else return 401)
     1. `is_admin(event)` returns True (else return 403 with `ADMIN_REQUIRED` error)
   - This function is called at the top of every admin endpoint handler.
1. Add to `error_responses.py`:
   - `admin_required() -> Dict[str, Any]`: error code `ADMIN_REQUIRED`, status 403, message "Admin access required"
   - `admin_disabled() -> Dict[str, Any]`: error code `ADMIN_DISABLED`, status 501, message "Admin features are disabled"

**Verification Checklist:**

- [x] `extract_admin_groups` handles string and list formats for `cognito:groups`
- [x] `is_admin` returns True when user is in `admins` group
- [x] `is_admin` returns False when user is not in `admins` group
- [x] `require_admin_request` returns 501 when `admin_enabled=false`
- [x] `require_admin_request` returns 401 when no JWT claims
- [x] `require_admin_request` returns 403 when user is not admin
- [x] `require_admin_request` returns claims when user is admin

**Testing Instructions:**

Create `tests/backend/unit/test_admin_auth.py`:

- Test `extract_admin_groups` with list format `["admins"]`
- Test `extract_admin_groups` with string format `"[admins]"`
- Test `extract_admin_groups` with no groups claim
- Test `is_admin` returns True for admin user
- Test `is_admin` returns False for non-admin user
- Test `require_admin_request` returns 501 when admin disabled
- Test `require_admin_request` returns 401 when no JWT
- Test `require_admin_request` returns 403 when not admin
- Test `require_admin_request` returns claims when admin

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_admin_auth.py -v`

**Commit Message Template:**

```text
feat(admin): add admin auth middleware with Cognito group check

- extract_admin_groups handles both string and list cognito:groups
- require_admin_request validates admin_enabled, auth, and group membership
- ADMIN_REQUIRED and ADMIN_DISABLED error responses
```

## Task 2: Admin User List and Detail Endpoints

**Goal:** Implement `GET /admin/users` (paginated list) and `GET /admin/users/{userId}` (detail).

**Files to Create:**

- `backend/src/admin/users.py` - User management admin endpoints

**Files to Modify:**

- `backend/src/lambda_function.py` - Add admin route handlers

**Prerequisites:** Task 1 (admin auth)

**Implementation Steps:**

1. Create `backend/src/admin/users.py`:
   - `handle_admin_users_list(event: dict, repo: UserRepository, correlation_id: str | None) -> dict`:
     1. Call `require_admin_request(event)`. Return error if not admin.
     1. Parse query parameters: `limit` (default 50, max 100), `lastKey` (pagination token, base64-encoded JSON of `LastEvaluatedKey`), `tier` (optional filter), `suspended` (optional filter, "true"/"false").
     1. Run `repo.scan_users(limit, last_key, tier_filter, suspended_filter)` (new method; see below).
     1. Return `{"users": [...], "nextKey": base64_encoded_last_key_or_null, "count": N}`.
   - `handle_admin_user_detail(event: dict, repo: UserRepository, correlation_id: str | None) -> dict`:
     1. Call `require_admin_request(event)`.
     1. Extract `userId` from path.
     1. Call `repo.get_user(userId)`.
     1. Return the user record or 404.
1. Add to `UserRepository`:
   - `scan_users(limit: int, last_key: dict | None, tier_filter: str | None, suspended_filter: bool | None) -> tuple[list[dict], dict | None]`: DynamoDB Scan with optional `FilterExpression` for `tier` and `isSuspended`. Exclude items with `userId` starting with `guest#`, `model#`, `metrics#`, or `revenue#` (these are non-user records in the single-table). Return `(items, LastEvaluatedKey)`.
1. Add routes to `lambda_function.py`:
   - `elif path == "/admin/users" and method == "GET": return handle_admin_users_list(...)`
   - `elif path.startswith("/admin/users/") and method == "GET": return handle_admin_user_detail(...)`
   - Import the handlers at the top of the file (not lazy import; admin endpoints are lightweight).
   - Apply JWT auth at the API Gateway level by adding new HttpApi events with `Auth: !If [AuthEnabledCondition, Authorizer: CognitoJwt, {}]` in `template.yaml`.

**Verification Checklist:**

- [x] User list returns paginated results
- [x] User list excludes `guest#`, `model#`, `metrics#`, `revenue#` items
- [x] Tier filter works correctly
- [x] Suspended filter works correctly
- [x] Pagination token round-trips correctly
- [x] User detail returns full user record
- [x] User detail returns 404 for unknown user
- [x] Non-admin users get 403

**Testing Instructions:**

Create `tests/backend/unit/test_admin_users.py`:

- Use moto DynamoDB mock with pre-populated user records (mix of free, paid, guest, suspended)
- Test list returns only real users (not guest#, model#, etc.)
- Test pagination with limit=2
- Test tier filter
- Test suspended filter
- Test user detail returns correct record
- Test user detail returns 404 for missing user
- Test non-admin auth returns 403

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_admin_users.py -v`

**Commit Message Template:**

```text
feat(admin): add user list and detail API endpoints

- Paginated DynamoDB Scan with tier and suspension filters
- Excludes non-user records from single-table design
- Full user detail retrieval
```

## Task 3: Admin Suspend, Unsuspend, and Notify Endpoints

**Goal:** Implement `POST /admin/users/{userId}/suspend`, `POST /admin/users/{userId}/unsuspend`, and `POST /admin/users/{userId}/notify`.

**Files to Modify:**

- `backend/src/admin/users.py` - Add suspend/unsuspend/notify handlers

**Prerequisites:** Task 1 (admin auth), Task 2 (admin user endpoints), Phase 2 Tasks 1-2 (email sender, templates)

**Implementation Steps:**

1. Add to `backend/src/admin/users.py`:
   - `handle_admin_suspend(event: dict, repo: UserRepository, correlation_id: str | None) -> dict`:
     1. Call `require_admin_request(event)`.
     1. Extract `userId` from path.
     1. Verify user exists (`repo.get_user`). Return 404 if not.
     1. Call `repo.suspend_user(userId)`.
     1. If `config.ses_enabled` and user has email, send `suspension_notice_email` with reason from request body (optional `reason` field, default "Policy violation").
     1. Return `{"status": "suspended", "userId": userId}`.
   - `handle_admin_unsuspend(event: dict, repo: UserRepository, correlation_id: str | None) -> dict`:
     1. Same auth and user existence checks.
     1. Call `repo.unsuspend_user(userId)`.
     1. Return `{"status": "active", "userId": userId}`.
   - `handle_admin_notify(event: dict, repo: UserRepository, correlation_id: str | None) -> dict`:
     1. Same auth check.
     1. Verify user exists and has an email address.
     1. Parse request body: `type` (one of "warning", "custom"), `message` (required for both), `subject` (required for custom).
     1. Render the appropriate template and call `send_email`.
     1. Return `{"status": "sent", "userId": userId}` or `{"status": "failed"}` if SES is disabled or email failed.
1. Add routes to `lambda_function.py`:
   - Match paths like `/admin/users/{userId}/suspend`, `/admin/users/{userId}/unsuspend`, `/admin/users/{userId}/notify` using regex or path splitting.
   - Route POST requests to the appropriate handler.

**Verification Checklist:**

- [x] Suspend sets `isSuspended=true` and returns 200
- [x] Suspend sends suspension email when SES is enabled
- [x] Suspend returns 404 for unknown user
- [x] Unsuspend sets `isSuspended=false` and returns 200
- [x] Notify sends warning email with custom message
- [x] Notify sends custom email with custom subject and message
- [x] Notify returns error when user has no email
- [x] All endpoints require admin auth

**Testing Instructions:**

Add tests to `tests/backend/unit/test_admin_users.py`:

- Test suspend sets isSuspended and sends email (mock sender)
- Test suspend returns 404 for unknown user
- Test unsuspend clears isSuspended
- Test notify sends warning email
- Test notify sends custom email
- Test notify returns error for user without email

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_admin_users.py -v`

**Commit Message Template:**

```text
feat(admin): add suspend, unsuspend, and notify user endpoints

- Suspend/unsuspend toggle isSuspended in DynamoDB
- Suspension sends SES notification when enabled
- Notify sends warning or custom email to user
```

## Task 4: Admin Model Status and Control Endpoints

**Goal:** Implement `GET /admin/models` (view status), `POST /admin/models/{model}/disable`, and `POST /admin/models/{model}/enable`.

**Files to Create:**

- `backend/src/admin/models.py` - Model management admin endpoints

**Files to Modify:**

- `backend/src/users/repository.py` - Add `get_model_runtime_config` and `set_model_runtime_config` methods
- `backend/src/lambda_function.py` - Add runtime disable check in `handle_generate` before dispatching models (this file is also modified in Phase 1 Task 4 for cost ceiling; the runtime disable check is an additional guard that runs alongside the cost ceiling check)

**Prerequisites:** Task 1 (admin auth), Phase 1 Task 2 (model counters)

**Implementation Steps:**

1. Create `backend/src/admin/models.py`:
   - `handle_admin_models_list(event: dict, model_counter_service, correlation_id: str | None) -> dict`:
     1. Call `require_admin_request(event)`.
     1. Get model counts via `model_counter_service.get_model_counts(now)`.
     1. For each model in `config.MODELS`, build a status dict: `name`, `displayName`, `enabled`, `provider`, `dailyCount`, `dailyCap`, `dailyResetAt`.
     1. Return `{"models": [...]}`.
   - `handle_admin_model_disable(event: dict, correlation_id: str | None) -> dict`:
     1. Call `require_admin_request(event)`.
     1. Extract model name from path. Validate it is in `config.MODELS`.
     1. Runtime disable: store `model#<name>#disabled` flag in DynamoDB (a new item `userId="config#model#<name>"` with `disabled=true`). This is a runtime override checked by the generation flow.
     1. Return `{"status": "disabled", "model": model_name}`.
   - `handle_admin_model_enable(event: dict, correlation_id: str | None) -> dict`:
     1. Same validation.
     1. Delete or set `disabled=false` on the config item.
     1. Return `{"status": "enabled", "model": model_name}`.
1. The runtime disable check needs to be integrated into `handle_generate` in `lambda_function.py`. Before dispatching a model, check if `config#model#<name>` item exists with `disabled=true`. This is a lightweight DynamoDB read (one per model). Cache this for the duration of the Lambda container lifetime (or just read each time; at 10 concurrent Lambdas and 4 models, that is 40 reads per second maximum).
1. Add a method to `UserRepository`:
   - `get_model_runtime_config(model_name: str) -> dict | None`: `get_user(f"config#model#{model_name}")`.
   - `set_model_runtime_config(model_name: str, disabled: bool) -> None`: `UpdateItem` on `userId=f"config#model#{model_name}"` setting `disabled` and `updatedAt`.

**Verification Checklist:**

- [x] Model list returns all 4 models with counts and caps
- [x] Model disable creates config item in DynamoDB
- [x] Model enable clears disabled flag
- [x] Disabled model is skipped in generation flow
- [x] Invalid model name returns 400
- [x] All endpoints require admin auth

**Testing Instructions:**

Create `tests/backend/unit/test_admin_models.py`:

- Use moto DynamoDB mock
- Test model list returns all 4 models with correct fields
- Test model disable sets disabled flag
- Test model enable clears disabled flag
- Test invalid model name returns 400
- Test disabled model is skipped in generation (integration test with handle_generate mock)

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_admin_models.py -v`

**Commit Message Template:**

```text
feat(admin): add model status, disable, and enable endpoints

- GET /admin/models returns per-model counts, caps, and enabled status
- Runtime disable/enable via DynamoDB config items
- Disabled models skipped in generation flow
```

## Task 5: Admin Metrics and Revenue Endpoints

**Goal:** Implement `GET /admin/metrics` and `GET /admin/revenue`.

**Files to Create:**

- `backend/src/admin/metrics.py` - Metrics and revenue admin endpoints

**Prerequisites:** Task 1 (admin auth), Phase 2 Tasks 4-6 (revenue tracking, daily snapshot)

**Implementation Steps:**

1. Create `backend/src/admin/metrics.py`:
   - `handle_admin_metrics(event: dict, repo: UserRepository, model_counter_service, correlation_id: str | None) -> dict`:
     1. Call `require_admin_request(event)`.
     1. Parse query parameter `days` (default 7, max 30).
     1. Read today's model counts from `model_counter_service.get_model_counts(now)`.
     1. Read recent daily snapshots: for each day in the range, call `repo.get_user(f"metrics#{date_str}")`. Collect into a list.
     1. Return `{"today": {model_counts}, "history": [snapshots], "days": N}`.
   - `handle_admin_revenue(event: dict, repo: UserRepository, correlation_id: str | None) -> dict`:
     1. Call `require_admin_request(event)`.
     1. Read `revenue#current` from `repo.get_revenue()`.
     1. Read recent daily snapshots (same as metrics, but extract only the `revenue` field from each).
     1. Return `{"current": {revenue_data}, "history": [daily_revenue_snapshots]}`.
1. Add routes to `lambda_function.py`:
   - `elif path == "/admin/metrics" and method == "GET": return handle_admin_metrics(...)`
   - `elif path == "/admin/revenue" and method == "GET": return handle_admin_revenue(...)`

**Verification Checklist:**

- [x] Metrics endpoint returns today's model counts and historical snapshots
- [x] Revenue endpoint returns current counters and historical data
- [x] Days parameter limits the history range
- [x] Missing snapshot days return empty entries (not errors)
- [x] All endpoints require admin auth

**Testing Instructions:**

Create `tests/backend/unit/test_admin_metrics.py`:

- Use moto DynamoDB mock with pre-populated metrics snapshots and revenue items
- Test metrics returns today's counts and N days of history
- Test revenue returns current and historical data
- Test missing snapshot days handled gracefully
- Test days parameter works correctly
- Test admin auth required

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_admin_metrics.py -v`

**Commit Message Template:**

```text
feat(admin): add metrics and revenue API endpoints

- GET /admin/metrics returns model counts and daily snapshot history
- GET /admin/revenue returns current and historical revenue data
- Configurable history range via days parameter
```

## Task 6: Route Registration and SAM Template Updates

**Goal:** Register all admin routes in `lambda_function.py` and add corresponding HttpApi events to `template.yaml`.

**Files to Modify:**

- `backend/src/lambda_function.py` - Add all admin route handlers
- `backend/template.yaml` - Add HttpApi events for admin routes

**Prerequisites:** Tasks 2-5

**Implementation Steps:**

1. In `lambda_function.py`, add admin route matching. Since admin paths have variable segments (`/admin/users/{userId}/suspend`), use a structured approach:
   - Add an `_route_admin(path, method, event, correlation_id)` function that handles all `/admin/*` paths.
   - Call this function from `lambda_handler` when `path.startswith("/admin/")`.
   - Inside `_route_admin`, parse the path segments and dispatch to the correct handler.
1. In `template.yaml`, add HttpApi events for admin endpoints. All admin routes require JWT auth:

   ```yaml
   AdminUsersListApi:
     Type: HttpApi
     Properties:
       Path: /admin/users
       Method: GET
       ApiId: !Ref HttpApi
       Auth: !If
         - AuthEnabledCondition
         - Authorizer: CognitoJwt
         - {}
   ```

   Repeat for all admin paths. For paths with variables (`/admin/users/{userId}`), use API Gateway path parameters.

1. Add admin route paths:
   - `GET /admin/users`
   - `GET /admin/users/{userId}`
   - `POST /admin/users/{userId}/suspend`
   - `POST /admin/users/{userId}/unsuspend`
   - `POST /admin/users/{userId}/notify`
   - `GET /admin/models`
   - `POST /admin/models/{model}/disable`
   - `POST /admin/models/{model}/enable`
   - `GET /admin/metrics`
   - `GET /admin/revenue`

**Verification Checklist:**

- [ ] All 10 admin routes are registered in `lambda_handler`
- [ ] All admin HttpApi events have JWT auth conditional
- [ ] Path parameter extraction works for variable segments
- [ ] `sam build` succeeds
- [ ] Unknown admin paths return 404

**Testing Instructions:**

Add routing tests to `tests/backend/unit/test_lambda_function.py`:

- Test each admin path routes to the correct handler (mock the handlers)
- Test unknown admin path returns 404
- Test admin paths with method mismatch return 404

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_lambda_function.py -v`

Verify SAM build: `cd backend && sam build`

**Commit Message Template:**

```text
feat(admin): register all admin routes in lambda handler and SAM template

- 10 admin API routes with JWT auth
- Structured admin route dispatcher
- HttpApi events for all admin paths
```

## Phase Verification

After all 6 tasks are complete:

1. All existing tests pass: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
1. New tests pass: `PYTHONPATH=backend/src pytest tests/backend/unit/test_admin_auth.py tests/backend/unit/test_admin_users.py tests/backend/unit/test_admin_models.py tests/backend/unit/test_admin_metrics.py -v`
1. Ruff lint passes: `ruff check backend/src/`
1. SAM build succeeds: `cd backend && sam build`
1. With `ADMIN_ENABLED=false`, all admin endpoints return 501
1. Non-admin users get 403 on all admin endpoints

## Known Limitations

- User list uses DynamoDB Scan, which is O(table size). Acceptable below 10,000 users per ADR-19.
- Model runtime disable is stored in DynamoDB and checked per request. A Lambda container restart will pick up the latest state, but there is no push notification to running containers. The disable takes effect within seconds as containers naturally rotate.
- No audit log for admin actions (suspend, unsuspend, notify, model disable/enable). This can be added later as a DynamoDB stream or explicit logging.
