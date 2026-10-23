"""Aggregate phase-envelope metrics by mode and algorithm."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def summarize_phase_envelopes(workspace: Path) -> dict[str, Any]:
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "wall_ms": 0.0,
            "statuses": defaultdict(int),
            "dispositions": defaultdict(int),
        }
    )
    for path in (workspace / "run/status").glob("**/*.json"):
        try:
            row = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or row.get("schema_version") != 1:
            continue
        implementation = row.get("implementation") or {}
        decision = row.get("decision") or {}
        phase = str(row.get("phase") or "unknown")
        algorithm = str(implementation.get("name") or "unknown")
        cost_tier = str(implementation.get("cost_tier", "unknown"))
        mode = str(decision.get("mode") or "unknown")
        group = groups[(phase, algorithm, mode, cost_tier)]
        group["count"] += 1
        wall = (row.get("measurements") or {}).get("wall_ms")
        if isinstance(wall, (int, float)) and not isinstance(wall, bool):
            group["wall_ms"] += float(wall)
        group["statuses"][str(row.get("status") or "unknown")] += 1
        group["dispositions"][str(decision.get("disposition") or "unknown")] += 1
    rows = []
    for (phase, algorithm, mode, cost_tier), group in sorted(groups.items()):
        count = group["count"]
        rows.append(
            {
                "phase": phase,
                "algorithm": algorithm,
                "mode": mode,
                "cost_tier": cost_tier,
                "count": count,
                "average_wall_ms": round(group["wall_ms"] / count, 3),
                "statuses": dict(group["statuses"]),
                "dispositions": dict(group["dispositions"]),
            }
        )
    return {"schema_version": 1, "groups": rows}

