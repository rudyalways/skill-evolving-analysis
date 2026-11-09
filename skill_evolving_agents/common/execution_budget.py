"""Strict wall-time, tool-call, and cost budgets with explicit outcomes.

Budgets are hard ceilings: a measurement strictly greater than its limit is a
violation.  A trial or run that exceeds any budget has the outcome
``efficiency_failure`` even when its task verifier passed.  Missing cost data is
recorded as unavailable and does not silently satisfy a non-null cost limit.
"""

from __future__ import annotations

from typing import Any

DEFAULT_BUDGETS: dict[str, Any] = {
    "wall_seconds": 900.0,
    "tool_calls": 120,
    "cost_usd": 2.0,
    "exceeded_outcome": "efficiency_failure",
}

USAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "wall_seconds": ("wall_seconds", "agent_seconds", "time_seconds", "duration_seconds"),
    "tool_calls": ("tool_calls", "n_tool_calls", "tool_call_count"),
    "cost_usd": ("cost_usd", "total_cost_usd", "agent_cost_usd"),
}


class ExecutionBudgetExceeded(RuntimeError):
    """Raised when a hard execution budget is exhausted."""


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def normalize_limits(raw: dict[str, Any] | None) -> dict[str, Any]:
    source = {**DEFAULT_BUDGETS, **(raw or {})}
    limits: dict[str, Any] = {"exceeded_outcome": source.get("exceeded_outcome", "efficiency_failure")}
    for metric in USAGE_ALIASES:
        value = source.get(metric, DEFAULT_BUDGETS[metric])
        number = _number(value)
        if number is not None:
            limits[metric] = number
    return limits


def _usage_value(usage: dict[str, Any], metric: str) -> float | None:
    for key in USAGE_ALIASES[metric]:
        value = _number(usage.get(key))
        if value is not None:
            return value
    return None


def evaluate(
    usage: dict[str, Any],
    limits: dict[str, Any] | None = None,
    *,
    passed: bool | None = None,
) -> dict[str, Any]:
    """Return the budget verdict and the final outcome for one unit of work."""
    active = normalize_limits(limits)
    observed: dict[str, float | None] = {}
    violations: list[dict[str, Any]] = []
    for metric in USAGE_ALIASES:
        limit = active.get(metric)
        value = _usage_value(usage, metric)
        observed[metric] = value
        if limit is None or value is None:
            continue
        if value > limit:
            violations.append({
                "metric": metric,
                "limit": limit,
                "observed": value,
                "overage": round(value - limit, 6),
            })
    within_budget = not violations
    if not within_budget:
        outcome = str(active["exceeded_outcome"])
    elif passed is None:
        outcome = "within_budget"
    else:
        outcome = "passed" if passed else "failed"
    return {
        "schema_version": 1,
        "outcome": outcome,
        "within_budget": within_budget,
        "limits": {key: active[key] for key in USAGE_ALIASES if key in active},
        "observed": observed,
        "violations": violations,
        "cost_available": observed["cost_usd"] is not None,
        "policy": "strict-wall-tool-cost-budget-v1",
    }


def classify_outcome(
    *,
    passed: bool,
    usage: dict[str, Any],
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return evaluate(usage, limits, passed=passed)
