#!/usr/bin/env python3
"""Verify each skill named by a delete action is gone.

A delete item in action.ops names a skill. That skill directory must
not remain under target/to_be_improved_skills.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from feedback import block
from goal_slice import slice_goal

ROOT = Path(__file__).resolve().parent
AGENT = ROOT.parents[1]
DEFAULT_GOAL = AGENT / "workspace" / "run" / "evolve-goal.json"
DEFAULT_IMPROVED = AGENT / "workspace" / "target" / "to_be_improved_skills"
_CHECKER = (
    AGENT / "common" / "skill_format_checker.py"
)
_spec = importlib.util.spec_from_file_location("skill_format_checker", _CHECKER)
skill_format_checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skill_format_checker)


def deleted_skills(goal: dict) -> list[str]:
    found: list[str] = []
    for op in (goal.get("action") or {}).get("ops") or []:
        if not isinstance(op, dict) or op.get("op") != "delete":
            continue
        for item in op.get("skills") or []:
            name = skill_format_checker.skill_name(item)
            if name and name.casefold() not in {kept.casefold() for kept in found}:
                found.append(name)
    return found


def check(goal: dict, improved_root: Path) -> list[str]:
    problems: list[str] = []
    for name in deleted_skills(goal):
        if (improved_root / name).exists():
            problems.append(
                block(
                    name,
                    "delete",
                    f"{name} is still in to_be_improved_skills",
                    f"Remove target/to_be_improved_skills/{name}.",
                    "Delete",
                )
            )
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("goal", nargs="?", type=Path, default=DEFAULT_GOAL)
    parser.add_argument("--improved", type=Path, default=DEFAULT_IMPROVED)
    parser.add_argument("--op", type=int, help="1-based action.ops index for this loop")
    args = parser.parse_args()
    goal = slice_goal(json.loads(args.goal.read_text()), args.op)
    names = deleted_skills(goal)
    if not names:
        print("delete: no skills")
        return
    problems = check(goal, args.improved)
    if problems:
        print("delete: fail")
        for line in problems:
            print(line)
            print()
        sys.exit(1)
    print(f"delete: pass {', '.join(names)}")


if __name__ == "__main__":
    main()
