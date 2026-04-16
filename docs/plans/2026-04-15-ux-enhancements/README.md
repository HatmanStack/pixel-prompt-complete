# UX Enhancements: Storage Refactor, Prompt History, Prompt Adaptation, Comparison, Download

## Overview

This plan delivers five interlocking improvements to Pixel Prompt Complete. The foundational change is a storage refactor that replaces base64-in-JSON image storage with raw image files in S3, eliminating 33% storage bloat, enabling direct CloudFront image serving (bypassing Lambda/API Gateway for image delivery), unlocking browser and CDN caching, and making presigned download URLs trivial.

On top of that foundation, four user-facing features ship: (1) prompt history with per-user DynamoDB records and a global recent prompts feed, (2) automatic per-model prompt adaptation that tailors the user's prompt to each provider's strengths at generation time via a single LLM call, (3) a side-by-side comparison modal for evaluating results across models with per-slot iteration pickers, and (4) one-click image download via presigned S3 URLs.

All backend features preserve the open-source `AUTH_ENABLED=false` experience. Prompt adaptation runs for all users (it is part of the generation pipeline, not gated by auth). Prompt history recording requires auth; the global recent feed is public.

## Prerequisites

- Node.js 24+ with npm (frontend)
- Python 3.13+ with uv (backend dependencies -- never bare pip)
- AWS SAM CLI (deployment)
- API keys for at least one enabled image provider
- API key for the prompt enhancement provider (`PROMPT_MODEL_API_KEY`)
- Existing deployment with the paid-tier DynamoDB table (`pixel-prompt-users`)

## Phase Summary

| Phase | Goal | Token Estimate |
|-------|------|----------------|
| 0 | Foundation: ADRs, conventions, testing strategy | ~5,000 |
| 1 | Backend: Storage refactor (raw images in S3) + download endpoint | ~45,000 |
| 2 | Backend: Per-model prompt adaptation + prompt history | ~40,000 |
| 3 | Frontend: Download button, adapted prompt display, prompt history UI, comparison modal | ~50,000 |

## Navigation

- [Phase-0.md](Phase-0.md) -- Foundation and architecture decisions
- [Phase-1.md](Phase-1.md) -- Backend storage refactor and download
- [Phase-2.md](Phase-2.md) -- Backend prompt adaptation and history
- [Phase-3.md](Phase-3.md) -- Frontend features
- [feedback.md](feedback.md) -- Review feedback tracker
- [brainstorm.md](brainstorm.md) -- Original brainstorm document
