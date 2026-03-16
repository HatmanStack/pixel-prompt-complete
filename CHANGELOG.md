# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- E2E test suite with LocalStack
