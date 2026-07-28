"""A spend bound that does not read the store it is bounding.

Six guards fail **open** when the quota store is unreachable -- the monthly
ceiling, the daily ceiling, the enhance sub-ceiling, the tier quota, the
per-model cap and the anon IP quota -- and spend recording silently stops at
the same time. Each of those choices is individually well argued from blast
radius, and ``CLAUDE.md`` documents the policy honestly. What none of them
accounts for is that they share **one DynamoDB table**: a single partition
problem opens every gate *and* switches off the accounting, so the service
runs unmetered and unbounded and the only surviving signal is an SNS email.
At the API Gateway throttle ceiling that is roughly $2k/day against a $500
monthly ceiling.

**The trade-off, stated so it is not mistaken for something stronger.**

This breaker is **per container**, deliberately. A shared or distributed
breaker would need the store that is failing, which is the whole problem.
Process-local state in a warm Lambda execution environment needs nothing,
costs nothing, and survives exactly the dependency it exists to survive.

What it therefore bounds is **one container's** blind dispatching. With
``ReservedConcurrentExecutions: 10`` the aggregate is at most ten containers'
worth of degraded budget -- roughly 10 x 20 generations at about $0.19 each,
call it $38 -- against a $25 daily and $500 monthly ceiling. That is weaker
than a real distributed breaker. It is also the strongest thing available
without the dependency that is down. **It is not a global cap**, and a future
reader who takes it for one will over-trust it.

It is a backstop, not a second ceiling. While DynamoDB is healthy every store
call records a success, the failure counter never reaches its threshold, and
this never binds.

See ADR-A13 in docs/plans/2026-07-26-audit-pixel-prompt/Phase-0.md.
"""

from __future__ import annotations

import threading

import config
from utils.logger import StructuredLogger

# Four generation threads touch these, so they are guarded. Module-level
# integers rather than a class because there is exactly one breaker per
# container and giving it a constructor would invite a second.
_lock = threading.Lock()
_consecutive_failures = 0
_degraded_dispatches = 0


def record_store_result(ok: bool) -> None:
    """Record the outcome of a call to the quota/spend store.

    Called at every site that swallows a store error into a fail-open. A
    single success resets the failure counter: the case being defended
    against is a partition, which looks like an unbroken run of failures, not
    a rate. A store that fails one call in ten is degraded but still
    metering, and shedding traffic for that would be the self-inflicted
    outage every fail-open here exists to avoid.
    """
    global _consecutive_failures
    with _lock:
        if ok:
            _consecutive_failures = 0
        else:
            _consecutive_failures += 1


def should_shed() -> bool:
    """True when the breaker has tripped and its degraded budget is spent.

    **Not a pure predicate.** While tripped and still under budget it consumes
    one unit of that budget, because the quantity being bounded is the number
    of generations dispatched blind. Call it exactly once per ``/generate``,
    after quota enforcement and before any provider is reached.

    The dispatch budget is **not** reset by a success, unlike the failure
    counter. It is a per-container lifetime allowance: a container that has
    already spent it has demonstrated it is running against an unreliable
    store, and Lambda will recycle it soon enough. Resetting it on every
    recovery would give a flapping store an unbounded budget, which is the
    one failure mode this cannot afford to permit.
    """
    global _degraded_dispatches
    with _lock:
        if _consecutive_failures < config.store_failure_threshold:
            return False
        if _degraded_dispatches >= config.degraded_dispatch_budget:
            return True
        _degraded_dispatches += 1
        remaining = config.degraded_dispatch_budget - _degraded_dispatches

    StructuredLogger.error(
        "Quota store is unreachable; dispatching without cost guards",
        consecutiveFailures=_consecutive_failures,
        degradedDispatchesRemaining=remaining,
    )
    return False


def state() -> dict[str, int]:
    """Current counters, for logging and assertions. Never for a decision."""
    with _lock:
        return {
            "consecutiveFailures": _consecutive_failures,
            "degradedDispatches": _degraded_dispatches,
        }


def reset() -> None:
    """Clear both counters.

    **For tests only.** Module-level state that leaks between tests is how a
    suite starts passing for the wrong reason, so every test that touches the
    breaker resets it in a fixture. Nothing in the request path calls this: a
    breaker something can switch off is not a breaker.
    """
    global _consecutive_failures, _degraded_dispatches
    with _lock:
        _consecutive_failures = 0
        _degraded_dispatches = 0
