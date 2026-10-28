#!/usr/bin/env python3
"""Materialize actual user-request scenarios returned by bootstrap probes.

Benchmark matrix cells are priors/provenance, not scenarios.  This tool joins a
completed run back to its source registry and extracts the concrete ``User
request`` emitted by the target into an auditable JSON artifact.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path


REQUEST_PATTERNS = (
    re.compile(r"(?:\*\*)?(?:User request|Realistic request(?: \([^)]*\))?|Example request(?: \([^)]*\))?|Request)(?:\*\*)?:\s*[“\"']?(.*?)[”\"']?(?=\n\s*\n|\n\*\*|$)", re.I | re.S),
    re.compile(r"(?:\*\*)?(?:Scenario|Assumed scenario)(?: \([^)]*\))?(?:\*\*)?[.:]\s*.*?[“\"](.*?)[”\"]", re.I | re.S),
    re.compile(r"(?:user asks|asks):\s*[“\"](.*?)[”\"]", re.I | re.S),
)


def extract_request(text: str) -> str | None:
    for pattern in REQUEST_PATTERNS:
        match = pattern.search(text)
        if match:
            return " ".join(match.group(1).strip().split()).strip("“”\"'")
    return None


def materialize(run_root: Path) -> list[dict]:
    registry = json.loads((run_root / "input/scenarios.json").read_text())
    source = {row["scenario_id"]: row for row in registry["scenarios"]}
    db = sqlite3.connect(run_root / "output/sampler.db")
    rows = db.execute(
        """SELECT r.run_id, s.scenario_id, s.sample_json, e.event_json
           FROM runs r JOIN samples s ON s.sample_id=r.sample_id
           JOIN events e ON e.run_id=r.run_id
           WHERE r.status='completed' AND e.event_type='response.completed'
           ORDER BY r.completed_at, r.run_id"""
    ).fetchall()
    observed = []
    for run_id, scenario_id, sample_json, event_json in rows:
        event = json.loads(event_json)
        text = event.get("data", {}).get("text", "")
        request = extract_request(text)
        if not request:
            continue
        prior = source[scenario_id]
        benchmark = next((tag.split(":", 1)[1] for tag in prior.get("tags", []) if tag.startswith("benchmark:")), None)
        # The benchmark and its coverage bucket are provenance.  They are not
        # inserted as tree levels.  The returned request is the scenario.
        domain = [prior["domain"][0]]
        category = prior["domain"][-1] if len(prior["domain"]) > 1 else None
        observed.append({
            "scenario_instance_id": f"observed.{run_id}",
            "source_scenario_id": scenario_id,
            "user_request": request,
            "domain": domain,
            "category": category,
            "benchmark_provenance": benchmark,
            "sample": json.loads(sample_json),
            "run_id": run_id,
        })
    return observed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.run_root / "output/observed-scenarios.json"
    scenarios = materialize(args.run_root)
    output.write_text(json.dumps({"schema_version": 1, "kind": "observed_scenarios", "count": len(scenarios), "scenarios": scenarios}, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(scenarios)} observed scenarios to {output}")


if __name__ == "__main__":
    main()
