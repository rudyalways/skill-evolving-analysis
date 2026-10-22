#!/usr/bin/env python3
"""Build the verification file from the skills named in the goal.

Each item in action.ops names skills. This script collects those names,
in op order, and writes one verification_steps item and one
feedback.per_skill item for each. The check list is copied from
verification-output.example.json. The agent fills status and feedback.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from feedback import block
from goal_slice import slice_goal

ROOT = Path(__file__).resolve().parent
AGENT = ROOT.parents[1]
EXAMPLE = ROOT / "verification-output.example.json"
DEFAULT_GOAL = AGENT / "workspace" / "run" / "evolve-goal.json"
DEFAULT_OUT = AGENT / "workspace" / "run" / "verification.json"
DEFAULT_CHANGELOG = AGENT / "workspace" / "run" / "changelog.json"
DEFAULT_INPUT = AGENT / "workspace" / "run" / "verification-input.json"
_NAMES = AGENT / "common" / "skill_names.py"
_spec = importlib.util.spec_from_file_location("skill_names", _NAMES)
skill_names_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skill_names_mod)


def fail(problem: str, fix: str) -> None:
    print(
        block(
            "",
            "verification_from_goal",
            problem,
            fix,
            "Goal",
        )
    )
    raise SystemExit(1)


def skills_in_ops(goal: dict) -> list[str]:
    ops = (goal.get("action") or {}).get("ops") or []
    if not isinstance(ops, list):
        fail("action.ops must be a list", "Write action.ops as a list of op objects in workspace/run/evolve-goal.json.")
    found: list[str] = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        for name in skill_names_mod.skill_names(op):
            if name.casefold() not in {item.casefold() for item in found}:
                found.append(name)
    return found


def prior_retries(path: Path) -> tuple[dict[str, int], int | None]:
    if not path.is_file():
        return {}, None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}, None
    feedback = data.get("feedback") or {}
    budget = feedback.get("retry_budget")
    kept_budget = budget if isinstance(budget, int) else None
    found: dict[str, int] = {}
    for row in feedback.get("per_skill") or []:
        if not isinstance(row, dict) or not isinstance(row.get("skill"), str):
            continue
        used = row.get("retries_used")
        if isinstance(used, int):
            found[row["skill"].casefold()] = used
    return found, kept_budget


def build(
    goal: dict,
    example: dict,
    earlier: dict[str, int],
    budget: int | None,
    changelog: dict | None = None,
    input_sha256: str | None = None,
) -> dict:
    skills = skills_in_ops(goal)
    if not skills:
        fail(
            "goal names no skills",
            "Name each skill on its action in action.ops. A skill field or a string in skills counts.",
        )
    steps = example.get("verification_steps") or []
    per_skill = (example.get("feedback") or {}).get("per_skill") or []
    if not steps or not isinstance(steps[0], dict):
        fail(
            "verification example needs one verification_steps item",
            "Restore the item in 05_verifiter_agent/verifiter/verification-output.example.json.",
        )
    if not per_skill or not isinstance(per_skill[0], dict):
        fail(
            "verification example needs one per_skill item",
            "Restore the per_skill item in 05_verifiter_agent/verifiter/verification-output.example.json.",
        )
    out = copy.deepcopy(example)
    out["verification_steps"] = []
    out["feedback"]["per_skill"] = []
    out["feedback"]["ood"] = []
    out["feedback"]["action"] = None
    out["changelog"] = copy.deepcopy((changelog or {}).get("changes") or [])
    if input_sha256 is not None:
        out["verification_input"] = {
            "path": "verification-input.json",
            "sha256": input_sha256,
        }
    if budget is not None:
        out["feedback"]["retry_budget"] = budget
    for name in skills:
        step = copy.deepcopy(steps[0])
        step["skill"] = name
        out["verification_steps"].append(step)
        row = copy.deepcopy(per_skill[0])
        row["skill"] = name
        row["retries_used"] = earlier.get(name.casefold(), 0)
        row["action"] = None
        out["feedback"]["per_skill"].append(row)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("goal", nargs="?", type=Path, default=DEFAULT_GOAL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--changelog", type=Path, default=DEFAULT_CHANGELOG)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--stdout", action="store_true")
    parser.add_argument("--op", type=int, help="1-based action.ops index for this loop")
    args = parser.parse_args()
    goal = slice_goal(json.loads(args.goal.read_text()), args.op)
    earlier, budget = prior_retries(args.out)
    try:
        changelog = json.loads(args.changelog.read_text())
    except FileNotFoundError:
        fail(
            "operation changelog was not produced",
            "Run the optimize stage through the pipeline so workspace/run/changelog.json is materialized.",
        )
    except json.JSONDecodeError:
        fail(
            "operation changelog is invalid JSON",
            "Rebuild workspace/run/changelog.json from the active operation.",
        )
    try:
        input_bytes = args.input.read_bytes()
        json.loads(input_bytes)
    except FileNotFoundError:
        fail(
            "verification input was not produced",
            "Run the optimize stage through the pipeline so workspace/run/verification-input.json is materialized.",
        )
    except json.JSONDecodeError:
        fail(
            "verification input is invalid JSON",
            "Rebuild workspace/run/verification-input.json from the active goal.",
        )
    out = build(
        goal,
        json.loads(EXAMPLE.read_text()),
        earlier,
        budget,
        changelog,
        hashlib.sha256(input_bytes).hexdigest(),
    )
    text = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    if args.stdout:
        sys.stdout.write(text)
        return
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(f"wrote {len(out['verification_steps'])} skills to {args.out}")


if __name__ == "__main__":
    main()
