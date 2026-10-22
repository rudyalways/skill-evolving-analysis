#!/usr/bin/env python3
"""Run the goal-align verification step.

The step is the item in verification-output.example.json whose ref is evolve-goal.
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
import tempfile
from pathlib import Path

from feedback import block
from goal_slice import slice_goal

ROOT = Path(__file__).resolve().parent
AGENT = ROOT.parents[1]
EXAMPLE = ROOT / "verification-output.example.json"
DEFAULT_GOAL = AGENT / "workspace" / "run" / "evolve-goal.json"
_CHECKER = (
    AGENT / "common" / "skill_format_checker.py"
)
_spec = importlib.util.spec_from_file_location("skill_format_checker", _CHECKER)
skill_format_checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skill_format_checker)


def goal_step(example: dict) -> dict:
    records = example.get("verification_steps") or []
    if isinstance(records, dict):
        records = [records]
    for record in records:
        if not isinstance(record, dict):
            continue
        for step in record.get("steps") or []:
            if isinstance(step, dict) and step.get("ref") == "evolve-goal":
                return step
    raise SystemExit("verification example has no step with ref evolve-goal")


def explain(line: str) -> str:
    skill = ""
    detail = line
    if ": " in line:
        head, tail = line.split(": ", 1)
        if head not in {"section", "dir", "heading", "file", "other", "frontmatter", "text"}:
            skill = head
            detail = tail
    raw = f"target/raw_skills/{skill}" if skill else "target/raw_skills/<skill>"
    improved = (
        f"target/to_be_improved_skills/{skill}"
        if skill
        else "target/to_be_improved_skills/<skill>"
    )
    if "is not in skill_format.json" in detail or detail in {
        "other section needs a heading",
        "other dir needs a name",
    }:
        fix = "On the goal, use a name from skill_format.json, or set the section or dir to other and give heading or name."
        next_state = "Goal"
    elif detail.startswith("section ") and detail.endswith(" changed"):
        name = detail.removeprefix("section ").removesuffix(" changed")
        fix = f"Restore section {name} in {improved}/SKILL.md from {raw}/SKILL.md. The goal did not claim it."
        next_state = "Update"
    elif "changed and is not named as other" in detail or detail.endswith(" changed"):
        fix = f"Restore the unclaimed change in {improved} from {raw}. If the change was intended, name it as other on the goal."
        next_state = "Update"
    elif "no heading" in detail or "SKILL.md" in detail or "must both exist" in detail:
        fix = f"Write SKILL.md in both {raw} and {improved}, with the headings the goal claims."
        next_state = "Update"
    else:
        fix = f"Fix this on {improved}. Leave text the goal did not claim equal to {raw}."
        next_state = "Update"
    return block(skill, "goal align", detail, fix, next_state)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("goal", nargs="?", type=Path, default=DEFAULT_GOAL)
    parser.add_argument("--list", type=Path, default=skill_format_checker.DEFAULT_LIST)
    parser.add_argument("--op", type=int, help="1-based action.ops index for this loop")
    args = parser.parse_args()
    goal = slice_goal(json.loads(args.goal.read_text()), args.op)
    step = goal_step(json.loads(EXAMPLE.read_text()))
    label = f"{step.get('id')} {step.get('check')}"
    sections, section_aliases, dirs, others = skill_format_checker.load_list(args.list)
    with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
        json.dump(goal, handle)
        handle.flush()
        errors = skill_format_checker.check_goal(
            Path(handle.name), sections, dirs, others, section_aliases
        )
    stored = skill_format_checker.compare_stored(
        goal,
        sections,
        section_aliases,
        dirs,
        others,
        skill_format_checker.DEFAULT_RAW,
        skill_format_checker.DEFAULT_IMPROVED,
    )
    problems = errors + stored
    if problems:
        print(f"{label}: fail")
        for line in problems:
            print(explain(line))
            print()
        sys.exit(1)
    print(f"{label}: pass")


if __name__ == "__main__":
    main()
