#!/usr/bin/env python3
"""Reject benchmark trials contaminated by answer/oracle discovery."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REMOTE_TOOL = re.compile(r"\b(curl|wget|git\s+clone|google|duckduckgo|github)\b", re.I)
ANSWER_MARKER = re.compile(
    r"(?:artifacts/(?:skills|solutions?)/|(?:^|/)oracle(?:/|\b)|"
    r"(?:^|/)solution(?:/|\b)|benchmark.{0,30}(?:answer|solution))",
    re.I,
)


def audit(trajectory: Path, task_id: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    task_token = task_id.lower().replace("_", "-")
    for line_number, line in enumerate(trajectory.read_text(errors="replace").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "tool_call":
            continue
        text = json.dumps(event, ensure_ascii=False)
        lower = text.lower().replace("_", "-")
        if REMOTE_TOOL.search(text) and (
            task_token in lower or ANSWER_MARKER.search(text)
        ):
            matches.append({
                "line": line_number,
                "tool": event.get("title") or event.get("kind"),
                "reason": "remote-answer-discovery",
            })
        elif task_token in lower and ANSWER_MARKER.search(text):
            matches.append({
                "line": line_number,
                "tool": event.get("title") or event.get("kind"),
                "reason": "task-specific-answer-artifact",
            })
    return {
        "schema_version": 1,
        "task_id": task_id,
        "trajectory": str(trajectory),
        "valid": not matches,
        "exclusion_reasons": sorted({row["reason"] for row in matches}),
        "matches": matches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trajectory", type=Path)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--require-valid", action="store_true")
    args = parser.parse_args()
    report = audit(args.trajectory, args.task_id)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.require_valid and not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
