# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-04-07

### Added
- Amazon Nova Canvas provider (Bedrock, IAM auth)
- Adobe Firefly provider (Image5, OAuth2 client credentials)
- Per-provider module structure under `backend/src/models/providers/`
- Column focus/expand UI: clicking a model column animates to ~60% width with full controls; others compress to ~13%
- Shared frontend constants in `frontend/src/config/constants.ts` for iteration limits
- markdownlint config and docs lint job in CI
- `.devcontainer/` configuration with `uv`-based post-create script
- `bedrock:InvokeModel` IAM permission in SAM template
- `astral-sh/setup-uv` action in CI for backend dependency installs

### Changed
- BREAKING: Provider lineup changed from Flux/Recraft/Gemini/OpenAI to Gemini/Nova/OpenAI/Firefly
- Gemini updated to `gemini-3.1-flash-image-preview` (Nano Banana 2)
- OpenAI generation locked to DALL-E 3; iteration/outpaint use `gpt-image-1` (DALL-E 3 lacks `images.edit`)
- Gallery list/detail responses return CloudFront URLs instead of base64 (fixes Lambda 6MB overflow)
- Backend coverage gate raised from 60% to 80%
- mypy `disallow_untyped_defs = true` enabled in backend pyproject
- Provider enable flags now require credentials (gemini/openai/firefly disabled when keys missing)
- Dev dependencies pinned in `backend/pyproject.toml [project.optional-dependencies]`
- CLAUDE.md fully rewritten for the new provider lineup

### Fixed
- CRITICAL: Gallery list/detail responses exceeding Lambda 6MB payload limit
- CRITICAL: BFL polling threads blocking `ThreadPoolExecutor` (removed with Flux)
- Session ID validation missing on `/iterate` and `/outpaint`
- `/log` endpoint returning 500 for `ValueError` instead of 400
- `_load_source_image` making redundant S3 reads
- `_compute_session_status` precedence bug (pending statuses now take precedence over completed)
- `_error_result` not sanitizing string errors (only Exception)
- Checkbox click in `ModelColumn` bubbling to column focus toggle
- ministack GHA healthcheck always failing (image has no curl/wget)
- Docs lint job never running on markdown-only PRs

### Removed
- BREAKING: Flux/BFL provider (config, handlers, tests, SAM params)
- BREAKING: Recraft provider (config, handlers, tests, SAM params)
- `backend/src/models/handlers.py` (replaced by `providers/` package)
- Phantom env vars: `VITE_DEBUG`, `VITE_API_TIMEOUT`, unused `VITE_CLOUDFRONT_DOMAIN`/`VITE_S3_BUCKET`/`VITE_ENVIRONMENT`
- Stale `ModelRegistry` reference in ADR-001
- All `.jsx` test files (migrated to `.tsx`)
- Stale `frontend/src/fixtures/apiResponses.ts` referencing old job-based API

## [1.1.0] - 2026-03-16

### Added
- Changelog-driven release automation via GitHub Actions
- Request body size limits and log metadata sanitization
- S3 pagination for gallery listing endpoints
- Configurable CORS allowed origin via `CORS_ALLOWED_ORIGIN` env var
- Comprehensive environment variable reference in CLAUDE.md
- E2E test suite running against MiniStack in CI
- `.env.example` and `requirements-lock.txt` for reproducibility
- `LICENSE` file

### Changed
- Refactored `handle_iterate` and `handle_outpaint` into shared `_handle_refinement` dispatch
- Extracted shared request validation pipeline from all POST handlers
- Reuse cached SDK clients in `PromptEnhancer` instead of creating per-request
- Froze `ModelConfig` dataclass to prevent accidental mutation
- Increased `SessionManager` optimistic lock retries from 3 to 5 with jitter
- Migrated `test_context_manager` from MagicMock to moto S3

### Fixed
- Gallery listing returning session UUID folders mixed with image galleries
- Flaky E2E tests caused by optimistic locking contention during parallel generation
- Pending iteration leak when handler exceptions occurred after `add_iteration`
- `useEffect` exhaustive-deps violation in `GenerationPanel`
- Frontend `REQUEST_TIMEOUT` too low for long-running generation requests (now 180s)
- `handle_status` missing `session_id` validation
- Error messages leaking internal details to clients

### Removed
- Dead code: unused Bedrock, Stability, Imagen, and generic handlers
- Dead code: unused `types.py` module, `save_image`, `_generate_thumbnail`, `clear_context`
- Dead code: unused config variables and `is_model_enabled` function
- Dead IAM policy entries for `gallery/*` prefix in `template.yaml`
- No-op gallery handler and placeholder test assertion in frontend

## [1.0.0] - 2026-03-16

### Added
- Initial release of Pixel Prompt v2
- 4 fixed AI models (Flux, Recraft, Gemini, OpenAI) running in parallel
- Iterative refinement with rolling 3-iteration context window
- Outpainting to different aspect ratios (16:9, 9:16, 1:1, 4:3, expand_all)
- S3-based session management with optimistic locking
- Rate limiting (global hourly + per-IP daily)
- Gallery browser with CloudFront CDN delivery
- LLM-based prompt enhancement
- React + TypeScript frontend with Zustand state management
- E2E test suite with MiniStack
