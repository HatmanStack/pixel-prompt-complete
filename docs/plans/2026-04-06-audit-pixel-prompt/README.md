# Provider Swap, Column Focus UI, and Audit Remediation

## Overview

This plan replaces the four image generation providers (Flux/BFL, Recraft, Gemini, OpenAI/gpt-image-1) with a new set (Gemini Nano Banana 2, Amazon Nova Canvas, OpenAI DALL-E 3, Adobe Firefly Image5). The backend undergoes a full handler rewrite with per-provider module structure, while the frontend gains a column focus/expand interaction where clicking a model column animates it to 60% width with full controls visible.

Simultaneously, this plan addresses 24 findings from three audit documents (health audit, code evaluation, documentation audit). Many findings are resolved naturally by the provider swap (removing Flux/Recraft eliminates BFL polling, splitting handlers.py happens as part of the rewrite). Remaining findings -- gallery base64 payload overflow, session ID validation, log endpoint error codes, coverage gates, test migrations, dependency pinning, and documentation drift -- are woven into the feature phases where they naturally fit.

The plan is structured in four phases: Phase 0 (foundation decisions), Phase 1 (backend provider swap with audit hardening), Phase 2 (frontend provider swap with column focus UI), and Phase 3 (documentation, CI, and DevEx polish).

## Prerequisites

- Node.js 24+ and npm (frontend)
- Python 3.13+ (backend)
- AWS SAM CLI (deployment)
- AWS account with Bedrock access in the target region (Nova Canvas)
- Adobe Developer Console project with Firefly Services entitlement
- Docker (for MiniStack E2E tests)
- API keys: Gemini, OpenAI, Firefly client credentials

## Phase Summary

| Phase | Goal | Token Estimate |
|-------|------|----------------|
| 0 | Foundation: ADRs, design decisions, testing strategy, shared patterns | ~3,000 |
| 1 | Backend: Provider swap, handler rewrite, gallery fix, session validation, log fix | ~45,000 |
| 2 | Frontend: Model type update, column focus UI, store changes, test migration | ~35,000 |
| 3 | Documentation, CI hardening, DevEx (.devcontainer, dependency pinning, markdownlint) | ~15,000 |

## Navigation

- [Phase-0.md](Phase-0.md) -- Foundation and architecture decisions
- [Phase-1.md](Phase-1.md) -- Backend provider swap and audit remediation
- [Phase-2.md](Phase-2.md) -- Frontend provider swap and column focus UI
- [Phase-3.md](Phase-3.md) -- Documentation, CI, and DevEx
