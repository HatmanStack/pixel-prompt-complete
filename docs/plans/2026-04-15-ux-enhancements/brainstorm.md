# Feature: UX Enhancements — Storage Refactor, Prompt History, Prompt Adaptation, Comparison, Download

## Overview

This plan delivers five interlocking improvements to Pixel Prompt Complete, all grounded in the application's core value proposition: helping users find the best AI-generated image faster by comparing results across providers without context switching.

The foundational change is a storage refactor that replaces the current base64-in-JSON image storage pattern with raw image files in S3 referenced by key. This eliminates 33% storage bloat from base64 encoding, enables CloudFront to serve images directly (bypassing Lambda and API Gateway entirely), unlocks standard browser and CDN caching, and makes presigned download URLs trivial. Every feature in this plan benefits from this change.

On top of that foundation, four user-facing features ship: (1) prompt history with per-user DynamoDB records and a global recent prompts feed, (2) automatic per-model prompt adaptation that tailors the user's prompt to each provider's strengths at generation time, (3) a side-by-side comparison modal for evaluating results across models, and (4) one-click image download via presigned S3 URLs.

## Decisions

1. **Image storage format**: Replace base64-in-JSON with raw image files in S3. Metadata references images by S3 key. Old format ages out via existing 30-day S3 lifecycle rule.
2. **Prompt history storage**: DynamoDB single-table design, same `pixel-prompt-users` table. Items use `userId=prompt#<uuid>` as the base-table PK, with a GSI (`PromptHistoryIndex`) on `promptOwner` (HASH) + `createdAt` (RANGE). Per-user items set `promptOwner=USER#<sub>`. See ADR-3 in Phase-0.md and `backend/src/prompts/repository.py` for the shipped design.
3. **Global recent prompts**: DynamoDB GSI query on `promptOwner=GLOBAL#RECENT`, newest-first. 50 items max, 7-day TTL. Prompts only (no thumbnails). Unfiltered (content filter already screens at generation time).
4. **Guest prompt history**: Guests see the global recent prompts feed. No per-guest history.
5. **Prompt re-run behavior**: Populates the prompt input field for editing. Does not auto-trigger generation.
6. **Per-model prompt adaptation**: Automatic and transparent at generation time, server-side. No user toggle — always active.
7. **Adaptation LLM call**: Single LLM call returns JSON object with 4 model-specific prompt variants (`{"gemini": "...", "nova": "...", "openai": "...", "firefly": "..."}`). Falls back to original prompt for all models if the call fails or JSON parsing fails.
8. **Model knowledge for adaptation**: Lives entirely in the system prompt text in `enhance.py`. No config metadata.
9. **Adapted prompt visibility**: Stored per-iteration in `status.json`. Displayed in an expandable "Prompt used" section on each iteration card.
10. **Comparison activation**: Multi-select checkboxes (existing) + "Compare" button. Requires 2+ models selected.
11. **Comparison UI**: Full-screen modal overlay with selected models at equal size.
12. **Comparison iteration selection**: Each slot defaults to latest completed iteration, with an iteration picker dropdown to select any iteration.
13. **Download mechanism**: Presigned S3 URL to the raw image file. Enabled by the storage refactor.

## Scope: In

- S3 storage refactor: raw image files alongside metadata, update all write paths (generate, iterate, outpaint) and read paths (status, gallery)
- CloudFront direct image serving (images served as real files, not JSON blobs)
- Presigned URL generation endpoint or utility for image download
- Download button on iteration cards
- DynamoDB prompt history records (per-user, write on each generation)
- Global recent prompts feed (DynamoDB, 50 items, 7-day TTL)
- Prompt history UI: browsable list, search/filter by text, one-click re-run (populates input)
- Recent prompts section visible to all users (including guests)
- Per-model prompt adaptation in `/generate` flow: single LLM call, JSON response, 4 variants
- Adapted prompt storage in session `status.json` per-iteration
- Adapted prompt display in iteration card UI (expandable)
- Comparison modal: full-screen, equal-size images, iteration picker per slot
- Compare button wired to existing multi-select state in `useAppStore`

## Scope: Out

- Image-to-image (img2img) as a generation starting point
- Batch download (zip of multiple images)
- Export to third-party tools (Figma, Canva, etc.)
- Format conversion (PNG to JPG, resize, etc.)
- Social/sharing features, public galleries
- Prompt templates or preset library
- User-facing prompt adaptation toggle (always on)
- Thumbnails in the global recent prompts feed
- Admin curation of the recent prompts feed
- Per-guest prompt history (guests only see global feed)
- Migration script for existing base64-in-JSON images (they age out via S3 lifecycle)
- Comparison view for more than ~4 images (matches model count)
- Image diff/overlay tools in comparison view

## Open Questions

- Should the adaptation system prompt include guidance on image dimensions/aspect ratios that each model handles differently, or only stylistic strengths?
- What is the right cap for per-user prompt history? Unlimited for paid, limited for free? Or unlimited for both since storage cost per prompt record is negligible?
- Should the compare modal support a swipe/slider overlay for pixel-level comparison between two images, or is side-by-side sufficient for v1?

## Relevant Codebase Context

### Backend

- `backend/src/utils/storage.py` — `ImageStorage` class. Current write path stores JSON with base64 `output` field. `upload_image()`, `get_image()`, `get_cloudfront_url()` all need updating. Already has `get_cloudfront_url(s3_key)` for URL generation.
- `backend/src/jobs/manager.py` — `SessionManager`. Session `status.json` stores prompt, model iterations with `imageKey` references. `complete_iteration()` writes the image key. The iteration data structure needs a new `adaptedPrompt` field.
- `backend/src/models/context.py` — `ContextManager`. Rolling 3-iteration context window per model. Context entries reference image keys — these must point to the new raw image files.
- `backend/src/api/enhance.py` — `PromptEnhancer` class. Currently enhances a single prompt. Needs a new `adapt_per_model()` method (or similar) that returns 4 variants via structured JSON output.
- `backend/src/config.py` — `ModelConfig` dataclass (frozen). 4 fixed models with `name`, `provider`, `model_id`, `display_name`. No changes needed for adaptation (knowledge stays in system prompt).
- `backend/src/lambda_function.py` — 1,123 lines. `handle_generate` dispatches to all enabled models via `ThreadPoolExecutor`. Adaptation call should happen before dispatch. Prompt history write should happen after session creation.
- `backend/src/users/repository.py` — `UserRepository` with DynamoDB single-table operations. `_atomic_increment`, `get_user`, `set_tier`. Prompt history and recent feed records follow the same table patterns.
- `backend/src/models/providers/` — Per-provider handler modules (gemini.py, nova.py, openai_provider.py, firefly.py). Each `handle_*` function returns `{'status': 'success', 'image': base64_str}`. The `image` field must change to return raw bytes or the handler must write the file directly.

### Frontend

- `frontend/src/stores/useAppStore.ts` — Zustand store. `prompt` field holds current input. `currentSession` mirrors backend session. Needs prompt history state and actions.
- `frontend/src/stores/useUIStore.ts` — UI state including `focusedModel` and `toggleFocus`. Comparison modal state belongs here.
- `frontend/src/components/generation/GenerationPanel.tsx` — Renders 4 `ModelColumn` components. Has multi-select state. Compare button goes here.
- `frontend/src/components/generation/ModelColumn.tsx` — Per-model column with `isFocused`/`isCompressed` props. `IterationCard` renders each iteration. Download button and adapted prompt display go on iteration cards.
- `frontend/src/components/generation/IterationCard.tsx` — Renders individual iteration results. Needs download button and expandable adapted prompt section.
- `frontend/src/api/client.ts` — API client with `generateSession()`, `iterateImage()`, `getSessionStatus()`. Needs prompt history fetch/search endpoints and download URL endpoint.
- `frontend/src/hooks/useSessionPolling.ts` — Polls `/status/{sessionId}`. Already handles progressive updates — adapted prompts will flow through naturally.

### Infrastructure

- `backend/template.yaml` — SAM template. DynamoDB table already exists (`pixel-prompt-users`). May need GSI for prompt search or global feed queries. S3 bucket policies unchanged. CloudFront already configured.
- S3 lifecycle: 30-day auto-delete on sessions. Old base64 JSON images age out without migration.
- API Gateway: 10MB payload limit currently constrains image delivery through Lambda. Storage refactor eliminates this bottleneck.

### Test Patterns

- Backend: pytest + moto for S3/DynamoDB mocks in `tests/backend/unit/`. Provider tests mock API calls and verify return shapes.
- Frontend: Vitest + React Testing Library in `frontend/tests/__tests__/`. Store tests, component tests, hook tests.
- Coverage gates: 80% backend, enforced in CI.

## Technical Constraints

- **Lambda 10MB response limit**: Currently constrains image delivery. Storage refactor bypasses this entirely by serving images through CloudFront.
- **S3 presigned URL expiry**: Presigned URLs have a max lifetime (default 1 hour for IAM role credentials in Lambda). Download URLs should be generated on demand, not cached.
- **LLM adaptation latency**: The per-model adaptation call adds latency to `/generate`. Should run concurrently with or just before the model dispatch. If the adaptation call takes >2s, generation start is delayed. Consider a timeout with fallback to original prompt.
- **DynamoDB hot partition**: The `PK=GLOBAL` partition for recent prompts could become hot at scale. Acceptable for current traffic levels. If needed later, shard across `GLOBAL#0` through `GLOBAL#N`.
- **Content-Type detection**: When storing raw images, the handler must determine the correct Content-Type (image/png vs image/jpeg). Most providers return PNG. Store Content-Type in metadata.
- **Backward compatibility**: During rollout, the frontend and status polling must handle both old (base64 in JSON) and new (S3 key to raw image) formats until old sessions age out.
