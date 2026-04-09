# Follow-Up: Global Cost-Ceiling Circuit Breaker

Source: `docs/plans/2026-04-08-paid-tier/Phase-0.md` ADR-8.

## Problem

The paid-tier plan introduced per-user quotas (guest, free, paid) backed by
DynamoDB. Per-user quotas bound individual abuse but do **not** bound
catastrophic aggregate spend. A bug, a viral moment, a compromised key, or a
pathological prompt loop could still drive total provider spend far past the
operator's budget before anyone notices. The tier system is not a cost
ceiling.

## Candidate Mitigations

1. **Per-model daily spend caps enforced in Lambda**. Track per-model call
    counts (or token/image cost estimates) in DynamoDB against an operator-set
    daily budget. Refuse calls to a given provider once its cap is hit, fall
    through to the remaining enabled models, and surface a clear error when
    all four are capped.
1. **CloudWatch billing alarms**. Alarm on estimated AWS charges and on
    per-service metrics (Bedrock InvokeModel count, Lambda duration). Page the
    operator rather than auto-shut-down; good for defense in depth, poor as a
    sole mechanism because the alarm fires after the spend has happened.
1. **Provider-side spend limits**. Use each provider's native cap where
    available (OpenAI usage limits, Adobe Firefly quota, Gemini project budget
    alerts, AWS budgets for Bedrock). Cheapest to implement, but inconsistent
    across providers and typically soft.

## Recommendation

Run `/brainstorm` on this as a new feature. Treat it as a sibling to the
paid-tier plan, not an amendment. The design question is non-trivial: where
cost state lives, how per-model budgets interact with per-user quotas, how
the circuit breaker degrades (soft warning vs. hard block vs. partial
fallback), and how the operator resets or overrides it. That belongs in its
own plan with its own ADRs.

Until that work lands, the tier system is the only runtime bound on spend.
Operators should set conservative per-tier limits, configure provider-side
budget alerts manually, and monitor the CloudWatch cost dashboard.
