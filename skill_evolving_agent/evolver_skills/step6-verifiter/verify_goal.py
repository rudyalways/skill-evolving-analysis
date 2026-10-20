#!/usr/bin/env python3
"""Run the goal-align verification step.

The step is the item in verification.example.json whose ref is evolve-goal.
Pass the run's evolve goal. The script checks that every section and
directory on that goal is on the closed list or named as other, then
compares each updated skill under target/raw_skills with the copy under
target/to_be_improved_skills.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENT = ROOT.parents[1]
EXAMPLE = ROOT / "verification.example.json"
DEFAULT_GOAL = AGENT / "workspace" / "run" / "evolve-goal.json"
_CHECKER = ROOT.parent / "reference-skill_format" / "skill_format_checker.py"
_spec = importlib.util.spec_from_file_location("skill_format_checker", _CHECKER)
skill_format_checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skill_format_checker)


def goal_step(example: dict) -> dict:
    steps = (example.get("verification_steps") or {}).get("steps") or []
    for step in steps:
        if isinstance(step, dict) and step.get("ref") == "evolve-goal":
            return step
    raise SystemExit("verification example has no step with ref evolve-goal")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("goal", nargs="?", type=Path, default=DEFAULT_GOAL)
    parser.add_argument("--list", type=Path, default=skill_format_checker.DEFAULT_LIST)
    args = parser.parse_args()
    step = goal_step(json.loads(EXAMPLE.read_text()))
    label = f"{step.get('id')} {step.get('check')}"
    sections, dirs, others = skill_format_checker.load_list(args.list)
    errors = skill_format_checker.check_goal(args.goal, sections, dirs, others)
    goal = json.loads(args.goal.read_text())
    stored = skill_format_checker.compare_stored(
        goal,
        sections,
        dirs,
        others,
        skill_format_checker.DEFAULT_RAW,
        skill_format_checker.DEFAULT_IMPROVED,
    )
    problems = errors + stored
    if problems:
        print(f"{label}: fail")
        for line in problems:
            print(line)
        sys.exit(1)
    print(f"{label}: pass")


if __name__ == "__main__":
    main()
