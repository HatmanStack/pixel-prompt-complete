# Phase 2: Backend Prompt Adaptation and Prompt History

## Phase Goal

Add per-model prompt adaptation to the generation pipeline and build the prompt history system (per-user records + global recent feed) with DynamoDB storage and new API endpoints.

**Success criteria:**

- `/generate` automatically adapts the user's prompt per model via a single LLM call
- Adapted prompts are stored per-iteration in `status.json` and returned via `/status`
- Prompt history is written to DynamoDB on each `/generate` call
- `GET /prompts/history` returns per-user prompt history (auth required)
- `GET /prompts/recent` returns the global recent feed (no auth required)
- All new code has tests, coverage stays above 80%
- `ruff check backend/src/` clean

**Token estimate:** ~40,000

## Prerequisites

- Phase 1 complete (storage refactor landed)
- `moto` installed in dev dependencies

## Task 2.1: Add Per-Model Prompt Adaptation to PromptEnhancer

### Goal

Add an `adapt_per_model()` method to `PromptEnhancer` that makes a single LLM call and returns a dict mapping model names to adapted prompt strings.

### Files to Modify

- `backend/src/api/enhance.py` -- Add `adapt_per_model()` method

### Implementation Steps

1. Add a new class attribute `adaptation_system_prompt` to `PromptEnhancer.__init__()` (after `self.system_prompt` at line 48). This prompt instructs the LLM to:
   - Take a user's image generation prompt
   - Return a JSON object with keys for each requested model
   - Tailor each variant to the model's strengths:
     - **Gemini**: strong at photorealism, natural scenes, complex multi-element compositions
     - **Nova Canvas**: artistic styles, illustrations, stylized imagery
     - **DALL-E 3 (OpenAI)**: precise composition, typography, literal interpretation of instructions
     - **Firefly**: clean commercial imagery, product photography, design assets
   - Keep the core intent identical across all variants
   - Each variant should be 2-4 sentences
   - Return ONLY the JSON object, no markdown formatting or explanation

   Example system prompt structure:

   ```text
   You are an expert at optimizing image generation prompts for specific AI models.
   Given a user's prompt, produce a JSON object with model-specific variants.
   Keys must match exactly: {model_keys}.
   Each variant should be 2-4 sentences tailored to the model's strengths.
   ...model descriptions...
   Return ONLY valid JSON. No markdown, no explanation.
   ```

1. Add method `adapt_per_model(self, prompt: str, enabled_models: list[str]) -> dict[str, str]`:
   - If `self.prompt_model` is None, return `{m: prompt for m in enabled_models}` (no LLM configured)
   - Build the system prompt with `model_keys` set to the enabled model names
   - Make the LLM call using the same provider branching as `enhance()` (Gemini or OpenAI)
   - Set a 10-second timeout on the call (override the default client timeout)
   - Parse the response text as JSON
   - Validate that the result is a dict with string values
   - For any enabled model missing from the response, fill in the original prompt
   - On any exception (timeout, JSON parse error, LLM error), log a warning and return `{m: prompt for m in enabled_models}` (graceful fallback)

1. For the OpenAI provider path: use `response_format={"type": "json_object"}` if the model supports it (GPT-4o and later do). This improves JSON reliability. Check if the model ID contains "gpt-4" or "gpt-5" before adding this parameter.

1. For the Gemini provider path: use `generation_config={"response_mime_type": "application/json"}` if supported. Otherwise, rely on the system prompt instruction.

### Verification Checklist

- [x] `adapt_per_model()` returns a dict with one key per enabled model
- [x] Each value is a non-empty string
- [x] Missing models in LLM response are filled with original prompt
- [x] LLM failure returns original prompt for all models
- [x] Timeout is respected (10 seconds)

### Testing Instructions

Add `tests/backend/unit/test_prompt_adaptation.py`:

- `test_adapt_per_model_returns_dict_for_all_models` -- mock LLM client to return valid JSON with all 4 models, verify dict has all keys
- `test_adapt_per_model_fills_missing_models` -- mock LLM response with only 2 models, verify missing models get original prompt
- `test_adapt_per_model_fallback_on_invalid_json` -- mock LLM response with non-JSON text, verify all models get original prompt
- `test_adapt_per_model_fallback_on_exception` -- mock LLM client to raise, verify fallback
- `test_adapt_per_model_no_llm_configured` -- create enhancer with no prompt model, verify all models get original prompt
- `test_adapt_per_model_only_enabled_models` -- pass 2 enabled models, verify only those appear in result

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_prompt_adaptation.py -v`

### Commit Message Template

```text
feat(enhance): add per-model prompt adaptation

- adapt_per_model() tailors prompts to each provider's strengths
- single LLM call with JSON structured output
- 10-second timeout with graceful fallback to original prompt
```

## Task 2.2: Integrate Prompt Adaptation into Generate Flow

### Goal

Wire `adapt_per_model()` into `handle_generate()` so each model receives its tailored prompt. Store the adapted prompt in the iteration data in `status.json`.

### Files to Modify

- `backend/src/lambda_function.py` -- `handle_generate()` (line 418), `_handle_successful_result()` (line 217)
- `backend/src/jobs/manager.py` -- `add_iteration()` (line 111)

### Implementation Steps

The design: the iteration's `prompt` field stores the user's original prompt (for display). A new `adaptedPrompt` field stores the model-specific version (what the handler actually received). The session-level `prompt` remains the original. The context window uses the original prompt for refinement continuity.

1. In `handle_generate()`, after the prompt is extracted (line 435) and before the `generate_for_model` inner function (line 485):
   - Call `adapted_prompts = prompt_enhancer.adapt_per_model(prompt, enabled_model_names)`
   - `enabled_model_names` is already constructed at line 470

1. Modify `add_iteration()` in `manager.py` (line 111):
   - Add parameter `adapted_prompt: str | None = None`
   - In the iteration dict construction (line 156), keep `"prompt": prompt` (the original user prompt)
   - If `adapted_prompt` is provided and differs from `prompt`, add `"adaptedPrompt": adapted_prompt` to the iteration dict

1. Modify `generate_for_model()` inner function (line 485):
   - Look up the adapted prompt: `model_prompt = adapted_prompts.get(model_name, prompt)`
   - Call `session_manager.add_iteration(session_id, model_name, prompt, adapted_prompt=model_prompt)` -- passes the original `prompt` as the main prompt, `model_prompt` as the adapted version
   - Pass the adapted prompt to the handler: `handler(config_dict, model_prompt, {})` (line 495)
   - Pass `context_prompt=prompt` (original) to `_handle_successful_result()` so the context window tracks the user's intent, not the adapted version

### Verification Checklist

- [x] Each model receives its adapted prompt via the handler call
- [x] Status.json iterations have `adaptedPrompt` field when adaptation is active
- [x] Session-level `prompt` field is the original user prompt
- [x] Context window entries use the original prompt (not adapted)
- [x] Adaptation failure results in all models receiving the original prompt

### Testing Instructions

Add to `tests/backend/unit/test_prompt_adaptation.py`:

- `test_generate_uses_adapted_prompts` -- mock `adapt_per_model` to return distinct prompts per model, mock handlers, call `handle_generate`, verify each handler received its model-specific prompt
- `test_generate_stores_adapted_prompt_in_session` -- after generation, load session status, verify iterations have `adaptedPrompt` field
- `test_generate_context_uses_original_prompt` -- after generation, load context for a model, verify context entries have the original prompt (not adapted)
- `test_generate_adaptation_failure_uses_original` -- mock `adapt_per_model` to raise, verify all handlers receive original prompt

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_prompt_adaptation.py -v`

### Commit Message Template

```text
feat(generate): integrate per-model prompt adaptation

- handle_generate calls adapt_per_model before dispatching
- each model handler receives tailored prompt
- adaptedPrompt field added to iteration data in status.json
- context window uses original prompt for refinement continuity
```

## Task 2.3: Add Prompt History Repository

### Goal

Add DynamoDB operations for storing and querying prompt history records, both per-user and for the global recent feed.

### Files to Create

- `backend/src/prompts/__init__.py` -- Empty init
- `backend/src/prompts/repository.py` -- PromptHistoryRepository class

### Files to Modify

- `backend/template.yaml` -- Add GSI to DynamoDB table

### Implementation Steps

1. Add GSI to the DynamoDB table in `template.yaml`. Find the `UsersTable` resource (search for `AWS::DynamoDB::Table`). Add a GlobalSecondaryIndex:

   ```yaml
   GlobalSecondaryIndexes:
     - IndexName: PromptHistoryIndex
       KeySchema:
         - AttributeName: promptOwner
           KeyType: HASH
         - AttributeName: createdAt
           KeyType: RANGE
       Projection:
         ProjectionType: ALL
   ```

   Also add `promptOwner` (S) and `createdAt` (N) to `AttributeDefinitions`.

1. Create `backend/src/prompts/repository.py` with class `PromptHistoryRepository`:
   - Constructor takes `table_name: str` and optionally `dynamodb_resource`
   - Uses the same `boto3.resource("dynamodb")` pattern as `UserRepository`

1. Add method `record_prompt(self, user_id: str | None, prompt: str, session_id: str) -> None`:
   - Always write a global feed item:
     - `userId`: `prompt#{uuid4()}` (unique primary key)
     - `promptOwner`: `GLOBAL#RECENT`
     - `createdAt`: `int(time.time())`
     - `prompt`: the prompt text
     - `sessionId`: the session ID
     - `ttl`: `int(time.time()) + 7 * 86400` (7-day TTL)
   - If `user_id` is not None (authenticated user), also write a per-user item:
     - `userId`: `prompt#{uuid4()}`
     - `promptOwner`: `USER#{user_id}`
     - `createdAt`: `int(time.time())`
     - `prompt`: the prompt text
     - `sessionId`: the session ID
     - (no TTL -- per-user history persists)
   - Use `batch_write_item` or two `put_item` calls (batch is more efficient)

1. Add method `get_user_history(self, user_id: str, limit: int = 50) -> list[dict]`:
   - Query the `PromptHistoryIndex` GSI with `promptOwner = USER#{user_id}`
   - `ScanIndexForward=False` (newest first)
   - `Limit=limit`
   - Return list of items (each has `prompt`, `sessionId`, `createdAt`)

1. Add method `get_recent_feed(self, limit: int = 50) -> list[dict]`:
   - Query the `PromptHistoryIndex` GSI with `promptOwner = GLOBAL#RECENT`
   - `ScanIndexForward=False` (newest first)
   - `Limit=limit`
   - Return list of items

1. Add method `search_user_history(self, user_id: str, query: str, limit: int = 20) -> list[dict]`:
   - Query the GSI with `promptOwner = USER#{user_id}` and `FilterExpression = contains(prompt, :q)`
   - `ScanIndexForward=False`
   - `Limit=limit`
   - Return matching items

### Verification Checklist

- [x] `record_prompt()` writes both global feed and per-user items when authenticated
- [x] `record_prompt()` writes only global feed item when `user_id` is None
- [x] `get_user_history()` returns newest-first, limited to N items
- [x] `get_recent_feed()` returns newest-first from global feed
- [x] `search_user_history()` filters by prompt text substring
- [x] Feed items have TTL set to 7 days from creation

### Testing Instructions

Create `tests/backend/unit/test_prompt_history.py`:

- `test_record_prompt_writes_global_feed` -- record with user_id=None, query global feed, verify item exists
- `test_record_prompt_writes_both_for_authenticated` -- record with user_id, query both feeds, verify items
- `test_get_user_history_newest_first` -- record 5 prompts with different timestamps, verify ordering
- `test_get_user_history_limit` -- record 10 prompts, request limit=3, verify only 3 returned
- `test_get_recent_feed` -- record several prompts from different users, verify all appear in feed
- `test_search_user_history` -- record prompts with distinct words, search for one, verify only matching returned
- `test_feed_items_have_ttl` -- record a prompt, verify the global item has `ttl` attribute set

Use `moto` mock DynamoDB. Create the table with the GSI in the test fixture.

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_prompt_history.py -v`

### Commit Message Template

```text
feat(prompts): add prompt history DynamoDB repository

- PromptHistoryRepository with record, query, and search
- global recent feed (50 items, 7-day TTL)
- per-user history (unlimited, newest-first)
- uses GSI PromptHistoryIndex on existing users table
```

## Task 2.4: Add Prompt History API Endpoints

### Goal

Add `GET /prompts/history` and `GET /prompts/recent` endpoints, and wire prompt recording into `handle_generate()`.

### Files to Modify

- `backend/src/lambda_function.py` -- Add routes, handlers, and recording call

### Implementation Steps

1. Add module-level initialization after `_model_counter_service` (around line 92):

   ```python
   from prompts.repository import PromptHistoryRepository
   _prompt_history = PromptHistoryRepository(config.users_table_name)
   ```

1. Add `handle_prompts_recent()` function:
   - Parse query params: `limit` (default 50, max 50)
   - Call `_prompt_history.get_recent_feed(limit=limit)`
   - Return `{"prompts": items, "total": len(items)}`
   - No auth required

1. Add `handle_prompts_history()` function:
   - If `AUTH_ENABLED` is false, return 501
   - Resolve tier via `resolve_tier(event, _user_repo, _guest_service)`
   - If not authenticated, return 401
   - Parse query params: `limit` (default 50, max 100), `q` (search query, optional)
   - If `q` is provided: call `_prompt_history.search_user_history(ctx.user_id, q, limit=limit)`
   - Else: call `_prompt_history.get_user_history(ctx.user_id, limit=limit)`
   - Return `{"prompts": items, "total": len(items)}`

1. Add routes in `lambda_handler()` (around line 390):
   - `elif path == "/prompts/recent" and method == "GET": return handle_prompts_recent(event, correlation_id)`
   - `elif path == "/prompts/history" and method == "GET": return handle_prompts_history(event, correlation_id)`

1. Wire prompt recording into `handle_generate()`:
   - After `session_id = session_manager.create_session(prompt, enabled_model_names)` (line 473)
   - Determine user_id: `user_id = validated.tier.user_id if validated.tier.is_authenticated else None`. Note: `validated.tier` is never None -- when `AUTH_ENABLED=false`, it is a synthetic `_anon_tier()` with `is_authenticated=False` and `user_id="anon"`, so this condition correctly evaluates to `None` for unauthenticated users
   - Call `_prompt_history.record_prompt(user_id, prompt, session_id)` in a try/except (best-effort, do not fail generation if history write fails)
   - Log any exception as a warning

### Verification Checklist

- [x] `GET /prompts/recent` returns recent prompts (no auth required)
- [x] `GET /prompts/history` returns per-user history (auth required)
- [x] `GET /prompts/history?q=landscape` filters by search term
- [x] Prompt is recorded on each `/generate` call
- [x] History recording failure does not break generation
- [x] Routes are registered in `lambda_handler()`

### Testing Instructions

Add to `tests/backend/unit/test_prompt_history.py`:

- `test_prompts_recent_endpoint` -- call the endpoint handler, verify response structure
- `test_prompts_history_requires_auth` -- call without auth, verify 401
- `test_prompts_history_returns_user_prompts` -- mock auth, call endpoint, verify response
- `test_prompts_history_search` -- mock auth, call with `q` param, verify filtered results
- `test_generate_records_prompt` -- call `handle_generate`, verify prompt was recorded in DynamoDB
- `test_generate_survives_history_write_failure` -- mock `record_prompt` to raise, verify generation still succeeds

Run: `PYTHONPATH=backend/src pytest tests/backend/unit/test_prompt_history.py -v`

### Commit Message Template

```text
feat(prompts): add prompt history endpoints and generation recording

- GET /prompts/recent for global feed (public)
- GET /prompts/history for per-user history (auth required)
- search via ?q= query parameter
- prompts recorded on each /generate call
```

## Task 2.5: Update SAM Template

### Goal

Add the `PromptHistoryIndex` GSI to the DynamoDB table in the SAM template, and add the new API routes.

### Files to Modify

- `backend/template.yaml`

### Implementation Steps

1. Find the `UsersTable` DynamoDB resource in `template.yaml`. Add the `PromptHistoryIndex` GSI as described in Task 2.3 step 1.

1. Add `AttributeDefinitions` for `promptOwner` (S) and `createdAt` (N). These are in addition to the existing `userId` (S) attribute.

1. Add new API events to the Lambda function for the new endpoints:
   - `PromptRecent` event: `GET /prompts/recent`
   - `PromptHistory` event: `GET /prompts/history` (add Auth if JWT authorizer is configured)

1. Verify that the DynamoDB IAM policy already grants full access to the table (it should, since the Lambda already reads/writes the table for quota and tier operations). If the policy is scoped to specific operations, add `Query` to the allowed actions for the GSI.

### Verification Checklist

- [x] `sam build` succeeds
- [x] GSI is defined with correct key schema
- [x] New routes are in the API events
- [x] DynamoDB IAM policy covers GSI queries

### Testing Instructions

```bash
cd backend && sam build && cd ..
```

Verify the build completes without errors.

### Commit Message Template

```text
infra(sam): add PromptHistoryIndex GSI and prompt endpoints

- GSI on promptOwner (HASH) + createdAt (RANGE)
- new GET /prompts/recent and GET /prompts/history routes
```

## Phase Verification

- [x] All tasks committed (2.1 through 2.5)
- [x] `ruff check backend/src/` returns clean
- [x] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v --cov=backend/src --cov-fail-under=80` passes
- [x] `/generate` produces adapted prompts per model (verify by checking status.json)
- [x] Adaptation failure falls back to original prompt (testable via mocking)
- [x] `GET /prompts/recent` returns the global feed
- [x] `GET /prompts/history` returns per-user history when authenticated
- [x] `sam build` succeeds
