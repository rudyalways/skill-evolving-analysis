#!/usr/bin/env python3
"""Aggregate comparable funnel, operation, cost, and resource statistics."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def aggregate(runs: list[Path]) -> dict[str, Any]:
    totals = Counter()
    operations = Counter()
    dispositions = Counter()
    resources = Counter()
    rows = []
    for run in runs:
        metrics = json.loads((run / "logs/phase-metrics.json").read_text())
        summary = json.loads((run / "run/pipeline-summary.json").read_text())
        funnel = metrics.get("funnel") or {}
        cost = ((metrics.get("phases") or {}).get("cost") or {})
        resource = ((metrics.get("phases") or {}).get("resources") or {})
        for key in ("selected_findings", "diagnosed_findings", "novel_goal_scopes", "proposed_operations", "accepted_proposals", "changed_scopes"):
            totals[key] += int(funnel.get(key) or 0)
        totals["agent_calls_actual"] += int(cost.get("agent_calls_actual") or 0)
        totals["agent_calls_avoided"] += int(cost.get("estimated_agent_calls_avoided") or 0)
        operations.update(funnel.get("accepted_operation_type_distribution") or {})
        dispositions[str(funnel.get("run_disposition") or "unknown")] += 1
        for key in ("skills", "operations", "unused_resources", "resource_plan_noncompliance"):
            resources[key] += int(resource.get(key) or 0)
        rows.append({"run_id": run.name, "outcome": summary.get("outcome"), "funnel": funnel, "cost": cost, "resources": resource})
    selected = totals["selected_findings"]
    proposed = totals["proposed_operations"]
    return {
        "schema_version": 1,
        "run_count": len(runs),
        "totals": dict(totals),
        "rates": {
            "proposal_per_selected_finding": round(proposed / selected, 6) if selected else None,
            "acceptance_per_proposal": round(totals["accepted_proposals"] / proposed, 6) if proposed else None,
            "changed_scope_per_selected_finding": round(totals["changed_scopes"] / selected, 6) if selected else None,
            "agent_call_avoidance": round(totals["agent_calls_avoided"] / (totals["agent_calls_actual"] + totals["agent_calls_avoided"]), 6) if totals["agent_calls_actual"] + totals["agent_calls_avoided"] else None,
        },
        "accepted_operations": dict(operations),
        "run_dispositions": dict(dispositions),
        "resource_totals": dict(resources),
        "runs": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = aggregate(args.runs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
