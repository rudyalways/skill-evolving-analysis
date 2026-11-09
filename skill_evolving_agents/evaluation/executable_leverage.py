#!/usr/bin/env python3
"""Measure executable leverage from a skill-activation audit.

The funnel is intentionally stricter than "a skill was present":

``discovered -> opened -> executed -> succeeded -> reduced calls``

A mounted or listed resource is not use.  A read is not execution.  A command
attempt is not success.  Execution that does not reduce paired tool calls is
recorded as ``succeeded-no-reduction`` instead of being celebrated as lift.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

STAGES = ("discovered", "opened", "executed", "succeeded", "reduced_calls")


def _rows(usage: dict[str, Any]) -> list[dict[str, Any]]:
    rows = usage.get("skills")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def measure(
    usage: dict[str, Any],
    *,
    baseline_tool_calls: int,
    treatment_tool_calls: int,
) -> dict[str, Any]:
    """Return one auditable leverage row for a paired treatment trial."""
    rows = _rows(usage)
    discovered = {
        resource
        for row in rows
        for resource in row.get("resources_discovered") or []
        if isinstance(resource, str) and resource
    }
    if rows:
        # An activated skill is discovered even when the trajectory only shows
        # the SKILL.md read and no separate resource listing.
        discovered.add("SKILL.md")
    opened = {
        resource
        for row in rows
        for resource in row.get("resources_observed") or []
        if isinstance(resource, str) and resource
    }
    if any(
        row.get("skill_md_read") or row.get("skill_md_injected") for row in rows
    ):
        opened.add("SKILL.md")
    attempted = {
        resource
        for row in rows
        for resource in (
            (row.get("script_execution") or {}).get("attempted") or []
        )
        if isinstance(resource, str) and resource
    }
    succeeded = {
        resource
        for row in rows
        for resource in (
            (row.get("script_execution") or {}).get("succeeded") or []
        )
        if isinstance(resource, str) and resource
    }
    reported = {
        resource
        for row in rows
        for resource in (
            (row.get("script_execution") or {}).get("reported") or []
        )
        if isinstance(resource, str) and resource
    }
    reported_succeeded = {
        resource
        for row in rows
        for resource in (
            (row.get("script_execution") or {}).get("reported_succeeded") or []
        )
        if isinstance(resource, str) and resource
    }
    baseline = max(0, int(baseline_tool_calls))
    treatment = max(0, int(treatment_tool_calls))
    reduced = treatment < baseline
    executable_available = any(
        resource.startswith("scripts/")
        for resource in discovered | opened | attempted | succeeded | reported
    )
    stages = {
        "discovered": bool(discovered),
        "opened": bool(opened),
        "executed": bool(attempted) if executable_available else None,
        "succeeded": (
            bool(succeeded & attempted) if attempted else bool(succeeded)
        )
        if executable_available
        else None,
        "reduced_calls": (
            reduced and bool(succeeded)
            if executable_available
            else reduced and bool(opened)
        ),
    }
    applicable = (
        STAGES
        if executable_available
        else ("discovered", "opened", "reduced_calls")
    )
    highest = 0
    for index, stage in enumerate(applicable, start=1):
        if not stages[stage]:
            break
        highest = index
    reported_execution = bool(reported)
    reported_success = bool(reported_succeeded & reported)
    if not executable_available:
        claim = "methodology-leverage" if stages["reduced_calls"] else (
            "opened-only" if stages["opened"] else (
                "discovered-only" if stages["discovered"] else "no-resource-evidence"
            )
        )
    elif reported_success and reduced and not succeeded:
        # The ACP adapter may drop command input while preserving the agent's
        # final command report. Keep this weaker claim explicit.
        claim = "reported-executable-leverage"
    elif highest == len(STAGES):
        claim = "executable-leverage"
    elif stages["succeeded"]:
        claim = "succeeded-no-reduction"
    elif stages["executed"]:
        claim = "executed-not-succeeded"
    elif stages["opened"]:
        claim = "opened-only"
    elif stages["discovered"]:
        claim = "discovered-only"
    else:
        claim = "no-resource-evidence"
    highest_stage = STAGES[highest - 1] if highest else None
    highest_count = highest
    leverage_score = round(highest / len(applicable), 6)
    if claim == "reported-executable-leverage":
        highest_stage = "reported-execution"
        highest_count = 4
        leverage_score = 0.8
    return {
        "schema_version": 1,
        "stages": stages,
        "highest_stage": highest_stage,
        "stage_count": highest_count,
        "leverage_score": leverage_score,
        "applicable_stages": list(applicable),
        "executable_available": executable_available,
        "reported_execution": reported_execution,
        "reported_succeeded": reported_success,
        "execution_evidence": (
            "observed" if succeeded else "reported" if reported_execution else None
        ),
        "claim": claim,
        "baseline_tool_calls": baseline,
        "treatment_tool_calls": treatment,
        "tool_call_delta": treatment - baseline,
        "tool_call_reduction": baseline - treatment,
        "resources": {
            "discovered": sorted(discovered),
            "opened": sorted(opened),
            "executed": sorted(attempted),
            "succeeded": sorted(succeeded),
            "reported": sorted(reported),
            "reported_succeeded": sorted(reported_succeeded),
        },
    }


def aggregate(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarize leverage rows without upgrading a partial stage to a claim."""
    values = [row for row in rows if isinstance(row, dict)]
    total = len(values)
    stage_counts = {
        stage: sum(bool((row.get("stages") or {}).get(stage)) for row in values)
        for stage in STAGES
    }
    claims: dict[str, int] = {}
    for row in values:
        claim = str(row.get("claim") or "unknown")
        claims[claim] = claims.get(claim, 0) + 1
    reductions = [int(row.get("tool_call_reduction") or 0) for row in values]
    return {
        "schema_version": 1,
        "pairs": total,
        "stage_counts": stage_counts,
        "stage_rates": {
            stage: round(count / total, 6) if total else None
            for stage, count in stage_counts.items()
        },
        "executable_leverage_rate": (
            round(stage_counts["reduced_calls"] / total, 6) if total else None
        ),
        "claims": dict(sorted(claims.items())),
        "mean_tool_call_reduction": (
            round(sum(reductions) / total, 6) if total else None
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trajectory", type=Path)
    parser.add_argument("--baseline-tool-calls", type=int, required=True)
    parser.add_argument("--treatment-tool-calls", type=int, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    import sys

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from evaluation.skillsbench_skill_usage import audit

    row = measure(
        audit(args.trajectory),
        baseline_tool_calls=args.baseline_tool_calls,
        treatment_tool_calls=args.treatment_tool_calls,
    )
    text = json.dumps(row, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
