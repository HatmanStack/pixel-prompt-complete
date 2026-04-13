# Phase 1: Cost Ceiling, Account Suspension, and CAPTCHA

## Phase Goal

Build the backend safety layer: per-model daily generation caps that prevent runaway costs, account suspension for abuse prevention, and Cloudflare Turnstile CAPTCHA for guest bot protection. These three features have no frontend work in this phase. The CAPTCHA frontend widget is built in Phase 4 Task 8; this phase implements only the backend verification. All features are gated behind feature flags.

**Success criteria:**

- Per-model daily counters enforce configurable caps; capped models are skipped during generation
- Suspended users receive 403 on all quota-checked endpoints
- Guest `/generate` requests with `CAPTCHA_ENABLED=true` require a valid Turnstile token
- All new code has unit tests passing at 80%+ coverage
- `sam build` succeeds with the updated `template.yaml`

**Estimated tokens:** ~40,000

## Prerequisites

- Paid-tier v1 fully implemented (ADR-1 through ADR-10)
- All existing tests passing (`PYTHONPATH=backend/src pytest tests/backend/unit/ -v`)

## Task 1: Config Module - New Environment Variables

**Goal:** Add all new feature flags, model cap defaults, CAPTCHA config, SES config, and admin config to `config.py`. This is the foundation all other tasks depend on.

**Files to Modify/Create:**

- `backend/src/config.py` - Add new env vars following existing `_safe_int` / `os.environ.get` pattern

**Prerequisites:** None

**Implementation Steps:**

1. Add feature flags at the top of `config.py` (after existing `billing_enabled` block):
   - `captcha_enabled` - boolean from `CAPTCHA_ENABLED`, default `false`
   - `ses_enabled` - boolean from `SES_ENABLED`, default `false`
   - `admin_enabled` - boolean from `ADMIN_ENABLED`, default `false`
1. Add validation: `admin_enabled` requires `auth_enabled` (same pattern as `billing_enabled` requires `auth_enabled`)
1. Add per-model daily cap variables:
   - `model_gemini_daily_cap` - `_safe_int("MODEL_GEMINI_DAILY_CAP", 500)`
   - `model_nova_daily_cap` - `_safe_int("MODEL_NOVA_DAILY_CAP", 500)`
   - `model_openai_daily_cap` - `_safe_int("MODEL_OPENAI_DAILY_CAP", 500)`
   - `model_firefly_daily_cap` - `_safe_int("MODEL_FIREFLY_DAILY_CAP", 500)`
1. Add a dict mapping model name to cap for easy lookup: `MODEL_DAILY_CAPS = {"gemini": model_gemini_daily_cap, ...}`
1. Add CAPTCHA config:
   - `turnstile_secret_key` - `os.environ.get("TURNSTILE_SECRET_KEY", "")`
   - Validation: if `captcha_enabled` and not `turnstile_secret_key`, raise `RuntimeError`
1. Add SES config:
   - `ses_from_email` - `os.environ.get("SES_FROM_EMAIL", "")`
   - `ses_region` - `os.environ.get("SES_REGION", "us-west-2")`
   - Validation: if `ses_enabled` and not `ses_from_email`, raise `RuntimeError`

**Verification Checklist:**

- [x] All new variables load with correct defaults when env vars are unset
- [x] `captcha_enabled=true` without `TURNSTILE_SECRET_KEY` raises RuntimeError
- [x] `ses_enabled=true` without `SES_FROM_EMAIL` raises RuntimeError
- [x] `admin_enabled=true` without `auth_enabled=true` raises RuntimeError
- [x] Existing tests still pass (config imports do not break)

**Testing Instructions:**

Add tests to `tests/backend/unit/test_config_feature_flags.py` (existing file):

- Test `captcha_enabled` defaults to `false`
- Test `captcha_enabled=true` with missing secret raises RuntimeError
- Test `admin_enabled=true` with `auth_enabled=false` raises RuntimeError
- Test `ses_enabled=true` with missing `SES_FROM_EMAIL` raises RuntimeError
- Test `MODEL_DAILY_CAPS` dict has all 4 model names
- Test per-model cap defaults to 500

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_config_feature_flags.py -v`

**Commit Message Template:**

```text
feat(ops): add config vars for cost ceiling, CAPTCHA, SES, and admin flags

- Per-model daily cap env vars with 500 default
- CAPTCHA_ENABLED, SES_ENABLED, ADMIN_ENABLED feature flags
- Validation: admin requires auth, captcha requires secret, ses requires email
```

## Task 2: Per-Model Cost Ceiling Counters

**Goal:** Implement per-model daily generation counters in DynamoDB using the existing `_atomic_increment` pattern. Provide a `check_model_cap` function that returns whether a model is allowed to generate.

**Files to Create:**

- `backend/src/ops/__init__.py` - Empty init
- `backend/src/ops/model_counters.py` - Model counter logic

**Prerequisites:** Task 1 (config vars)

**Implementation Steps:**

1. Create `backend/src/ops/__init__.py` (empty file).
1. Create `backend/src/ops/model_counters.py` with a `ModelCounterService` class:
   - Constructor takes a `UserRepository` instance (dependency injection, same pattern as quota enforcement).
   - `increment_model_count(model_name: str, now: int) -> tuple[bool, dict]`: calls the public method `repo.increment_daily(user_id="model#<model_name>", window_seconds=86400, limit=config.MODEL_DAILY_CAPS[model_name], now=now)`. The `increment_daily` method (defined at `repository.py` line 192) is a public wrapper around `_atomic_increment` that uses counter `"dailyCount"` and window field `"dailyResetAt"` internally. Always use this public wrapper, never call `_atomic_increment` directly from outside `UserRepository`.
   - `get_model_counts(now: int) -> dict[str, dict]`: reads all 4 model counter items, returns `{model_name: {"dailyCount": N, "cap": M, "dailyResetAt": T}}`. Uses `repo.get_user("model#<name>")` for each.
   - `check_model_allowed(model_name: str, now: int) -> bool`: convenience; calls `increment_model_count` and returns the boolean.
1. The `increment_daily` method (which wraps `_atomic_increment`) handles `create_if_missing=True` by default, so the first call for a model name will create the item automatically.

**Verification Checklist:**

- [x] `check_model_allowed` returns True when under cap
- [x] `check_model_allowed` returns False when at cap
- [x] Counter resets after 24-hour window expires
- [x] `get_model_counts` returns data for all 4 models
- [x] Model counter items use `model#<name>` partition key

**Testing Instructions:**

Create `tests/backend/unit/test_model_counters.py`:

- Use moto `@mock_aws` decorator with a DynamoDB table fixture (same pattern as `test_user_repository.py`)
- Test increment under cap returns `(True, item)`
- Test increment at cap returns `(False, item)`
- Test window reset after 86400 seconds
- Test `get_model_counts` returns all 4 models with defaults when no items exist
- Test `check_model_allowed` convenience method

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_model_counters.py -v`

**Commit Message Template:**

```text
feat(ops): add per-model daily generation counters

- ModelCounterService with DynamoDB atomic increment
- model#<name> partition keys in existing users table
- 24h rolling window with configurable per-model caps
```

## Task 3: Account Suspension in User Repository

**Goal:** Add `isSuspended` boolean support to the user repository and integrate suspension checks into quota enforcement.

**Files to Modify:**

- `backend/src/users/repository.py` - Add `suspend_user`, `unsuspend_user`, `is_suspended` methods
- `backend/src/users/quota.py` - Add suspension check at top of `enforce_quota`
- `backend/src/utils/error_responses.py` - Add `account_suspended` error factory

**Prerequisites:** Task 1

**Implementation Steps:**

1. Add to `UserRepository`:
   - `suspend_user(user_id: str) -> None`: `UpdateItem` setting `isSuspended = true` and `updatedAt = now`.
   - `unsuspend_user(user_id: str) -> None`: `UpdateItem` setting `isSuspended = false` and `updatedAt = now`.
   - `is_suspended(user_id: str) -> bool`: `get_user` and check `item.get("isSuspended", False)`.
1. Add to `error_responses.py`:
   - `account_suspended() -> Dict[str, Any]`: returns error with code `ACCOUNT_SUSPENDED`, status 403, message "Your account has been suspended. Contact support for assistance."
1. Modify `enforce_quota` in `quota.py`. The full function signature is at line 29: `enforce_quota(ctx: TierContext, endpoint: Literal["generate", "refine"], repo: UserRepository, now: int) -> QuotaResult`. The first parameter is named `ctx` and is a `TierContext` instance (defined in `users/tier.py` line 20) with attributes `.tier` (Literal["guest", "free", "paid"]) and `.user_id` (str).
   - At the very top, after the `auth_enabled` short-circuit (lines 35-36 return early when `not config.auth_enabled`), add: if `ctx.tier != "guest"` and `repo.is_suspended(ctx.user_id)`, return `QuotaResult(allowed=False, reason="suspended", reset_at=0)`.
   - Do not check suspension for guests (they have no persistent user record to suspend).
1. Update `_parse_and_validate_request` in `lambda_function.py` to handle the new `"suspended"` reason: return `response(403, error_responses.account_suspended())`.

**Verification Checklist:**

- [ ] `suspend_user` sets `isSuspended=true` in DynamoDB
- [ ] `unsuspend_user` sets `isSuspended=false`
- [ ] `is_suspended` returns False for users without the field
- [ ] `enforce_quota` returns `allowed=False, reason="suspended"` for suspended users
- [ ] Suspended users get 403 on `/generate` and `/iterate`
- [ ] Unsuspending restores normal quota enforcement
- [ ] Guests are not affected by suspension logic

**Testing Instructions:**

Create `tests/backend/unit/test_suspension.py`:

- Test `suspend_user` + `is_suspended` round trip
- Test `unsuspend_user` clears suspension
- Test `is_suspended` returns False for user without field
- Test `enforce_quota` blocks suspended free user
- Test `enforce_quota` blocks suspended paid user
- Test `enforce_quota` allows unsuspended user
- Test guest tier skips suspension check

Add to existing `tests/backend/unit/test_error_responses.py`:

- Test `account_suspended()` returns correct error code and message

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_suspension.py tests/backend/unit/test_error_responses.py -v`

**Commit Message Template:**

```text
feat(ops): add account suspension with quota enforcement integration

- isSuspended field in DynamoDB user records
- Suspension check at top of enforce_quota
- 403 ACCOUNT_SUSPENDED error response
```

## Task 4: Integrate Model Cost Ceiling into Generation Flow

**Goal:** Wire the per-model cost ceiling into the `/generate` handler so capped models are skipped and the response indicates which models were blocked.

**Files to Modify:**

- `backend/src/lambda_function.py` - Modify `handle_generate` to check model caps before dispatching

**Prerequisites:** Task 2 (model counters), Task 3 (suspension)

**Implementation Steps:**

1. Import `ModelCounterService` in `lambda_function.py`.
1. Create a module-level `_model_counter_service = ModelCounterService(_user_repo)` (same pattern as other module-level services).
1. In `handle_generate`, after getting `enabled_models`, filter by cost ceiling:
   - For each model in `enabled_models`, call `_model_counter_service.check_model_allowed(model.name, int(time.time()))`.
   - Models that fail the check get added to results with `{"status": "skipped", "reason": "daily_cap_reached"}` instead of being dispatched.
   - Only models that pass the check are submitted to the thread pool.
1. If no models pass the cost ceiling check, return 429 with a new `model_cost_ceiling()` error response (add to `error_responses.py`).
1. The cost ceiling check runs only when `config.auth_enabled` is true (no point tracking model costs in open-source mode where there are no per-user quotas either). When `auth_enabled` is false, skip the model cap check entirely.

**Verification Checklist:**

- [ ] Models at daily cap are skipped with `status: "skipped"` in response
- [ ] Models under cap are dispatched normally
- [ ] All models capped returns 429 with `MODEL_COST_CEILING` error
- [ ] `auth_enabled=false` skips cost ceiling check entirely
- [ ] Successful generation increments the model counter

**Testing Instructions:**

Add tests to `tests/backend/unit/test_lambda_function.py` or create `tests/backend/unit/test_cost_ceiling_integration.py`:

- Mock `ModelCounterService.check_model_allowed` to return False for one model, True for others
- Verify skipped model appears in response with `status: "skipped"`
- Mock all models capped, verify 429 response
- Test with `auth_enabled=false`, verify no cap checks

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_cost_ceiling_integration.py -v`

**Commit Message Template:**

```text
feat(ops): integrate per-model cost ceiling into generation flow

- Capped models skipped with status "skipped" in response
- 429 MODEL_COST_CEILING when all models hit daily cap
- Cost ceiling bypassed when AUTH_ENABLED=false
```

## Task 5: Cloudflare Turnstile CAPTCHA Verification

**Goal:** Implement server-side Turnstile verification for guest `/generate` requests.

**Files to Create:**

- `backend/src/ops/captcha.py` - Turnstile verification logic

**Files to Modify:**

- `backend/src/lambda_function.py` - Add CAPTCHA check in `_parse_and_validate_request`
- `backend/src/utils/error_responses.py` - Add `captcha_failed` and `captcha_required` error factories

**Prerequisites:** Task 1 (config vars)

**Implementation Steps:**

1. Create `backend/src/ops/captcha.py`:
   - `verify_turnstile(token: str, remote_ip: str | None = None) -> bool`: POST to `https://challenges.cloudflare.com/turnstile/v0/siteverify` with `{"secret": config.turnstile_secret_key, "response": token}`. Optionally include `remoteip` if provided. Use `urllib.request` (stdlib, no new dependency). Return `True` if response JSON `success` is `True`, `False` otherwise. Catch network errors and return `False` (fail closed).
   - Set a 5-second timeout on the HTTP request.
1. Add to `error_responses.py`:
   - `captcha_required()`: error code `CAPTCHA_REQUIRED`, status 403, message "CAPTCHA verification required"
   - `captcha_failed()`: error code `CAPTCHA_FAILED`, status 403, message "CAPTCHA verification failed. Please try again."
1. Modify `_parse_and_validate_request` in `lambda_function.py`:
   - After tier resolution, before prompt extraction: if `config.captcha_enabled` and `tier_ctx.tier == "guest"` and `endpoint_kind == "generate"`:
     - Extract `captchaToken` from `body`
     - If missing, return `response(403, error_responses.captcha_required())`
     - Call `verify_turnstile(captchaToken, ip)`
     - If verification fails, return `response(403, error_responses.captcha_failed())`
   - Authenticated users and non-generate endpoints skip CAPTCHA entirely.

**Verification Checklist:**

- [ ] `verify_turnstile` returns True on successful verification
- [ ] `verify_turnstile` returns False on failed verification
- [ ] `verify_turnstile` returns False on network error (fail closed)
- [ ] Guest `/generate` without `captchaToken` returns 403 `CAPTCHA_REQUIRED` when enabled
- [ ] Guest `/generate` with invalid token returns 403 `CAPTCHA_FAILED` when enabled
- [ ] Authenticated users skip CAPTCHA
- [ ] `CAPTCHA_ENABLED=false` skips all CAPTCHA logic

**Testing Instructions:**

Create `tests/backend/unit/test_captcha.py`:

- Mock `urllib.request.urlopen` to return success JSON
- Mock `urllib.request.urlopen` to return failure JSON
- Mock `urllib.request.urlopen` to raise `URLError` (network failure), verify returns False
- Test 5-second timeout is set

Add CAPTCHA integration tests to `tests/backend/unit/test_lambda_function.py` or a new file:

- Test guest generate with valid CAPTCHA token (mock verification)
- Test guest generate without token returns 403
- Test guest generate with failed verification returns 403
- Test authenticated user generate skips CAPTCHA
- Test `CAPTCHA_ENABLED=false` skips CAPTCHA

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_captcha.py -v`

**Commit Message Template:**

```text
feat(captcha): add Cloudflare Turnstile verification for guest /generate

- Server-side token verification via Turnstile API
- CAPTCHA_REQUIRED/CAPTCHA_FAILED error responses
- Gated behind CAPTCHA_ENABLED feature flag
```

## Task 6: SAM Template Updates for Phase 1

**Goal:** Add new SAM parameters, environment variables, and IAM permissions for cost ceiling and CAPTCHA features.

**Files to Modify:**

- `backend/template.yaml` - Add parameters, env vars, Cognito admins group

**Prerequisites:** Tasks 1-5

**Implementation Steps:**

1. Add new Parameters section entries:
   - `CaptchaEnabled` (String, default "false", AllowedValues "true"/"false")
   - `TurnstileSecretKey` (String, NoEcho, default "")
   - `SesEnabled` (String, default "false", AllowedValues "true"/"false")
   - `SesFromEmail` (String, default "")
   - `SesRegion` (String, default "us-west-2")
   - `AdminEnabled` (String, default "false", AllowedValues "true"/"false")
   - `ModelGeminiDailyCap` (Number, default 500)
   - `ModelNovaDailyCap` (Number, default 500)
   - `ModelOpenaiDailyCap` (Number, default 500)
   - `ModelFireflyDailyCap` (Number, default 500)
1. Add environment variables to `PixelPromptFunction`:
   - Map all new parameters to their env var names
1. Add `AdminsGroup` Cognito resource (conditional on `AuthEnabledCondition`):

   ```yaml
   AdminsGroup:
     Type: AWS::Cognito::UserPoolGroup
     Condition: AuthEnabledCondition
     Properties:
       GroupName: admins
       UserPoolId: !Ref UserPool
       Description: Administrators with access to /admin endpoints
   ```

1. Add Parameter Groups in Metadata for the new parameters.

**Verification Checklist:**

- [ ] `sam build` succeeds with no errors
- [ ] All new parameters have sensible defaults
- [ ] `AdminsGroup` is conditional on `AuthEnabledCondition`
- [ ] New env vars appear in the Lambda environment

**Testing Instructions:**

Run `sam build` from `backend/` directory (do not deploy):

```bash
cd backend && sam build
```

Verify no errors in the build output.

**Commit Message Template:**

```text
chore(sam): add parameters for cost ceiling, CAPTCHA, SES, and admin

- Per-model daily cap parameters with 500 defaults
- CAPTCHA, SES, Admin feature flag parameters
- Cognito admins group resource (conditional)
```

## Task 7: Update .env.example and CLAUDE.md

**Goal:** Document all new environment variables in the backend .env.example and update CLAUDE.md with new config.

**Files to Modify:**

- `backend/.env.example` - Add new env vars with comments
- `CLAUDE.md` (repo root) - Add new env vars to the environment variables table

**Prerequisites:** Tasks 1-6

**Implementation Steps:**

1. Append to `backend/.env.example`:
   - Cost ceiling section with all 4 model cap vars
   - CAPTCHA section with `CAPTCHA_ENABLED` and `TURNSTILE_SECRET_KEY`
   - SES section with `SES_ENABLED`, `SES_FROM_EMAIL`, `SES_REGION`
   - Admin section with `ADMIN_ENABLED`
1. Update the Environment Variables tables in `CLAUDE.md` with new variables.

**Verification Checklist:**

- [ ] `.env.example` has all new vars with descriptive comments
- [ ] CLAUDE.md environment variables table includes all new vars
- [ ] Default values match what `config.py` uses

**Testing Instructions:**

No automated tests. Visual review that the documentation matches the code.

**Commit Message Template:**

```text
docs: add env vars for cost ceiling, CAPTCHA, SES, and admin features
```

## Phase Verification

After all 7 tasks are complete:

1. All existing tests pass: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
1. New tests pass: `PYTHONPATH=backend/src pytest tests/backend/unit/test_model_counters.py tests/backend/unit/test_suspension.py tests/backend/unit/test_captcha.py tests/backend/unit/test_config_feature_flags.py -v`
1. Ruff lint passes: `ruff check backend/src/`
1. SAM build succeeds: `cd backend && sam build`
1. With all feature flags set to `false` (default), the app behaves identically to before this phase
1. No changes to the frontend in this phase

## Known Limitations

- Per-model counters use DynamoDB Scans for the admin read path (Task 2 `get_model_counts`). Acceptable at current scale.
- CAPTCHA verification adds 50-100ms to guest `/generate`. This is acceptable.
- The cost ceiling check in `/generate` adds one DynamoDB read per enabled model (up to 4). At 10 concurrent Lambda invocations, this is approximately 40 DynamoDB reads per second during peak, well within on-demand capacity.
