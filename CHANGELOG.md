# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Everything below has landed on `main` since the `v2.0.1` tag and is not yet
released. No tag has been created; that is the operator's call.

### Changed

- **BREAKING**: `POST /generate` returns **202** and dispatches asynchronously. The response carries `sessionId`, `prompt` and a `models` map whose dispatched entries are `pending`; clients poll `GET /status/{sessionId}` for results. API Gateway HTTP APIs cap the integration timeout at 30s and the quota is not adjustable, so four providers in parallel routinely returned 504 to a caller whose images were generated, stored and billed anyway. Set `GENERATE_ASYNC=false` to restore the previous synchronous `200` with the full session — the browser client needed no change either way, because it already polled when no session was attached
- **BREAKING**: `AUTH_ENABLED` must be set explicitly. `config.py` raises at import when it is unset and the SAM parameter has no default, so the choice appears in the deploy parameters instead of being assumed
- `AUTH_ENABLED` now gates **identity only**. Quota, per-model cost caps and spend metering apply in every configuration; with auth off, callers resolve to the `anon` tier and are metered against a hash of their source IP. "I have no Cognito" and "I want no spend limits" are unrelated statements and one flag should not assert both
- Client retries are restricted to idempotent methods, and `429` is no longer retryable (a rolling-window quota cannot succeed a second later, and each retry re-entered `enforce_quota`, issuing DynamoDB writes and inflating the rejection alarm). One user click could bill twelve provider calls
- Quota refunds now apply on the default configuration. `_refund_credits` became `_refund_usage` and decrements the tier counter when `CREDITS_ENABLED=false`, which is the default — previously the entire refund path was inert and a free user whose generation failed lost their hourly allowance
- Paid-tier generations are private; every other tier is public. Visibility is fixed at session creation and recorded on `status.json` alongside `ownerId`, and private objects are written under a prefix the CloudFront origin grant does not cover, so they have no unsigned URL at all
- `GLOBAL_DAILY_SPEND_CEILING_USD_MICROS` default lowered from $100/day to **$25/day**, and `ENHANCE_DAILY_SPEND_CEILING_USD_MICROS` from $5/day to **$2/day**
- `AGE_GATE_ENABLED` defaults **on** — the only flag in `config.py` that does. Google's API terms permit use only where the service is not "likely to be accessed by" under-18s, so the compliant behaviour is what an operator gets by doing nothing
- Every provider timeout is derived from the budget that binds the request. A hardcoded 60s made Firefly's four-call outpaint chain ~190s against a 70s budget
- `/enhance` timeout is clamped under the 29s gateway ceiling rather than merely defaulted, because a 30s enhance inside a 29s ceiling cannot succeed at its limit
- One `PutMetricData` call per generation instead of one per model
- `/gallery/list` no longer fans out one S3 LIST per gallery folder
- Session-lock round trips halved by reusing the ETag from the read that preceded the write
- CORS headers are built by a single helper shared by `lambda_function.response()` and the admin path, and the credentials header is omitted whenever the allowed origin is `*` — the combination the spec forbids. Admin rejections now carry CORS headers instead of reaching the browser as opaque failures
- Production builds no longer emit source maps (~3 MB of readable source) or the module-graph visualiser (~437 KB). `ANALYZE=true npm run build` still writes `dist/stats.html`
- ESLint now lints the TypeScript source — 149 files that the previous flat config matched none of
- `ruff check` covers `backend/src/`, `tests/` and `backend/scripts/`, and `ruff format --check backend/src/` is gated in CI
- Backend and frontend dependencies install from lockfiles in CI (`npm ci`, `backend/requirements-lock.txt`), and `make lock-check` fails on drift. The previous lockfile carried no `stripe` entry and a `pydantic-core` that did not match its `pydantic`
- Frontend coverage thresholds ratcheted to 72/65/75/73 statements/branches/functions/lines

### Added

- Stripe billing: checkout, customer portal, and a signature-verified webhook with per-event dedup claims, leased so a failed release cannot silently drop an event
- Stripe reconciliation script (`backend/scripts/`) and a `StripeCustomerIndex` reverse lookup, needed because real `customer.subscription.*` payloads carry no `userId`
- Credit ledger behind `CREDITS_ENABLED` (default `false`): `CREDITS_PER_GENERATE`, `CREDITS_PER_REFINE`, `CREDITS_PER_OUTPAINT`, `FREE_MONTHLY_CREDITS`, `PAID_MONTHLY_CREDITS`, `FREE_CREDIT_PERIOD_SECONDS`, `PAID_CREDIT_FALLBACK_PERIOD_SECONDS`, `PAID_PRICE_USD_CENTS`, `OVERAGE_USD_CENTS_PER_CREDIT`. `config.py` raises at import if any is non-positive while the flag is on
- Dollar-denominated spend metering in micro-dollars: a per-model, per-operation cost table (`COST_{GEMINI,NOVA,OPENAI,FIREFLY}_{GENERATE,REFINE,OUTPAINT}_USD_MICROS`, constructed dynamically so grep will not find them) plus `COST_ENHANCE_USD_MICROS`. Counting calls hid a ~4x difference between generate and refine and a ~2x difference between the cheapest and most expensive provider
- `MONTHLY_SPEND_CEILING_USD_MICROS` ($500), the bound that caps the invoice — a daily ceiling alone does not
- `ENHANCE_DAILY_SPEND_CEILING_USD_MICROS`, a sub-ceiling bounding the unauthenticated `/enhance` surface
- `backend/src/ops/store_breaker.py`: a per-container circuit breaker (`STORE_FAILURE_THRESHOLD`, `DEGRADED_DISPATCH_BUDGET`) that sheds `/generate` with 503 after N consecutive store failures. Six spend and quota guards fail open on a DynamoDB error, and every one of them reads the same table; this is the only bound that needs nothing from the dependency it exists to survive. With `ReservedConcurrentExecutions: 10` it bounds roughly ten containers, not the fleet
- CloudWatch alarms on daily spend, monthly spend, free-tier spend, quota-rejection spikes, provider errors and Lambda errors, each paging an SNS topic
- `GET /pricing`, serving prices from the backend so the displayed price is derived from Stripe rather than duplicated in the client
- `PAID_DAILY_GENERATE_LIMIT` — paid generation was previously unbounded, and `GET /me` now reports it, because a limit the user cannot see is a limit they experience as a bug
- `ANON_GENERATE_LIMIT`, `ANON_REFINE_LIMIT`, `ANON_WINDOW_SECONDS` — the meter for `AUTH_ENABLED=false` deployments
- `GUEST_IP_GENERATE_LIMIT`, `GUEST_IP_WINDOW_SECONDS` — guest quota bound to source IP as well as to the cookie, and persisted after CAPTCHA rather than before
- `AGE_GATE_ENABLED` and the `ageAffirmed` request field on `POST /generate`. A prior affirmation is remembered against the caller's identity, so the prompt appears once
- `GENERATE_ASYNC` (default `true`) and a `SelfInvokeForGeneration` IAM statement scoped to the function it is attached to
- `Retry-After` emitted as a real header on 429s, not only mirrored in the body
- ErrorBoundary crashes reported to `POST /log`, and a diagnostic screen instead of a blank page when the frontend is misconfigured
- Content-filter escape hatch, so the filter stops rejecting "blood orange"
- `docs/adr/003`-`008`, promoting six decisions that governed live code out of per-plan `Phase-0.md` files, plus `docs/adr/README.md`
- `docs/follow-ups/2026-07-audit-deferred.md`, recording every finding this remediation deliberately deferred, each with a retirement condition
- `.github/PULL_REQUEST_TEMPLATE.md`, which `CONTRIBUTING.md` had instructed contributors to fill out for months
- `make install`, `make check`, `make docs-lint`, `make lock-check` — every CI job now has a local equivalent, and `docs-lint` and `lock-check` are invoked by CI as the same targets rather than copies
- mypy in CI behind a shrinking per-module override list, and type-checking of the build configuration itself. `noUncheckedIndexedAccess` was attempted and deferred; `frontend/tsconfig.json` records the error count in a comment beside the disabled flag

### Fixed

- **Paid-tier generation, which failed on every request.** `ImageStorage` writes to a `private/` S3 prefix that the Lambda execution role had no grant for, so every paid generation returned AccessDenied. A test now reads `WRITTEN_PREFIXES` from the code and asserts the role in `template.yaml` grants exactly those — neither moto nor MiniStack enforces IAM, which is how it shipped
- **Client retries re-dispatching non-idempotent POSTs**, turning one 504 into four provider dispatches
- Two unguarded `resolve_tier` call sites that passed `GuestTokenService | None` into a parameter typed non-optional and dereferenced
- `enforce_quota` failing closed for some tiers and open for others; it now fails open for all, consistently with the spend and cap checks, and logs at ERROR so the gap is alarmable
- Guest refinement refused before any write, rather than after
- Per-IP counter buckets never expiring
- `scan_users` paging, and a bare `assert` used as a runtime check
- Revenue counter updates made atomic per webhook event
- Stripe cancellation handling, webhook item parsing, both subscription period shapes, and outpaint charged at its own rate
- `/enhance` returning the same string twice instead of two distinct prompts, making a second LLM call on the fallback path, and requesting JSON mode from a provider that does not support it
- Gemini's prompt part passed by keyword rather than position
- The provider-error alarm could never fire, and CloudWatch calls were unbounded
- Root-logger configuration shipping SDK INFO logs to CloudWatch
- The terminal raise in the retry decorator, and a race on the cached client factories
- `_LEET_MAP` in the content filter
- Four stale spend-ceiling figures in `config.py` comments that contradicted the code beside them
- `CLAUDE.md`, `README.md`, `CONTRIBUTING.md` and both `.env.example` templates reconciled with the code: 28 undocumented variables, an install path that taught the forbidden `pip`, coverage gates understated by up to 8 points, and a `utils/` rate limiter that had been deleted
- `docs/legal/README.md` described the 18+ requirement as unaddressed after the gate shipped

### Removed

- `docs/follow-ups/cost-ceiling.md`, which told the reader the tier system was the only runtime bound on spend and to brainstorm a feature that had shipped
- `scripts/deploy.sh`, which passed `ModelCount` and per-index model parameters that `template.yaml` has not declared since ADR 001 fixed the lineup at four models — it could not succeed. `npm run deploy` (`backend/scripts/deploy.js`) is the live entrypoint
- The unused `rate-limit/*` S3 grant on the Lambda role
- The `status_code` parameter that all 20 error-response factories passed and none of them used
- Unreachable backend branches, unreferenced frontend files and exports, and three coexisting component directory schemes collapsed into one
- `backend/uv.lock`, referenced nowhere, and `frontend/.npmrc`'s `legacy-peer-deps`, which nothing needed
- Two integration test files that had been silently skipped since they were written; their one uncovered assertion was ported and the correlation-id tests were replaced with stronger ones

### Security

- Pillow and two npm advisories patched; a clean `npm ci` reports 0 vulnerabilities

## [2.0.1] - 2026-04-18

> **Addendum, 2026-07-27.** This entry omitted the largest subsystems the
> release actually contained. Cognito authentication, the guest/free/paid tier
> system, the DynamoDB users table, Stripe checkout and webhooks, per-model
> daily cost caps, Cloudflare Turnstile CAPTCHA, the admin dashboard and SES
> notifications all landed between 2026-04-08 and 2026-04-12, before this tag.
> The bullets below are left as published; this note records what they left out.

### Added

- Firefly OAuth2 token caching with 50-minute TTL (saves ~500ms per request)
- Specific `ConnectionError` and `HTTPError` handling for OpenAI image downloads
- CORS wildcard warning when `AUTH_ENABLED=true` with `CORS_ALLOWED_ORIGIN=*`
- `ENHANCE_TIMEOUT` env var for configurable prompt enhancement timeout (default 30s)
- `_adapt_prompts_for_models` extraction with batch optimization docstring
- `atexit` shutdown handler for `ThreadPoolExecutor` instances
- Troubleshooting section in README
- Test coverage thresholds documented in CONTRIBUTING.md
- 5 gallery flow integration tests (previously skipped)
- Token caching, error handling, and resilience test suites

### Changed

- `API_CLIENT_TIMEOUT` default reduced from 120s to 60s (prevents Lambda timeout exhaustion)
- Frontend coverage thresholds raised from 45-52% to 52-60%
- `future.result()` calls now include timeout and individual try-catch (prevents cascading failures)
- Bare `except Exception: pass` replaced with explicit `StructuredLogger.warning` calls (2 locations)
- Enhance timeout values consolidated from hardcoded 10s/30s into single `ENHANCE_TIMEOUT` config

### Fixed

- CRITICAL: Unhandled `future.result()` exception during parallel model generation could crash entire `/generate` request
- README AI Models table listed wrong models (Flux/Recraft instead of Nova Canvas/Firefly)
- CLAUDE.md missing 7 API endpoints from documentation table
- CLAUDE.md frontend environment variables table had 3 phantom vars and 3 missing vars
- `frontend/.env.example` used port 5173 instead of 3000 (mismatched `vite.config.ts`)
- Stale comments referencing old model names (flux/recraft) in config.py and manager.py
- Missing `correlation_id` in PromptEnhancer warning logs

## [2.0.0] - 2026-04-07

### Added

- Amazon Nova Canvas provider (Bedrock, IAM auth)
- Adobe Firefly provider (Image5, OAuth2 client credentials)
- Per-provider module structure under `backend/src/models/providers/`
- Column focus/expand UI: clicking a model column animates to ~60% width with full controls; others compress to ~13%
- Shared frontend constants in `frontend/src/config/constants.ts` for iteration limits
- markdownlint config and docs lint job in CI
- `.devcontainer/` configuration with `uv`-based post-create script
- `bedrock:InvokeModel` IAM permission in SAM template
- `astral-sh/setup-uv` action in CI for backend dependency installs

### Changed

- BREAKING: Provider lineup changed from Flux/Recraft/Gemini/OpenAI to Gemini/Nova/OpenAI/Firefly
- Gemini updated to `gemini-3.1-flash-image-preview` (Nano Banana 2)
- OpenAI generation locked to DALL-E 3; iteration/outpaint use `gpt-image-1` (DALL-E 3 lacks `images.edit`)
- Gallery list/detail responses return CloudFront URLs instead of base64 (fixes Lambda 6MB overflow)
- Backend coverage gate raised from 60% to 80%
- mypy `disallow_untyped_defs = true` enabled in backend pyproject
- Provider enable flags now require credentials (gemini/openai/firefly disabled when keys missing)
- Dev dependencies pinned in `backend/pyproject.toml [project.optional-dependencies]`
- CLAUDE.md fully rewritten for the new provider lineup

### Fixed

- CRITICAL: Gallery list/detail responses exceeding Lambda 6MB payload limit
- CRITICAL: BFL polling threads blocking `ThreadPoolExecutor` (removed with Flux)
- Session ID validation missing on `/iterate` and `/outpaint`
- `/log` endpoint returning 500 for `ValueError` instead of 400
- `_load_source_image` making redundant S3 reads
- `_compute_session_status` precedence bug (pending statuses now take precedence over completed)
- `_error_result` not sanitizing string errors (only Exception)
- Checkbox click in `ModelColumn` bubbling to column focus toggle
- ministack GHA healthcheck always failing (image has no curl/wget)
- Docs lint job never running on markdown-only PRs

### Removed

- BREAKING: Flux/BFL provider (config, handlers, tests, SAM params)
- BREAKING: Recraft provider (config, handlers, tests, SAM params)
- `backend/src/models/handlers.py` (replaced by `providers/` package)
- Phantom env vars: `VITE_DEBUG`, `VITE_API_TIMEOUT`, unused `VITE_CLOUDFRONT_DOMAIN`/`VITE_S3_BUCKET`/`VITE_ENVIRONMENT`
- Stale `ModelRegistry` reference in ADR-001
- All `.jsx` test files (migrated to `.tsx`)
- Stale `frontend/src/fixtures/apiResponses.ts` referencing old job-based API

## [1.1.0] - 2026-03-16

### Added

- Changelog-driven release automation via GitHub Actions
- Request body size limits and log metadata sanitization
- S3 pagination for gallery listing endpoints
- Configurable CORS allowed origin via `CORS_ALLOWED_ORIGIN` env var
- Comprehensive environment variable reference in CLAUDE.md
- E2E test suite running against MiniStack in CI
- `.env.example` and `requirements-lock.txt` for reproducibility
- `LICENSE` file

### Changed

- Refactored `handle_iterate` and `handle_outpaint` into shared `_handle_refinement` dispatch
- Extracted shared request validation pipeline from all POST handlers
- Reuse cached SDK clients in `PromptEnhancer` instead of creating per-request
- Froze `ModelConfig` dataclass to prevent accidental mutation
- Increased `SessionManager` optimistic lock retries from 3 to 5 with jitter
- Migrated `test_context_manager` from MagicMock to moto S3

### Fixed

- Gallery listing returning session UUID folders mixed with image galleries
- Flaky E2E tests caused by optimistic locking contention during parallel generation
- Pending iteration leak when handler exceptions occurred after `add_iteration`
- `useEffect` exhaustive-deps violation in `GenerationPanel`
- Frontend `REQUEST_TIMEOUT` too low for long-running generation requests (now 180s)
- `handle_status` missing `session_id` validation
- Error messages leaking internal details to clients

### Removed

- Dead code: unused Bedrock, Stability, Imagen, and generic handlers
- Dead code: unused `types.py` module, `save_image`, `_generate_thumbnail`, `clear_context`
- Dead code: unused config variables and `is_model_enabled` function
- Dead IAM policy entries for `gallery/*` prefix in `template.yaml`
- No-op gallery handler and placeholder test assertion in frontend

## [1.0.0] - 2026-03-16

### Added

- Initial release of Pixel Prompt v2
- 4 fixed AI models (Flux, Recraft, Gemini, OpenAI) running in parallel
- Iterative refinement with rolling 3-iteration context window
- Outpainting to different aspect ratios (16:9, 9:16, 1:1, 4:3, expand_all)
- S3-based session management with optimistic locking
- Rate limiting (global hourly + per-IP daily)
- Gallery browser with CloudFront CDN delivery
- LLM-based prompt enhancement
- React + TypeScript frontend with Zustand state management
- E2E test suite with MiniStack
