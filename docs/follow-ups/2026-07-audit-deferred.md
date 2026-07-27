# Deferred: 2026-07 Audit Remediation

What the July 2026 audit remediation deliberately did **not** do, and what
retires each item.

Three audits ran against this repository on 2026-07-26 — a technical-debt
health audit, a 12-pillar staff evaluation and a documentation drift audit. The
resulting nine-phase plan
(`docs/plans/2026-07-26-audit-pixel-prompt/`) fixed most of what they found.
This file is everything it declined, plus the residual risks the phases
themselves recorded.

**Every entry carries a "Retire this section when" line.** That is the line the
document this file replaces did not have: `docs/follow-ups/cost-ceiling.md`
described work that shipped three months before anyone deleted it, and it
misdirected every reader in between. An entry with no retirement condition
becomes a permanent claim about a temporary state.

Keep this a single file. A directory of one-item files is how the previous
`docs/follow-ups/` ended up holding one stale document nobody revisited.

## Structure

### 1. Split `backend/src/lambda_function.py`

**Finding.** The module is ~1,900 lines and contains a 24-branch route
dispatcher (health findings H33 and H34, eval target 5). It is the structural
risk in the codebase.

**Why deferred.** It is the file that five of the nine phases modified.
Splitting it into `api/routes.py`, `api/middleware.py`, `api/generation.py` and
so on while those phases changed its behaviour would have made every one of
those diffs unreviewable, and a module split with no behaviour change closes no
finding on its own. **This is the top follow-up**, to be done as a standalone
PR with its own review. Phase 3 already cut the first seam by extracting
`run_generation()` out of `handle_generate`, which is the boundary the split
would follow.

**Retire this section when** the route dispatch, the request-validation
pipeline and the generation path live in separate modules, and
`lambda_function.py` is a thin entry point.

### 2. Split reserved concurrency across two functions

**Finding.** One Lambda serves every route with
`ReservedConcurrentExecutions: 10`. Since `/generate` became asynchronous
(`docs/adr/008-async-generate-dispatch.md`) the worker invocation holds one of
those ten for up to 70 seconds, so `/status` polls contend with generations.
Eval target 3.

**Why deferred.** It means duplicating a 73-entry environment block across two
`AWS::Serverless::Function` resources in a template that already declares 77
parameters, and the async change already removed the user-visible failure this
would improve.

**Retire this section when** read routes (`/status`, `/gallery/*`,
`/prompts/*`, `/me`) run on a second function with their own reserved
concurrency, or when the environment block is factored so that duplicating it
is not a maintenance hazard.

## Infrastructure and deployment

### 3. Narrow `ses:SendEmail` from `Resource: "*"`

**Finding.** The Lambda execution role grants `ses:SendEmail` on every identity
in the account (health finding H36).

**Why deferred.** Narrowing it needs the verified SES identity ARN, which is a
deploy-time value not available in the template without a new parameter. Small,
real, and better done with the operator present.

**Retire this section when** the statement's `Resource` is the verified
identity ARN, sourced from a SAM parameter.

### 4. Modernise the CloudFront distribution

**Finding.** The distribution uses a legacy origin access identity rather than
origin access control, `ForwardedValues` rather than cache and origin-request
policies, and carries no `ResponseHeadersPolicy` (no HSTS,
`X-Content-Type-Options`, CSP or `Referrer-Policy`), no access logging and no
WAF association. Health finding H39.

**Why deferred.** An OAI-to-OAC migration is a replace-in-place with a
cache-invalidation window. That is a deployment operation, not a remediation
change.

**Retire this section when** the distribution uses OAC, named cache and
origin-request policies, and a response-headers policy, with access logging on.

### 5. Add a frontend deploy target

**Finding.** There is no way to deploy the built frontend: no S3 sync, no
`Cache-Control` policy distinguishing content-hashed `assets/*` from
`index.html`, no CloudFront invalidation. Health finding H40.

**Why deferred.** This is a new deployment capability, not a fix to an existing
one. Phase 7 added the CI build, which is the prerequisite.

**Retire this section when** `make deploy-frontend` (or equivalent) syncs
`dist/` with per-path cache headers and invalidates the distribution.

### 6. Put `.github/workflows/ci.yml` in its own paths filter

**Finding.** A pull request that touches only the workflow file produces
`frontend == 'false'` and `backend == 'false'`, both jobs are skipped, and
`status-check` treats `skipped` as success. A change to the backend job's
environment block, install commands or lint scope therefore merges without that
job having run once. Raised in the Phase 7 review; pre-existing, and it makes
no gate inert.

**Why deferred.** Found during review of a phase that was already closing a
different half of the same problem, and it blocks nothing.

**Retire this section when** `- '.github/workflows/ci.yml'` appears under both
the `frontend` and `backend` outputs of the `changes` job.

### 7. Provider-side spend limits

**Finding.** Each provider offers a native spend cap — OpenAI usage limits,
Adobe Firefly quota, Gemini project budget alerts, AWS Budgets for Bedrock.
None is configured by this repository. Carried forward from
`docs/follow-ups/cost-ceiling.md`'s third candidate mitigation, which was the
only one of its three that had not shipped when that document was retired.

**Why deferred.** It is an operator action in four provider consoles, with no
code to write. Deferring it is not the same as it being unimportant: it is the
only bound that survives this service being wrong about everything.

**Retire this section when** each provider console has a spend cap configured
and the values are recorded in the deployment runbook.

### 8. An automated action on the spend alarm

**Finding.** The daily and monthly spend alarms page an SNS topic. Nothing acts
on them automatically. Eval target 2 asked for both halves.

**Why deferred.** An alarm action that automatically disables the service has a
blast radius a remediation plan should not choose on the operator's behalf. The
per-container circuit breaker (`backend/src/ops/store_breaker.py`, Phase 5)
delivers the other half of that finding — a bound that does not read DynamoDB.

**Retire this section when** the operator has decided what the alarm should do
and it does it.

## Data model and performance

### 9. A DynamoDB gallery index

**Finding.** `/gallery/list` performs one paginating S3 `LIST` over the whole
`sessions/` prefix — O(sessions), and it grows forever. Phase 4 removed the
unbounded per-folder fan-out but could not remove the top-level listing. Eval
target 3, and the open question left by
`docs/adr/002-s3-session-state.md`'s 2026-07-27 amendment.

**Why deferred.** Closing it properly means writing a gallery index row at
session creation, which is a schema change to the table
`docs/adr/003-dynamodb-single-table.md` describes.

**Retire this section when** `/gallery/list` is a DynamoDB `Query` against an
index written at session creation, and the S3 `LIST` is gone.

### 10. Collapse `_atomic_increment`'s three DynamoDB round trips

**Finding.** `UserRepository._atomic_increment` costs three round trips where
its docstring claimed one. Eval target 3. Phase 8 corrected the docstring so it
no longer claims otherwise; the round trips remain.

**Why deferred.** It is a rewrite of the reset-then-increment sequence in the
most correctness-sensitive helper in the repository, and every quota, cap and
guest counter runs through it.

**Retire this section when** the reset-and-increment is one conditional
`UpdateItem` and the tests that cover window rollover still pass.

## Product decisions

### 11. Resolve the two coexisting quota systems

**Finding.** Two systems answer "may this call proceed": the credit ledger
(`CREDITS_ENABLED`, default `false`) and rolling-window call counting. Both are
live code, both are configurable, and they meter different things. Eval target 8.

**Why deferred.** Which one is authoritative is a pricing decision, not a
cleanup. Phase 4 made refunds work on both paths so that neither is silently
broken in the meantime.

**Retire this section when** one system is the source of truth and the other is
deleted, not merely defaulted off. See
`docs/adr/004-ratelimiter-removed.md` for why "defaulted off but still present"
is the state this repository has already learned to distrust.

### 12. Gate `/enhance`

**Finding.** `/enhance` is unauthenticated and calls an LLM. It is bounded only
by `ENHANCE_DAILY_SPEND_CEILING_USD_MICROS` (~$2/day), which exists because the
endpoint is open. Eval target 8.

**Why deferred.** Gating it means deciding which tiers may enhance and adding a
quota bucket — a product decision with a visible UI consequence, since the
enhance control is shown to signed-out users. Phase 5 did clamp `ENHANCE_TIMEOUT`
under the gateway ceiling, because that was a correctness bug rather than a
product question.

**Retire this section when** `/enhance` consumes a quota bucket and the
sub-ceiling that exists to bound an open endpoint can be removed.

### 13. An idempotency key on `POST /generate`

**Finding.** `POST /generate` is not idempotent, and there is no key. Phase 2
stopped the client from retrying it, which is what made the amplification stop,
but a user who double-submits still fires two generations. ADR-A2.

**Why deferred.** A key requires a DynamoDB claim path and a change to the
request contract. It is the right long-term answer and it was not what made the
bleeding stop.

**Retire this section when** `POST /generate` accepts an idempotency key,
claims it before dispatch, and returns the original response for a repeat.

### 14. Wire the Stripe customer portal into the UI

**Finding.** `frontend/src/api/billing.ts` exports `openBillingPortal` and
`frontend/src/api/config.ts` exports `BILLING_ENABLED`; neither is referenced
anywhere in the frontend. `startCheckout` **is** wired, through
`components/tier/UpgradeModal.tsx`. So a user can subscribe in the app and
cannot manage or cancel the subscription in the app, although the backend route
(`POST /billing/portal`) exists and works.

**Why deferred.** Phase 1 found the unreferenced exports and left them rather
than deleting a working client for a working endpoint. Building the entry point
is UI work nobody scoped.

**Retire this section when** a signed-in paid user has an in-app control that
reaches `openBillingPortal`.

### 15. Render the paid generate counter

**Finding.** `GET /me` reports the paid daily generate counter
(`docs/adr/007-me-endpoint-contract.md`) and `QuotaIndicator` does not display
it. Raised in the Phase 4 review.

**Why deferred.** A product call about what the indicator shows, not a defect.

**Retire this section when** the indicator shows the counter that binds the
caller, on every tier.

## Declared correctness gaps

### 16. A dead `/generate` worker leaves the charge consumed — RESOLVED IN PART

**Resolved.** `handle_generate`'s outermost `except Exception` now calls
`_refund_usage` before returning 500. The double-refund this section warned
about is handled by a `refund_owned_downstream` flag set once `run_generation`
returns rather than by branching on `config.generate_async`: after that call
the refund decision is already made — refund on total failure, deliberately
none on a partial result — and the outer handler must not make it again. The
flag is the stronger form, because it also refunds a synchronous failure that
lands _before_ `run_generation`, which the `generate_async`-conditional form
proposed here would have missed. Both branches are covered by tests.

**What remains.** On the asynchronous path the caller already holds a `202`,
so there is no response left to attach a refund to. A worker that raises past
its own handler therefore leaves the charge consumed. `EventInvokeConfig`
(`MaximumRetryAttempts: 2`) covers the common case, a throttled delivery that
never ran; it does not cover a worker that runs and dies. Closing it needs a
compensating path — a reaper over sessions stuck in `in_progress`, or a DLQ
consumer that refunds — neither of which exists yet.

**Retire this section when** a session whose worker died has its charge
returned without operator action.

## Testing

### 17. Extend E2E coverage

**Finding.** The E2E suite covers 11 tests over the generation and gallery
paths. Tier resolution, quota exhaustion, guest-cookie issuance and the Stripe
webhook round trip are unit-tested only. Eval target 10.

**Why deferred.** It is a multi-day test-authoring project against a MiniStack
that provides S3 only — no DynamoDB, no Cognito, no Stripe — so each surface
needs a fake before it needs a test. The surfaces named are unit-tested at
~93% backend coverage.

**Retire this section when** those four flows are exercised end to end against
whatever local stack grows to support them.

### 18. Test against a deployed stack

**Finding.** Phase 7 removed the two `tests/backend/integration/` files, which
had been silently skipped since they were written because the `API_ENDPOINT`
they gated on was never set in CI. Their content was either already covered by
unit tests or ported. Nothing now tests a deployed stack.

**Why deferred.** A deployed-stack test needs a deployed stack, which needs
credentials and a target environment. No task in this plan required a live
cloud resource, deliberately.

**Retire this section when** a smoke suite runs against a real deployment,
gated so that its absence is visible rather than silent — which is the specific
failure the deleted files had.

## Tooling

### 19. Standardise the frontend export convention

**Finding.** `knip` reports ~45 unused exports, dominated by an
`export const X` + `export default X` pattern applied across ~25 components.
Both forms are consumed somewhere in the tree, so removing either touches ~25
components and their tests. ADR-A5.

**Why deferred.** A codebase-wide mechanical change belongs in its own PR with
its own review, and it delivers no behavioural gain. `knip` is not wired into
CI and no config was added for it either — dead config is what this plan was
removing.

**Retire this section when** components export one way, and `knip` reports only
findings that mean something.

### 20. Widen the ruff rule set

**Finding.** `ruff` selects `["E", "F", "W", "I"]`. Eval target 9 asks for
`ARG` (unused arguments) and `ERA` (commented-out code). `ruff format --check`
also covers `backend/src/` only, not `tests/`. ADR-A6.

**Why deferred.** Phase 6 widened the _scope_ of `ruff check` to the whole
Python tree in the same release; adding rule families at the same time would
have landed an unknown number of findings in the change that widened the scope.
Formatting 65 test files produces a diff no reviewer will read.

**Retire this section when** `ARG` and `ERA` are in `select` with the findings
cleared, and `ruff format --check tests/` is either gated or explicitly
declined in writing.

### 21. Frontend type strictness

**Finding.** `noUncheckedIndexedAccess` was attempted on 2026-07-27 and
deferred: **59 errors** (16 in `src`, 43 in tests) against ADR-A10's threshold
of 30. `frontend/tsconfig.json` records the count beside the disabled flag.
`exactOptionalPropertyTypes` was not attempted at all — it interacts with
React's prop spreading in ways that produce large mechanical churn.

**Why deferred.** Both were bounded by a documented threshold that the measured
count exceeded. Neither was silenced with `any`: there are zero `any` in
`frontend/src`, and that is worth more than either flag.

**Retire this section when** both flags are on, or the comment in
`frontend/tsconfig.json` explains why they never will be.

### 22. Empty the mypy override list

**Finding.** `mypy` runs in CI behind a per-module `[[tool.mypy.overrides]]`
list in `backend/pyproject.toml`. That is the design — a gate that runs beats a
strict config that does not — and the list is a ratchet: modules come off it,
never onto it.

**Not a blanket ignore.** No entry uses `ignore_errors`. Each names the error
codes that module reports today via `disable_error_code`, so a **new** class of
error in a listed module still fails the build. ADR-A3 planned
`ignore_errors = true`; Phase 6 shipped something stricter, and
`backend/pyproject.toml:56-60` records why. Do not read this entry as saying
the listed modules are unchecked.

**Why deferred.** By construction. Fixing all of it before adding the gate
would have delayed the gate that prevents regression.

**Retire this section when** the override list is empty and the block is
deleted from `backend/pyproject.toml`.

### 23. `make check` does not detect npm lockfile drift

**Finding.** CI runs `npm ci`, so it detects a `package.json` /
`package-lock.json` disagreement. `make check` does not. The Python side has
`make lock-check` for exactly this.

**Why deferred.** Eval target 7 scoped the drift check to Python only, so
nothing was dropped — this is an asymmetry, not a gap that was created.

**Retire this section when** `make check` fails on npm lockfile drift the way
it already fails on Python lockfile drift.

## Small items, for whenever the file is next open

These are each a line or two. None justifies a commit on its own.

1. `backend/pyproject.toml`'s `api.enhance` override comment says "15 errors";
   the measured figure is 14. Every other per-module count is correct.
1. Nothing pins `config.paid_daily_generate_limit == 50`, although
   `test_config_feature_flags.py` pins its sibling `paid_daily_limit == 200`.
   `config.py`, `.env.example` and `template.yaml` agree today and could drift
   silently. One line beside the existing assertion.
1. `--passWithNoTests` appears in `make test`'s vitest line and not in CI's. A
   flag difference in a target whose stated goal is command-for-command
   equality; immaterial in practice, because the coverage floors fail on an
   empty run anyway.
1. `make e2e-up` reports the MiniStack container unhealthy on first start and
   exits non-zero while the container becomes healthy seconds later. The suite
   then passes against it. The CI e2e job polls the health endpoint itself and
   is unaffected.
1. Frontend coverage has no per-file floor. Phase 6 recorded this as a decision
   rather than an oversight: nine files sit at 0%.

## Consciously not listed

Three items appear in the phases' "Known limitations" sections and are **not**
follow-ups, because they are the design rather than a shortfall:

- **The content filter is a keyword filter.** Phase 5 made the module honest
  about being one rather than pretending to more.
- **The ~20 remaining `console.error` sites report nowhere.** Deliberate:
  Phase 5 wired the `ErrorBoundary` to `POST /log`, which is the surface that
  catches what a user sees. Reporting every console site would be log volume
  without a reader.
- **The store breaker is per container.** With
  `ReservedConcurrentExecutions: 10` it bounds roughly ten containers' worth of
  degraded dispatch, not the fleet. A global breaker would need the store that
  is failing. Stated in the module docstring and accepted as the strongest
  thing available without the dependency that is down.

Documentation prevention tooling — link checkers, doc-generation scripts, new
markdownlint rules — is also not listed. The documentation audit set
`prevention_scope: none`, and a committed script that nothing runs is the next
stale artifact.
