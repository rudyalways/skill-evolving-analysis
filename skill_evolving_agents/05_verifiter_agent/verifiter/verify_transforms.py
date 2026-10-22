#!/usr/bin/env python3
"""Verify merge and split filesystem effects for one goal op."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from feedback import block
from goal_slice import slice_goal

ROOT = Path(__file__).resolve().parent
AGENT = ROOT.parents[1]
DEFAULT_GOAL = AGENT / "workspace" / "run" / "evolve-goal.json"
DEFAULT_RAW = AGENT / "workspace" / "target" / "raw_skills"
DEFAULT_IMPROVED = AGENT / "workspace" / "target" / "to_be_improved_skills"


def requested_dirs(record: dict) -> list[str]:
    found: list[str] = []
    for item in record.get("dirs") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name") if item.get("dir") == "other" else item.get("dir")
        if isinstance(name, str) and name:
            found.append(name)
    return found


def check_dir(skill: str, record: dict, improved: Path, problems: list[str]) -> None:
    for name in requested_dirs(record):
        if not (improved / skill / name).is_dir():
            problems.append(
                block(
                    skill,
                    "transform dirs",
                    f"requested directory is missing: {name}",
                    f"Create {name} under the transformed skill and preserve its requested content.",
                    "Edit",
                )
            )


def check(goal: dict, raw: Path, improved: Path) -> list[str]:
    problems: list[str] = []
    ops = (goal.get("action") or {}).get("ops") or []
    for op in ops:
        if not isinstance(op, dict):
            continue
        if op.get("op") == "merge":
            sources = [value for value in op.get("skills") or [] if isinstance(value, str)]
            into = op.get("into") or {}
            target = into.get("skill") if isinstance(into, dict) else None
            for source in sources:
                if not (raw / source).is_dir():
                    problems.append(
                        block(
                            source,
                            "merge snapshot",
                            "raw source snapshot is missing",
                            "Copy every merge source to raw_skills before editing.",
                            "Merge",
                        )
                    )
                if source != target and (improved / source).exists():
                    problems.append(
                        block(
                            source,
                            "merge source removal",
                            "source skill remains after merge",
                            "Remove the merged source after the target is complete.",
                            "Merge",
                        )
                    )
            if not isinstance(target, str) or not (improved / target).is_dir():
                problems.append(
                    block(
                        str(target or ""),
                        "merge target",
                        "merged target skill is missing",
                        "Create the merge target named by into.skill.",
                        "Merge",
                    )
                )
            elif isinstance(into, dict):
                check_dir(target, into, improved, problems)
        elif op.get("op") == "split":
            source = op.get("skill")
            parts = [item for item in op.get("into") or [] if isinstance(item, dict)]
            names = [
                item.get("skill")
                for item in parts
                if isinstance(item.get("skill"), str)
            ]
            if isinstance(source, str) and not (raw / source).is_dir():
                problems.append(
                    block(
                        source,
                        "split snapshot",
                        "raw source snapshot is missing",
                        "Copy the split source to raw_skills before editing.",
                        "Split",
                    )
                )
            if isinstance(source, str) and source not in names and (improved / source).exists():
                problems.append(
                    block(
                        source,
                        "split source removal",
                        "source skill remains after split",
                        "Remove the source after all split targets are complete.",
                        "Split",
                    )
                )
            for part in parts:
                name = part.get("skill")
                if not isinstance(name, str) or not (improved / name).is_dir():
                    problems.append(
                        block(
                            str(name or ""),
                            "split target",
                            "split target skill is missing",
                            "Create every skill named in split.into.",
                            "Split",
                        )
                    )
                else:
                    check_dir(name, part, improved, problems)
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("goal", nargs="?", type=Path, default=DEFAULT_GOAL)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--improved", type=Path, default=DEFAULT_IMPROVED)
    parser.add_argument("--op", type=int, help="1-based action.ops index")
    args = parser.parse_args()
    goal = slice_goal(json.loads(args.goal.read_text()), args.op)
    problems = check(goal, args.raw, args.improved)
    if problems:
        print("transforms: fail")
        print("\n\n".join(problems))
        sys.exit(1)
    print("transforms: pass")


if __name__ == "__main__":
    main()
