"""Validate the directory contract for a golden skill bundle."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .golden import GoldenSkill, GoldenSkillError


REQUIRED_FILES = ("SKILL.md", "skill.json", "README.md")
REQUIRED_EVAL_FILES = ("evals/tasks.json",)
OPTIONAL_DIRS = ("scripts", "references", "assets", "environment", "simulator", "stage-goldens")


@dataclass
class BundleReport:
    path: Path
    skill_id: str
    failures: list[str]
    warnings: list[str]
    gold_ready: bool

    @property
    def valid(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "skill_id": self.skill_id,
            "valid": self.valid,
            "gold_ready": self.gold_ready,
            "failures": self.failures,
            "warnings": self.warnings,
        }


def validate_bundle(root: Path | str, *, require_gold: bool = False) -> BundleReport:
    root = Path(root)
    failures: list[str] = []
    warnings: list[str] = []
    skill_id = root.name
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            failures.append(f"missing {relative}")
    for relative in REQUIRED_EVAL_FILES:
        if not (root / relative).is_file():
            failures.append(f"missing {relative}")
    for relative in OPTIONAL_DIRS:
        path = root / relative
        if path.exists() and not path.is_dir():
            failures.append(f"{relative} must be a directory")
    try:
        skill = GoldenSkill.load(root)
        skill_id = skill.skill_id
        source = skill.source
        review = skill.review
    except GoldenSkillError as error:
        failures.append(str(error))
        source = {}
        review = {}
    tasks_path = root / "evals/tasks.json"
    if tasks_path.is_file():
        try:
            tasks = json.loads(tasks_path.read_text())
        except json.JSONDecodeError as error:
            failures.append(f"invalid evals/tasks.json: {error}")
            tasks = None
        if not isinstance(tasks, list) or not tasks:
            failures.append("evals/tasks.json must be a non-empty list")
        elif len(tasks) < 5:
            warnings.append("fewer than 5 task cards")
    else:
        tasks = None
    origin = str(source.get("origin") or "")
    if not origin:
        failures.append("source.origin is required")
    if not source.get("authority_sources"):
        failures.append("source.authority_sources is required")
    if origin == "synthetic":
        warnings.append("synthetic origin cannot be gold without a reviewed authority basis")
    reviewers = [
        row for row in review.get("reviewers") or []
        if isinstance(row, dict)
    ]
    roles = {str(row.get("role") or "") for row in reviewers}
    required_roles = {
        str(value) for value in review.get("required_roles") or []
    }
    if review.get("status") != "approved":
        warnings.append("review.status is not approved")
    if len(reviewers) < 2:
        warnings.append("fewer than two reviewers")
    if required_roles and not required_roles <= roles:
        warnings.append("required reviewer roles are not covered")
    if not review.get("notes"):
        warnings.append("review.notes is empty")
    gold_ready = (
        not failures
        and origin != "synthetic"
        and review.get("status") == "approved"
        and len(reviewers) >= 2
        and (not required_roles or required_roles <= roles)
        and tasks is not None
        and len(tasks) >= 5
    )
    if require_gold and not gold_ready:
        failures.append("bundle is not gold-ready")
    return BundleReport(
        path=root,
        skill_id=skill_id,
        failures=failures,
        warnings=warnings,
        gold_ready=gold_ready,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--require-gold", action="store_true")
    args = parser.parse_args()
    report = validate_bundle(args.bundle, require_gold=args.require_gold)
    print(json.dumps(report.to_dict(), indent=2))
    raise SystemExit(0 if report.valid else 1)


if __name__ == "__main__":
    main()
