# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
