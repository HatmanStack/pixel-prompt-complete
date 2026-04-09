# Phase 1: Infrastructure and Config Scaffolding

## Phase Goal

Land all infrastructure definitions (SAM template resources, IAM, API routes) and `config.py` additions so that subsequent phases can import the new env vars and target the new resources without touching infrastructure. No runtime behavior changes in this phase — the new routes return 501 placeholders.

**Success criteria:**

- `sam build` succeeds locally.
- `ruff check backend/src/` passes.
- `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes (existing tests untouched).
- With `AUTH_ENABLED=false` and `BILLING_ENABLED=false`, `lambda_function.py` behaves identically to pre-phase. `test_lambda_function_smoke.py` (if present) still passes.

**Token estimate:** ~35k

## Prerequisites

- Read `Phase-0.md` in full.
- Read `/home/christophergalliart/projects/pixel-prompt-complete/backend/template.yaml` to understand the existing resource graph.
- Read `/home/christophergalliart/projects/pixel-prompt-complete/backend/src/config.py` to understand the env-var loading pattern.

## Task 1.1: Add Feature Flags and Tier Env Vars to config.py

### Goal

Introduce all new env-var constants in `config.py`, delete old rate-limit constants, and add a feature-flag validity check.

### Files to Modify

- `backend/src/config.py`

### Implementation Steps

1. Add imports if needed (`os` already imported).
1. Add feature-flag loading near the top, after `aws_region`:

    ```python
    auth_enabled = os.environ.get("AUTH_ENABLED", "false").lower() == "true"
    billing_enabled = os.environ.get("BILLING_ENABLED", "false").lower() == "true"
    if billing_enabled and not auth_enabled:
        raise RuntimeError("BILLING_ENABLED=true requires AUTH_ENABLED=true")
    ```

1. Add Cognito constants: `cognito_user_pool_id`, `cognito_user_pool_client_id`, `cognito_domain`, `cognito_region` (all `os.environ.get(..., "")`).
1. Add DynamoDB constant: `users_table_name = os.environ.get("USERS_TABLE_NAME", "pixel-prompt-users")`.
1. Add guest tracking constants: `guest_token_secret`, `guest_generate_limit` (`_safe_int("GUEST_GENERATE_LIMIT", 1)`), `guest_window_seconds` (`_safe_int("GUEST_WINDOW_SECONDS", 3600)`), `guest_global_limit` (`_safe_int("GUEST_GLOBAL_LIMIT", 5)`), `guest_global_window_seconds` (`_safe_int("GUEST_GLOBAL_WINDOW_SECONDS", 3600)`).
1. Add free-tier constants: `free_generate_limit` (default 1), `free_refine_limit` (default 2), `free_window_seconds` (default 3600).
1. Add paid-tier constants: `paid_daily_limit` (default 200), `paid_window_seconds` (default 86400).
1. Add Stripe constants: `stripe_secret_key`, `stripe_webhook_secret`, `stripe_price_id`, `stripe_success_url`, `stripe_cancel_url`, `stripe_portal_return_url` (all `os.environ.get(..., "")`).
1. **Delete** `global_limit`, `ip_limit`, `ip_include_str`, `ip_include`.

### Verification Checklist

- [x] `ruff check backend/src/config.py` passes.
- [x] `python -c "import sys; sys.path.insert(0,'backend/src'); import config"` succeeds with default env.
- [x] `BILLING_ENABLED=true AUTH_ENABLED=false python -c "..."` raises `RuntimeError`.

### Testing Instructions

Add `tests/backend/unit/test_config_feature_flags.py`:

- Test default flags are both `False`.
- Test `AUTH_ENABLED=true` alone is valid.
- Test `BILLING_ENABLED=true` without auth raises `RuntimeError` (use `monkeypatch.setenv` + `importlib.reload`).
- Test each quota env var parses correctly and falls back to its default on invalid input.

### Commit Message Template

```text
feat(config): add tier feature flags and quota env vars

Introduces AUTH_ENABLED / BILLING_ENABLED, Cognito + Stripe config,
guest / free / paid quota knobs. Removes GLOBAL_LIMIT / IP_LIMIT /
IP_INCLUDE in preparation for the tier-based quota layer.
```

## Task 1.2: Update lambda_function.py to Unblock Removed Config

### Goal

`config.py` no longer exports `global_limit`, `ip_limit`, `ip_include`. Update `lambda_function.py` imports so the module still loads. The `RateLimiter` still runs — we temporarily hard-code its old defaults inline — until Phase 2 deletes it. This keeps Phase 1 a pure infra phase.

### Files to Modify

- `backend/src/lambda_function.py`

### Implementation Steps

1. Remove `global_limit`, `ip_limit`, `ip_include` from the `from config import (...)` block.
1. Replace the `RateLimiter(s3_client, s3_bucket, global_limit, ip_limit, ip_include)` line with `RateLimiter(s3_client, s3_bucket, 1000, 50, [])`. Leave an inline comment: `# Transitional: rate_limit.py is deleted in Phase 2`.

### Verification Checklist

- [x] `ruff check backend/src/lambda_function.py` passes.
- [x] Existing lambda tests pass.

### Commit Message Template

```text
refactor(lambda): decouple from removed rate-limit config

Transitional step — RateLimiter is pinned to inline defaults so
config.py can drop GLOBAL_LIMIT / IP_LIMIT / IP_INCLUDE without
breaking import. The limiter itself is removed in Phase 2.
```

## Task 1.3: Add DynamoDB users Table to SAM Template

### Goal

Define `AWS::DynamoDB::Table` for the users table with TTL enabled and on-demand billing. Grant the Lambda IAM role CRUD permissions.

### Files to Modify

- `backend/template.yaml`

### Implementation Steps

1. Under `Resources`, add a new `UsersTable` resource:

    ```yaml
    UsersTable:
      Type: AWS::DynamoDB::Table
      Properties:
        TableName: !Ref UsersTableName
        BillingMode: PAY_PER_REQUEST
        AttributeDefinitions:
          - AttributeName: userId
            AttributeType: S
        KeySchema:
          - AttributeName: userId
            KeyType: HASH
        TimeToLiveSpecification:
          AttributeName: ttl
          Enabled: true
    ```

1. Add a SAM parameter `UsersTableName` with default `pixel-prompt-users`.
1. In the Lambda function `Policies` list, add a `DynamoDBCrudPolicy` scoped to `!Ref UsersTable`.
1. Pass the table name as a Lambda env var: `USERS_TABLE_NAME: !Ref UsersTable`.

### Verification Checklist

- [x] `sam build` succeeds.
- [x] `sam validate --lint` (if available) passes.
- [x] Grep template for `UsersTable` — appears in Resources, Policies, Environment.

### Commit Message Template

```text
chore(sam): add DynamoDB users table for tier state
```

## Task 1.4: Add Cognito User Pool and Hosted UI

### Goal

Define Cognito User Pool, User Pool Client, and User Pool Domain so the frontend has a working Hosted UI endpoint.

### Files to Modify

- `backend/template.yaml`

### Implementation Steps

1. Add SAM parameters `CognitoDomainPrefix` (required, no default), `CognitoCallbackUrl` (required), `CognitoLogoutUrl` (required).
1. Add resources:

    ```yaml
    UserPool:
      Type: AWS::Cognito::UserPool
      Properties:
        UserPoolName: !Sub "${AWS::StackName}-users"
        AutoVerifiedAttributes: [email]
        UsernameAttributes: [email]
        Policies:
          PasswordPolicy:
            MinimumLength: 10
            RequireLowercase: true
            RequireNumbers: true
            RequireSymbols: false
            RequireUppercase: true

    UserPoolClient:
      Type: AWS::Cognito::UserPoolClient
      Properties:
        UserPoolId: !Ref UserPool
        ClientName: !Sub "${AWS::StackName}-web"
        GenerateSecret: false
        AllowedOAuthFlows: [code]
        AllowedOAuthScopes: [openid, email, profile]
        AllowedOAuthFlowsUserPoolClient: true
        CallbackURLs: [!Ref CognitoCallbackUrl]
        LogoutURLs: [!Ref CognitoLogoutUrl]
        SupportedIdentityProviders: [COGNITO]

    UserPoolDomain:
      Type: AWS::Cognito::UserPoolDomain
      Properties:
        Domain: !Ref CognitoDomainPrefix
        UserPoolId: !Ref UserPool
    ```

1. Add outputs for `UserPoolId`, `UserPoolClientId`, `UserPoolDomain` so deployers can wire the frontend.
1. Pass as Lambda env vars: `COGNITO_USER_POOL_ID`, `COGNITO_USER_POOL_CLIENT_ID`, `COGNITO_DOMAIN`, `COGNITO_REGION: !Ref AWS::Region`.

### Verification Checklist

- [x] `sam build` succeeds.
- [x] Outputs exported for UserPoolId, ClientId, Domain.
- [x] Lambda env vars include all four Cognito values.

### Commit Message Template

```text
chore(sam): add Cognito user pool and hosted UI
```

## Task 1.5: Add JWT Authorizer and New API Routes

### Goal

Add an HttpApi JWT authorizer wired to the new Cognito pool, attach it to `/iterate`, `/outpaint`, `/me`, `/billing/checkout`, `/billing/portal`. Add `/stripe/webhook` as unauthenticated.

### Files to Modify

- `backend/template.yaml`

### Implementation Steps

1. On the existing `HttpApi` resource, add an `Auth` block:

    ```yaml
    Auth:
      Authorizers:
        CognitoJwt:
          JwtConfiguration:
            issuer: !Sub "https://cognito-idp.${AWS::Region}.amazonaws.com/${UserPool}"
            audience:
              - !Ref UserPoolClient
          IdentitySource: "$request.header.Authorization"
    ```

    Do **not** set `DefaultAuthorizer` — we want per-route opt-in.

1. For each route in the `Events` block of the Lambda function that maps to `/iterate`, `/outpaint`, add `Auth: { Authorizer: CognitoJwt }`. Confirmed via inspection of `backend/template.yaml`: routes are already defined as explicit `HttpApi` events (not an `ANY /{proxy+}` catch-all), so no route splitting is required — only add the `Auth` block to the existing `/iterate` and `/outpaint` event entries.
1. Add new explicit `Events` entries: `GetMe` (`GET /me`, `Authorizer: CognitoJwt`), `PostBillingCheckout`, `PostBillingPortal`, `PostStripeWebhook` (no authorizer).

### Verification Checklist

- [x] `sam build` succeeds.
- [x] All five protected routes reference `CognitoJwt`.
- [x] `/stripe/webhook` route has no authorizer.
- [x] `/generate` is still unauthenticated.

### Commit Message Template

```text
chore(sam): add JWT authorizer and billing routes
```

## Task 1.6: Add Route Stubs in lambda_function.py

### Goal

Register the four new routes so API Gateway requests return `501 Not Implemented` with a clear error message. Business logic lands in Phases 2 and 3.

### Files to Modify

- `backend/src/lambda_function.py`

### Implementation Steps

1. In `lambda_handler`'s route table, add branches for `GET /me`, `POST /billing/checkout`, `POST /billing/portal`, `POST /stripe/webhook`.
1. Each stub calls a new module-local function `_not_implemented(endpoint: str)` that returns `response(501, {"error": f"{endpoint} not implemented"})`.
1. No imports of the new `auth/`, `billing/`, `users/` modules yet — those arrive in Phases 2 and 3.

### Verification Checklist

- [x] Routes appear in the dispatch table in `lambda_handler`.
- [x] Sending a request to each returns 501 in a unit test.

### Testing Instructions

Add `tests/backend/unit/test_route_stubs.py` with one parameterized test per new route verifying status code 501 and error body.

### Commit Message Template

```text
feat(lambda): stub /me, /billing/*, /stripe/webhook routes
```

## Task 1.7: Update backend/.env.example

### Goal

Document every new env var in `backend/.env.example` with a one-line comment. Remove stale rate-limit vars.

### Files to Modify

- `backend/.env.example`

### Implementation Steps

1. Delete the `GLOBAL_LIMIT`, `IP_LIMIT`, `IP_INCLUDE` block.
1. Add a new section `# Tier system (Phase 2026-04-08-paid-tier)` containing every env var listed in `Phase-0.md` under "New Environment Variables", each with a short comment.

### Verification Checklist

- [x] `grep -E "GLOBAL_LIMIT|IP_LIMIT|IP_INCLUDE" backend/.env.example` returns nothing.
- [x] All vars from Phase-0 appear.

### Commit Message Template

```text
docs(env): document tier-system environment variables
```

## Phase Verification

- [x] All 7 tasks committed.
- [x] `ruff check backend/src/` passes.
- [x] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes.
- [x] `cd backend && sam build` succeeds.
- [x] With both feature flags unset, `/generate` and `/iterate` still work exactly as before in unit tests.
- [x] `/me`, `/billing/*`, `/stripe/webhook` return 501.
- [x] No references to `global_limit` / `ip_limit` / `ip_include` remain in `backend/src/`.
