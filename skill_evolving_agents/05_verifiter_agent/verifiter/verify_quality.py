#!/usr/bin/env python3
"""Deterministically reject low-value or redundant methodology skill edits."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


TOKEN = re.compile(r"[A-Za-z0-9_]+")
GENERIC = {
    "analyze the task",
    "read relevant files",
    "make the changes",
    "run tests",
    "fix errors",
    "verify the result",
}


def words(value: Any) -> set[str]:
    if isinstance(value, str):
        return {token.casefold() for token in TOKEN.findall(value)}
    if isinstance(value, dict):
        result: set[str] = set()
        for item in value.values():
            result.update(words(item))
        return result
    if isinstance(value, list):
        result = set()
        for item in value:
            result.update(words(item))
        return result
    return set()


def similarity(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def skill_names(op: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for item in op.get("skills") or []:
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, dict) and isinstance(item.get("skill"), str):
            found.append(item["skill"])
    for key in ("skill", "into"):
        value = op.get(key)
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, list):
            found.extend(item for item in value if isinstance(item, str))
    return sorted(set(found))


def check(
    goal: dict[str, Any],
    finding: dict[str, Any],
    skills_root: Path,
    raw_root: Path,
    config: dict[str, Any],
) -> list[str]:
    features = finding.get("features") or {}
    if features.get("candidate_source") not in {
        "methodology",
        "methodology_consolidated",
    }:
        return []
    policy = config.get("evolution_policy") or {}
    quality = features.get("quality") or {}
    value = float(quality.get("value") or 0)
    problems: list[str] = []
    minimum = float(policy.get("min_methodology_value", 0.08))
    if value < minimum:
        problems.append(
            f"methodology value {value:.3f} is below {minimum:.3f}"
        )
    lesson_words = words(features.get("lesson") or {})
    maximum_similarity = float(policy.get("novelty_max_similarity", 0.82))
    ops = (goal.get("action") or {}).get("ops") or []
    for op in ops:
        if not isinstance(op, dict):
            continue
        for name in skill_names(op):
            path = skills_root / name / "SKILL.md"
            if not path.is_file():
                problems.append(f"{name}: edited SKILL.md is missing")
                continue
            text = path.read_text(errors="replace")
            folded = " ".join(text.casefold().split())
            generic_count = sum(phrase in folded for phrase in GENERIC)
            if generic_count >= 4 and len(words(text)) < 120:
                problems.append(
                    f"{name}: methodology is mostly a generic inspect/edit/test checklist"
                )
            if lesson_words and similarity(lesson_words, words(text)) < 0.05:
                problems.append(
                    f"{name}: edit does not preserve the evidence-backed methodology lesson"
                )
            for other in skills_root.glob("*/SKILL.md"):
                if other.parent.name == name:
                    continue
                score = similarity(words(text), words(other.read_text(errors="replace")))
                if score > maximum_similarity:
                    problems.append(
                        f"{name}: duplicates {other.parent.name} at similarity {score:.3f}"
                    )
                    break
            raw = raw_root / name / "SKILL.md"
            if op.get("op") == "update" and raw.is_file():
                if words(raw.read_text(errors="replace")) == words(text):
                    problems.append(f"{name}: update adds no lexical information")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("goal", type=Path)
    parser.add_argument("--finding", required=True, type=Path)
    parser.add_argument("--skills", required=True, type=Path)
    parser.add_argument("--raw-skills", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    problems = check(
        json.loads(args.goal.read_text()),
        json.loads(args.finding.read_text()),
        args.skills,
        args.raw_skills,
        json.loads(args.config.read_text()),
    )
    if problems:
        for problem in problems:
            print(f"quality: {problem}")
        raise SystemExit(1)
    print("quality: pass")


if __name__ == "__main__":
    main()
