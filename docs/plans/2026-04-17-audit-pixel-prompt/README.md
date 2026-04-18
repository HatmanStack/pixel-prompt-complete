# Audit Remediation Plan: pixel-prompt-complete

## Overview

This plan remediates findings from the 2026-04-17 unified audit (health + eval + docs). The codebase was rated GOOD overall with 1 critical, 5 high, 8 medium, and 3 low health findings. The 12-pillar eval scored 6/12 at the 9/10 target, with the biggest gaps in Defensiveness (7/10) and Creativity, Pragmatism, Performance, Test Value, and Onboarding (all 8/10). Documentation audit found 6 drift items, 3 gaps, and 3 config drift issues.

The remediation is organized into a foundation phase (Phase 0) plus 3 implementation phases following the audit pipeline ordering: subtractive cleanup first, then code fixes, then documentation.

## Prerequisites

- Node.js 18+ and npm
- Python 3.13+ with uv
- AWS SAM CLI
- All dependencies installed (`npm install` in frontend, `uv pip install -r backend/src/requirements.txt`)

## Phase Summary

| Phase | Tag | Goal | Estimated Tokens |
|-------|-----|------|-----------------|
| 0 | -- | Foundation: conventions, testing strategy, shared patterns | ~3,000 |
| 1 | [HYGIENIST] | Fix stale model name references in code comments | ~3,000 |
| 2 | [IMPLEMENTER] | Operational resilience hardening + test improvements | ~30,000 |
| 3 | [DOC-ENGINEER] | Documentation drift remediation + onboarding improvements | ~15,000 |

## Navigation

- [Phase-0.md](Phase-0.md) — Foundation and conventions
- [Phase-1.md](Phase-1.md) — [HYGIENIST] Stale reference cleanup
- [Phase-2.md](Phase-2.md) — [IMPLEMENTER] Operational resilience hardening
- [Phase-3.md](Phase-3.md) — [DOC-ENGINEER] Documentation fixes

## Intake Documents

- [health-audit.md](health-audit.md) — 1 critical, 5 high, 8 medium, 3 low findings
- [eval.md](eval.md) — 6/12 pillars at 9/10 target
- [doc-audit.md](doc-audit.md) — 6 drift, 3 gaps, 3 config drift
