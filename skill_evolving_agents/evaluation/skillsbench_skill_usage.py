#!/usr/bin/env python3
"""Audit whether a SkillsBench ``with-skill`` rollout actually used a skill."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


SKILL_PATH = re.compile(
    r"(?:/skills|/\.agents/skills|/\.claude/skills|/\.codex/skills)"
    r"/([a-z0-9][a-z0-9._-]*)/(scripts/[^\s\"':]+|references/[^\s\"':]+|assets/[^\s\"':]+)",
    re.IGNORECASE,
)
SKILL_FRONTMATTER = re.compile(
    r"(?m)^---\s*$.*?^name:\s*([a-z0-9][a-z0-9._-]*)\s*$.*?^description:\s*\S",
    re.IGNORECASE | re.DOTALL,
)
MOUNTED_SKILL = re.compile(
    r"<mounted-skill\s+path=(?:/skills|/\.agents/skills|/\.claude/skills|/\.codex/skills)"
    r"/([a-z0-9][a-z0-9._-]*)/SKILL\.md>",
    re.IGNORECASE,
)
REPORTED_SCRIPT = re.compile(
    r"(?:python(?:3)?|bash|sh|node)\s+([^\s`'\"]*?/skills/"
    r"([a-z0-9][a-z0-9._-]*)/scripts/[^\s`'\"]+)",
    re.IGNORECASE,
)
EXECUTION_SUCCESS = re.compile(
    r"exit\s+(?:status|code)\s*0|\bexit\s*0\b|"
    r"\"status\"\s*:\s*\"pass\"|exits?\s+zero|"
    r"preflight[^.\n]{0,48}\bpass|checker[^.\n]{0,48}\bpass",
    re.IGNORECASE,
)


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _events(path: Path) -> Iterable[dict[str, Any]]:
    """Yield events from either an ATIF JSON document or legacy JSONL."""
    text = path.read_text(errors="replace")
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        document = None
    if isinstance(document, dict) and isinstance(document.get("steps"), list):
        for event in document["steps"]:
            if isinstance(event, dict):
                yield event
        return
    if isinstance(document, list):
        for event in document:
            if isinstance(event, dict):
                yield event
        return
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def audit(path: Path) -> dict[str, Any]:
    skills: dict[str, set[str]] = {}
    discovered: dict[str, set[str]] = {}
    injected: set[str] = set()
    resource_attempts: dict[str, set[str]] = {}
    resource_successes: dict[str, set[str]] = {}
    resource_failures: dict[str, set[str]] = {}
    reported_attempts: dict[str, set[str]] = {}
    reported_successes: dict[str, set[str]] = {}
    matched_events = 0
    for event in _events(path):
        event_matches: set[tuple[str, str]] = set()
        resource_matches: set[tuple[str, str]] = set()
        event_text = "\n".join(_strings(event))
        mounted_names = set(MOUNTED_SKILL.findall(event_text))
        injected.update(mounted_names)
        for text in _strings(event):
            for match in SKILL_FRONTMATTER.finditer(text):
                skill_name = match.group(1)
                if skill_name in mounted_names or event.get("type") == "user_message":
                    injected.add(skill_name)
                else:
                    event_matches.add((skill_name, "SKILL.md"))
            for match in SKILL_PATH.finditer(text):
                resource_matches.add((match.group(1), match.group(2)))
        if event.get("type") == "agent_message":
            # Some ACP adapters retain only tool output, not the command input.
            # A final report that names a skill script is weaker than an observed
            # execution, but it is better than a false "never executed" claim.
            succeeded = bool(EXECUTION_SUCCESS.search(event_text))
            for match in REPORTED_SCRIPT.finditer(event_text):
                skill = match.group(2)
                resource = "scripts/" + match.group(1).split("/scripts/", 1)[1]
                reported_attempts.setdefault(skill, set()).add(resource)
                if succeeded:
                    reported_successes.setdefault(skill, set()).add(resource)
        title = str(event.get("title") or "").lower()
        kind = str(event.get("kind") or "").lower()
        listing_only = title in {"ls", "list", "find"} and kind == "read"
        for skill, resource in resource_matches:
            discovered.setdefault(skill, set()).add(resource)
            if not listing_only:
                event_matches.add((skill, resource))
                escaped_resource = re.escape(resource.rstrip("/"))
                explicit_execution = bool(
                    re.search(
                        rf"(?:python(?:3)?|bash|sh|node|ruby)\s+[^\n]*{escaped_resource}",
                        event_text,
                        re.IGNORECASE,
                    )
                    or re.search(
                        rf"(?:can't open file|cannot open|permission denied)[^\n]*{escaped_resource}",
                        event_text,
                        re.IGNORECASE,
                    )
                )
                if (
                    resource.startswith("scripts/")
                    and str(event.get("kind") or "").lower() == "execute"
                    and explicit_execution
                ):
                    resource_attempts.setdefault(skill, set()).add(resource)
                    lowered = event_text.casefold()
                    failed = any(
                        marker in lowered
                        for marker in (
                            "permission denied",
                            "not found",
                            "no such file",
                            "command failed",
                            "failed with exit code",
                        )
                    )
                    target = resource_failures if failed else resource_successes
                    target.setdefault(skill, set()).add(resource)
        if event_matches:
            matched_events += 1
        for skill, resource in event_matches:
            skills.setdefault(skill, set()).add(resource)

    all_skill_names = set(skills) | set(discovered) | injected
    skill_rows = [
        {
            "name": name,
            "skill_md_read": "SKILL.md" in resources,
            "skill_md_injected": name in injected,
            "resources_observed": sorted(
                resource for resource in resources if resource != "SKILL.md"
            ),
            "resources_discovered": sorted(discovered.get(name, set())),
            "script_execution": {
                "attempted": sorted(resource_attempts.get(name, set())),
                "succeeded": sorted(resource_successes.get(name, set())),
                "failed": sorted(resource_failures.get(name, set())),
                "reported": sorted(reported_attempts.get(name, set())),
                "reported_succeeded": sorted(
                    reported_successes.get(name, set())
                ),
            },
        }
        for name in sorted(all_skill_names)
        for resources in [skills.get(name, set())]
    ]
    read_observed = any(row["skill_md_read"] for row in skill_rows)
    injected_observed = any(row["skill_md_injected"] for row in skill_rows)
    activated = read_observed or injected_observed
    return {
        "schema_version": 1,
        "trajectory": str(path),
        "activated": activated,
        "activation_mode": (
            "read" if read_observed else "injected" if injected_observed else None
        ),
        "skill_md_read_observed": read_observed,
        "skill_md_injected": injected_observed,
        "matched_events": matched_events,
        "skills": skill_rows,
        "reason": (
            None
            if activated
            else "no SKILL.md read or full skill injection observed in trajectory"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trajectory", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-activation", action="store_true")
    args = parser.parse_args()
    report = audit(args.trajectory)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        print(text, end="")
    if args.require_activation and not report["activated"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
