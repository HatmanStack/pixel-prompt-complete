# ADR 001: Fixed Four-Model Architecture

## Status

Accepted

## Context

The original Pixel Prompt design used a dynamic model registry where operators could configure 1-20 models via CloudFormation parameters. This created complexity in the frontend layout (variable-width columns), testing (combinatorial model configurations), and session schema (dynamic model arrays).

## Decision

Fix the architecture to exactly four models: Gemini (Google), Nova Canvas (Amazon Bedrock), DALL-E 3 (OpenAI), and Firefly (Adobe). Each can be enabled or disabled via environment variables, but no models can be added or removed without code changes.

## Consequences

### Positive

- **Predictable UI layout**: Always a 4-column grid on desktop, simplifying responsive design
- **Simpler testing**: Fixed model set means deterministic test fixtures and session schemas
- **Session schema stability**: `status.json` always contains the same four model keys
- **Reduced configuration surface**: No CloudFormation parameter arrays or dynamic loop constructs

### Negative

- Adding a fifth model requires code changes in `config.py`, `models/providers/`, `SessionManager`, and frontend `ModelColumn` layout

### Neutral

- Each model has its own generate/iterate/outpaint handler triplet under `backend/src/models/providers/` (one module per provider)
- Per-model enable/disable flags provide sufficient flexibility for most deployments
