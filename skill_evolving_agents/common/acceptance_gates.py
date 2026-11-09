"""Acceptance gates that structural verification alone must not satisfy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RESOURCE_DIRECTORIES = frozenset({"scripts", "references", "assets", "agents", "evals"})
REPLAY_FIXTURE_NAMES = (
    "evaluation/held_out/{skill}.json",
    "evaluation/held-out/{skill}.json",
    "evaluation/fixtures/{skill}.json",
    "run/replay/manifest.json",
    "run/replay/held-out-evals.json",
)


def _directory_name(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value.strip("/")
    if isinstance(value, dict):
        candidate = value.get("dir") or value.get("directory") or value.get("path")
        if isinstance(candidate, str) and candidate:
            return candidate.strip("/")
    return None


def resource_change_directories(
    op: dict[str, Any] | None = None,
    operation_directory: Path | None = None,
) -> list[str]:
    """Return canonical resource directories touched by an operation.

    The changelog is authoritative after optimization because it records what
    was actually materialized.  The goal's resource plan is a fallback for
    resumed or partially archived operations.
    """
    directories: set[str] = set()
    if operation_directory is not None:
        changelog_path = operation_directory / "changelog.json"
        if changelog_path.is_file():
            try:
                changelog = json.loads(changelog_path.read_text())
            except json.JSONDecodeError:
                changelog = {}
            for change in changelog.get("changes") or []:
                if not isinstance(change, dict):
                    continue
                for value in change.get("directories") or []:
                    name = _directory_name(value)
                    if name:
                        directories.add(name.split("/", 1)[0])
    for skill in (op or {}).get("skills") or []:
        if not isinstance(skill, dict):
            continue
        for row in skill.get("resource_plan") or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("decision") or "") != "use":
                continue
            name = _directory_name(row.get("resource") or row.get("path"))
            if name:
                directories.add(name.split("/", 1)[0])
    return sorted(directories & RESOURCE_DIRECTORIES)


def replay_fixtures(workspace: Path, skill: str) -> list[Path]:
    """Return replay fixtures that make structural-only acceptance unsafe."""
    found: list[Path] = []
    for template in REPLAY_FIXTURE_NAMES:
        path = workspace / template.format(skill=skill)
        if path.is_file():
            found.append(path)
    return found


def replay_acceptance(
    workspace: Path,
    *,
    operation_directory: Path,
    op: dict[str, Any] | None,
    verification: dict[str, Any] | None = None,
    affected: set[str] | None = None,
) -> dict[str, Any]:
    """Decide whether a resource-changing operation may be accepted.

    * a passing available replay is required;
    * an available replay that failed blocks acceptance;
    * a replay fixture without an executed replay blocks acceptance instead of
      silently degrading to structural evidence;
    * with no fixture and no replay, acceptance stays provisional.
    """
    directories = resource_change_directories(op, operation_directory)
    if not directories:
        return {
            "schema_version": 1,
            "required": False,
            "decision": "not-required",
            "reason": "no-resource-change",
            "resource_directories": [],
            "fixtures": [],
            "replay": None,
        }
    skills = {
        str(skill.get("skill"))
        for skill in (op or {}).get("skills") or []
        if isinstance(skill, dict) and skill.get("skill")
    }
    skills.update(str(name) for name in (affected or set()) if name)
    skills = sorted(skills)
    fixtures = [
        path
        for skill in skills
        for path in replay_fixtures(workspace, skill)
    ]
    replay = ((verification or {}).get("feedback") or {}).get("replay") or {}
    if not isinstance(replay, dict):
        replay = {}
    available = replay.get("available") is True
    passed = available and replay.get("status") == "pass"
    if available and passed:
        decision, reason = "accept", "replay-passed"
    elif available:
        decision, reason = "reject", "replay-failed"
    elif fixtures:
        decision, reason = "reject", "replay-required-fixture-available"
    else:
        decision, reason = "accept-provisional", "no-replay-fixture"
    return {
        "schema_version": 1,
        "required": True,
        "decision": decision,
        "reason": reason,
        "resource_directories": directories,
        "skills": skills,
        "fixtures": [str(path.relative_to(workspace)) for path in fixtures],
        "replay": {
            "available": available,
            "status": replay.get("status"),
            "kind": replay.get("kind"),
        },
    }
