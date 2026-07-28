# ADR 008: `POST /generate` Dispatches Asynchronously

## Status

Accepted

Source: ADR-A1 in `docs/plans/2026-07-26-audit-pixel-prompt/Phase-0.md`, revised
here to match what shipped. This is the one decision in this directory that was
made and implemented by the same plan, so where the plan and the code differ the
code is what is recorded.

## Context

API Gateway HTTP APIs cap the integration timeout at **30 seconds**, and the
quota is not adjustable. `/generate` dispatches four providers in parallel with
a budget of `API_CLIENT_TIMEOUT + 10` — 70 seconds at the shipped defaults —
against a 900-second Lambda timeout.

Four providers routinely exceed 29 seconds. The gateway returned `504` while the
Lambda ran to completion: generating images, writing S3, metering spend and
debiting credits for a request the caller had been told failed. The client then
retried the non-idempotent `POST` up to three more times.

Options considered:

1. **Shrink the dispatch budget under 30 seconds.** Rejected.
   `API_CLIENT_TIMEOUT` would have to drop to roughly 19s.
   `backend/src/utils/clients.py` derives Nova's Bedrock read timeout from the
   budget, so a 25s budget yields a ~5s read timeout and Nova fails on
   essentially every call. Firefly's four-call chain does not fit either. This
   trades an occasional 504 for a guaranteed provider failure.
1. **Return early and let the threads finish.** Rejected. Lambda freezes the
   execution environment when the handler returns. In-flight threads are
   suspended, not completed, and may resume mid-write on a later invocation.
1. **Move the work to SQS or Step Functions.** Rejected as disproportionate: a
   new queue, a new IAM surface and a second deployment artifact to move work
   from one invocation of this function to another invocation of the same
   function.
1. **Self-invoke asynchronously.** Chosen.

## Decision

`POST /generate` does everything that must precede the answer **in the request
path** — validate, resolve tier, enforce spend ceilings, CAPTCHA, the age gate
and quota, reserve per-model cost slots, create the session — then hands the
provider work to a second invocation of the same function with
`InvocationType="Event"` and returns **`202`** immediately:

```json
{
  "sessionId": "…",
  "prompt": "…",
  "models": { "gemini": { "status": "pending" }, "…": {} }
}
```

Skipped models keep their existing `{"status": "skipped", "reason": …}` shape,
because a skipped model never becomes a session iteration and this response is
the only place the daily-cap and admin-disable signals exist.

Three properties make it safe:

- **The worker payload is JSON-only.** It carries `sessionId`, `prompt`,
  `modelNames`, `skipped`, `visibility`, `tier`, `userId` and `correlationId`,
  and nothing derived from the HTTP event. The worker reconstructs a _minimal_
  `TierContext` whose `is_authenticated=False` is a placeholder, never an
  authorization input — the caller was already authorized in the request path.
- **Dispatch failure falls back to inline.** `_dispatch_generation_async`
  returns `False` on any failure — `AWS_LAMBDA_FUNCTION_NAME` absent, the
  `lambda:InvokeFunction` grant missing, the account throttling — and the
  handler runs the generation synchronously instead. A deploy whose IAM grant
  did not land degrades to the pre-async behaviour rather than to sessions that
  are created, answered `202`, and never worked on.
- **The worker never re-raises.** Every per-model failure is already recorded on
  the session, so raising would add an unexplained invocation error _and_ a
  platform-chosen retry that would generate and bill the images a second time.

**Escape hatch.** `GENERATE_ASYNC` (default `true`, SAM parameter
`GenerateAsync`) selects the behaviour. Set `false` and the handler runs
generation inline and returns `200` with the full session, exactly as before.
That keeps `sam local start-api` usable and lets `tests/backend/e2e/` — which
runs against MiniStack, where there is no Lambda service to invoke — exercise
the whole path in one process.

There is deliberately **no import-time assertion** that the budget fits under
the gateway ceiling. Synchronous mode necessarily violates that relationship at
the shipped defaults, and raising at config import would break exactly the test
modules that set the flag. The relationship is asserted by a parametrised unit
test over explicit `(api_client_timeout, generate_async)` pairs instead. A
constraint belonging to a deployed gateway should not fail closed in
environments that have no gateway.

**No frontend change was required.** `GenerationPanel` branches on
`response.session`; when it is absent it builds a placeholder session and hands
over to `useSessionPolling`, which polls `/status/{sessionId}` every 2s until
the session reaches a terminal status. That was already the path taken whenever
a session was not attached.

## Code Governed

- `backend/src/lambda_function.py` — `_dispatch_generation_async`,
  `run_generation`, the `source == "generate_worker"` branch in
  `lambda_handler`, and the `202` return in `handle_generate`
- `backend/src/config.py` — `generate_async`
- `backend/template.yaml` — the `GenerateAsync` parameter, the `GENERATE_ASYNC`
  environment variable, the `SelfInvokeForGeneration` IAM statement, and the
  explicit `TimeoutInMillis: 29000` on the routes that can do provider work
- `tests/backend/unit/test_generate_async_dispatch.py` — the `202` contract, the
  worker payload, the worker branch and the inline fallback
- `tests/backend/unit/test_dispatch_budget.py` — the declared integration
  timeouts, the budget-against-ceiling invariant, and the scope of the
  self-invoke grant

## Consequences

### Positive

- **The 504 is gone**, and with it the retry amplification that billed one user
  click as up to four dispatches.
- **The provider budget is bounded by the Lambda timeout, not the gateway.** The
  worker has 900s available, so `API_CLIENT_TIMEOUT` can be tuned for providers
  rather than for API Gateway.
- **The client already handled it**, so the contract change cost no frontend
  work and no migration window.

### Negative

- **`POST /generate` returns `202`, not `200`.** This is a breaking change for
  any non-browser client that asserts `200` or reads results from the generate
  response. `GENERATE_ASYNC=false` restores the old behaviour.
- **The worker holds one of the function's 10 reserved concurrent executions**
  for the duration of the dispatch. Splitting read routes onto a second function
  with its own reserved concurrency is recorded in
  [../follow-ups/2026-07-audit-deferred.md](../follow-ups/2026-07-audit-deferred.md).
- **Two code paths for one endpoint.** Synchronous mode is not dead code — E2E
  depends on it — but it is a second path that must keep working.

### Neutral

- `POST /generate` is still not idempotent. Retries are now restricted to
  idempotent methods client-side, which stops the amplification; a true
  idempotency key is a follow-up.
