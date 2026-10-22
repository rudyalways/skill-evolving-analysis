#!/usr/bin/env python3
"""Build the verification file from the skills named in the goal.

Each item in action.ops names skills. This script collects those names,
in op order, and writes one verification_steps item and one
feedback.per_skill item for each. The check list is copied from
the runtime verification-input.json, including goal-derived assertions.
verification-output.template.json supplies only the output envelope. The agent
fills status and feedback.
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
TEMPLATE = ROOT / "verification-output.template.json"
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


def build(
    goal: dict,
    example: dict,
    changelog: dict | None = None,
    input_sha256: str | None = None,
    verification_input: dict | None = None,
) -> dict:
    skills = skills_in_ops(goal)
    if not skills:
        fail(
            "goal names no skills",
            "Name each skill on its action in action.ops. A skill field or a string in skills counts.",
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
    out["feedback"]["retry_budget"] = 0
    input_skills = {
        row.get("skill"): row
        for row in (verification_input or {}).get("skills") or []
        if isinstance(row, dict)
    }
    input_skill_positions = {
        row.get("skill"): index
        for index, row in enumerate((verification_input or {}).get("skills") or [])
        if isinstance(row, dict)
    }
    input_checks = (verification_input or {}).get("checks") or {}
    for name in skills:
        if name not in input_skills:
            fail(
                f"verification input is missing skill {name}",
                "Rebuild workspace/run/verification-input.json from the active operation.",
            )
        step = {
            "skill": name,
            "used_by": "verifier stage",
            "steps_from": (
                "verification-input.json#/skills/"
                f"{input_skill_positions[name]}/checks"
            ),
            "steps": [],
        }
        input_skill = input_skills.get(name) or {}
        role = input_skill.get("role")
        skill_checks = {
            check.get("id"): check
            for check in input_skill.get("checks") or []
            if isinstance(check, dict)
        }
        skill_check_positions = {
            check.get("id"): index
            for index, check in enumerate(input_skill.get("checks") or [])
            if isinstance(check, dict)
        }
        applicable_weight = 0.0
        for step_id, input_check in input_checks.items():
            skill_check = skill_checks.get(step_id) or {}
            applicable = skill_check.get(
                "applicable",
                role in (input_check.get("applies_to") or []),
            )
            result = {
                "id": step_id,
                "check": input_check.get("check"),
                "input_ref": (
                    f"#/skills/{input_skill_positions[name]}/checks/"
                    f"{skill_check_positions[step_id]}"
                ),
                "applicable": applicable,
            }
            if applicable:
                applicable_weight += float(
                    ((verification_input or {}).get("scoring") or {})
                    .get("step_weights", {})
                    .get(step_id, 0)
                )
            if applicable:
                result.update(
                    {
                        "status": "<pass|fail>",
                        "score": 0.0,
                        "reasoning": (
                            "<why this score follows from the assertions "
                            "and evidence>"
                        ),
                        "evidence": ["<observed result>"],
                        "assertion_results": [
                            {
                                "assertion_id": assertion.get("id"),
                                "status": "<pass|fail>",
                                "score": 0.0,
                                "reasoning": (
                                    "<why the assertion passed or failed>"
                                ),
                                "evidence": ["<observed result>"],
                            }
                            for assertion in [
                                *(input_check.get("assertions") or []),
                                *(skill_check.get("assertions") or []),
                            ]
                            if isinstance(assertion, dict)
                        ],
                    }
                )
            else:
                result["status"] = "not_applicable"
                result["score"] = None
                result["reasoning"] = f"Step does not apply to skill role {role}."
                result["evidence"] = []
                result["assertion_results"] = []
            step["steps"].append(result)
        out["verification_steps"].append(step)
        row = {
            "skill": name,
            "status": "<pass|fail>",
            "score": 0.0,
            "applicable_weight": applicable_weight,
            "failed_required_steps": [],
            "penalties": [],
            "feedback": "<text>",
            "retries_used": 0,
            "action": None,
        }
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
        verification_input = json.loads(input_bytes)
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
        json.loads(TEMPLATE.read_text()),
        changelog,
        hashlib.sha256(input_bytes).hexdigest(),
        verification_input,
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
