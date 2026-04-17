# Phase 0: Foundation

## Phase Goal

Establish architecture decisions, conventions, and testing strategy that all implementation phases inherit. No code ships in this phase.

**Success criteria:**

- All ADRs documented and numbered
- Testing strategy defined for both new storage format and DynamoDB items
- Project conventions section captures all relevant patterns from CLAUDE.md

**Token estimate:** ~5,000

## Project Conventions

These conventions are derived from `CLAUDE.md` and the existing codebase. All phases must follow them.

- **Package manager:** `uv` for Python, `npm` for frontend. Never bare `pip`.
- **Python runtime:** 3.13
- **Backend test command:** `PYTHONPATH=backend/src pytest tests/backend/unit/ -v`
- **Frontend test command:** `cd frontend && npm test`
- **Linting:** `ruff check backend/src/` (rules E/F/W/I, line-length 100, ignore E501) and `npm run lint` + `npm run typecheck` for frontend
- **Coverage gate:** 80% backend, enforced in CI
- **Commit format:** Conventional commits (`feat(scope): description`, `test(scope): ...`, `refactor(scope): ...`)
- **Framework versions:** React 19, Zustand 5, Tailwind CSS 4, Vite 8, Vitest 4
- **Backend patterns:** Frozen dataclasses for config, optimistic locking via S3 ETag, retry with `@retry_with_backoff` decorator, `StructuredLogger` for all logging
- **Frontend patterns:** Zustand stores (not Context API), hooks for side effects, `apiFetch` wrapper for API calls, `ErrorBoundary` wrappers for components
- **DynamoDB patterns:** Single-table design on `pixel-prompt-users`, `userId` as partition key, synthetic prefixes for non-user items (`guest#`, `config#model#`, `revenue#`, `metrics#`)
- **SAM template:** `backend/template.yaml`, deploy via `sam build && sam deploy`
- **Test mocking:** `moto` for S3 and DynamoDB in backend tests, Vitest mocks for frontend
- **MODELS constant:** Always exactly 4: gemini, nova, openai, firefly

## Architecture Decisions

### ADR-1: Raw Image Storage in S3

**Decision:** Replace the current pattern of storing images as JSON files containing base64-encoded image data with raw binary image files (PNG/JPEG) stored directly in S3.

**Context:** Currently `storage.py:_store_image()` wraps the base64 image string in a JSON metadata object and stores it with `ContentType: application/json`. This means:

- Images are inflated 33% by base64 encoding
- CloudFront serves JSON, not images -- browsers cannot render or cache them natively
- Every image view requires Lambda to fetch JSON, parse it, and extract base64
- API Gateway's 10MB payload limit constrains image delivery
- Presigned download URLs would serve JSON, not a real image file

**New pattern:**

- `upload_image()` decodes the base64 string to raw bytes and stores as `sessions/{target}/{model}-{timestamp}{iter_suffix}.png` with `ContentType: image/png`
- Image metadata (model, prompt, timestamp) is already stored in `status.json` per-iteration, so no separate metadata file is needed
- `get_cloudfront_url()` returns a URL to the raw image -- browsers render it directly with `<img src=...>`
- For iterate/outpaint source image loading, `_load_source_image()` reads raw bytes from S3 and base64-encodes them for the handler (handlers expect `str | bytes` per `_common.py` type hints)

**Backward compatibility:** Old sessions with `.json` image files will continue to work during the 30-day S3 lifecycle window. `_load_source_image()` must detect the file extension and handle both formats: if the key ends in `.json`, read and parse JSON to extract `output`; if `.png`/`.jpg`, read raw bytes. Gallery handlers must similarly handle both formats. After 30 days, all old sessions auto-delete via S3 lifecycle.

**Consequences:**

- Images served directly by CloudFront with standard browser caching
- ~33% reduction in S3 storage cost
- Lambda is no longer in the image serving path
- Presigned download URLs are trivial (`s3.generate_presigned_url` on the image key)
- 30-day transition period where both formats coexist

### ADR-2: Per-Model Prompt Adaptation via Structured LLM Output

**Decision:** Add an `adapt_per_model()` method to `PromptEnhancer` that makes a single LLM call returning a JSON object with 4 model-specific prompt variants. This runs automatically during `/generate` before model dispatch.

**Context:** Each image generation provider has different strengths. DALL-E 3 handles typography and precise composition well. Gemini excels at photorealism. Nova Canvas is strong with artistic styles. Firefly produces clean commercial imagery. A single generic prompt leaves performance on the table.

**Design:**

- New method `PromptEnhancer.adapt_per_model(prompt: str, enabled_models: list[str]) -> dict[str, str]`
- Returns `{"gemini": "adapted...", "nova": "adapted...", ...}` for each enabled model
- Model knowledge lives entirely in the system prompt text (not in config metadata)
- Falls back to the original prompt for all models if the LLM call fails or JSON parsing fails
- Timeout of 10 seconds on the adaptation call (fail fast, don't block generation)
- Adapted prompt stored per-iteration in `status.json` as a new `adaptedPrompt` field alongside the existing `prompt` field

**Integration point:** In `handle_generate()`, after validation and before `generate_for_model()` dispatch. The adapted prompts dict is passed to `generate_for_model()` so each model receives its tailored prompt. The original user prompt is still stored as the session-level `prompt`.

**Consequences:**

- Adds one LLM call (with timeout) to generation latency
- Each model gets a prompt tuned to its strengths
- Users can see what each model actually received (transparency)
- Graceful degradation: if adaptation fails, original prompt is used for all models

### ADR-3: Prompt History in DynamoDB Single-Table

**Decision:** Store prompt history records in the existing `pixel-prompt-users` DynamoDB table using the single-table pattern.

**Schema:**

Add a GSI named `PromptHistoryIndex` with partition key `promptOwner` (string) and sort key `createdAt` (number). The base table `userId` remains the sole primary key (no sort key change). Each prompt history record uses a unique `userId` value (`prompt#<uuid>`) so it does not collide with user or synthetic items.

**Item structure (base table):**

```text
userId:      prompt#<uuid>           (PK, unique per record)
promptOwner: USER#<cognito_sub>      (GSI PK -- or GLOBAL#RECENT for feed)
createdAt:   <epoch_int>             (GSI SK -- enables ScanIndexForward=False for newest-first)
prompt:      <string>
sessionId:   <string>
ttl:         <epoch_int>             (optional, 7-day for feed items)
```

**Query patterns:**

- "My prompt history": Query GSI with `promptOwner = USER#<sub>`, `ScanIndexForward=False`, `Limit=50`
- "Global recent feed": Query GSI with `promptOwner = GLOBAL#RECENT`, `ScanIndexForward=False`, `Limit=50`
- "Search my prompts": Query GSI + FilterExpression `contains(prompt, :q)`

**Caps:**

- Global feed: 50 items, 7-day TTL (whichever limit hits first). New items beyond 50 are naturally pruned by TTL.
- Per-user: no cap (negligible storage cost per prompt record)

**Auth gating:**

- Writing per-user history: requires authenticated user (`AUTH_ENABLED=true` and signed in)
- Writing global feed: happens on every `/generate` call regardless of auth
- Reading per-user history: requires auth (endpoint returns 401 for guests)
- Reading global feed: public (no auth required)

**Consequences:**

- One new GSI on the existing table (no base table schema change)
- Feed items auto-clean via TTL
- Prompt search is basic (`contains` filter) but sufficient for v1

### ADR-4: Comparison Modal with Iteration Picker

**Decision:** Build a full-screen modal overlay that shows 2-4 selected models' images side-by-side at equal size, with a per-slot iteration picker dropdown.

**Activation:** User selects 2+ models via existing multi-select checkboxes, then clicks a new "Compare" button that appears in the `GenerationPanel` toolbar area (next to the `MultiIterateInput`).

**UI structure:**

- Full-screen modal (uses existing `useUIStore.isModalOpen` pattern or a dedicated `isCompareOpen` state)
- Grid of 2-4 equal-width slots, responsive (2-up on small screens, 3-4 on desktop)
- Each slot shows: model name, current image at full width, iteration picker dropdown (defaults to latest completed)
- Close via ESC key, close button, or clicking outside

**State:** New `useUIStore` fields: `isCompareOpen: boolean`, `compareModels: ModelName[]`. The iteration selection per slot is local state within the modal component.

**Consequences:**

- Leverages existing multi-select machinery
- No new API calls (images already loaded in session state)
- Modal pattern is consistent with existing `ImageModal`

### ADR-5: Presigned URL Download

**Decision:** Add a `GET /download/{sessionId}/{model}/{iterationIndex}` endpoint that returns a presigned S3 URL for the raw image file. The frontend redirects the browser to this URL to trigger a download.

**Alternative considered:** Client-side blob download (decode base64 in browser). Rejected because the storage refactor removes base64 from the frontend path entirely -- images are now served as real files via CloudFront URLs. A presigned URL with `Content-Disposition: attachment` is the cleanest approach.

**Presigned URL parameters:**

- Expiry: 300 seconds (5 minutes)
- Response headers: `Content-Disposition: attachment; filename="{model}-{iteration}.png"`, `Content-Type: image/png`

**Auth:** Same as `/status` -- no JWT required. The session ID is the access token (unguessable UUID). If `AUTH_ENABLED=true`, the endpoint still does not require JWT because image downloads should work for shared links.

## Testing Strategy

### Backend

- **Storage refactor tests:** Use `moto` mock S3. Test that `upload_image` stores raw bytes with correct Content-Type. Test that `_load_source_image` handles both old JSON format and new raw format. Test presigned URL generation.
- **Prompt adaptation tests:** Mock the LLM client. Test JSON parsing of 4-model response. Test fallback when LLM returns invalid JSON. Test timeout behavior.
- **Prompt history tests:** Use `moto` mock DynamoDB. Test write + query via GSI. Test TTL is set correctly on feed items. Test the 50-item feed cap behavior.
- **Download endpoint tests:** Use `moto` mock S3. Test presigned URL generation with correct response headers. Test 404 for missing sessions.
- **Backward compatibility tests:** Create old-format JSON image files in mock S3, verify they can still be read by `_load_source_image` and gallery handlers.

### Frontend

- **Comparison modal tests:** Render with mock session data, verify model slots appear, test iteration picker changes, test ESC closes modal.
- **Download button tests:** Verify button renders on completed iteration cards, mock API call for download URL.
- **Adapted prompt display tests:** Render IterationCard with `adaptedPrompt` field, verify expandable section appears and toggles.
- **Prompt history tests:** Mock API responses, verify history list renders, test re-run populates prompt input, test recent feed renders for unauthenticated users.

## Commit Message Format

All commits use conventional commits:

```text
feat(storage): store raw images in S3 instead of base64 JSON
test(storage): add backward compatibility tests for old format
feat(enhance): add per-model prompt adaptation
feat(prompts): add prompt history DynamoDB repository
feat(frontend): add comparison modal with iteration picker
```
