# Feature: Provider Swap & Column Focus UI

## Overview

Replace the current 4 image generation providers (Flux/BFL, Recraft, Gemini, OpenAI) with a new set of 4 providers: Google Gemini Nano Banana 2, Amazon Nova Canvas, OpenAI DALL-E 3, and Adobe Firefly Image5. This involves removing all Flux and Recraft code (handlers, tests, config), updating the Gemini handler to target the latest model, keeping the OpenAI handler targeting DALL-E 3, and implementing two entirely new provider integrations (Nova Canvas via AWS Bedrock, Firefly via Adobe's OAuth2 API).

Simultaneously, redesign the frontend column layout to support a focus/expand interaction. Clicking a model column smoothly animates it to ~60% width while the other three compress to ~13% each. The focused column reveals additional controls (outpaint, download, full iteration history, iteration counter, model selection checkbox) while compressed columns remain interactive, showing the latest image and iteration input. The shared prompt input at the top and per-column iteration inputs remain unchanged in behavior.

The application continues to enforce exactly 4 fixed models with parallel generation, per-model iteration (up to 7 iterations with rolling 3-iteration context), and outpaint support for all providers.

## Decisions

1. **Provider lineup**: Gemini Nano Banana 2, Amazon Nova Canvas, OpenAI DALL-E 3, Adobe Firefly Image5 — replacing Flux/BFL and Recraft
2. **Gemini model ID**: Update from `gemini-2.5-flash-image` to `gemini-3.1-flash-image-preview` (Nano Banana 2)
3. **Nova Canvas auth**: Use Lambda's existing IAM role with `bedrock:InvokeModel` permission added to SAM template — no separate API key needed
4. **Firefly auth**: OAuth2 client credentials flow, fetch fresh access token per request (~100-200ms overhead), no token caching — simplest approach for Lambda
5. **Handler coverage**: All 4 providers get all 3 handler types (generate, iterate, outpaint) from day one
6. **Internal keys**: `gemini`, `nova`, `openai`, `firefly` — keeps existing Gemini and OpenAI keys, adds new ones for Nova and Firefly
7. **Display names**: Gemini, Nova Canvas, DALL-E 3, Firefly
8. **Column order**: `['gemini', 'nova', 'openai', 'firefly']` (left to right)
9. **Focus animation**: Smooth transition — focused column expands to ~60% width, others compress to ~13% each (all remain visible)
10. **Focused column controls**: Shows outpaint, download, full iteration history, iteration counter, model selection checkbox, plus iteration input
11. **Compressed column content**: Shows latest image thumbnail + iteration input (still interactive without focusing)
12. **Prompt UX**: Unchanged — shared prompt at top for parallel generation, per-column iteration inputs below each model
13. **Old code cleanup**: Clean delete of all Flux/BFL and Recraft handler code, tests, and config — no backwards compatibility

## Scope: In

- Remove Flux/BFL provider: handler code, config, env vars, tests
- Remove Recraft provider: handler code, config, env vars, tests
- Update Gemini config to target `gemini-3.1-flash-image-preview` (Nano Banana 2)
- Confirm OpenAI handler works correctly with DALL-E 3 as explicit target
- Implement Amazon Nova Canvas provider: generate, iterate, outpaint handlers via Bedrock API
- Implement Adobe Firefly provider: generate, iterate, outpaint handlers via Firefly Services API with OAuth2 auth
- Add `bedrock:InvokeModel` permission to Lambda IAM role in SAM template
- Add Firefly env vars: `FIREFLY_CLIENT_ID`, `FIREFLY_CLIENT_SECRET`, `FIREFLY_ENABLED`, `FIREFLY_MODEL_ID`
- Add Nova env vars: `NOVA_ENABLED`, `NOVA_MODEL_ID` (auth via IAM role, no API key)
- Update `ModelName` type from `'flux' | 'recraft' | 'gemini' | 'openai'` to `'gemini' | 'nova' | 'openai' | 'firefly'`
- Update `MODELS` array ordering to `['gemini', 'nova', 'openai', 'firefly']`
- Implement column focus/expand behavior with smooth CSS transitions
- Focused column at ~60% width with full controls visible
- Compressed columns at ~13% width with latest image + iteration input
- Add `focusedModel` state to manage which column is expanded
- Update all frontend tests for new model names
- Update all backend tests for new providers
- Update `config.py` model definitions
- Update `backend/.env.example` and `frontend/.env.example`
- Update CLAUDE.md documentation

## Scope: Out

- Mobile layout changes (focus behavior is desktop-only; mobile keeps snap-scroll)
- DynamoDB migration for session state (S3 remains)
- Thumbnail generation system for gallery previews (separate concern from audit)
- Gallery response payload optimization (separate concern from audit)
- Token caching for Firefly OAuth2 (per-request token fetch is sufficient)
- Any 5th+ provider support
- Changes to the prompt enhancement system
- Changes to rate limiting, content filtering, or session lifecycle

## Open Questions

- **Nova Canvas iteration API**: Does Bedrock's Nova Canvas support image-to-image refinement natively, or will iteration need to use image conditioning with the original + prompt? Planner should research the exact Bedrock API shape for image editing/inpainting.
- **Firefly iteration API**: Does the Firefly API support iterative image editing (inpainting/refining from a source image), or only text-to-image? Planner should research the Firefly Services API for edit/refine endpoints.
- **Firefly outpaint**: Does Firefly support generative expand / outpainting natively? If not, the outpaint handler may need to use a different approach (e.g., canvas resize + inpaint).
- **Nova Canvas outpaint**: Similar question — does Nova Canvas have a native outpaint/expand capability or does it need to be composed from inpainting?
- **DALL-E 3 iteration**: The current `handle_openai` iterate handler uses `images.edit` (inpainting) which is a DALL-E 2 feature. DALL-E 3 does not support `images.edit`. Planner needs to determine if we use DALL-E 2 for iteration while DALL-E 3 for generation, use GPT-Image-1 for iteration, or use a prompt-chaining approach.

## Relevant Codebase Context

### Backend
- `backend/src/config.py` — Model definitions as frozen dataclasses, env var loading, `MODELS` dict, `get_enabled_models()`, `get_model()`, `get_model_config_dict()`
- `backend/src/models/handlers.py` — All 12 handlers (3 types x 4 providers) in single 777-line file. Registry pattern via `get_handler()`, `get_iterate_handler()`, `get_outpaint_handler()` dicts. `HandlerFunc`, `IterateHandlerFunc`, `OutpaintHandlerFunc` type aliases.
- `backend/src/utils/clients.py` — Cached API client factories with composite cache keys for Lambda container reuse. New providers will follow this pattern.
- `backend/src/lambda_function.py` — Entry point, routing, parallel generation via `ThreadPoolExecutor`. Module-level singleton initialization.
- `backend/src/models/context.py` — `ContextManager` for rolling 3-iteration context window per model in S3
- `backend/src/jobs/manager.py` — `SessionManager` with S3-based session state and optimistic locking
- `backend/template.yaml` — SAM template defining Lambda, IAM role, API Gateway. Bedrock permission needs to be added here.
- `backend/src/utils/storage.py` — `ImageStorage` handles S3 upload and CloudFront URL generation

### Frontend
- `frontend/src/types/api.ts` — `ModelName` type union, `MODELS` array, `Session`, `ModelColumn`, `Iteration` interfaces
- `frontend/src/stores/useAppStore.ts` — Zustand store with session state, `selectedModels`, `iterationWarnings` keyed by `ModelName`
- `frontend/src/components/generation/GenerationPanel.tsx` — Maps over `MODELS` array to render `ModelColumn` components in flex container
- `frontend/src/components/generation/ModelColumn.tsx` — Fixed width (`min-w-[250px] max-w-[300px]`), contains iteration cards, iteration input, outpaint controls. Wrapped in `memo()`.
- `frontend/src/components/generation/IterationInput.tsx` — Per-column text input for refinement
- `frontend/src/components/generation/IterationCard.tsx` — Individual iteration display with image
- `frontend/src/components/generation/OutpaintControls.tsx` — Aspect ratio preset buttons
- `frontend/src/hooks/useIteration.ts` — Per-model iteration hook with limit checking (`MAX_ITERATIONS = 7`)
- `frontend/src/hooks/useSessionPolling.ts` — Polls `/status/{sessionId}` with stale-closure guards
- `frontend/src/components/layout/DesktopLayout.tsx` — 2-column grid (gallery + generation)
- `frontend/src/api/client.ts` — API client with retry logic

### Tests
- `tests/backend/unit/test_handlers.py` — Handler unit tests per provider
- `tests/backend/unit/test_iterate_handlers.py` — Iterate handler tests with contract verification
- `tests/backend/unit/test_lambda_function.py` — Integration-style Lambda handler tests
- `frontend/tests/__tests__/` — Vitest + React Testing Library tests for components, hooks, stores

### Existing Patterns to Follow
- Handler functions return `{'status': 'success', 'image': base64_str}` or `{'status': 'error', 'error': msg}`
- Client caching via `_client_cache` dict with composite key in `utils/clients.py`
- Exponential backoff via `@with_retry` decorator in `utils/retry.py`
- Error sanitization via `sanitize_error_message()` strips API keys from error messages
- Config via frozen dataclasses with env var overrides

## Technical Constraints

- **Lambda execution**: 900s timeout, 3008 MB memory, 10 reserved concurrent executions
- **Bedrock access**: Lambda IAM role must include `bedrock:InvokeModel` for `amazon.nova-canvas-v1:0` (or current model ARN). Region must have Nova Canvas available.
- **Firefly API**: Requires Adobe Developer Console project with Firefly Services entitlement. OAuth2 client credentials grant. Rate limits TBD.
- **DALL-E 3 limitation**: Does not support `images.edit` endpoint — iteration strategy needs research (see Open Questions)
- **S3 session structure**: Unchanged — `sessions/{sessionId}/status.json` with per-model iteration arrays
- **Python 3.13 runtime**: No new runtime dependencies for Bedrock (boto3 already available). Firefly needs HTTP client (use `urllib3` or `requests` — check what's already available).
- **Frontend bundle**: No new npm dependencies expected — column focus is pure CSS/Tailwind transitions + Zustand state
