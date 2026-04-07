# Phase 0 -- Foundation

This phase contains architecture decisions, design rationale, shared patterns, and testing strategy that apply across all implementation phases. Every implementer must read this before starting any phase.

## Architecture Decision Records

### ADR-1: Per-Provider Module Structure

**Decision:** Split the monolithic `handlers.py` (777 lines) into per-provider modules under `backend/src/models/providers/`.

**Structure:**

```text
backend/src/models/
  providers/
    __init__.py        # Re-exports get_handler, get_iterate_handler, get_outpaint_handler
    gemini.py          # handle_google_gemini, iterate_gemini, outpaint_gemini
    nova.py            # handle_nova, iterate_nova, outpaint_nova
    openai_provider.py # handle_openai, iterate_openai, outpaint_openai (file named to avoid shadowing)
    firefly.py         # handle_firefly, iterate_firefly, outpaint_firefly
    _common.py         # Shared helpers: _decode_source_image, _build_context_prompt, etc.
  handlers.py          # DELETE this file (replaced by providers/)
  context.py           # Unchanged
```

**Rationale:** The eval scored Architecture at 7/10 specifically citing the 777-line handlers.py. Since we are rewriting all handlers for new providers anyway, this is zero incremental cost. Each provider file stays under 200 lines.

### ADR-2: Gallery Response Payload Fix (CRITICAL)

**Decision:** Stop returning base64 `output` field in gallery list and gallery detail responses. Clients use CloudFront URLs instead.

**Changes:**

- `handle_gallery_list`: Return `previewUrl` (CloudFront URL of first image) instead of `previewData` (base64 blob).
- `handle_gallery_detail`: Return `url` (CloudFront URL) without the `output` field.
- Frontend `GalleryListItem.previewData` becomes `GalleryListItem.previewUrl`.
- Frontend `GalleryDetailImage.output` is removed.

**Rationale:** This is CRITICAL-1 from the health audit. Each base64 image is 1-2MB. With 15+ galleries, the response exceeds Lambda's 6MB response limit causing silent 502 errors. CloudFront URLs are ~100 bytes each.

### ADR-3: Bedrock Integration Pattern

**Decision:** Use `boto3.client('bedrock-runtime')` for Nova Canvas, not HTTP requests. The client is cached at module level like other clients.

**Auth:** Lambda's existing IAM role gets `bedrock:InvokeModel` permission added in template.yaml. No API key needed.

**Rationale:** Bedrock is an AWS service -- using boto3 is the standard pattern and avoids managing SigV4 signing manually. The Lambda already has boto3 available (it is part of the Lambda runtime).

### ADR-4: Firefly OAuth2 Per-Request Token

**Decision:** Fetch a fresh OAuth2 access token on every Firefly handler invocation. No token caching.

**Flow:** `client_id` + `client_secret` -> POST to Adobe IMS token endpoint -> use access token for the single API call.

**Rationale:** Lambda invocations are stateless. Token caching would require either module-level state (fragile with container reuse expiry) or external storage (over-engineering). The token fetch adds ~100-200ms, acceptable given image generation takes 5-30 seconds.

### ADR-5: DALL-E 3 Iteration Strategy

**Decision:** Use `gpt-image-1` (which supports `images.edit`) for iteration and outpainting, while using DALL-E 3 (`dall-e-3`) for initial generation. The `iterate_openai` and `outpaint_openai` handlers will explicitly use `gpt-image-1` regardless of the generation model ID.

**Rationale:** DALL-E 3 does not support `images.edit`. Using gpt-image-1 for edit operations is the only option that preserves image-to-image refinement. The alternative (prompt-only re-generation) loses the iterative refinement that is core to the product.

### ADR-6: Session Manager Model Name Update

**Decision:** Update `SessionManager.create_session()` to use the new model name list `["gemini", "nova", "openai", "firefly"]` instead of the hardcoded `["flux", "recraft", "gemini", "openai"]`.

**Approach:** Replace the hardcoded list with `list(MODELS.keys())` to derive model names from the config, making it dynamic.

**Rationale:** The current hardcoded list at `manager.py:70` would break with new model names. Using the config dict makes it future-proof.

## Design Decisions

### Provider Internal Keys and Display Names

| Internal Key | Provider Identifier | Display Name | Auth Method |
|-------------|-------------------|--------------|-------------|
| `gemini` | `google_gemini` | Gemini | API key |
| `nova` | `bedrock_nova` | Nova Canvas | IAM role |
| `openai` | `openai` | DALL-E 3 | API key |
| `firefly` | `adobe_firefly` | Firefly | OAuth2 (client credentials) |

### Handler Return Contract

All handlers continue to return the existing `HandlerResult` TypedDict:

```python
{"status": "success", "image": "<base64_str>", "model": "<model_id>", "provider": "<provider>"}
{"status": "error", "error": "<sanitized_msg>", "model": "<model_id>", "provider": "<provider>"}
```

### Client Caching Strategy

- **Gemini:** Existing `get_genai_client(api_key)` pattern, unchanged.
- **OpenAI:** Existing `get_openai_client(api_key)` pattern, unchanged.
- **Nova (Bedrock):** New `get_bedrock_client()` in `utils/clients.py`. Cached by region (no API key). Uses `boto3.client('bedrock-runtime')`.
- **Firefly:** No cached client. Each call creates a fresh `requests.Session` with the per-request OAuth2 token.

### Type Annotations

All new code must have complete type annotations. Enable `disallow_untyped_defs = true` in `pyproject.toml` after the provider rewrite is complete (Phase 1 final task).

### Frontend Column Focus Layout

- `focusedModel: ModelName | null` state in `useUIStore`
- Clicking a column header sets `focusedModel` to that model; clicking again clears it
- CSS transitions via Tailwind classes: `transition-all duration-300 ease-in-out`
- Focused column: `w-[60%]` with full controls (outpaint, download, iteration history, iteration counter, checkbox)
- Compressed columns: `w-[13%]` showing latest image thumbnail + iteration input
- Mobile: Focus behavior disabled; keep existing snap-scroll

## Python Package Management

**Always use `uv` for Python package operations.** Never use bare `pip` or `pip3`.

- Local install: `uv pip install -r backend/src/requirements.txt`
- Dev install: `uv pip install -e "backend/.[dev]"`
- One-off tools: `uvx <tool>` (e.g., `uvx vulture`, `uvx pip-audit`)
- CI: Add `astral-sh/setup-uv` action before any Python install steps

## Testing Strategy

### Backend Testing

- **Framework:** pytest with pytest-mock, pytest-cov
- **Mocking:** moto for S3, `unittest.mock.patch` for external API calls
- **Coverage gate:** Raise from 60% to 80% in CI (Phase 3)
- **Test location:** `tests/backend/unit/` (existing pattern)
- **New test files:**
  - `tests/backend/unit/test_gemini_handler.py`
  - `tests/backend/unit/test_nova_handler.py`
  - `tests/backend/unit/test_openai_handler.py`
  - `tests/backend/unit/test_firefly_handler.py`
  - `tests/backend/unit/test_gallery_payload.py` (gallery base64 fix)
- **Deleted test files:** Remove all Flux/BFL and Recraft test code from existing files
- **conftest.py:** The existing `conftest.py` provides `mock_s3` fixture and client cache clearing. No changes needed.

### Frontend Testing

- **Framework:** Vitest + React Testing Library
- **Test location:** `frontend/tests/__tests__/` (existing pattern)
- **Migration:** Convert `.jsx` test files to `.tsx` (Phase 2)
- **New tests:** Column focus behavior, new model name references
- **Pattern:** Follow existing patterns in `useSessionPolling.test.ts` for hook testing

### Mocking External APIs

For each new provider, mock at the HTTP boundary:

- **Gemini:** Mock `client.models.generate_content()` return value
- **Nova:** Mock `boto3.client('bedrock-runtime').invoke_model()` return value
- **OpenAI:** Mock `client.images.generate()` and `client.images.edit()` return values
- **Firefly:** Mock `requests.post()` for both OAuth2 token and API calls

### Commit Message Format

Follow conventional commits as enforced by commitlint:

```text
feat(providers): add Nova Canvas generate handler
fix(gallery): stop returning base64 in gallery list response
refactor(handlers): split monolithic handlers.py into per-provider modules
test(nova): add unit tests for Nova Canvas handlers
chore(ci): raise backend coverage gate to 80%
docs: update CLAUDE.md for new provider lineup
```

## Audit Finding Cross-Reference

This table maps each audit finding to the phase and task where it is addressed.

| Finding | Source | Severity | Resolution Phase |
|---------|--------|----------|-----------------|
| Gallery base64 overflow | health-audit CRITICAL-1 | CRITICAL | Phase 1, Task 9 |
| BFL polling thread blocking | health-audit CRITICAL-2 | CRITICAL | Phase 1, Task 1 (Flux removal) |
| Redundant S3 reads in _load_source_image | health-audit HIGH-3 | HIGH | Phase 1, Task 9 |
| Split handlers.py | health-audit HIGH-4, eval Architecture | HIGH | Phase 1, Task 3 (provider modules) |
| Private _GALLERY_FOLDER_RE access | health-audit HIGH-5 | HIGH | Phase 1, Task 9 |
| Log endpoint 500 for validation errors | health-audit HIGH-6 | HIGH | Phase 1, Task 10 |
| MAX_ITERATIONS frontend/backend sync | health-audit HIGH-7 | HIGH | Phase 2, Task 5 |
| Gallery detail base64 | health-audit HIGH-8 | HIGH | Phase 1, Task 9 |
| Session ID validation missing | eval Defensiveness | HIGH | Phase 1, Task 10 |
| Duplicate GenerateButton test | health-audit MED-10 | MEDIUM | Phase 2, Task 6 |
| Stale fixtures in src/ | health-audit MED-11 | MEDIUM | Phase 2, Task 6 |
| isNetworkError too broad | eval Code Quality | MEDIUM | Phase 2, Task 7 |
| enhance.py model branching | health-audit MED-13 | MEDIUM | Phase 1, Task 11 |
| SessionGenerateResponse loose types | health-audit MED-15 | MEDIUM | Phase 2, Task 2 |
| disallow_untyped_defs | eval Type Rigor | MEDIUM | Phase 1, Task 11 |
| Coverage gate 60 to 80 | eval Test Value | MEDIUM | Phase 3, Task 2 |
| jsx to tsx test migration | eval Test Value | LOW | Phase 2, Task 6 |
| Pin dev dependencies | eval Reproducibility | MEDIUM | Phase 3, Task 3 |
| Add .devcontainer | eval Reproducibility | MEDIUM | Phase 3, Task 4 |
| Markdownlint + lychee in CI | doc-audit Structure | MEDIUM | Phase 3, Task 5 |
| Phantom VITE_DEBUG/VITE_API_TIMEOUT | doc-audit Config Drift | LOW | Phase 2, Task 8 |
| CI branch drift (develop) | doc-audit DRIFT-1 | LOW | Phase 3, Task 1 |
| S3 gallery prefix drift | doc-audit DRIFT-2 | LOW | Phase 3, Task 1 |
| Version number drift | doc-audit DRIFT-3 | LOW | Phase 3, Task 1 |
| Missing /log SAM route | doc-audit DRIFT-4 | LOW | Phase 1, Task 10 |
| Stale ADR (ModelRegistry) | doc-audit STALE-1 | LOW | Phase 3, Task 6 |
| Legacy typing imports | health-audit LOW-23,24 | LOW | Phase 1, Task 3 and Task 11 |
| retry.py logging inconsistency | health-audit LOW-20 | LOW | Phase 1, Task 11 |
| S3 error handling inconsistency | health-audit LOW-21 | LOW | Phase 1, Task 11 |

## Out of Scope

The following audit findings are intentionally excluded from this plan with rationale.

| Finding | Source | Severity | Rationale |
|---------|--------|----------|-----------|
| CustomEvent keyboard shortcuts | health-audit MED-18 | MEDIUM | Low risk, no user-facing impact. Keyboard shortcut accessibility is a polish item that can be addressed in a future sprint. |
| DRY: complete/fail_iteration | health-audit MED-17 | MEDIUM | The `complete_iteration` and `fail_iteration` duplication in `manager.py` is a minor DRY violation (~10 lines). Refactoring carries risk of breaking optimistic locking logic for minimal benefit. Defer to a dedicated refactoring pass. |
| S3 CORS wildcard | eval Problem-Solution Fit | LOW | The S3 CORS wildcard in `template.yaml` is an infrastructure hardening item. Tightening it requires knowing the production CloudFront domain at deploy time, which varies per environment. Best addressed as part of a security hardening sprint, not a provider swap. |
| CORS origin prod warning | eval Defensiveness | LOW | The `CORS_ALLOWED_ORIGIN` defaulting to `*` in `config.py` is documented behavior and configurable via environment variable. Adding a startup warning log is low value since operators set this during `sam deploy --guided`. Defer to security hardening. |
| S3 rate limiting hot path | health-audit HIGH-9 | HIGH | The `rate_limit.py` S3-backed rate limiter adds 100-300ms latency per request due to S3 reads/writes on every invocation. Fixing this properly requires moving to DynamoDB or ElastiCache, which is a significant architectural change outside the scope of a provider swap. The brainstorm explicitly scoped out "changes to rate limiting." |
