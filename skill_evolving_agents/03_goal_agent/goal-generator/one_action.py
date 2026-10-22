#!/usr/bin/env python3
"""Ensure each skill is named by only one action.

Each item in action.ops is one action. A skill name is a `skill` field,
or a string in a `skills` list. Angle brackets around a fill-in value
are ignored. The same name in two actions fails.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENT = ROOT.parents[1]
DEFAULT_GOAL = AGENT / "workspace" / "run" / "evolve-goal.json"
_NAMES = AGENT / "common" / "skill_names.py"
_spec = importlib.util.spec_from_file_location("skill_names", _NAMES)
skill_names_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skill_names_mod)
skill_names = skill_names_mod.skill_names
_CONTRACTS = AGENT / "common" / "pipeline_contracts.py"
_contract_spec = importlib.util.spec_from_file_location(
    "pipeline_contracts", _CONTRACTS
)
pipeline_contracts = importlib.util.module_from_spec(_contract_spec)
_contract_spec.loader.exec_module(pipeline_contracts)


def check(goal: dict) -> list[str]:
    ops = (goal.get("action") or {}).get("ops") or []
    if not isinstance(ops, list):
        raise SystemExit("action.ops must be a list")
    seen: dict[str, str] = {}
    problems: list[str] = []
    for index, op in enumerate(ops, start=1):
        if not isinstance(op, dict):
            continue
        label = f"{index}:{op.get('op')}"
        for name in skill_names(op):
            previous = seen.get(name.casefold())
            if previous is not None:
                problems.append(f"{name} is in {previous} and {label}")
            else:
                seen[name.casefold()] = label
    return problems


def validate(path: Path) -> list[str]:
    return check(pipeline_contracts.validate_goal(path))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("goal", nargs="?", type=Path, default=DEFAULT_GOAL)
    args = parser.parse_args()
    problems = validate(args.goal)
    if problems:
        print("one action: fail")
        for line in problems:
            name = line.split(" is in ", 1)[0]
            print(f"skill: {name}")
            print("check: one action")
            print(f"problem: {line}")
            print(
                f"fix: Keep {name} in only one action.ops item. Remove it from the other action."
            )
            print("next: Goal")
            print()
        sys.exit(1)
    print("one action: pass")


if __name__ == "__main__":
    main()
