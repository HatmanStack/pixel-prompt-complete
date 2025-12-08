# Phase 1: Backend Transformation

## Phase Goal

Transform the backend from a dynamic 20-model system to a focused 4-model architecture with iteration capabilities. This phase implements new API endpoints (`/iterate`, `/outpaint`), conversation context management, provider-specific iteration handlers, and simplified configuration.

**Success Criteria:**
- SAM template reduced to 4 fixed models with enable/disable flags
- `/iterate` endpoint accepts image + prompt and returns refined image
- `/outpaint` endpoint accepts image + preset and returns expanded image
- Conversation context stored and retrieved per model column
- All backend unit tests pass with mocked providers
- Deploy script updated for new configuration schema

**Estimated Tokens:** ~45,000

## Prerequisites

- Phase 0 complete (ADRs accepted, testing strategy defined)
- API documentation for all 4 providers reviewed:
  - [BFL Flux API](https://docs.bfl.ai/)
  - [Recraft API](https://www.recraft.ai/docs)
  - [Google Gemini API](https://ai.google.dev/gemini-api/docs/image-generation)
  - [OpenAI Images API](https://platform.openai.com/docs/api-reference/images)

---

## Task 1: Simplify SAM Template

**Goal:** Replace the 20 dynamic model parameters with 4 fixed model configurations, each with enable/disable capability.

**Files to Modify/Create:**
- `backend/template.yaml` - Complete rewrite with 4 fixed models
- `backend/.env.deploy.example` - Updated example configuration

**Prerequisites:**
- None (first task)

**Implementation Steps:**

1. **Remove all Model1-Model20 parameters** from the Parameters section. Replace with explicit parameters for each of the 4 models:
   - `FluxEnabled` (Boolean), `FluxApiKey`, `FluxModelId`
   - `RecraftEnabled` (Boolean), `RecraftApiKey`, `RecraftModelId`
   - `GeminiEnabled` (Boolean), `GeminiApiKey`, `GeminiModelId`
   - `OpenaiEnabled` (Boolean), `OpenaiApiKey`, `OpenaiModelId`

2. **Update Metadata section** to group parameters logically:
   - Environment Configuration
   - Flux Configuration
   - Recraft Configuration
   - Gemini Configuration
   - OpenAI Configuration
   - Prompt Enhancement
   - Rate Limiting

3. **Simplify Lambda environment variables** to use the new parameter names directly:
   ```yaml
   Environment:
     Variables:
       FLUX_ENABLED: !Ref FluxEnabled
       FLUX_API_KEY: !Ref FluxApiKey
       FLUX_MODEL_ID: !Ref FluxModelId
       # ... similar for other 3 models
   ```

4. **Update API Gateway events** to add new routes:
   - `POST /iterate` - Image iteration endpoint
   - `POST /outpaint` - Outpainting endpoint

5. **Keep existing infrastructure** (S3, CloudFront, CloudWatch) unchanged.

**Verification Checklist:**
- [x] Template validates: `sam validate`
- [x] Template has <300 lines (down from ~1300)
- [x] All 4 model parameter groups present
- [x] Enable/disable flags for each model
- [x] New API routes defined
- [x] No Model1-Model20 references remain

**Testing Instructions:**
- Unit test: Validate YAML structure programmatically
- Integration test: `sam build` succeeds without errors

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

refactor(backend): simplify SAM template to 4 fixed models

Replace 20 dynamic model parameters with 4 explicit configurations
Add enable/disable flags per model
Add /iterate and /outpaint API routes
Reduce template from ~1300 to ~250 lines
```

---

## Task 2: Update Configuration Module

**Goal:** Rewrite `config.py` to load the 4 fixed models with enable/disable support.

**Files to Modify/Create:**
- `backend/src/config.py` - Rewrite for 4 fixed models

**Prerequisites:**
- Task 1 complete (new environment variable names)

**Implementation Steps:**

1. **Define model configuration structure:**
   ```python
   @dataclass
   class ModelConfig:
       name: str           # 'flux', 'recraft', 'gemini', 'openai'
       provider: str       # Provider identifier for handler lookup
       enabled: bool
       api_key: str
       model_id: str
       display_name: str   # Human-readable name for UI
   ```

2. **Load each model explicitly:**
   ```python
   MODELS = {
       'flux': ModelConfig(
           name='flux',
           provider='bfl',
           enabled=os.getenv('FLUX_ENABLED', 'true').lower() == 'true',
           api_key=os.getenv('FLUX_API_KEY', ''),
           model_id=os.getenv('FLUX_MODEL_ID', 'flux-pro-1.1'),
           display_name='Flux'
       ),
       # ... similar for recraft, gemini, openai
   }
   ```

3. **Provide helper functions:**
   - `get_enabled_models()` - Returns list of enabled ModelConfig objects
   - `get_model(name)` - Returns specific model config or raises error
   - `is_model_enabled(name)` - Boolean check

4. **Remove all dynamic model loading logic** (the `for i in range(1, MODEL_COUNT+1)` pattern).

**Verification Checklist:**
- [x] `get_enabled_models()` returns only enabled models
- [x] `get_model('flux')` returns correct config when enabled
- [x] `get_model('flux')` raises error when disabled
- [x] No references to MODEL_COUNT or MODEL_{N}_* patterns
- [x] Default values work when env vars missing

**Testing Instructions:**
- Unit tests for each helper function
- Test with various enabled/disabled combinations
- Test default values

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

refactor(backend): rewrite config for 4 fixed models

Add ModelConfig dataclass with enable/disable support
Implement get_enabled_models(), get_model(), is_model_enabled()
Remove dynamic MODEL_{N} loading pattern
Add default model IDs for each provider
```

---

## Task 3: Implement Conversation Context Manager

**Goal:** Create a module to manage rolling 3-iteration conversation context per model column.

**Files to Modify/Create:**
- `backend/src/models/context.py` - New context management module

**Prerequisites:**
- Task 2 complete (config structure)

**Implementation Steps:**

1. **Define context entry structure:**
   ```python
   @dataclass
   class ContextEntry:
       iteration: int
       prompt: str
       image_key: str
       timestamp: str  # ISO8601
   ```

2. **Create ContextManager class:**
   ```python
   class ContextManager:
       def __init__(self, s3_client, bucket: str):
           self.s3 = s3_client
           self.bucket = bucket
           self.window_size = 3

       def get_context(self, session_id: str, model: str) -> List[ContextEntry]:
           """Load context window from S3."""

       def add_entry(self, session_id: str, model: str, entry: ContextEntry) -> None:
           """Add entry to context, maintaining window size."""

       def clear_context(self, session_id: str, model: str) -> None:
           """Clear context for a model column."""
   ```

3. **Implement S3 storage:**
   - Path: `sessions/{session_id}/context/{model}.json`
   - Format: JSON array of ContextEntry objects
   - Window management: Keep only last 3 entries (FIFO)

4. **Handle edge cases:**
   - Missing context file (return empty list)
   - Corrupted JSON (log warning, return empty list)
   - S3 errors (raise with meaningful message)

**Verification Checklist:**
- [x] `get_context()` returns empty list for new session
- [x] `add_entry()` maintains 3-entry window
- [x] Oldest entry removed when window exceeds 3
- [x] Context persists across Lambda invocations
- [x] Handles missing/corrupted files gracefully

**Testing Instructions:**
- Unit tests with mocked S3 (moto)
- Test window overflow behavior
- Test error handling for corrupted JSON

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(backend): add conversation context manager

Implement ContextManager for rolling 3-iteration window
Store context per session/model in S3
Add ContextEntry dataclass for structured entries
Handle missing files and corrupted JSON gracefully
```

---

## Task 4: Implement Session Manager

**Goal:** Replace job-based storage with session-based storage that tracks iterations per model.

**Files to Modify/Create:**
- `backend/src/jobs/manager.py` - Rename to session-based, add iteration tracking
- `backend/src/jobs/session.py` - New session-focused manager (alternative: modify existing)

**Prerequisites:**
- Task 3 complete (context manager)

**Implementation Steps:**

1. **Define session status structure:**
   ```python
   {
       "sessionId": "uuid",
       "status": "pending|in_progress|completed|partial|failed",
       "prompt": "original prompt",
       "createdAt": "ISO8601",
       "updatedAt": "ISO8601",
       "models": {
           "flux": {
               "enabled": true,
               "status": "completed",
               "iterationCount": 3,
               "iterations": [
                   {"index": 0, "status": "completed", "imageKey": "...", "prompt": "original"},
                   {"index": 1, "status": "completed", "imageKey": "...", "prompt": "make sky purple"},
                   {"index": 2, "status": "in_progress", "prompt": "add clouds"}
               ]
           },
           # ... similar for other models
       }
   }
   ```

2. **Create SessionManager class:**
   ```python
   class SessionManager:
       def create_session(self, prompt: str, enabled_models: List[str]) -> str:
           """Create new session, return session ID."""

       def get_session(self, session_id: str) -> Optional[Dict]:
           """Get session status from S3."""

       def add_iteration(self, session_id: str, model: str, prompt: str) -> int:
           """Add iteration to model, return iteration index."""

       def complete_iteration(self, session_id: str, model: str, index: int, image_key: str) -> None:
           """Mark iteration as completed with image key."""

       def fail_iteration(self, session_id: str, model: str, index: int, error: str) -> None:
           """Mark iteration as failed with error."""

       def get_iteration_count(self, session_id: str, model: str) -> int:
           """Return current iteration count for limit checking."""
   ```

3. **Implement S3 storage:**
   - Path: `sessions/{session_id}/status.json`
   - Use optimistic locking (version field) for concurrent updates

4. **Add iteration limit enforcement:**
   - Check count before `add_iteration()`
   - Return error if limit (7) exceeded

**Verification Checklist:**
- [x] `create_session()` initializes all enabled models
- [x] `add_iteration()` increments count correctly
- [x] `add_iteration()` rejects when count >= 7
- [x] `complete_iteration()` stores image key
- [x] Concurrent updates handled via versioning
- [x] Session status computed from model statuses

**Testing Instructions:**
- Unit tests with mocked S3
- Test iteration limit enforcement
- Test concurrent update handling

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(backend): implement session manager with iteration tracking

Replace job-based storage with session-centric model
Track iterations per model column (max 7)
Add optimistic locking for concurrent updates
Compute session status from model statuses
```

---

## Task 5: Implement Provider Iteration Handlers

**Goal:** Add `iterate()` methods to each provider handler that refine an existing image.

**Files to Modify/Create:**
- `backend/src/models/handlers.py` - Add iterate functions for each provider

**Prerequisites:**
- Task 3 complete (context manager for context retrieval)
- Task 4 complete (session manager for iteration tracking)

**Implementation Steps:**

1. **Add `iterate_flux()` function:**
   - Use FLUX Fill API with full-image mask
   - Send source image + prompt
   - Context: Include last 3 prompts in request
   ```python
   def iterate_flux(model_config: Dict, source_image: bytes, prompt: str, context: List[Dict]) -> Dict:
       # FLUX Fill endpoint: https://api.bfl.ai/v1/flux-pro-1.1-fill
       # Requires: image, mask (all white for full refinement), prompt
   ```

2. **Add `iterate_recraft()` function:**
   - Use Recraft imageToImage endpoint
   - POST to `https://external.api.recraft.ai/v1/images/imageToImage`
   - Multipart form with image file and prompt
   ```python
   def iterate_recraft(model_config: Dict, source_image: bytes, prompt: str, context: List[Dict]) -> Dict:
       # Recraft imageToImage endpoint
       # Requires: image file, prompt, optional style parameters
   ```

3. **Add `iterate_gemini()` function:**
   - Use multi-turn conversation with image
   - Send image + prompt in generate_content call
   - Leverage conversation history for context
   ```python
   def iterate_gemini(model_config: Dict, source_image: bytes, prompt: str, context: List[Dict]) -> Dict:
       # Gemini natively supports multi-turn with images
       # Build conversation from context entries
       # Add current image + prompt
   ```

4. **Add `iterate_openai()` function:**
   - Use images.edit endpoint
   - gpt-image-1 accepts image + prompt without mask
   ```python
   def iterate_openai(model_config: Dict, source_image: bytes, prompt: str, context: List[Dict]) -> Dict:
       # OpenAI images.edit endpoint
       # Supports image + prompt for refinement
   ```

5. **Add `get_iterate_handler()` dispatcher:**
   ```python
   def get_iterate_handler(provider: str) -> Callable:
       handlers = {
           'bfl': iterate_flux,
           'recraft': iterate_recraft,
           'google_gemini': iterate_gemini,
           'openai': iterate_openai,
       }
       return handlers.get(provider)
   ```

**Verification Checklist:**
- [x] Each handler returns standardized response format
- [x] Handlers gracefully handle API errors
- [x] Context is utilized appropriately per provider
- [x] API keys sanitized from error messages
- [x] Timeout handling for each provider

**Testing Instructions:**
- Unit tests with mocked API responses for each provider
- Test error handling for common failure modes
- Test context integration

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(backend): add iteration handlers for all 4 providers

Implement iterate_flux() using FLUX Fill API
Implement iterate_recraft() using imageToImage endpoint
Implement iterate_gemini() with multi-turn conversation
Implement iterate_openai() using images.edit endpoint
Add get_iterate_handler() dispatcher
```

---

## Task 6: Implement Outpainting Handlers

**Goal:** Add `outpaint()` methods to each provider handler that expand images using aspect presets.

**Files to Modify/Create:**
- `backend/src/models/handlers.py` - Add outpaint functions
- `backend/src/utils/outpaint.py` - New utility for aspect calculations

**Prerequisites:**
- Task 5 complete (iteration handlers as reference)

**Implementation Steps:**

1. **Create outpaint utility module:**
   ```python
   # backend/src/utils/outpaint.py

   def calculate_expansion(width: int, height: int, preset: str) -> Dict:
       """
       Calculate expansion pixels for aspect preset.

       Args:
           width: Current image width
           height: Current image height
           preset: '16:9', '9:16', '1:1', '4:3', 'expand_all'

       Returns:
           {
               'left': int, 'right': int, 'top': int, 'bottom': int,
               'new_width': int, 'new_height': int
           }
       """

   def create_expansion_mask(width: int, height: int, expansion: Dict) -> bytes:
       """Create binary mask with transparent edges for expansion."""
   ```

2. **Implement preset calculations:**
   - `16:9`: Calculate horizontal expansion to reach 16:9 ratio
   - `9:16`: Calculate vertical expansion to reach 9:16 ratio
   - `1:1`: Expand shorter dimension to match longer
   - `4:3`: Calculate expansion to reach 4:3 ratio
   - `expand_all`: Add 50% to each edge uniformly

3. **Add `outpaint_flux()` function:**
   - Use FLUX Fill with edge mask
   - Pad image with transparency, create mask
   ```python
   def outpaint_flux(model_config: Dict, source_image: bytes, preset: str, prompt: str) -> Dict:
       expansion = calculate_expansion(w, h, preset)
       padded_image = pad_image(source_image, expansion)
       mask = create_expansion_mask(w, h, expansion)
       # Call FLUX Fill with padded image + mask + prompt
   ```

4. **Add `outpaint_recraft()` function:**
   - Use Recraft outpaint endpoint
   - Pass direction parameters based on expansion
   ```python
   def outpaint_recraft(model_config: Dict, source_image: bytes, preset: str, prompt: str) -> Dict:
       expansion = calculate_expansion(w, h, preset)
       # Recraft supports direction-based outpainting
   ```

5. **Add `outpaint_gemini()` function:**
   - Use prompt-based approach
   - "Extend this image [direction] to show [prompt]"
   ```python
   def outpaint_gemini(model_config: Dict, source_image: bytes, preset: str, prompt: str) -> Dict:
       direction_text = get_direction_description(preset)
       full_prompt = f"Extend this image {direction_text}. {prompt}"
       # Use generate_content with image + expansion prompt
   ```

6. **Add `outpaint_openai()` function:**
   - Pad canvas with transparency
   - Use images.edit with padded image
   ```python
   def outpaint_openai(model_config: Dict, source_image: bytes, preset: str, prompt: str) -> Dict:
       expansion = calculate_expansion(w, h, preset)
       padded_image = pad_image_with_transparency(source_image, expansion)
       # Call images.edit with padded image + prompt
   ```

7. **Add `get_outpaint_handler()` dispatcher.**

**Verification Checklist:**
- [x] `calculate_expansion()` correct for all presets
- [x] Mask generation creates valid binary masks
- [x] Each handler returns expanded image
- [x] Presets produce expected aspect ratios
- [x] Error handling for unsupported dimensions

**Testing Instructions:**
- Unit tests for expansion calculations (math verification)
- Unit tests for mask generation
- Integration tests with mocked APIs

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(backend): add outpainting handlers with aspect presets

Add calculate_expansion() for 5 aspect presets
Implement outpaint_flux() with FLUX Fill edge masks
Implement outpaint_recraft() with direction parameters
Implement outpaint_gemini() with prompt-based expansion
Implement outpaint_openai() with canvas padding
```

---

## Task 7: Add API Endpoints

**Goal:** Implement `/iterate` and `/outpaint` Lambda handler routes.

**Files to Modify/Create:**
- `backend/src/lambda_function.py` - Add new route handlers

**Prerequisites:**
- Task 4 complete (session manager)
- Task 5 complete (iteration handlers)
- Task 6 complete (outpaint handlers)

**Implementation Steps:**

1. **Add `/iterate` POST handler:**
   ```python
   def handle_iterate(event: Dict) -> Dict:
       """
       Iterate on an existing image.

       Request body:
       {
           "sessionId": "uuid",
           "model": "flux|recraft|gemini|openai",
           "prompt": "refinement instruction"
       }

       Response:
       {
           "sessionId": "uuid",
           "model": "flux",
           "iteration": 3,
           "status": "in_progress",
           "jobId": "uuid"  # For polling
       }
       """
       # 1. Validate session exists
       # 2. Check iteration limit (return 400 if >= 7)
       # 3. Get latest image for model
       # 4. Get conversation context
       # 5. Add iteration to session (in_progress)
       # 6. Call iterate handler
       # 7. Update session with result
       # 8. Update context window
       # 9. Return response
   ```

2. **Add `/outpaint` POST handler:**
   ```python
   def handle_outpaint(event: Dict) -> Dict:
       """
       Expand an image using aspect preset.

       Request body:
       {
           "sessionId": "uuid",
           "model": "flux|recraft|gemini|openai",
           "iterationIndex": 2,  # Which image to expand
           "preset": "16:9|9:16|1:1|4:3|expand_all",
           "prompt": "description for expanded area"
       }

       Response:
       {
           "sessionId": "uuid",
           "model": "flux",
           "iteration": 3,  # New iteration created
           "status": "in_progress"
       }
       """
       # 1. Validate session and iteration exist
       # 2. Check iteration limit
       # 3. Get source image
       # 4. Add iteration to session
       # 5. Call outpaint handler
       # 6. Update session with result
       # 7. Return response
   ```

3. **Update route dispatcher** in `lambda_handler()`:
   ```python
   if path == '/iterate' and method == 'POST':
       return handle_iterate(event)
   elif path == '/outpaint' and method == 'POST':
       return handle_outpaint(event)
   ```

4. **Add input validation:**
   - Session ID format (UUID)
   - Model name (one of 4)
   - Prompt length (1-1000 chars)
   - Preset value (one of 5)

5. **Add iteration limit check:**
   - Return 400 with `ITERATION_LIMIT` code if >= 7

**Verification Checklist:**
- [x] `/iterate` creates new iteration and returns job ID
- [x] `/outpaint` creates new iteration with expanded image
- [x] 400 returned when iteration limit exceeded
- [x] 404 returned for invalid session/model
- [x] Input validation rejects invalid data
- [x] CORS headers present on responses

**Testing Instructions:**
- Unit tests for input validation
- Integration tests with mocked handlers
- Test iteration limit enforcement

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

feat(backend): add /iterate and /outpaint API endpoints

Implement handle_iterate() for image refinement
Implement handle_outpaint() for aspect-based expansion
Add input validation for all parameters
Enforce 7-iteration limit per model column
Return appropriate error codes for edge cases
```

---

## Task 8: Update Generate Endpoint

**Goal:** Modify `/generate` to create sessions with 4 models and support partial results.

**Files to Modify/Create:**
- `backend/src/lambda_function.py` - Update `handle_generate()`
- `backend/src/jobs/executor.py` - Update for 4-model execution

**Prerequisites:**
- Task 2 complete (config with enabled models)
- Task 4 complete (session manager)

**Implementation Steps:**

1. **Update `handle_generate()` to use session manager:**
   ```python
   def handle_generate(event: Dict) -> Dict:
       # 1. Validate prompt
       # 2. Get enabled models from config
       # 3. Create session with enabled models
       # 4. Execute all models in parallel with retry
       # 5. Return session ID and initial status
   ```

2. **Update executor for 4-model parallel execution:**
   ```python
   def execute_session(session_id: str, prompt: str, models: List[ModelConfig]) -> None:
       """
       Execute initial generation for all enabled models.

       Uses ThreadPoolExecutor with auto-retry on failure.
       """
       with ThreadPoolExecutor(max_workers=4) as executor:
           futures = {
               executor.submit(execute_with_retry, model, prompt): model
               for model in models
           }
           for future in as_completed(futures):
               model = futures[future]
               try:
                   result = future.result()
                   # Update session with success
               except Exception as e:
                   # Update session with error
   ```

3. **Implement auto-retry logic:**
   ```python
   def execute_with_retry(model: ModelConfig, prompt: str, max_retries: int = 1) -> Dict:
       for attempt in range(max_retries + 1):
           try:
               handler = get_handler(model.provider)
               return handler({'id': model.model_id, 'api_key': model.api_key}, prompt, {})
           except Exception as e:
               if attempt == max_retries:
                   raise
               time.sleep(2)  # 2 second backoff
   ```

4. **Support partial results:**
   - Continue execution even if some models fail
   - Session status reflects partial completion
   - Failed models show error in response

**Verification Checklist:**
- [x] Session created with all enabled models
- [x] All enabled models execute in parallel
- [x] Failed models retry once automatically
- [x] Partial results returned if some fail
- [x] Session status accurate (completed/partial/failed)

**Testing Instructions:**
- Unit tests for retry logic
- Integration tests with mocked handlers
- Test partial failure scenarios

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

refactor(backend): update /generate for session-based storage

Create sessions instead of jobs
Execute 4 models in parallel with auto-retry
Support partial results on model failures
Return session ID for status polling
```

---

## Task 9: Update Status Endpoint

**Goal:** Modify `/status/{id}` to return session status with iteration details.

**Files to Modify/Create:**
- `backend/src/lambda_function.py` - Update `handle_status()`

**Prerequisites:**
- Task 4 complete (session manager)
- Task 8 complete (generate creates sessions)

**Implementation Steps:**

1. **Update response format:**
   ```python
   def handle_status(event: Dict) -> Dict:
       """
       Get session status with all iterations.

       Response:
       {
           "sessionId": "uuid",
           "status": "in_progress|completed|partial|failed",
           "prompt": "original prompt",
           "createdAt": "ISO8601",
           "updatedAt": "ISO8601",
           "models": {
               "flux": {
                   "enabled": true,
                   "status": "completed",
                   "iterations": [
                       {
                           "index": 0,
                           "status": "completed",
                           "imageUrl": "https://cloudfront.../flux-0.png",
                           "prompt": "original prompt",
                           "completedAt": "ISO8601"
                       },
                       // ... more iterations
                   ]
               },
               // ... other models
           }
       }
       """
   ```

2. **Generate CloudFront URLs for images:**
   - Convert S3 keys to CloudFront URLs
   - Include for all completed iterations

3. **Handle disabled models:**
   - Include in response with `enabled: false`
   - Empty iterations array

**Verification Checklist:**
- [x] Response includes all 4 models
- [x] Disabled models marked appropriately
- [x] All iterations included with URLs
- [x] Status computed correctly
- [x] Timestamps present

**Testing Instructions:**
- Unit tests for response format
- Test with various session states

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

refactor(backend): update /status for session-based responses

Return session status with iteration details
Include all 4 models with enabled flag
Generate CloudFront URLs for completed images
Compute overall status from model statuses
```

---

## Task 10: Update Gallery Endpoints

**Goal:** Modify gallery endpoints to return sessions grouped by original prompt.

**Files to Modify/Create:**
- `backend/src/lambda_function.py` - Update gallery handlers

**Prerequisites:**
- Task 4 complete (session manager)

**Implementation Steps:**

1. **Update `/gallery/list` response:**
   ```python
   {
       "sessions": [
           {
               "sessionId": "uuid",
               "prompt": "a sunset over mountains",
               "createdAt": "ISO8601",
               "modelCount": 4,
               "totalIterations": 12,  # Sum across all models
               "thumbnail": "https://cloudfront.../flux-0.png"  # First image
           },
           // ... more sessions
       ]
   }
   ```

2. **Update `/gallery/{id}` response:**
   - Return full session status (same as `/status/{id}`)

3. **Sort sessions by creation date** (newest first)

4. **Limit list to recent sessions** (e.g., last 50)

**Verification Checklist:**
- [x] List returns sessions sorted by date
- [x] Each session includes prompt and stats
- [x] Thumbnail URL points to valid image
- [x] Detail endpoint returns full session

**Testing Instructions:**
- Unit tests for list format
- Test sorting and limits

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

refactor(backend): update gallery endpoints for sessions

Return sessions grouped by prompt
Include iteration count and thumbnail
Sort by creation date (newest first)
Limit list to 50 most recent sessions
```

---

## Task 11: Update Deploy Script

**Goal:** Modify `deploy.js` to support new configuration schema with enable/disable flags.

**Files to Modify/Create:**
- `backend/scripts/deploy.js` - Update for new schema
- `backend/.env.deploy.example` - Update example file
- `.gitignore` - Add `.deploy-config.json`

**Prerequisites:**
- Task 1 complete (new SAM parameters)

**Implementation Steps:**

1. **Update `.deploy-config.json` schema** as defined in Phase 0

2. **Implement interactive prompts** for missing values:
   - Use `readline` module for CLI interaction
   - Prompt for each model's enabled status
   - Prompt for API keys only if model enabled
   - Save responses to `.deploy-config.json`

3. **Update `buildParameterOverrides()` function:**
   ```javascript
   function buildParameterOverrides(config) {
       const overrides = [
           `FluxEnabled=${config.models.flux.enabled}`,
           // Only include API key if enabled
           ...(config.models.flux.enabled ? [`FluxApiKey=${config.models.flux.apiKey}`] : []),
           // ... similar for other models
       ];
       return overrides;
   }
   ```

4. **Update frontend `.env` generation:**
   - Include `VITE_{MODEL}_ENABLED` variables
   - Frontend uses these to show/hide columns

5. **Add configuration validation:**
   - At least one model must be enabled
   - Enabled models must have API keys (except local testing)

**Verification Checklist:**
- [ ] Interactive prompts work for fresh setup
- [ ] Saved config loads correctly on subsequent runs
- [ ] Parameter overrides generated correctly
- [ ] Frontend .env includes enabled flags
- [ ] Validation catches missing API keys

**Testing Instructions:**
- Manual test: Run deploy script fresh
- Manual test: Run with existing config
- Unit tests for validation logic

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

refactor(deploy): update script for 4-model configuration

Add interactive prompts for model enable/disable
Save configuration to .deploy-config.json
Generate parameter overrides for enabled models only
Update frontend .env with enabled flags
Add validation for required API keys
```

---

## Task 12: Backend Unit Tests

**Goal:** Write comprehensive unit tests for all new backend functionality.

**Files to Modify/Create:**
- `backend/tests/unit/test_config.py` - Config module tests
- `backend/tests/unit/test_context.py` - Context manager tests
- `backend/tests/unit/test_session.py` - Session manager tests
- `backend/tests/unit/test_handlers_iterate.py` - Iteration handler tests
- `backend/tests/unit/test_handlers_outpaint.py` - Outpaint handler tests
- `backend/tests/unit/test_outpaint_utils.py` - Outpaint calculation tests
- `backend/tests/requirements.txt` - Test dependencies

**Prerequisites:**
- All previous tasks complete

**Implementation Steps:**

1. **Add test dependencies:**
   ```
   pytest>=7.0
   pytest-cov>=4.0
   moto>=4.0
   responses>=0.23
   ```

2. **Write config tests:**
   - Test `get_enabled_models()` with various combinations
   - Test `get_model()` for enabled/disabled models
   - Test default values

3. **Write context manager tests:**
   - Test empty context retrieval
   - Test add entry and window overflow
   - Test corrupted JSON handling

4. **Write session manager tests:**
   - Test session creation
   - Test iteration addition and limit
   - Test concurrent updates

5. **Write iteration handler tests:**
   - Mock API responses for each provider
   - Test success and error paths
   - Test context utilization

6. **Write outpaint tests:**
   - Test expansion calculations for all presets
   - Test mask generation
   - Test handler calls

**Verification Checklist:**
- [ ] All tests pass: `pytest backend/tests/unit/ -v`
- [ ] Coverage >80%: `pytest --cov=src backend/tests/unit/`
- [ ] No live API calls in tests
- [ ] All edge cases covered

**Testing Instructions:**
```bash
cd backend
pip install -r tests/requirements.txt
PYTHONPATH=src pytest tests/unit/ -v --tb=short
```

**Commit Message Template:**
```
Author & Committer: HatmanStack
Email: 82614182+HatmanStack@users.noreply.github.com

test(backend): add comprehensive unit tests for v2 features

Add tests for config module with enable/disable
Add tests for context manager window behavior
Add tests for session manager with iteration limits
Add tests for iteration handlers with mocked APIs
Add tests for outpaint calculations and handlers
Achieve 80%+ code coverage
```

---

## Phase Verification

### Test Suite Execution

```bash
# Run all backend tests
cd backend
PYTHONPATH=src pytest tests/ -v --tb=short

# Run with coverage
PYTHONPATH=src pytest tests/unit/ --cov=src --cov-report=html
open htmlcov/index.html
```

### Manual Verification

```bash
# Validate SAM template
cd backend && sam validate

# Build successfully
sam build

# Local invocation (requires .env.deploy)
sam local invoke -e events/generate.json
```

### Integration Points to Test

1. **Generate → Status flow**: Create session, poll status, see all 4 models
2. **Iterate flow**: Generate, then iterate on one model
3. **Outpaint flow**: Generate, then outpaint with aspect preset
4. **Iteration limit**: Attempt 8th iteration, receive error

### Known Limitations

1. **No migration**: Existing jobs not converted to sessions
2. **Synchronous iteration**: Each iteration waits for completion
3. **Provider differences**: Outpaint quality varies by provider
4. **Context limitations**: Only 3 iterations in context window

---

## Next Phase

Proceed to [Phase 2: Frontend Redesign](./Phase-2.md) to implement the column-based UI, iteration controls, and gallery reorganization.
