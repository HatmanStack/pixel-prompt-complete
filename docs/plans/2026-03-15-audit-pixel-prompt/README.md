# Unified Audit Remediation Plan

## Overview

This plan consolidates findings from three independent audits of the pixel-prompt-complete codebase:
a **health audit** (26 tech debt findings), a **12-pillar evaluation** (11 of 12 pillars below target),
and a **documentation audit** (14 drift/gap/stale findings). The current overall health is FAIR, with
the lowest-scoring pillar being Performance at 6/10 and only Onboarding meeting its 9/10 target.

The remediation is sequenced following a strict order: (1) subtractive cleanup to reduce surface area,
(2) structural code fixes for architecture, error handling, and performance, (3) additive guardrails
for type safety and CI enforcement, and (4) documentation corrections and drift prevention. Each phase
is tagged with the implementer role responsible for it.

## Prerequisites

- Node.js 24+ with npm
- Python 3.13+ with pip
- AWS SAM CLI (for `sam build` verification)
- Access to the repository at `/home/user/pixel-prompt-complete`
- Familiarity with: React/TypeScript, Python/AWS Lambda, Vitest, pytest, moto

## Phase Summary

| Phase | Tag | Goal | Token Estimate |
|-------|-----|------|----------------|
| 0 | — | Foundation: shared conventions, testing strategy, ADRs | ~2,000 |
| 1 | [HYGIENIST] | Dead code removal, unused dependency cleanup, stale reference purge | ~15,000 |
| 2 | [IMPLEMENTER] | Performance fixes (S3 pagination), error handling, input validation, client caching | ~30,000 |
| 3 | [IMPLEMENTER] | Architecture: extract shared pipeline, split lambda_function.py, freeze configs | ~35,000 |
| 4 | [FORTIFIER] | Type rigor, CI enhancements, test quality improvements | ~20,000 |
| 5 | [DOC-ENGINEER] | Fix all documentation drift, gaps, stale references, and broken links | ~15,000 |

## Navigation

- [Phase-0.md](Phase-0.md) — Foundation (applies to all phases)
- [Phase-1.md](Phase-1.md) — [HYGIENIST] Dead code and cleanup
- [Phase-2.md](Phase-2.md) — [IMPLEMENTER] Error handling, performance, validation
- [Phase-3.md](Phase-3.md) — [IMPLEMENTER] Architecture refactoring
- [Phase-4.md](Phase-4.md) — [FORTIFIER] Type safety, CI, test quality
- [Phase-5.md](Phase-5.md) — [DOC-ENGINEER] Documentation fixes
- [feedback.md](feedback.md) — Review feedback channel
