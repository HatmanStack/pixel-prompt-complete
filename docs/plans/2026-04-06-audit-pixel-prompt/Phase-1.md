# Phase 1 -- Backend Provider Swap and Audit Remediation

## Phase Goal

Replace all backend image generation providers (remove Flux/BFL and Recraft, update Gemini, keep OpenAI, add Nova Canvas and Firefly) while simultaneously addressing critical and high-severity audit findings in the backend. The handler code is restructured from a single 777-line file into per-provider modules.

**Success criteria:**

1. All Flux/BFL and Recraft code, config, and tests are removed
1. Four new provider modules exist under `models/providers/` with all 3 handler types each
1. Gallery endpoints no longer return base64 image data
1. Session ID validation is present on iterate/outpaint endpoints
1. Log endpoint returns 400 for validation errors
1. SAM template updated for new providers (Bedrock permission, Firefly env vars)
1. All existing backend tests pass; new provider tests achieve 80%+ coverage of new code
1. `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes with zero failures

**Estimated tokens:** ~45,000

## Prerequisites

- Phase 0 read and understood
- AWS account with Bedrock Nova Canvas access
- Adobe Firefly developer credentials available for testing
- Python 3.13 environment (managed via `uv`) with `uv pip install -r backend/src/requirements.txt`

## Task 1: Remove Flux/BFL Provider

**Goal:** Clean-delete all Flux/BFL code. This also resolves CRITICAL-2 (BFL polling thread blocking) since the polling code is entirely removed.

**Files to Modify/Create:**

- `backend/src/config.py` -- Remove `flux` ModelConfig entry, remove BFL polling config vars
- `backend/src/models/handlers.py` -- Remove `handle_bfl`, `iterate_flux`, `outpaint_flux`, `_poll_bfl_job` functions and their registry entries
- `backend/src/jobs/manager.py` -- Remove `"flux"` from hardcoded model list at line 70
- `backend/src/lambda_function.py` -- Remove BFL-related imports if any
- `backend/template.yaml` -- Remove Flux parameters (`FluxEnabled`, `FluxApiKey`, `FluxModelId`) and corresponding environment variables
- `backend/.env.example` -- Remove Flux entries
- `tests/backend/unit/test_handlers.py` -- Remove all Flux/BFL test cases
- `tests/backend/unit/test_iterate_handlers.py` -- Remove Flux iteration test cases
- `tests/backend/unit/test_config.py` -- Remove Flux config test cases
- `tests/backend/unit/test_lambda_function.py` -- Update mock model lists to exclude flux

**Prerequisites:** None

**Implementation Steps:**

1. Search the entire codebase for references to `flux`, `bfl`, `BFL`, `Flux`, `FLUX` to ensure complete removal
1. Remove the `flux` entry from the `MODELS` dict in `config.py`
1. Remove `bfl_max_poll_attempts` and `bfl_poll_interval` config variables and the `_poll_bfl_job` helper function
1. Remove `handle_bfl`, `iterate_flux`, `outpaint_flux` functions from `handlers.py`
1. Remove `"bfl"` entries from all three handler registry dicts (`get_handler`, `get_iterate_handler`, `get_outpaint_handler`)
1. Remove all SAM template parameters and environment variable mappings for Flux
1. Remove `"flux"` from the hardcoded model name list in `SessionManager.create_session()`
1. Remove all BFL-specific imports (`bfl_max_poll_attempts`, `bfl_poll_interval` from config imports in handlers.py)
1. Update all test files to remove Flux test cases and update fixture model lists
1. Run `ruff check backend/src/` to verify no import errors or unused references remain

**Verification Checklist:**

- [ ] `grep -r "flux\|bfl\|BFL\|Flux\|FLUX" backend/src/` returns no matches
- [ ] `grep -r "flux\|bfl\|BFL\|Flux\|FLUX" backend/template.yaml` returns no matches
- [ ] `ruff check backend/src/` passes with no errors
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes (test count will decrease)

**Testing Instructions:**

- No new tests needed -- this is pure removal
- Verify all remaining tests still pass after removal

**Commit Message Template:**

```text
feat(providers): remove Flux/BFL provider

- Delete handle_bfl, iterate_flux, outpaint_flux handlers
- Remove _poll_bfl_job polling helper (resolves CRITICAL-2)
- Remove flux config, SAM params, env vars, and all test cases
- Remove BFL polling config (bfl_max_poll_attempts, bfl_poll_interval)
```

---

## Task 2: Remove Recraft Provider

**Goal:** Clean-delete all Recraft code.

**Files to Modify/Create:**

- `backend/src/config.py` -- Remove `recraft` ModelConfig entry
- `backend/src/models/handlers.py` -- Remove `handle_recraft`, `iterate_recraft`, `outpaint_recraft` functions and registry entries
- `backend/src/jobs/manager.py` -- Remove `"recraft"` from hardcoded model list
- `backend/template.yaml` -- Remove Recraft parameters and environment variables
- `backend/.env.example` -- Remove Recraft entries
- `tests/backend/unit/test_handlers.py` -- Remove Recraft test cases
- `tests/backend/unit/test_iterate_handlers.py` -- Remove Recraft iteration test cases
- `tests/backend/unit/test_config.py` -- Remove Recraft config test cases
- `tests/backend/unit/test_lambda_function.py` -- Update mock model lists

**Prerequisites:** Task 1 complete

**Implementation Steps:**

1. Search codebase for `recraft`, `Recraft`, `RECRAFT`
1. Remove the `recraft` entry from `MODELS` dict
1. Remove `handle_recraft`, `iterate_recraft`, `outpaint_recraft` from `handlers.py`
1. Remove `"recraft"` from all three handler registries
1. Remove SAM template parameters and env var mappings
1. Remove `"recraft"` from `SessionManager.create_session()` hardcoded list
1. Update tests
1. Run linter

**Verification Checklist:**

- [ ] `grep -r "recraft\|Recraft\|RECRAFT" backend/src/` returns no matches
- [ ] `grep -r "recraft\|Recraft\|RECRAFT" backend/template.yaml` returns no matches
- [ ] `ruff check backend/src/` passes
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes

**Testing Instructions:**

- No new tests needed -- pure removal
- Verify remaining tests pass

**Commit Message Template:**

```text
feat(providers): remove Recraft provider

- Delete handle_recraft, iterate_recraft, outpaint_recraft handlers
- Remove recraft config, SAM params, env vars, and all test cases
```

---

## Task 3: Create Provider Module Structure and Migrate Common Code

**Goal:** Restructure handlers from a single file into per-provider modules. This task creates the directory structure and migrates the shared helper functions and types. It resolves the Architecture score-7 finding from the eval.

**Files to Modify/Create:**

- `backend/src/models/providers/__init__.py` -- Create: Re-export registry functions
- `backend/src/models/providers/_common.py` -- Create: Shared helpers migrated from handlers.py
- `backend/src/models/handlers.py` -- Delete after migration is complete (but keep until Task 4-5 are done)

**Prerequisites:** Tasks 1-2 complete (Flux and Recraft removed, so handlers.py only has Gemini and OpenAI)

**Implementation Steps:**

1. Create directory `backend/src/models/providers/`
1. Create `backend/src/models/providers/__init__.py` with:
   - Imports from each provider module (will be populated as providers are added)
   - Re-exports: `get_handler`, `get_iterate_handler`, `get_outpaint_handler`, `sanitize_error_message`
1. Create `backend/src/models/providers/_common.py` containing:
   - `_decode_source_image(source_image: str | bytes) -> bytes`
   - `_build_context_prompt(prompt: str, context: list[dict[str, Any]], max_history: int = 3) -> str`
   - `_ensure_base64(source_image: str | bytes) -> str`
   - `_extract_gemini_image(response) -> str`
   - `_download_image_as_base64(url: str, timeout: int) -> str`
   - `HandlerSuccess`, `HandlerError`, `HandlerResult` TypedDicts
   - `ModelConfig`, `GenerationParams`, `HandlerFunc`, `IterateHandlerFunc`, `OutpaintHandlerFunc` type aliases
   - `sanitize_error_message(error: Exception | str) -> str`
   - `_success_result(image: str, model_config: ModelConfig, provider: str) -> HandlerResult`
   - `_error_result(error: Exception | str, model_config: ModelConfig, provider: str) -> HandlerResult`
1. Use modern Python 3.13 type syntax throughout: `str | bytes` instead of `Union[str, bytes]`, `dict` instead of `Dict`, `list` instead of `List`. This addresses LOW-23/24 (legacy typing imports).
1. Create empty provider module files: `gemini.py`, `nova.py`, `openai_provider.py`, `firefly.py`
1. Update `lambda_function.py` imports to use `from models.providers import get_handler, get_iterate_handler, get_outpaint_handler, sanitize_error_message` instead of `from models.handlers import ...`
1. Do NOT delete `handlers.py` yet -- keep it as reference until all providers are migrated

**Verification Checklist:**

- [ ] `backend/src/models/providers/__init__.py` exists and exports all registry functions
- [ ] `backend/src/models/providers/_common.py` contains all shared helpers with modern type syntax
- [ ] No `from typing import Dict, List, Union` in new files (use built-in generics)
- [ ] `ruff check backend/src/` passes
- [ ] `PYTHONPATH=backend/src python -c "from models.providers import get_handler"` succeeds (even if registries are empty initially)

**Testing Instructions:**

- Existing tests should still pass via the updated import paths
- No new tests needed for this structural change

**Commit Message Template:**

```text
refactor(handlers): create per-provider module structure

- Create models/providers/ package with _common.py shared helpers
- Use modern Python 3.13 type syntax (str | bytes, dict, list)
- Update lambda_function.py imports to use new package
```

---

## Task 4: Implement Gemini Provider Module (Update)

**Goal:** Migrate existing Gemini handlers to the new module structure and update the model ID to `gemini-3.1-flash-image-preview` (Nano Banana 2).

**Files to Modify/Create:**

- `backend/src/models/providers/gemini.py` -- Create: All 3 Gemini handlers
- `backend/src/models/providers/__init__.py` -- Register Gemini handlers in registries
- `backend/src/config.py` -- Update Gemini default model ID
- `tests/backend/unit/test_gemini_handler.py` -- Create: Gemini handler tests

**Prerequisites:** Task 3 complete

**Implementation Steps:**

1. Create `gemini.py` with functions migrated from `handlers.py`:
   - `handle_google_gemini(model_config, prompt, _params) -> HandlerResult`
   - `iterate_gemini(model_config, source_image, prompt, context) -> HandlerResult`
   - `outpaint_gemini(model_config, source_image, preset, prompt) -> HandlerResult`
1. Import shared helpers from `._common`
1. Import `get_genai_client` from `utils.clients`
1. Add complete type annotations to all function signatures and local variables
1. Update `config.py`: Change Gemini default model_id from `"gemini-2.5-flash-image"` to `"gemini-3.1-flash-image-preview"`
1. Register all 3 handlers in `__init__.py` registries
1. Write unit tests covering:
   - Successful generation with mocked genai client
   - Error handling (empty candidates, no image data)
   - Iteration with source image and context
   - Outpaint with preset direction mapping
   - Verify response format matches `HandlerResult` contract

**Verification Checklist:**

- [ ] `backend/src/models/providers/gemini.py` has all 3 handler functions with complete type annotations
- [ ] Gemini default model ID is `gemini-3.1-flash-image-preview` in config.py
- [ ] `from models.providers import get_handler; get_handler("google_gemini")` returns the Gemini generate handler
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/test_gemini_handler.py -v` passes with 5+ tests

**Testing Instructions:**

Create `tests/backend/unit/test_gemini_handler.py` with the following test cases:

- `test_handle_google_gemini_success` -- Mock `genai.Client.models.generate_content` to return a response with inline_data. Assert result has `status: "success"` and non-empty `image` field.
- `test_handle_google_gemini_empty_candidates` -- Mock response with empty candidates. Assert result has `status: "error"`.
- `test_iterate_gemini_success` -- Mock response with inline_data. Pass source image bytes and context list. Assert success.
- `test_iterate_gemini_builds_context_prompt` -- Verify `_build_context_prompt` is called correctly by checking the prompt passed to the genai client.
- `test_outpaint_gemini_success` -- Mock response with inline_data. Pass a preset like `"16:9"`. Assert success.
- `test_outpaint_gemini_uses_direction` -- Verify the prompt includes direction description from `get_direction_description`.

Mock pattern: Use `unittest.mock.patch("models.providers.gemini._get_genai_client")` to intercept the client factory.

**Commit Message Template:**

```text
feat(providers): add Gemini provider module with Nano Banana 2

- Migrate Gemini handlers to models/providers/gemini.py
- Update default model ID to gemini-3.1-flash-image-preview
- Add full type annotations
- Add unit tests for all 3 handler types
```

---

## Task 5: Implement OpenAI Provider Module (DALL-E 3 Update)

**Goal:** Migrate OpenAI handlers to the new module structure, update generate handler to target DALL-E 3 (`dall-e-3`), and keep iteration/outpaint handlers using `gpt-image-1` per ADR-5.

**Files to Modify/Create:**

- `backend/src/models/providers/openai_provider.py` -- Create: All 3 OpenAI handlers
- `backend/src/models/providers/__init__.py` -- Register OpenAI handlers
- `backend/src/config.py` -- Update OpenAI default model_id from `gpt-image-1` to `dall-e-3`, update display_name to `DALL-E 3`
- `tests/backend/unit/test_openai_handler.py` -- Create: OpenAI handler tests

**Prerequisites:** Task 3 complete

**Implementation Steps:**

1. Create `openai_provider.py` with:
   - `handle_openai(model_config, prompt, _params) -> HandlerResult` -- Uses `model_config["id"]` (which will be `dall-e-3`). DALL-E 3 returns URLs (not b64_json), so always download the image.
   - `iterate_openai(model_config, source_image, prompt, context) -> HandlerResult` -- **Always uses `gpt-image-1`** for `images.edit`, regardless of `model_config["id"]`. This is the DALL-E 3 limitation workaround from ADR-5.
   - `outpaint_openai(model_config, source_image, preset, prompt) -> HandlerResult` -- **Always uses `gpt-image-1`** for `images.edit`, same as iterate.
1. Import shared helpers from `._common`
1. Import `get_openai_client` from `utils.clients`
1. In `iterate_openai` and `outpaint_openai`, override the model parameter: `model="gpt-image-1"` in the `client.images.edit()` call, ignoring `model_config["id"]`
1. Add a clear code comment explaining the DALL-E 3 limitation and the gpt-image-1 fallback
1. Update `config.py`: Change OpenAI default model_id from `"gpt-image-1"` to `"dall-e-3"`, change display_name from `"OpenAI"` to `"DALL-E 3"`
1. Register all 3 handlers in `__init__.py` registries

**Verification Checklist:**

- [ ] `handle_openai` uses `model_config["id"]` (dall-e-3) for generation
- [ ] `iterate_openai` hardcodes `model="gpt-image-1"` in `images.edit` call
- [ ] `outpaint_openai` hardcodes `model="gpt-image-1"` in `images.edit` call
- [ ] OpenAI default model_id in config.py is `"dall-e-3"`
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/test_openai_handler.py -v` passes

**Testing Instructions:**

Create `tests/backend/unit/test_openai_handler.py`:

- `test_handle_openai_dalle3_success` -- Mock `client.images.generate` returning a response with `data[0].url`. Mock `requests.get` for image download. Assert success with base64 image.
- `test_handle_openai_dalle3_empty_response` -- Mock empty data array. Assert error.
- `test_iterate_openai_uses_gpt_image_1` -- Mock `client.images.edit`. **Assert that the `model` argument passed to `images.edit` is `"gpt-image-1"`**, not `dall-e-3`. This is the critical test for ADR-5.
- `test_iterate_openai_success` -- Full iteration flow with mocked edit response.
- `test_outpaint_openai_uses_gpt_image_1` -- Same assertion as iterate: verify `model="gpt-image-1"` in the edit call.
- `test_outpaint_openai_success` -- Full outpaint flow.
- `test_handle_openai_timeout` -- Mock `requests.get` to raise `requests.Timeout`. Assert error result.

Mock pattern: Use `unittest.mock.patch("models.providers.openai_provider._get_openai_client")`.

**Commit Message Template:**

```text
feat(providers): add OpenAI provider module targeting DALL-E 3

- DALL-E 3 for generation, gpt-image-1 for iteration/outpaint (ADR-5)
- Migrate handlers to models/providers/openai_provider.py
- Update default model ID to dall-e-3
- Add unit tests verifying gpt-image-1 fallback for edit operations
```

---

## Task 6: Implement Nova Canvas Provider Module (New)

**Goal:** Implement Amazon Nova Canvas via AWS Bedrock for all 3 handler types. Add Bedrock permissions to the SAM template.

**Files to Modify/Create:**

- `backend/src/models/providers/nova.py` -- Create: All 3 Nova Canvas handlers
- `backend/src/models/providers/__init__.py` -- Register Nova handlers
- `backend/src/utils/clients.py` -- Add `get_bedrock_client()` cached factory
- `backend/src/config.py` -- Add `nova` ModelConfig entry
- `backend/template.yaml` -- Add `bedrock:InvokeModel` IAM permission, add Nova parameters and env vars
- `backend/.env.example` -- Add Nova entries
- `tests/backend/unit/test_nova_handler.py` -- Create: Nova handler tests

**Prerequisites:** Task 3 complete

**Implementation Steps:**

1. Add `get_bedrock_client(region: str | None = None) -> Any` to `utils/clients.py`:
   - Cache key: region string (default from `config.aws_region`)
   - Creates `boto3.client("bedrock-runtime", region_name=region)`
   - Follow existing caching pattern with `_bedrock_clients: dict[str, Any] = {}`
1. Add `nova` ModelConfig to `config.py`:

   ```python
   "nova": ModelConfig(
       name="nova",
       provider="bedrock_nova",
       enabled=os.environ.get("NOVA_ENABLED", "true").lower() == "true",
       api_key="",  # Auth via IAM role, no API key
       model_id=os.environ.get("NOVA_MODEL_ID", "amazon.nova-canvas-v1:0"),
       display_name="Nova Canvas",
   ),
   ```

1. Create `nova.py` with 3 handlers:

   **`handle_nova(model_config, prompt, _params) -> HandlerResult`:**
   - Get Bedrock client via `get_bedrock_client()`
   - Call `client.invoke_model(modelId=model_config["id"], body=json.dumps({...}), contentType="application/json")`
   - Nova Canvas text-to-image request body:

     ```json
     {
       "taskType": "TEXT_IMAGE",
       "textToImageParams": {
         "text": "<prompt>"
       },
       "imageGenerationConfig": {
         "numberOfImages": 1,
         "width": 1024,
         "height": 1024,
         "cfgScale": 8.0
       }
     }
     ```

   - Parse response body JSON, extract `images[0]` which is base64-encoded
   - Return success with the base64 image

   **`iterate_nova(model_config, source_image, prompt, context) -> HandlerResult`:**
   - Use Nova Canvas IMAGE_VARIATION task type for iteration:

     ```json
     {
       "taskType": "IMAGE_VARIATION",
       "imageVariationParams": {
         "text": "<context_prompt>",
         "images": ["<base64_source>"],
         "similarityStrength": 0.7
       },
       "imageGenerationConfig": {
         "numberOfImages": 1,
         "width": 1024,
         "height": 1024
       }
     }
     ```

   - Build context prompt using `_build_context_prompt`

   **`outpaint_nova(model_config, source_image, preset, prompt) -> HandlerResult`:**
   - Use Nova Canvas OUTPAINTING task type:

     ```json
     {
       "taskType": "OUTPAINTING",
       "outPaintingParams": {
         "text": "<prompt>",
         "image": "<base64_source>",
         "outPaintingMode": "DEFAULT"
       },
       "imageGenerationConfig": {
         "numberOfImages": 1,
         "width": "<new_width>",
         "height": "<new_height>"
       }
     }
     ```

   - Use `calculate_expansion` from `utils.outpaint` to determine new dimensions

1. Update SAM template:
   - Add `NovaEnabled` and `NovaModelId` parameters (no API key parameter -- IAM auth)
   - Add `NOVA_ENABLED` and `NOVA_MODEL_ID` environment variables
   - Add Bedrock IAM policy statement:

     ```yaml
     - Sid: BedrockInvokeModel
       Effect: Allow
       Action: bedrock:InvokeModel
       Resource: !Sub 'arn:aws:bedrock:${AWS::Region}::foundation-model/*'
     ```

1. Register all 3 handlers in `__init__.py` with provider key `"bedrock_nova"`

**API Shape Verification:**

The task types `TEXT_IMAGE`, `IMAGE_VARIATION`, and `OUTPAINTING` used above are documented in the AWS Bedrock Nova Canvas API reference: <https://docs.aws.amazon.com/nova/latest/userguide/image-gen-req-resp-structure.html>. The `imageVariationParams` and `outPaintingParams` schemas are specific to Nova Canvas.

If the API shape does not match (e.g., task types have different names, or the response structure differs), the authoritative source is the Bedrock API reference above. Fallback strategy: if `IMAGE_VARIATION` is not available, use `TEXT_IMAGE` with the source image encoded in the prompt context (prompt-only re-generation). If `OUTPAINTING` is not available, use `INPAINTING` with a mask covering the expansion area, or fall back to generating a new image at the target aspect ratio with the original prompt.

**Verification Checklist:**

- [ ] `get_bedrock_client()` exists in `utils/clients.py` with caching
- [ ] `nova` ModelConfig exists in `config.py` with `provider="bedrock_nova"` and `api_key=""`
- [ ] SAM template has `bedrock:InvokeModel` permission
- [ ] SAM template has `NovaEnabled` and `NovaModelId` parameters
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/test_nova_handler.py -v` passes

**Testing Instructions:**

Create `tests/backend/unit/test_nova_handler.py`:

- `test_handle_nova_success` -- Mock `boto3.client('bedrock-runtime').invoke_model` to return a response body with `{"images": ["<base64>"]}`. Assert success.
- `test_handle_nova_empty_response` -- Mock response with empty images array. Assert error.
- `test_handle_nova_bedrock_error` -- Mock `invoke_model` to raise `ClientError`. Assert error result (not unhandled exception).
- `test_iterate_nova_success` -- Mock invoke_model for IMAGE_VARIATION. Assert success and verify the request body contains the source image.
- `test_iterate_nova_context_prompt` -- Verify context prompt is built correctly from the context list.
- `test_outpaint_nova_success` -- Mock invoke_model for OUTPAINTING. Verify request body includes correct dimensions for the preset.
- `test_outpaint_nova_no_expansion` -- When preset results in zero expansion (image already at target ratio), verify handler returns the original image.

Mock pattern: Use `unittest.mock.patch("models.providers.nova.get_bedrock_client")` to return a mock client. The mock client's `invoke_model` return value should have a `body` attribute that is a `StreamingBody`-like object. Use `io.BytesIO(json.dumps(response).encode())` to simulate this.

**Commit Message Template:**

```text
feat(providers): add Amazon Nova Canvas provider via Bedrock

- Implement generate, iterate (IMAGE_VARIATION), outpaint handlers
- Add cached Bedrock client factory to utils/clients.py
- Add bedrock:InvokeModel IAM permission to SAM template
- Add Nova config, SAM params, and env vars
- Add unit tests for all 3 handler types
```

---

## Task 7: Implement Adobe Firefly Provider Module (New)

**Goal:** Implement Adobe Firefly Image5 with OAuth2 client credentials flow for all 3 handler types.

**Files to Modify/Create:**

- `backend/src/models/providers/firefly.py` -- Create: All 3 Firefly handlers plus OAuth2 token helper
- `backend/src/models/providers/__init__.py` -- Register Firefly handlers
- `backend/src/config.py` -- Add `firefly` ModelConfig entry, add Firefly config vars
- `backend/template.yaml` -- Add Firefly parameters and env vars
- `backend/.env.example` -- Add Firefly entries
- `tests/backend/unit/test_firefly_handler.py` -- Create: Firefly handler tests

**Prerequisites:** Task 3 complete

**Implementation Steps:**

1. Add Firefly config to `config.py`:

   ```python
   # Firefly OAuth2 credentials
   firefly_client_id = os.environ.get("FIREFLY_CLIENT_ID", "")
   firefly_client_secret = os.environ.get("FIREFLY_CLIENT_SECRET", "")
   ```

   And the ModelConfig entry:

   ```python
   "firefly": ModelConfig(
       name="firefly",
       provider="adobe_firefly",
       enabled=os.environ.get("FIREFLY_ENABLED", "true").lower() == "true",
       api_key="",  # Auth via OAuth2, not API key
       model_id=os.environ.get("FIREFLY_MODEL_ID", "firefly-image-5"),
       display_name="Firefly",
   ),
   ```

1. Create `firefly.py` with:

   **`_get_firefly_access_token() -> str`:**
   - POST to `https://ims-na1.adobelogin.com/ims/token/v3`
   - Body: `grant_type=client_credentials&client_id=<id>&client_secret=<secret>&scope=openid,AdobeID,firefly_api`
   - Content-Type: `application/x-www-form-urlencoded`
   - Timeout: 10 seconds
   - Returns the `access_token` from response JSON
   - Raises on HTTP error or missing token

   **`handle_firefly(model_config, prompt, _params) -> HandlerResult`:**
   - Get access token via `_get_firefly_access_token()`
   - POST to `https://firefly-api.adobe.io/v3/images/generate`
   - Headers: `Authorization: Bearer <token>`, `x-api-key: <client_id>`, `Content-Type: application/json`
   - Body:

     ```json
     {
       "prompt": "<prompt>",
       "n": 1,
       "size": {"width": 1024, "height": 1024},
       "contentClass": "photo"
     }
     ```

   - Response contains `outputs[0].image.url` -- download and convert to base64
   - Handle errors: token failure, API error, download failure

   **`iterate_firefly(model_config, source_image, prompt, context) -> HandlerResult`:**
   - Use Firefly's structure reference endpoint for iteration
   - POST to `https://firefly-api.adobe.io/v3/images/generate`
   - Include structure reference with the source image:

     ```json
     {
       "prompt": "<context_prompt>",
       "n": 1,
       "size": {"width": 1024, "height": 1024},
       "structure": {
         "imageReference": {
           "source": {"uploadId": "<upload_id>"}
         },
         "strength": 70
       }
     }
     ```

   - First upload the source image via `POST https://firefly-api.adobe.io/v2/storage/image`
   - Then reference the upload ID in the generate call
   - Build context prompt using `_build_context_prompt`

   **`outpaint_firefly(model_config, source_image, preset, prompt) -> HandlerResult`:**
   - Use Firefly's generative expand endpoint
   - POST to `https://firefly-api.adobe.io/v3/images/expand`
   - Upload source image first, then call expand with new dimensions
   - Use `calculate_expansion` from `utils.outpaint` for dimensions
   - Body includes the uploaded image reference and target size

1. Update SAM template:
   - Add `FireflyEnabled`, `FireflyClientId`, `FireflyClientSecret`, `FireflyModelId` parameters
   - `FireflyClientId` and `FireflyClientSecret` with `NoEcho: true`
   - Add corresponding environment variables
1. Register all 3 handlers in `__init__.py` with provider key `"adobe_firefly"`

**API Shape Verification:**

The Firefly API endpoints and payload shapes above are based on the Adobe Firefly Services API reference: <https://developer.adobe.com/firefly-services/docs/firefly-api/>. Key endpoints:

- Generate: `POST /v3/images/generate` -- documented at <https://developer.adobe.com/firefly-services/docs/firefly-api/guides/api/image_generation/V3/>
- Storage upload: `POST /v2/storage/image` -- documented at <https://developer.adobe.com/firefly-services/docs/firefly-api/guides/api/upload/>
- Generative expand: `POST /v3/images/expand` -- documented at <https://developer.adobe.com/firefly-services/docs/firefly-api/guides/api/generative_expand/V3/>

If the API shape does not match (e.g., structure reference is not supported, or the expand endpoint has a different path):

- **Iteration fallback:** If structure reference is unavailable, use prompt-only re-generation via the standard generate endpoint with the context prompt. This loses image-to-image fidelity but preserves the iteration workflow.
- **Outpaint fallback:** If generative expand is unavailable, generate a new image at the target aspect ratio using the original prompt. Document the limitation in the handler's docstring.
- **Auth fallback:** If the IMS token endpoint path changes, check <https://developer.adobe.com/developer-console/docs/guides/authentication/ServerToServerAuthentication/implementation/> for the current OAuth2 server-to-server flow.

1. Update `get_model_config_dict` in `config.py` to include `client_id` and `client_secret` for Firefly:

   ```python
   if model.provider == "adobe_firefly":
       config["client_id"] = firefly_client_id
       config["client_secret"] = firefly_client_secret
   ```

**Verification Checklist:**

- [ ] `_get_firefly_access_token` is a standalone function, not cached across invocations
- [ ] All 3 handlers acquire a fresh token per call
- [ ] SAM template has `FireflyClientId` and `FireflyClientSecret` with `NoEcho: true`
- [ ] `ruff check backend/src/` passes
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/test_firefly_handler.py -v` passes

**Testing Instructions:**

Create `tests/backend/unit/test_firefly_handler.py`:

- `test_get_firefly_access_token_success` -- Mock `requests.post` to return `{"access_token": "test-token"}`. Assert token is returned.
- `test_get_firefly_access_token_failure` -- Mock `requests.post` to return 401. Assert ValueError is raised.
- `test_handle_firefly_success` -- Mock token fetch and `requests.post` for generation API. Mock image download. Assert success.
- `test_handle_firefly_token_failure` -- Mock token fetch to fail. Assert error result.
- `test_handle_firefly_api_error` -- Mock token success but API returns 400. Assert error result.
- `test_iterate_firefly_success` -- Mock token, image upload, and generation with structure reference. Assert success.
- `test_iterate_firefly_upload_failure` -- Mock image upload to fail. Assert error result.
- `test_outpaint_firefly_success` -- Mock token, image upload, and expand API. Assert success.
- `test_outpaint_firefly_dimensions` -- Verify that the expand API receives correct dimensions for a given preset.

Mock pattern: Use `unittest.mock.patch("models.providers.firefly.requests")` or patch individual methods. For the token helper, patch `requests.post` in `models.providers.firefly`.

**Commit Message Template:**

```text
feat(providers): add Adobe Firefly provider with OAuth2 auth

- Implement generate, iterate (structure reference), outpaint (expand)
- Per-request OAuth2 token fetch (no caching per ADR-4)
- Add Firefly config, SAM params (NoEcho secrets), and env vars
- Add unit tests for all 3 handler types including auth flow
```

---

## Task 8: Finalize Provider Registry and Remove Old handlers.py

**Goal:** Complete the provider registry in `__init__.py`, update `SessionManager` to use config-derived model names, and delete the old `handlers.py` file.

**Files to Modify/Create:**

- `backend/src/models/providers/__init__.py` -- Finalize all registry dicts
- `backend/src/models/handlers.py` -- Delete
- `backend/src/jobs/manager.py` -- Replace hardcoded model list with config-derived list
- `backend/src/lambda_function.py` -- Verify all imports use `models.providers`
- `tests/backend/unit/test_lambda_function.py` -- Update import patches and model lists

**Prerequisites:** Tasks 4-7 complete (all 4 providers implemented)

**Implementation Steps:**

1. Verify `__init__.py` has complete registries:

   ```python
   _GENERATE_HANDLERS: dict[str, HandlerFunc] = {
       "google_gemini": handle_google_gemini,
       "bedrock_nova": handle_nova,
       "openai": handle_openai,
       "adobe_firefly": handle_firefly,
   }

   _ITERATE_HANDLERS: dict[str, IterateHandlerFunc] = {
       "google_gemini": iterate_gemini,
       "bedrock_nova": iterate_nova,
       "openai": iterate_openai,
       "adobe_firefly": iterate_firefly,
   }

   _OUTPAINT_HANDLERS: dict[str, OutpaintHandlerFunc] = {
       "google_gemini": outpaint_gemini,
       "bedrock_nova": outpaint_nova,
       "openai": outpaint_openai,
       "adobe_firefly": outpaint_firefly,
   }
   ```

1. Update `SessionManager.create_session()` at `manager.py:70` to replace the hardcoded `["flux", "recraft", "gemini", "openai"]` with `list(MODELS.keys())` imported from config:

   ```python
   from config import MODELS
   # ...
   for model_name in list(MODELS.keys()):
   ```

1. Verify `lambda_function.py` imports only from `models.providers`, not `models.handlers`
1. Delete `backend/src/models/handlers.py`
1. Update `test_lambda_function.py`:
   - Patch paths change from `models.handlers.*` to `models.providers.*`
   - Update mock model name lists from `["flux", "recraft", "gemini", "openai"]` to `["gemini", "nova", "openai", "firefly"]`
1. Update `test_iterate_handlers.py`:
   - Update to test new provider names and import paths
   - Contract tests should verify all 4 new providers return consistent response format

**Verification Checklist:**

- [ ] `backend/src/models/handlers.py` is deleted
- [ ] `grep -r "from models.handlers" backend/src/` returns no matches
- [ ] `SessionManager.create_session` uses `list(MODELS.keys())` not a hardcoded list
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes all tests
- [ ] `ruff check backend/src/` passes

**Testing Instructions:**

- Run the full test suite to verify no import errors from the deletion
- The contract test in `test_iterate_handlers.py` should verify all 4 new providers

**Commit Message Template:**

```text
refactor(handlers): finalize provider registry and remove old handlers.py

- Complete registry with all 4 providers in providers/__init__.py
- Replace hardcoded model list in SessionManager with config-derived list
- Delete monolithic handlers.py (777 lines -> 4 modules ~150 lines each)
- Update all test imports and model name fixtures
```

---

## Task 9: Fix Gallery Base64 Payload Overflow (CRITICAL)

**Goal:** Stop returning base64 image data in gallery list and gallery detail responses. Return CloudFront URLs instead. This resolves CRITICAL-1 and HIGH-8 from the health audit. Also add public `validate_gallery_id()` method to resolve HIGH-5.

**Files to Modify/Create:**

- `backend/src/lambda_function.py` -- Modify `handle_gallery_list` and `handle_gallery_detail`
- `backend/src/utils/storage.py` -- Add `validate_gallery_id()` public method, add `get_image_metadata()` method
- `tests/backend/unit/test_storage.py` -- Add tests for new methods
- `tests/backend/unit/test_lambda_function.py` -- Update gallery test expectations

**Prerequisites:** None (can run in parallel with Tasks 4-7)

**Implementation Steps:**

1. Add `validate_gallery_id(gallery_id: str) -> bool` to `ImageStorage`:

   ```python
   def validate_gallery_id(self, gallery_id: str) -> bool:
       """Validate gallery ID matches expected timestamp format."""
       return bool(self._GALLERY_FOLDER_RE.match(gallery_id))
   ```

1. Add `get_image_metadata(image_key: str) -> dict | None` to `ImageStorage` that returns metadata WITHOUT the `output` field:

   ```python
   def get_image_metadata(self, image_key: str) -> dict | None:
       """Get image metadata from S3 excluding the base64 output data."""
       data = self.get_image(image_key)
       if data:
           data.pop("output", None)
           return data
       return None
   ```

1. Update `handle_gallery_list`:
   - Replace `preview_data = preview_metadata["output"]` with `preview_url = image_storage.get_cloudfront_url(images[0])`
   - Return `"previewUrl": preview_url` instead of `"previewData": preview_data`

1. Update `handle_gallery_detail`:
   - Replace `image_storage._GALLERY_FOLDER_RE.match(gallery_id)` with `image_storage.validate_gallery_id(gallery_id)`
   - In `_load_image`, use `get_image_metadata` instead of `get_image`
   - Remove the `"output": metadata.get("output")` field from the response

1. Update `_load_source_image` to fix the redundant S3 reads (HIGH-3):
   - Call `session_manager.get_session()` once
   - Extract iteration count and latest image key from the same session object
   - This requires refactoring `_load_source_image` to inline the logic from `get_iteration_count` and `get_latest_image_key` using a single session fetch

**Verification Checklist:**

- [ ] `handle_gallery_list` response contains `previewUrl` (string URL), not `previewData` (base64 blob)
- [ ] `handle_gallery_detail` response does not contain `output` field in image entries
- [ ] `handle_gallery_detail` uses `image_storage.validate_gallery_id()` not `image_storage._GALLERY_FOLDER_RE`
- [ ] `_load_source_image` makes exactly 1 S3 call for session data (was 2)
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes

**Testing Instructions:**

Add to `tests/backend/unit/test_storage.py`:

- `test_validate_gallery_id_valid` -- Pass `"2025-11-15-14-30-45"`. Assert True.
- `test_validate_gallery_id_invalid` -- Pass `"not-a-timestamp"`. Assert False.
- `test_validate_gallery_id_uuid` -- Pass a UUID. Assert False.
- `test_get_image_metadata_excludes_output` -- Store image with output field, retrieve via `get_image_metadata`. Assert `output` key is not present.

Add to `tests/backend/unit/test_lambda_function.py`:

- `test_gallery_list_returns_preview_url` -- Assert response has `previewUrl` (not `previewData`) in gallery entries.
- `test_gallery_detail_no_output_field` -- Assert image entries do not contain `output` key.
- `test_load_source_image_single_s3_read` -- Mock `get_session` and verify it is called exactly once (not twice).

**Commit Message Template:**

```text
fix(gallery): stop returning base64 data in gallery responses

- Return CloudFront URLs instead of base64 blobs (resolves CRITICAL-1)
- Add validate_gallery_id() public method (resolves HIGH-5)
- Add get_image_metadata() excluding output field
- Fix redundant S3 reads in _load_source_image (resolves HIGH-3)
```

---

## Task 10: Fix Log Endpoint and Add Session ID Validation

**Goal:** Fix the log endpoint to return 400 for validation errors (HIGH-6), add session ID validation to iterate/outpaint (eval Defensiveness finding), and add the `/log` route to the SAM template (doc-audit DRIFT-4).

**Files to Modify/Create:**

- `backend/src/lambda_function.py` -- Add `ValueError` catch in `handle_log_endpoint`, add session ID regex to `_validate_refinement_request`
- `backend/template.yaml` -- Add `/log` POST event to Lambda function events
- `tests/backend/unit/test_log_endpoint.py` -- Add test for 400 response on validation error
- `tests/backend/unit/test_lambda_function.py` -- Add test for session ID validation

**Prerequisites:** None

**Implementation Steps:**

1. In `handle_log_endpoint` (lambda_function.py), add a `ValueError` catch before the generic `Exception` catch:

   ```python
   except json.JSONDecodeError:
       return response(400, {"error": "Invalid JSON in request body"})
   except ValueError as e:
       return response(400, {"error": str(e)})
   except Exception as e:
       # ... existing 500 handler
   ```

1. In `_validate_refinement_request`, add session ID format validation after the `if not session_id` check:

   ```python
   if not re.match(r"^[a-zA-Z0-9\-]{1,64}$", session_id):
       return None, response(400, {"error": "Invalid session ID format"})
   ```

   This uses the same regex already used in `handle_status` at line 616.

1. Add the `/log` route to `template.yaml` Events:

   ```yaml
   LogApi:
     Type: HttpApi
     Properties:
       Path: /log
       Method: POST
       ApiId: !Ref HttpApi
   ```

**Verification Checklist:**

- [ ] POST to `/log` with missing `level` field returns HTTP 400, not 500
- [ ] POST to `/iterate` with `sessionId: "../../../etc/passwd"` returns HTTP 400
- [ ] POST to `/outpaint` with invalid sessionId returns HTTP 400
- [ ] SAM template has a LogApi event for `/log` POST
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes

**Testing Instructions:**

Add to `tests/backend/unit/test_log_endpoint.py`:

- `test_log_missing_level_returns_400` -- POST with body `{"message": "test"}` (no level). Assert HTTP 400, not 500.
- `test_log_invalid_level_returns_400` -- POST with body `{"level": "INVALID", "message": "test"}`. Assert HTTP 400.

Add to `tests/backend/unit/test_lambda_function.py`:

- `test_iterate_invalid_session_id_returns_400` -- POST `/iterate` with `sessionId: "../../hack"`. Assert HTTP 400.
- `test_outpaint_invalid_session_id_returns_400` -- POST `/outpaint` with `sessionId: "../../hack"`. Assert HTTP 400.
- `test_iterate_valid_session_id_accepted` -- POST `/iterate` with a valid UUID sessionId. Assert it does not return 400 for format (may return other errors due to session not found).

**Commit Message Template:**

```text
fix(api): return 400 for log validation errors and validate session IDs

- Catch ValueError in handle_log_endpoint, return 400 (resolves HIGH-6)
- Add session ID format validation to _validate_refinement_request
- Add /log POST route to SAM template (resolves doc-audit DRIFT-4)
```

---

## Task 11: Backend Cleanup and Type Hardening

**Goal:** Address remaining backend audit findings: enhance.py model branching, retry.py logging, S3 error handling consistency, legacy typing imports, and enable strict mypy.

**Files to Modify/Create:**

- `backend/src/api/enhance.py` -- Extract model-specific params into config map
- `backend/src/utils/retry.py` -- Switch from `logging.getLogger` to `StructuredLogger`
- `backend/src/models/context.py` -- Use `ClientError` pattern instead of `self.s3.exceptions.NoSuchKey`
- `backend/src/config.py` -- Remove `from typing import Dict, List`, use built-in generics
- `backend/src/lambda_function.py` -- Remove `from typing import Any, Dict, Optional`, use built-in generics and `X | None`
- `backend/src/jobs/manager.py` -- Remove legacy typing imports
- `backend/src/utils/storage.py` -- Remove legacy typing imports
- `backend/pyproject.toml` -- Set `disallow_untyped_defs = true`

**Prerequisites:** Tasks 1-8 complete (all provider work done, so we can enable strict types safely)

**Implementation Steps:**

1. In `enhance.py`, replace the `if "gpt-5" in model_id` / `elif "gpt-4o" in model_id` branching (lines 114-136) with a config map:

   ```python
   _MODEL_PARAMS: dict[str, dict[str, Any]] = {
       "gpt-5": {"max_completion_tokens": 300},
       "gpt-4o": {"max_tokens": 300},
   }
   _DEFAULT_PARAMS: dict[str, Any] = {"max_tokens": 300}

   def _get_model_params(model_id: str) -> dict[str, Any]:
       for key, params in _MODEL_PARAMS.items():
           if key in model_id:
               return params
       return _DEFAULT_PARAMS
   ```

1. In `retry.py`, replace `import logging` / `logger = logging.getLogger(__name__)` with:

   ```python
   from utils.logger import StructuredLogger
   ```

   And replace all `logger.warning(...)` calls with `StructuredLogger.warning(...)`.

1. In `context.py`, replace `self.s3.exceptions.NoSuchKey` with:

   ```python
   from botocore.exceptions import ClientError
   # ...
   except ClientError as e:
       if e.response["Error"]["Code"] == "NoSuchKey":
           return []
       raise
   ```

1. In all modified backend files, replace legacy typing imports:
   - `Dict` -> `dict`, `List` -> `list`, `Optional[X]` -> `X | None`, `Union[X, Y]` -> `X | Y`
   - Remove `from typing import Dict, List, Optional, Union` when no longer needed

1. In `pyproject.toml`, change `disallow_untyped_defs = false` to `disallow_untyped_defs = true`
1. Run `mypy backend/src/` and fix any type errors in new or modified code
1. Remove unnecessary blank lines in `enhance.py` (lines 112-113, 146-147) per LOW-14

**Verification Checklist:**

- [ ] `grep -r "from typing import Dict" backend/src/` returns no matches in modified files
- [ ] `enhance.py` has no `if "gpt-5"` / `elif "gpt-4o"` string-matching branches
- [ ] `retry.py` uses `StructuredLogger`, not `logging.getLogger`
- [ ] `context.py` uses `ClientError` pattern, not `self.s3.exceptions.NoSuchKey`
- [ ] `disallow_untyped_defs = true` in pyproject.toml
- [ ] `ruff check backend/src/` passes
- [ ] `PYTHONPATH=backend/src pytest tests/backend/unit/ -v` passes

**Testing Instructions:**

- Existing tests cover these modules. Run the full backend test suite to verify no regressions.
- If `mypy` reports errors, fix them before committing.

**Commit Message Template:**

```text
refactor(backend): type hardening and cleanup

- Extract enhance.py model params into config map (resolves MED-13)
- Switch retry.py to StructuredLogger (resolves LOW-20)
- Standardize S3 error handling in context.py (resolves LOW-21)
- Replace legacy typing imports with built-in generics (resolves LOW-23/24)
- Enable disallow_untyped_defs in mypy config
- Remove unnecessary blank lines in enhance.py
```

---

## Task 12: Update Backend .env.example and Config Order

**Goal:** Update the `.env.example` and config.py `MODELS` dict to reflect the new 4-provider lineup with correct ordering.

**Files to Modify/Create:**

- `backend/.env.example` -- Rewrite for new providers
- `backend/src/config.py` -- Ensure `MODELS` dict order is `gemini, nova, openai, firefly`

**Prerequisites:** Tasks 1-7 complete

**Implementation Steps:**

1. Verify `MODELS` dict in `config.py` is ordered: `gemini`, `nova`, `openai`, `firefly` (Python 3.7+ dicts preserve insertion order)
1. Rewrite `backend/.env.example` with:
   - Gemini section (API key, enabled, model ID)
   - Nova section (enabled, model ID -- no API key since IAM auth)
   - OpenAI section (API key, enabled, model ID defaulting to `dall-e-3`)
   - Firefly section (client ID, client secret, enabled, model ID)
   - Remove all Flux and Recraft entries
   - Remove BFL polling config entries
   - Keep all other sections unchanged

**Verification Checklist:**

- [ ] `MODELS` dict keys in config.py are in order: gemini, nova, openai, firefly
- [ ] `.env.example` has no Flux or Recraft entries
- [ ] `.env.example` has Firefly client_id and client_secret entries
- [ ] `.env.example` has Nova entries with note about IAM auth

**Commit Message Template:**

```text
chore(config): update .env.example and model ordering for new providers

- Rewrite .env.example for Gemini, Nova, OpenAI (DALL-E 3), Firefly
- Remove Flux and Recraft entries
- Ensure MODELS dict order matches frontend column order
```

---

## Phase Verification

After completing all tasks in Phase 1:

1. Run: `ruff check backend/src/` -- must pass with no errors
1. Run: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v --tb=short` -- all tests pass
1. Run: `PYTHONPATH=backend/src pytest tests/backend/unit/ -v --cov=backend/src --cov-report=term-missing` -- verify coverage of new provider modules
1. Verify: `grep -r "flux\|recraft\|bfl\|Flux\|Recraft\|BFL\|FLUX\|RECRAFT" backend/src/` returns no matches (except possibly in comments about migration)
1. Verify: `backend/src/models/handlers.py` does not exist
1. Verify: `backend/src/models/providers/` contains `__init__.py`, `_common.py`, `gemini.py`, `nova.py`, `openai_provider.py`, `firefly.py`
1. Verify: SAM template has parameters and env vars for Gemini, Nova, OpenAI, Firefly (not Flux, not Recraft)
1. Verify: SAM template has `bedrock:InvokeModel` IAM permission
1. Verify: SAM template has `/log` POST event

**Known limitations after Phase 1:**

- Frontend still references old model names (addressed in Phase 2)
- Documentation not yet updated (addressed in Phase 3)
- Coverage gate still at 60% (raised in Phase 3)
- E2E tests not yet updated (may need Phase 2 frontend changes first)
