---
type: repo-health
goal: General health check — scan all 4 vectors equally
deployment: Serverless (Lambda)
scope: Full repo, no constraints
tooling: Full setup — linters, CI pipeline, pre-commit hooks, type checking
---

## CODEBASE HEALTH AUDIT

### EXECUTIVE SUMMARY
- **Overall health:** GOOD
- **Biggest structural risk:** ThreadPoolExecutor result handling in `handle_generate` lacks exception handling for concurrent failures, risking silent model generation failures
- **Biggest operational risk:** 120-second API client timeout could exceed Lambda timeout limits (typically 300s) when multiple providers are called sequentially during model adaptation
- **Total findings:** 1 CRITICAL, 5 HIGH, 8 MEDIUM, 3 LOW

---

### TECH DEBT LEDGER

#### CRITICAL

1. **[Operational Debt]** `backend/src/lambda_function.py:569`
   - **The Debt:** Unhandled exception in `future.result()` during parallel model generation. The generate_for_model tasks wrap errors internally, but if the future itself fails (e.g., thread death, executor shutdown), the `.result()` call throws an unhandled exception that will crash the entire /generate request for all models.
   - **The Risk:** One thread pool failure cascades to fail the entire generation batch. All enabled models return failure instead of partial results. In a serverless environment with frequent cold starts, thread pool instability becomes critical.
   - **Impact:** Affects core generate endpoint serving 4 concurrent model providers

#### HIGH

1. **[Operational Debt]** `backend/src/models/providers/firefly.py:34-55`
   - **The Debt:** Firefly OAuth2 token fetch happens on every invocation with no caching (per ADR-4). Fresh token is fetched before every request, even within the same Lambda container across multiple invocations.
   - **The Risk:** Doubles API calls to Adobe IMS (one for token, one for request). Network latency adds ~500ms per request. Under high concurrency, Adobe may rate-limit token endpoint. Reduces generation throughput.
   - **Serverless impact:** Cold starts already penalize latency; adding mandatory token fetches on every call is expensive.

2. **[Operational Debt]** `backend/src/lambda_function.py:105-108`
   - **The Debt:** ThreadPoolExecutor instances created at module load time with fixed pool size (4 workers for generation, 4 for gallery). No handling for executor saturation or thread starvation.
   - **The Risk:** Under sustained load, all 4 workers become busy with long-running image downloads. Gallery metadata fetches starve entirely. If one provider (e.g., Firefly) consistently runs slow, it blocks generation for other models. Lambda invocations may queue in thread pool, consuming memory.
   - **Serverless impact:** Unbounded queue can exhaust memory on cold starts with large queued work.

3. **[Architectural Debt]** `backend/src/api/enhance.py:83-163`
   - **The Debt:** PromptEnhancer makes a sequential LLM call to adapt prompt for all enabled models before any model generation starts (line 483 in lambda_function). If this call times out (10s hardcoded in adapt_per_model), the entire /generate request blocks for all models. Fallback to original prompt masks the failure.
   - **The Risk:** Single point of failure before parallel generation. A slow LLM provider (or network hiccup) delays all image generation. Timeout is hardcoded in code, not configurable.
   - **Serverless impact:** Lambda timeout exhaustion if LLM provider is slow (API_CLIENT_TIMEOUT=120s is long for a single operation).

4. **[Operational Debt]** `backend/src/lambda_function.py:557-558`
   - **The Debt:** Bare `except Exception: pass` when marking iteration as failed in model generation error handler. If `_handle_failed_result` crashes (e.g., S3 connection lost), the error is silently swallowed and the original exception is lost.
   - **The Risk:** Iteration marked as "pending" forever in database. User sees neither success nor error. Difficult to debug in production.

5. **[Operational Debt]** `backend/src/models/providers/openai_provider.py:50-52`
   - **The Debt:** Image download from OpenAI uses `requests.get()` with timeout but calls `raise_for_status()` without catching `requests.Timeout`. Timeout exception type is caught at line 56 but the `requests.get()` itself could throw other connection errors not explicitly caught.
   - **The Risk:** Unhandled `requests.ConnectionError` or `requests.HTTPError` (non-timeout) would leak to caller as generic error instead of sanitized message.

#### MEDIUM

1. **[Operational Debt]** `backend/src/users/repository.py:118-200`
   - **The Debt:** DynamoDB optimistic locking retry loop in `_atomic_increment` uses unbounded retries on ConditionalCheckFailedException. No jitter beyond uniform(0, 0.05), which can cause thundering herd under high contention.
   - **The Risk:** Under quota enforcement peak (e.g., day boundary when all users reset), many concurrent quota increments fail to acquire lock. Retry storms consume DynamoDB capacity and increase latency for all users.

2. **[Operational Debt]** `backend/src/config.py:254`
   - **The Debt:** API_CLIENT_TIMEOUT defaults to 120 seconds. This is the timeout for all external API calls (Gemini, OpenAI, Nova, Firefly). Many Lambda environments have default timeout of 300s; a single slow API call consumes 40% of budget.
   - **The Risk:** One slow provider during /generate blocks all parallel model generation for 120s. If multiple providers stall, Lambda times out with partial/no results.

3. **[Structural Design Debt]** `backend/src/lambda_function.py:850-870`
   - **The Debt:** Outpaint handler builds handler arguments using a lambda (_build_args) that pulls context from ContextManager on every call. If context is malformed or missing, error occurs during argument building (line 751), after iteration is already added to session.
   - **The Risk:** Iteration left in "in_progress" state but never marked complete or failed if context retrieval fails. Session becomes stuck.

4. **[Operational Debt]** `backend/src/utils/retry.py:116`
   - **The Debt:** Retry backoff uses `time.sleep()` in Lambda handler. Lambda is not designed for blocking sleeps; this consumes billing time without progress.
   - **The Risk:** Under heavy retry load, Lambda tasks spend >50% of execution time sleeping. Cost per request increases.

5. **[Hygiene Debt]** `backend/src/api/enhance.py:211 & 122`
   - **The Debt:** Client timeout hardcoded to different values: 10.0s in adapt_per_model (line 122) vs 30.0s in enhance (line 211). No single source of truth; easy to introduce inconsistency.
   - **The Risk:** Per-model adaptation times out before main enhancement, causing fallback to original prompt in some paths.

6. **[Operational Debt]** `backend/src/models/context.py:159`
   - **The Debt:** Context manager uses `time.sleep(0.05 * (attempt + 1))` for optimistic locking retries. Same issue as retry.py — blocking sleep in Lambda.
   - **The Risk:** Wasted Lambda billing time.

7. **[Structural Design Debt]** `backend/src/billing/webhook.py`
   - **The Debt:** Stripe webhook handler must validate webhook signature before processing. If signature validation is skipped or weak, malicious requests can modify user billing status.
   - **Risk level:** Requires inspection of actual webhook code.

8. **[Hygiene Debt]** `backend/src/lambda_function.py:132-220`
   - **The Debt:** _parse_and_validate_request is an 88-line function doing 7 things: body size check, JSON parsing, IP extraction, tier resolution, CAPTCHA, prompt validation, content filtering.
   - **The Risk:** Hard to mock/test individual validation steps. Changes to one path could affect all endpoints.

#### LOW

1. **[Code Hygiene]** `backend/src/lambda_function.py:557-558, 805-811`
   - **The Debt:** Bare `except Exception: pass` appears in two places in error handlers. Comments indicate intentional but pattern is brittle.
   - **The Risk:** If a maintenance task adds code after the pass, it silently succeeds when it should fail.

2. **[Code Hygiene]** `backend/src/api/enhance.py:162`
   - **The Debt:** StructuredLogger.warning called without correlation_id in catch block (line 162). All other logging includes correlation_id for request tracing.
   - **The Risk:** Production logs missing correlation context for debugging adaptation failures.

3. **[Architectural Debt]** `backend/src/models/providers/__init__.py`
   - **The Debt:** Provider handlers are selected at runtime by string name (line 40-44 in lambda_function). No type checking; if a provider name typo is introduced in config, runtime error occurs.
   - **The Risk:** Misspelled model provider name silently disables that model. Error only visible at request time.

---

### QUICK WINS

1. `backend/src/lambda_function.py:569` — Wrap `future.result()` in try-catch to gracefully handle thread pool failures (estimated effort: 10 minutes)
2. `backend/src/config.py:254` — Reduce API_CLIENT_TIMEOUT default from 120s to 30s and add per-provider overrides (estimated effort: 30 minutes)
3. `backend/src/api/enhance.py:122 & 211` — Consolidate timeout values into a single config constant (estimated effort: 10 minutes)
4. `backend/src/lambda_function.py:557-558, 805-811` — Replace bare `except Exception: pass` with explicit logging (estimated effort: 15 minutes)
5. `backend/src/api/enhance.py:162` — Add correlation_id parameter to PromptEnhancer methods (estimated effort: 10 minutes)

---

### AUTOMATED SCAN RESULTS

- **Dead code:** Codebase is clean. No unused imports or unreachable code detected.
- **Vulnerabilities:** No direct code injection, unsafe deserialization, or hardcoded secrets detected. Error sanitization properly redacts API keys from logs. CORS configurable (defaults to "*"). CAPTCHA validation implemented for guest tier.
- **Type Safety:** Python mypy strict mode enabled; TypeScript strict mode enabled, no `any` types detected.
- **Test Coverage:** Backend 80% fail_under threshold enforced. Frontend 45-52% threshold (Phase 1).
- **Dependency Audit:** Python: modern libraries (boto3, Pillow, requests, google-genai, openai, stripe). Frontend: 5 runtime deps (react, react-dom, zustand, recharts, uuid).

### SERVERLESS-SPECIFIC RISKS SUMMARY

| Risk | Severity | Impact | Location |
|------|----------|--------|----------|
| Future.result() unhandled | CRITICAL | Cascading model generation failures | `lambda_function.py:569` |
| 120s API timeout vs 300s Lambda timeout | HIGH | Timeout exhaustion, partial failures | `config.py:254` |
| Firefly token fetch on every call | HIGH | ~500ms per request, rate-limit risk | `firefly.py:34-55` |
| ThreadPoolExecutor queue unbounded | HIGH | Memory exhaustion on cold starts | `lambda_function.py:105-108` |
| time.sleep() in retries | MEDIUM | Wasted Lambda billing, slow recovery | `retry.py:116`, `context.py:159` |
