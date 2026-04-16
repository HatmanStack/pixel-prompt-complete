# Feedback Log

## Active Feedback

<!-- Reviewers append new items here with Status: OPEN -->

## Resolved Feedback

<!-- Generators move resolved items here with a resolution note -->

### FB-6: Missing Download Route in SAM Template

- **Tag:** FINAL_REVIEW
- **Category:** Implementation-level
- **Phase/Task:** Phase 1, Task 1.5
- **Severity:** CRITICAL (blocks production deployment)
- **Status:** RESOLVED
- **Resolution:** Added `DownloadApi` event (`GET /download/{sessionId}/{model}/{iterationIndex}`) to the Lambda function events in `backend/template.yaml`, placed after the `PromptHistoryApi` event. Verified with `sam build`.

### FB-7: Test Isolation Bug Causes 9 Test Errors in Full Suite

- **Tag:** FINAL_REVIEW
- **Category:** Implementation-level
- **Phase/Task:** Phase 2, Task 2.4
- **Severity:** HIGH (blocks CI green status)
- **Status:** RESOLVED
- **Resolution:** Removed all module-level `mock_aws()` calls from `test_prompt_history.py`, `test_lambda_function.py`, and `test_prompt_adaptation.py`. Each file now uses per-test `mock_aws()` contexts inside fixtures, with `lambda_function` imported via a `_get_lambda_handler()` helper inside the mock context. Also fixed `test_route_stubs.py` (which had a module-level `from lambda_function import lambda_handler`) to defer the import inside per-test `mock_aws()` contexts. Fixed `test_cost_ceiling_integration.py` which was missing a `_user_repo` patch (causing SSO token errors against real AWS). Full suite now passes: 480 passed, 0 errors.

### FB-1: Hallucinated File in Task 1.6

- **Tag:** PLAN_REVIEW
- **Phase/Task:** Phase 1, Task 1.6
- **Status:** RESOLVED
- **Resolution:** Removed `test_gallery_payload.py` from the Files to Modify list and removed the corresponding instruction step, since the file does not exist. Gallery format tests are covered by the new `test_storage_refactor.py` tests in Tasks 1.1 and 1.4.

### FB-2: Task 2.2 Contains Contradictory Inline Revisions

- **Tag:** PLAN_REVIEW
- **Phase/Task:** Phase 2, Task 2.2
- **Status:** RESOLVED
- **Resolution:** Consolidated Task 2.2 into a single coherent instruction set. Added a design summary at the top of the implementation steps. Removed intermediate deliberation (the "Alternative (simpler)" and "Revised approach" sections). The final design is: `prompt` field = original user prompt, `adaptedPrompt` field = model-specific version, handler receives the adapted prompt, context window uses the original.

### FB-3: Phase 0 ADR-3 Contains Rejected Schema Approaches

- **Tag:** PLAN_REVIEW
- **Phase/Task:** Phase 0, ADR-3
- **Status:** RESOLVED
- **Resolution:** Removed the two rejected schema approaches (sort key change, encoded userId with Scan). ADR-3 now presents only the final GSI approach directly.

### FB-4: Task 3.2 Ambiguous "Add" for Test File That Does Not Exist

- **Tag:** PLAN_REVIEW
- **Phase/Task:** Phase 3, Task 3.2
- **Status:** RESOLVED
- **Resolution:** Changed "Add" to "Create" for `IterationCard.test.tsx` in Task 3.2 testing instructions.

### FB-5: Task 2.4 References validated.tier Without Null Guard

- **Tag:** PLAN_REVIEW
- **Phase/Task:** Phase 2, Task 2.4
- **Status:** RESOLVED
- **Resolution:** Updated the user_id determination to remove the unnecessary `validated.tier and` null guard. Added an inline note explaining that `validated.tier` is never None -- when `AUTH_ENABLED=false` it is a synthetic `_anon_tier()` with `is_authenticated=False`.
