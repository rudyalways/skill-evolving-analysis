#!/usr/bin/env python3
"""Append a normalized objective-verifier event to a SkillsBench ACP trace."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ASSERTION = re.compile(r"(?:E\s+)?AssertionError:\s*(.+)")
MOUNTED_SKILL = re.compile(r"<mounted-skill path=/skills/([^/]+)/SKILL\.md>")


def verifier_failures(ctrf: dict[str, Any]) -> list[dict[str, str]]:
    failures = []
    for row in ((ctrf.get("results") or {}).get("tests") or []):
        if not isinstance(row, dict) or row.get("status") != "failed":
            continue
        trace = str(row.get("trace") or row.get("message") or "")
        matches = ASSERTION.findall(trace)
        failures.append(
            {
                "test": str(row.get("name") or "unknown"),
                "assertion": matches[-1].strip() if matches else str(row.get("message") or "failed"),
            }
        )
    return failures


def export(trial: Path, output: Path) -> dict[str, Any]:
    trajectory = trial / "trajectory/acp_trajectory.jsonl"
    trajectory_text = trajectory.read_text(errors="replace")
    activated_skills = sorted(set(MOUNTED_SKILL.findall(trajectory_text)))
    result = json.loads((trial / "result.json").read_text())
    ctrf_path = trial / "verifier/ctrf.json"
    ctrf = json.loads(ctrf_path.read_text()) if ctrf_path.is_file() else {}
    verifier_output_path = trial / "verifier/test-stdout.txt"
    verifier_output = (
        verifier_output_path.read_text(errors="replace")
        if verifier_output_path.is_file()
        else ""
    )
    payload = {
        "error": result.get("verifier_error"),
        "agent_error": result.get("error"),
        "agent_timeout_info": result.get("agent_timeout_info"),
        "timing": result.get("timing"),
        "reward": float((result.get("rewards") or {}).get("reward") or 0),
        "rewards": result.get("rewards") or {},
        "skill_mode": result.get("skill_mode"),
        "activated_skills": activated_skills,
        "tool_calls": result.get("n_tool_calls"),
        "verifier_failures": verifier_failures(ctrf),
        "verifier_output": verifier_output[:50000],
        "verifier_output_truncated": len(verifier_output) > 50000,
    }
    event = {
        "type": "tool_call",
        "tool_call_id": "skillsbench-objective-verifier",
        "kind": "verify",
        "title": "skillsbench_objective_verifier",
        "status": "completed" if payload["reward"] >= 1 else "failed",
        "input": {"source": "benchflow", "objective": True},
        "content": [
            {
                "type": "content",
                "content": {"type": "text", "text": json.dumps(payload)},
            }
        ],
    }
    lines = trajectory_text.splitlines()
    lines.append(json.dumps(event, ensure_ascii=False))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.trial, args.out), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
