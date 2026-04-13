# Feedback Tracker

## Active Feedback

(none)

## Resolved Feedback

### CODE_REVIEW - Phase 2 - 2026-04-12

#### Issue 1: Missing subscription_activated_email in _on_subscription_upsert

Phase-2 Task 3 spec states:

> `_on_subscription_upsert` where status is "active": send `subscription_activated_email`

The `_on_checkout_completed` handler sends `welcome_email`, `_on_subscription_deleted` sends `subscription_cancelled_email`, and `_on_payment_failed` sends `payment_failed_email`. But `_on_subscription_upsert` (at `backend/src/billing/webhook.py` line 97) does not call `_send_lifecycle_email` with `email_templates.subscription_activated_email` when the subscription status is "active".

The `subscription_activated_email` template exists in `backend/src/notifications/templates.py` (line 58) and is tested in `test_email_templates.py`, but it is never actually used anywhere in the codebase.

There is also no corresponding test in `test_stripe_webhook.py` verifying that `customer.subscription.created` or `customer.subscription.updated` with status "active" sends the subscription activated email.

- Could `_on_subscription_upsert` send `subscription_activated_email` when `status` is `"active"`, as specified in Task 3 step 2?
- Could a test in `test_stripe_webhook.py` verify this behavior?

**Resolution:** Added `_send_lifecycle_email(repo, user_id, email_templates.subscription_activated_email)` call in `_on_subscription_upsert` when `status == "active"` (after the `set_tier` call, matching the pattern used by other handlers). Added two tests in `test_stripe_webhook.py`: `test_subscription_upsert_active_sends_activated_email` verifies the email is sent for active status, and `test_subscription_upsert_non_active_skips_email` verifies no email is sent for non-active statuses (e.g., `past_due`). All 372 backend unit tests pass.

### PLAN_REVIEW - 2026-04-12

#### Critical Issues (Must Fix)

1. **Hallucinated File -- `backend/src/auth/claims.py`**: Phase 0 (New Backend Modules), Phase 1 Task 3 (step 4 references `_parse_and_validate_request` handling a `"suspended"` reason, which is fine), and Phase 3 Task 1 all say "Modify `backend/src/auth/claims.py`" to add `require_admin`, `extract_admin_groups`, and `is_admin`. This file does not exist on disk. The `auth/` directory contains only `__init__.py` and `guest_token.py`. The `extract_claims` function that the plan references actually lives in `backend/src/users/tier.py`. Phase 3 Task 1 must say "Create `backend/src/auth/claims.py`" (not "Modify"), and the instructions must note that `extract_claims` is imported from `users/tier.py`, not from `auth/claims.py`.

   **Resolution:** Fixed across all three locations. Phase-0 New Backend Modules section now says "CREATE new file" and notes the import relationship. Phase-0 ADR-15 now says "a new file to be created" and documents the import from `users.tier`. Phase-3 Task 1 now says "Create `backend/src/auth/claims.py` (new file)" with an explicit import instruction: `from users.tier import extract_claims`, and notes the function is defined at `backend/src/users/tier.py` line 31.

1. **Phase 1 Task 3 references `backend/src/users/quota.py` method `enforce_quota` with `ctx.tier` and `ctx.user_id` fields**: The plan says to insert a suspension check "after the `auth_enabled` short-circuit" inside `enforce_quota`. The implementer needs to know the exact parameter name for the tier context object. Verify that `enforce_quota` receives a `TierContext` with `.tier` and `.user_id` attributes, or document the correct attribute names. Currently the plan says `ctx` but the function signature may use a different name. This is borderline -- an engineer reading the source will figure it out, but it would be clearer if the plan said "read the current parameter names from `quota.py` line 29+".

   **Resolution:** Verified against source. The function signature at `quota.py` line 29 is `enforce_quota(ctx: TierContext, endpoint: Literal["generate", "refine"], repo: UserRepository, now: int) -> QuotaResult`. The parameter is indeed named `ctx` and `TierContext` (defined at `users/tier.py` line 20) has `.tier` (Literal["guest", "free", "paid"]) and `.user_id` (str). Updated Phase-1 Task 3 step 3 to include the full function signature, line number, parameter types, and the exact lines where the `auth_enabled` short-circuit occurs (lines 35-36).

1. **Phase 1 success criteria says "CAPTCHA widget is Phase 4 adjacent but the backend verification lands here"**: However, the CAPTCHA widget is actually in Phase 4 Task 8, not in a separate Phase 4-adjacent location. This is not wrong, just confusingly worded. The real issue is that Phase 4 Task 8 (CAPTCHA widget) modifies `frontend/src/components/generation/GenerationPanel.tsx` but does not specify what the generate request payload looks like or where the `captchaToken` is added to the API call. The plan should reference the specific API client function or store action that builds the `/generate` request body, so the implementer knows where to add the `captchaToken` field.

   **Resolution:** Two changes made. (1) Phase-1 phase goal wording clarified to say "The CAPTCHA frontend widget is built in Phase 4 Task 8; this phase implements only the backend verification." (2) Phase-4 Task 8 step 2 now explicitly identifies both files: `generateSession` in `frontend/src/api/client.ts` at line 194 (the function that builds the POST body, currently `JSON.stringify({ prompt })`), and the call site in `GenerationPanel.tsx` at line 190. Includes the exact current signature, the updated signature with optional `captchaToken`, and step-by-step instructions for modifying the call site.

#### Non-Critical Issues (Should Fix)

1. **Phase 3 Task 1 step 1 says `extract_admin_groups` should handle `cognito:groups` as a string like `"[admins, editors]"`**: This is an unusual format. Cognito JWT `cognito:groups` is typically a JSON array claim, not a bracketed string. The plan should clarify that this is a defensive measure for edge cases, or correct the expected format to match what API Gateway's JWT authorizer actually passes through (`event.requestContext.authorizer.jwt.claims`). The claim value in that path is a string representation of the list, so handling both is reasonable, but the plan should state this explicitly as the reason.

   **Resolution:** Phase-3 Task 1 step 1 now explicitly explains why both formats are handled: "API Gateway's HttpApi JWT authorizer (which reads claims from `event.requestContext.authorizer.jwt.claims`) serializes JSON array claims into their string form, e.g., `"[admins, editors]"`. This is a defensive measure: handle both string format (strip brackets, split on comma, strip whitespace from each element) and native list format (in case future API Gateway versions pass the array directly)."

1. **Phase 2 Task 4 mentions `_on_subscription_upsert` handler**: Phase 2 Task 3 also references `_on_subscription_upsert` and `_on_subscription_deleted`. The plan should verify these are the actual function names in `backend/src/billing/webhook.py`. If the existing code uses different names (e.g., `_handle_subscription_updated`, `_handle_subscription_deleted`), the implementer will be confused.

   **Resolution:** Verified against source. The actual function names in `backend/src/billing/webhook.py` are `_on_subscription_upsert` (line 75) and `_on_subscription_deleted` (line 90), registered in the `_DISPATCH` dict at lines 114-120 for events `customer.subscription.created`, `customer.subscription.updated`, and `customer.subscription.deleted`. The plan already uses the correct names. No changes needed.

1. **Phase 4 Task 3 creates `frontend/src/pages/Admin.tsx`**: The existing pages directory contains only `BillingSuccess.tsx`, `BillingCancel.tsx`, and `AuthCallback.tsx`. This is a "Create" operation, which is correctly labeled. However, the task says to check "if user is admin (read from auth store or `/me` response)" but does not specify which store or how the admin status is determined on the frontend. The `/me` endpoint response schema is not documented in this plan. The implementer needs to know whether the `/me` response already includes a `groups` or `isAdmin` field, or whether this plan needs to add it.

   **Resolution:** Phase-4 Task 3 now includes a detailed "Required backend change" section that explains: (1) `handle_me` (line 905) does not currently include admin info, (2) the exact import and code addition needed (`from auth.claims import extract_admin_groups`, add `"groups": extract_admin_groups(event)` to the response dict), (3) the complete updated `/me` response schema showing the new `groups` field, and (4) how the frontend should read the `groups` array from the response and store it in the auth store.

1. **Phase 3 Task 4 introduces runtime model disable via DynamoDB `config#model#<name>` items**: This runtime disable check must be integrated into `handle_generate` in `lambda_function.py`, but the task says this only in prose. Phase 1 Task 4 already modifies `handle_generate` to add cost ceiling checks. Phase 3 Task 4 should explicitly state it modifies `lambda_function.py` in its "Files to Modify" section (it is currently only listed under Phase 3 Task 6 for route registration).

   **Resolution:** Phase-3 Task 4 "Files to Modify" section now explicitly lists `backend/src/lambda_function.py` with the note: "Add runtime disable check in `handle_generate` before dispatching models (this file is also modified in Phase 1 Task 4 for cost ceiling; the runtime disable check is an additional guard that runs alongside the cost ceiling check)."

#### Suggestions

1. **Phase 0 ADR-11 `_atomic_increment` with `create_if_missing=True`**: The plan says Phase 1 Task 2 will call `repo._atomic_increment` (a private method) from `ModelCounterService`. Calling a private method from outside the class is a code smell. Consider adding a public method to `UserRepository` or documenting why the private method access is acceptable.

   **Resolution:** The plan already intended to use the public `increment_daily` method (which wraps `_atomic_increment`), but the ADR-11 wording was ambiguous. Updated Phase-0 ADR-11 and Phase-1 Task 2 to explicitly state: "Always call `increment_daily`, never call `_atomic_increment` directly from outside `UserRepository`." The `increment_daily` public method (defined at `repository.py` line 192) already provides the correct interface with `create_if_missing=True` by default.

1. **Phase 2 Task 6 overlaps with Phase 1 Task 6**: Both tasks modify `backend/template.yaml`. Phase 1 Task 6 adds the Cognito admins group and all new parameters. Phase 2 Task 6 and Task 7 add SES and CloudWatch permissions. This is fine for ordering, but the plan should note that the SAM template changes are cumulative and the implementer should not expect a clean diff -- they are building on top of Phase 1's changes.

   **Resolution:** Phase-2 Task 6 already had a cumulative note (added during initial plan creation). Added an equivalent note to Phase-2 Task 7: "Like Task 6, these `template.yaml` changes are cumulative. The template already contains Phase 1 Task 6's parameters and env vars, plus Task 6's EventBridge schedule and CloudWatch permission. This task adds SES permission on top of those existing changes."
