# ADR 001: Fixed Four-Model Architecture

## Status

Accepted

## Context

The original Pixel Prompt design used a dynamic model registry where operators could configure 1-20 models via CloudFormation parameters. This created complexity in the frontend layout (variable-width columns), testing (combinatorial model configurations), and session schema (dynamic model arrays).

## Decision

Fix the architecture to exactly four models: Flux (BFL), Recraft, Gemini (Google), and OpenAI. Each can be enabled or disabled via environment variables, but no models can be added or removed without code changes.

## Consequences

### Positive

- **Predictable UI layout**: Always a 4-column grid on desktop, simplifying responsive design
- **Simpler testing**: Fixed model set means deterministic test fixtures and session schemas
- **Session schema stability**: `status.json` always contains the same four model keys
- **Reduced configuration surface**: No CloudFormation parameter arrays or dynamic loop constructs

### Negative

- Adding a fifth model requires code changes in `config.py`, `handlers.py`, `SessionManager`, and frontend `ModelColumn` layout
- The legacy `ModelRegistry` class remains in `models/registry.py` (unused but not yet removed)

### Neutral

- Each model still needs its own generate/iterate/outpaint handler triplet in `handlers.py`
- Per-model enable/disable flags provide sufficient flexibility for most deployments
