"""Leakage-resistant scoring for pipeline configuration search."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from .optimization import OptimizationError

STAGES = ("train", "validation", "holdout")


def _wilson_low(passed: int, total: int) -> float:
    if total == 0:
        return 0.0
    z = 1.959963984540054
    p = passed / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return center - radius


def _stage_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    treatment_passes = sum(bool(row.get("treatment_passed")) for row in rows)
    baseline_passes = sum(bool(row.get("baseline_passed")) for row in rows)
    regressions = sum(
        bool(row.get("baseline_passed")) and not bool(row.get("treatment_passed"))
        for row in rows
    )
    lifts = sum(
        not bool(row.get("baseline_passed")) and bool(row.get("treatment_passed"))
        for row in rows
    )
    efficiency_failures = sum(bool(row.get("efficiency_failure")) for row in rows)
    call_deltas = [
        float(row["treatment_tool_calls"]) - float(row["baseline_tool_calls"])
        for row in rows
        if isinstance(row.get("baseline_tool_calls"), (int, float))
        and isinstance(row.get("treatment_tool_calls"), (int, float))
    ]
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_domain[str(row.get("domain") or "unknown")].append(row)
    domain_lifts = {
        domain: (
            sum(bool(row.get("treatment_passed")) for row in values) / len(values)
            - sum(bool(row.get("baseline_passed")) for row in values) / len(values)
        )
        for domain, values in by_domain.items()
    }
    lift_domains = Counter(
        str(row.get("domain") or "unknown")
        for row in rows
        if not bool(row.get("baseline_passed")) and bool(row.get("treatment_passed"))
    )
    concentration = max(lift_domains.values(), default=0) / max(lifts, 1)
    return {
        "tasks": total,
        "domains": len(by_domain),
        "baseline_pass_rate": baseline_passes / total if total else 0.0,
        "treatment_pass_rate": treatment_passes / total if total else 0.0,
        "treatment_wilson_low_95": _wilson_low(treatment_passes, total),
        "absolute_lift": (treatment_passes - baseline_passes) / total if total else 0.0,
        "lifts": lifts,
        "regressions": regressions,
        "regression_rate": regressions / total if total else 0.0,
        "efficiency_failures": efficiency_failures,
        "efficiency_failure_rate": efficiency_failures / total if total else 0.0,
        "mean_tool_call_delta": sum(call_deltas) / len(call_deltas) if call_deltas else 0.0,
        "lift_domain_concentration": concentration,
        "by_domain_lift": dict(sorted(domain_lifts.items())),
    }


def evaluate_generalization(
    observations: list[dict[str, Any]], policy: dict[str, Any]
) -> dict[str, Any]:
    """Score validation evidence while keeping holdout completely sealed.

    Holdout outcomes are reported only as a final gate.  They never affect the
    search reward, preventing MCTS or another optimizer from learning the test
    cohort through repeated trials.
    """
    unknown = sorted({str(row.get("stage")) for row in observations} - set(STAGES))
    if unknown:
        raise OptimizationError(f"unknown generalization stages: {', '.join(unknown)}")
    memberships: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in observations:
        stage = str(row.get("stage"))
        for field in ("task_id", "group_id"):
            value = row.get(field)
            if value is not None and str(value).strip():
                memberships[(field, str(value))].add(stage)
    leaks = [
        f"{field}={value} ({','.join(sorted(stages))})"
        for (field, value), stages in memberships.items()
        if len(stages) > 1
    ]
    if leaks:
        raise OptimizationError(
            "cross-stage benchmark leakage: " + "; ".join(sorted(leaks))
        )
    grouped = {
        stage: _stage_summary([row for row in observations if row.get("stage") == stage])
        for stage in STAGES
    }
    validation = grouped["validation"]
    weights = policy.get("search_reward") or {}
    search_reward = (
        float(weights.get("pass_rate", 1.0)) * validation["treatment_pass_rate"]
        + float(weights.get("absolute_lift", 1.0)) * validation["absolute_lift"]
        - float(weights.get("regression_rate", 2.0)) * validation["regression_rate"]
        - float(weights.get("efficiency_failure_rate", 1.0))
        * validation["efficiency_failure_rate"]
        - float(weights.get("lift_domain_concentration", 0.25))
        * validation["lift_domain_concentration"]
        - float(weights.get("positive_call_delta", 0.001))
        * max(validation["mean_tool_call_delta"], 0.0)
    )
    minimum = policy.get("minimum_evidence") or {}
    validation_eligible = (
        validation["tasks"] >= int(minimum.get("validation_tasks", 12))
        and validation["domains"] >= int(minimum.get("validation_domains", 6))
        and validation["regressions"] <= int(policy.get("maximum_regressions", 0))
        and validation["efficiency_failure_rate"]
        <= float(policy.get("maximum_efficiency_failure_rate", 0.1))
        and validation["absolute_lift"] > 0
    )
    holdout = grouped["holdout"]
    holdout_present = holdout["tasks"] > 0
    milestone_met = holdout_present and (
        holdout["tasks"] >= int(minimum.get("holdout_tasks", 16))
        and holdout["domains"] >= int(minimum.get("holdout_domains", 8))
        and holdout["treatment_pass_rate"] >= float(policy.get("target_pass_rate", 0.6))
        and holdout["regressions"] <= int(policy.get("maximum_regressions", 0))
        and holdout["efficiency_failure_rate"]
        <= float(policy.get("maximum_efficiency_failure_rate", 0.1))
    )
    return {
        "schema_version": 1,
        "search_reward": round(search_reward, 8),
        "search_uses_stages": ["validation"],
        "holdout_used_for_search": False,
        "cross_stage_leakage": False,
        "validation_eligible": validation_eligible,
        "milestone_met": milestone_met,
        "decision": (
            "target_met" if milestone_met else
            "advance_to_sealed_holdout" if validation_eligible and not holdout_present else
            "continue_search"
        ),
        "stages": grouped,
    }
