# Phase 2: Email Notifications, Operational Metrics, Revenue Tracking

## Phase Goal

Build the notification and observability layer: Amazon SES email notifications triggered by Stripe webhook events and admin actions, CloudWatch custom metrics emitted from the hot path, a daily snapshot Lambda for historical data, and webhook-fed revenue aggregates. All gated behind feature flags.

**Success criteria:**

- Lifecycle emails (welcome, subscription activated/cancelled, payment failed) fire on webhook events when `SES_ENABLED=true`
- CloudWatch custom metrics emitted for request rate, error rate, and latency per model
- Daily snapshot Lambda writes `metrics#YYYY-MM-DD` items to DynamoDB
- Revenue counters updated atomically alongside webhook handlers
- All new code has unit tests passing at 80%+ coverage

**Estimated tokens:** ~35,000

## Prerequisites

- Phase 1 complete (config vars, model counters, suspension, CAPTCHA)
- All Phase 1 tests passing

## Task 1: SES Client and Email Sender

**Goal:** Create a cached SES client factory and a `send_email` function that respects the `SES_ENABLED` feature flag.

**Files to Create:**

- `backend/src/notifications/__init__.py` - Empty init
- `backend/src/notifications/ses_client.py` - Cached SES client factory
- `backend/src/notifications/sender.py` - `send_email` function

**Prerequisites:** Phase 1 Task 1 (config vars with `ses_enabled`, `ses_from_email`, `ses_region`)

**Implementation Steps:**

1. Create `backend/src/notifications/__init__.py` (empty file).
1. Create `backend/src/notifications/ses_client.py`:
   - Follow the pattern from `billing/stripe_client.py` (cached client).
   - `get_ses_client()` returns a `boto3.client("ses", region_name=config.ses_region)`. Cache at module level. Raise `RuntimeError` if `ses_enabled` is False.
1. Create `backend/src/notifications/sender.py`:
   - `send_email(to: str, subject: str, html_body: str, text_body: str) -> bool`: if not `config.ses_enabled`, return False (no-op). Otherwise, call `ses_client.send_email()` with `Source=config.ses_from_email`, `Destination={"ToAddresses": [to]}`, `Message` with both HTML and plain text. Wrap in try/except, log errors via `StructuredLogger`, return False on failure. Return True on success.
   - No retry logic; SES is fire-and-forget for notifications. Failures are logged but do not block the request.

**Verification Checklist:**

- [x] `get_ses_client()` returns cached boto3 SES client
- [x] `get_ses_client()` raises RuntimeError when `ses_enabled=false`
- [x] `send_email` returns False when `ses_enabled=false`
- [x] `send_email` returns True on successful SES call
- [x] `send_email` returns False and logs on SES error
- [x] `send_email` does not raise exceptions (fire-and-forget)

**Testing Instructions:**

Create `tests/backend/unit/test_ses_sender.py`:

- Use moto `@mock_aws` with SES mock (verify email identity first in test setup)
- Test `send_email` with `ses_enabled=true` delivers to SES
- Test `send_email` with `ses_enabled=false` returns False without calling SES
- Test `send_email` handles SES client error gracefully

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_ses_sender.py -v`

**Commit Message Template:**

```text
feat(notifications): add SES client and email sender with feature flag

- Cached SES client factory following stripe_client pattern
- Fire-and-forget send_email with error logging
- No-op when SES_ENABLED=false
```

## Task 2: Email Templates

**Goal:** Create HTML and plain-text email templates for lifecycle events and admin notices.

**Files to Create:**

- `backend/src/notifications/templates.py` - Template rendering functions

**Prerequisites:** Task 1

**Implementation Steps:**

1. Create `backend/src/notifications/templates.py` with functions that return `(subject, html_body, text_body)` tuples:
   - `welcome_email(email: str) -> tuple[str, str, str]`
   - `subscription_activated_email(email: str) -> tuple[str, str, str]`
   - `subscription_cancelled_email(email: str) -> tuple[str, str, str]`
   - `payment_failed_email(email: str) -> tuple[str, str, str]`
   - `suspension_notice_email(email: str, reason: str) -> tuple[str, str, str]`
   - `warning_email(email: str, message: str) -> tuple[str, str, str]`
   - `custom_email(email: str, subject: str, message: str) -> tuple[str, str, str]`
1. HTML templates should be minimal inline-styled HTML (no external CSS). Use a shared `_base_html(title, body_content)` helper that wraps content in a basic email layout.
1. Plain-text templates are the text-only equivalent of the HTML content.
1. Keep templates simple. No Jinja2 or external templating engine. Python f-strings are sufficient.

**Verification Checklist:**

- [x] Each template function returns a 3-tuple of (subject, html, text)
- [x] HTML output contains the email address or relevant parameters
- [x] Plain-text output is readable without HTML tags
- [x] All 7 template functions exist and are callable

**Testing Instructions:**

Create `tests/backend/unit/test_email_templates.py`:

- Test each template function returns a 3-tuple of strings
- Test HTML output contains expected content (email address, key phrases)
- Test plain-text output does not contain HTML tags
- Test `_base_html` wraps content in `<html>` tags

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_email_templates.py -v`

**Commit Message Template:**

```text
feat(notifications): add email templates for lifecycle and admin notices

- Welcome, subscription, payment, suspension, warning, custom templates
- HTML with inline styles + plain-text fallback
- No external templating dependency
```

## Task 3: Webhook Integration for Lifecycle Emails

**Goal:** Extend the existing Stripe webhook dispatch to send lifecycle emails when `SES_ENABLED=true`.

**Files to Modify:**

- `backend/src/billing/webhook.py` - Add email sends to existing dispatch handlers

**Prerequisites:** Tasks 1, 2

**Implementation Steps:**

1. Import `sender` and `templates` from `notifications`.
1. In each existing handler function, after the DynamoDB update succeeds, send the corresponding email if the user has an email address:
   - `_on_checkout_completed`: send `welcome_email` (look up email from `repo.get_user`)
   - `_on_subscription_upsert` where status is "active": send `subscription_activated_email`
   - `_on_subscription_deleted`: send `subscription_cancelled_email`
   - `_on_payment_failed`: send `payment_failed_email`
1. Email sends are fire-and-forget. If `send_email` returns False, log a warning but do not fail the webhook handler. The webhook must always return 200 to Stripe.
1. To get the user's email: call `repo.get_user(user_id)` (the user record was just updated, so this is fresh). If `email` is not in the record, skip the email send.

**Verification Checklist:**

- [ ] `_on_checkout_completed` sends welcome email when SES is enabled
- [ ] `_on_subscription_deleted` sends cancellation email
- [ ] `_on_payment_failed` sends payment failed warning
- [ ] Email failure does not cause webhook to return non-200
- [ ] No email sent when `ses_enabled=false`
- [ ] No email sent when user has no email address

**Testing Instructions:**

Update `tests/backend/unit/test_stripe_webhook.py`:

- Mock `notifications.sender.send_email` and verify it is called with correct template for each event type when `ses_enabled=true`
- Verify `send_email` is not called when `ses_enabled=false`
- Verify webhook still returns 200 even when `send_email` raises an exception

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_stripe_webhook.py -v`

**Commit Message Template:**

```text
feat(notifications): send lifecycle emails from Stripe webhook handlers

- Welcome email on checkout completed
- Cancellation email on subscription deleted
- Payment warning on invoice.payment_failed
- Fire-and-forget, gated behind SES_ENABLED
```

## Task 4: Revenue Tracking in Webhook Handlers

**Goal:** Extend webhook handlers to maintain running revenue counters in a `revenue#current` DynamoDB item.

**Files to Modify:**

- `backend/src/billing/webhook.py` - Add revenue counter updates
- `backend/src/users/repository.py` - Add revenue counter methods

**Prerequisites:** Phase 1 Task 1 (config vars)

**Implementation Steps:**

1. Add to `UserRepository`:
   - `increment_revenue_counter(field: str, delta: int) -> None`: `UpdateItem` on `userId="revenue#current"` using `ADD {field} :delta`. Create item if missing (use `if_not_exists` pattern). Also set `updatedAt`.
   - `decrement_revenue_counter(field: str, delta: int) -> None`: same but with negative delta.
   - `get_revenue() -> dict`: `get_user("revenue#current")`, return item or empty dict.
1. Update webhook handlers:
   - `_on_checkout_completed`: call `repo.increment_revenue_counter("activeSubscribers", 1)`. If `config.stripe_price_id` price amount is known, also increment `mrr` (but since we do not have the price amount in the webhook, skip MRR for now and let the daily snapshot handle it).
   - `_on_subscription_deleted`: call `repo.decrement_revenue_counter("activeSubscribers", 1)` and `repo.increment_revenue_counter("monthlyChurn", 1)`.
   - Simplification: track `activeSubscribers` and `monthlyChurn` counters only. MRR calculation is deferred to the admin dashboard (activeSubscribers * price, or fetched from Stripe API).
1. The `monthlyChurn` counter resets monthly. Use a `churnResetAt` window field with 30-day rolling window, or simply let the daily snapshot capture and reset it. For simplicity, do not auto-reset; let the daily snapshot copy and zero it.

**Verification Checklist:**

- [ ] `increment_revenue_counter` creates item if missing
- [ ] `increment_revenue_counter` atomically increments counter
- [ ] `_on_checkout_completed` increments `activeSubscribers`
- [ ] `_on_subscription_deleted` decrements `activeSubscribers` and increments `monthlyChurn`
- [ ] `get_revenue` returns current counters

**Testing Instructions:**

Add tests to `tests/backend/unit/test_revenue_tracking.py`:

- Use moto DynamoDB mock
- Test `increment_revenue_counter` creates item on first call
- Test `increment_revenue_counter` increments on subsequent calls
- Test `decrement_revenue_counter` decrements
- Test `get_revenue` returns current state

Update `tests/backend/unit/test_stripe_webhook.py`:

- Verify `increment_revenue_counter` called on checkout completed
- Verify `decrement_revenue_counter` called on subscription deleted

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_revenue_tracking.py tests/backend/unit/test_stripe_webhook.py -v`

**Commit Message Template:**

```text
feat(ops): add revenue tracking counters to webhook handlers

- revenue#current DynamoDB item with activeSubscribers, monthlyChurn
- Atomic increment/decrement on checkout and subscription events
- Revenue counter methods in UserRepository
```

## Task 5: CloudWatch Custom Metrics Emitter

**Goal:** Emit per-request operational metrics (request count, error count, latency) to CloudWatch from the Lambda hot path.

**Files to Create:**

- `backend/src/ops/metrics.py` - CloudWatch metrics emitter and daily snapshot handler

**Prerequisites:** Phase 1 Task 1 (config vars)

**Implementation Steps:**

1. Create `backend/src/ops/metrics.py`:
   - `emit_request_metric(endpoint: str, model: str | None, duration_ms: float, is_error: bool) -> None`: fire-and-forget `PutMetricData` to CloudWatch namespace `PixelPrompt/Operations`. Dimensions: `Endpoint`, `Model` (if applicable). Metrics: `RequestCount` (1), `ErrorCount` (1 if error, 0 otherwise), `Latency` (duration_ms, Unit=Milliseconds). Use boto3 CloudWatch client cached at module level.
   - Wrap the entire function body in try/except. Log errors but never raise. This must not break the request path.
   - Batch up to 20 metric data points per `PutMetricData` call (CloudWatch API limit). For simplicity, emit one call per request (max 3 metric values). Batching can be added later if throughput warrants it.
1. Add a module-level `_cw_client = None` with lazy initialization (avoid creating the client if metrics are never emitted).
1. Integrate into `lambda_function.py`:
   - In `handle_generate`, after all model results are collected, emit one metric per model with the model's duration and error status.
   - In `handle_iterate` and `handle_outpaint` (via `_handle_refinement`), emit one metric at the end with the endpoint name, model, duration, and error status.
   - Gate behind a simple check: only emit if `config.auth_enabled` (same gate as cost ceiling; no point tracking metrics in open-source mode).

**Verification Checklist:**

- [ ] `emit_request_metric` calls CloudWatch `PutMetricData`
- [ ] Metric namespace is `PixelPrompt/Operations`
- [ ] Dimensions include `Endpoint` and optionally `Model`
- [ ] Errors in metric emission do not propagate
- [ ] CloudWatch client is lazily initialized
- [ ] Metrics not emitted when `auth_enabled=false`

**Testing Instructions:**

Add tests to `tests/backend/unit/test_model_counters.py` or create a new `tests/backend/unit/test_cw_metrics.py`:

- Mock `boto3.client("cloudwatch")` and verify `put_metric_data` is called with correct namespace and dimensions
- Test error in `put_metric_data` does not raise
- Test lazy client initialization

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_cw_metrics.py -v`

**Commit Message Template:**

```text
feat(ops): add CloudWatch custom metrics for request tracking

- Fire-and-forget PutMetricData per request
- PixelPrompt/Operations namespace with Endpoint and Model dimensions
- Gated behind AUTH_ENABLED, errors suppressed
```

## Task 6: Daily Snapshot Lambda Handler

**Goal:** Create a scheduled handler that snapshots operational data into DynamoDB for historical tracking.

**Files to Modify/Create:**

- `backend/src/ops/metrics.py` - Add `handle_daily_snapshot` function
- `backend/template.yaml` - Add EventBridge scheduled rule and Lambda event

**Note:** The `template.yaml` changes in this task and Task 7 are cumulative on top of Phase 1 Task 6's SAM changes. The implementer should expect to see the parameters and environment variables already added by Phase 1 and build on top of them, not start from a clean template.

**Prerequisites:** Tasks 2 (model counters from Phase 1), 4 (revenue tracking), 5 (metrics module exists)

**Implementation Steps:**

1. Add `handle_daily_snapshot(event, context)` to `backend/src/ops/metrics.py`:
   - Compute today's date string: `YYYY-MM-DD`
   - Read all 4 model counter items from DynamoDB: `repo.get_user("model#<name>")` for each
   - Read `revenue#current` item
   - Scan the users table to count users by tier and suspended users. Use a full Scan with `Select="SPECIFIC_ATTRIBUTES"` projecting only `tier` and `isSuspended`. Paginate through all results. (Acceptable at current scale; see ADR-19.)
   - Write a `metrics#YYYY-MM-DD` item to DynamoDB with: `modelCounts` (map), `usersByTier` (map), `suspendedCount` (number), `revenue` (map), `createdAt` (epoch).
   - Use `put_item` with `ConditionExpression="attribute_not_exists(userId)"` so re-running the snapshot for the same day is idempotent.
   - Reset `monthlyChurn` in `revenue#current` to 0 on the first day of each month (check if today is day 1).
1. Add to `template.yaml`:
   - A new event source on `PixelPromptFunction` for the daily snapshot:

     ```yaml
     DailySnapshotSchedule:
       Type: Schedule
       Properties:
         Schedule: cron(0 0 * * ? *)
         Description: Daily operational metrics snapshot
         Enabled: true
         Input: '{"source": "scheduled", "action": "daily_snapshot"}'
     ```

   - In `lambda_handler`, detect the scheduled event by checking `event.get("source") == "scheduled"` and `event.get("action") == "daily_snapshot"`, then call `handle_daily_snapshot`.
1. Add IAM permission for CloudWatch `PutMetricData` in the Lambda policy (for Task 5 integration):

   ```yaml
   - Sid: CloudWatchPutMetrics
     Effect: Allow
     Action: cloudwatch:PutMetricData
     Resource: "*"
   ```

**Verification Checklist:**

- [ ] Snapshot writes `metrics#YYYY-MM-DD` item with model counts, user counts, revenue
- [ ] Snapshot is idempotent (re-running same day does not overwrite)
- [ ] Monthly churn counter resets on first of month
- [ ] EventBridge rule triggers at 00:00 UTC daily
- [ ] `lambda_handler` routes scheduled event to snapshot handler
- [ ] `sam build` succeeds with the new event source

**Testing Instructions:**

Create `tests/backend/unit/test_daily_snapshot.py`:

- Use moto DynamoDB mock with pre-populated model counters, user records, and revenue item
- Test snapshot creates `metrics#YYYY-MM-DD` item with correct aggregates
- Test snapshot is idempotent (second call does not overwrite)
- Test monthly churn reset on day 1
- Test scheduled event routing in `lambda_handler`

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_daily_snapshot.py -v`

**Commit Message Template:**

```text
feat(ops): add daily snapshot Lambda for operational metrics

- Snapshots model counts, user tiers, revenue to metrics#YYYY-MM-DD
- Idempotent write with conditional expression
- EventBridge cron rule at 00:00 UTC daily
- CloudWatch PutMetricData IAM permission
```

## Task 7: SAM Template Updates for Phase 2

**Goal:** Add SES IAM permissions and ensure all Phase 2 infrastructure is in the SAM template.

**Files to Modify:**

- `backend/template.yaml` - Add SES permissions

**Note:** Like Task 6, these `template.yaml` changes are cumulative. The template already contains Phase 1 Task 6's parameters and env vars, plus Task 6's EventBridge schedule and CloudWatch permission. This task adds SES permission on top of those existing changes.

**Prerequisites:** Tasks 1-6

**Implementation Steps:**

1. Add SES IAM permission to the Lambda policy:

   ```yaml
   - Sid: SesSendEmail
     Effect: Allow
     Action: ses:SendEmail
     Resource: "*"
   ```

   This is unconditional (harmless without SES_ENABLED). Scoping to a specific SES identity ARN is a production hardening step the operator can do manually.

1. Verify all new environment variables from Phase 1 Task 6 and Phase 2 are in the template.

**Verification Checklist:**

- [ ] `sam build` succeeds
- [ ] SES and CloudWatch permissions present in Lambda policy
- [ ] EventBridge schedule event is defined

**Testing Instructions:**

Run `sam build` from `backend/` directory.

**Commit Message Template:**

```text
chore(sam): add SES and CloudWatch IAM permissions

- ses:SendEmail for notification emails
- cloudwatch:PutMetricData for operational metrics
```

## Phase Verification

After all 7 tasks are complete:

1. All existing tests pass: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
1. New tests pass: `PYTHONPATH=backend/src pytest tests/backend/unit/test_ses_sender.py tests/backend/unit/test_email_templates.py tests/backend/unit/test_revenue_tracking.py tests/backend/unit/test_cw_metrics.py tests/backend/unit/test_daily_snapshot.py -v`
1. Ruff lint passes: `ruff check backend/src/`
1. SAM build succeeds: `cd backend && sam build`
1. With `SES_ENABLED=false`, no emails are sent and no SES calls are made
1. Webhook handlers still return 200 regardless of email send success/failure

## Known Limitations

- Email templates are basic inline HTML. No rich branding or image assets. Sufficient for v1.
- MRR is not tracked in real-time (only `activeSubscribers` count). MRR can be computed as `activeSubscribers * stripe_price_amount` in the admin dashboard.
- The daily snapshot does a full DynamoDB Scan. At 10,000+ users, this will need pagination optimization or a GSI. Acceptable for now per ADR-19.
- CloudWatch metrics are emitted one request at a time. Batching can be added if costs become a concern at high throughput.
