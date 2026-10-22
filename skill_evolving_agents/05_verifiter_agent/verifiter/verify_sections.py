#!/usr/bin/env python3
"""Verify create and update skills against the sections the goal claims.

Create: the skill exists under target/to_be_improved_skills, SKILL.md has
each claimed section, and each claimed directory is present. Update: only
the claimed sections and directories differ from target/raw_skills.
A heading or directory named under other is checked by that name.
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
DEFAULT_LIST = (
    AGENT / "common" / "skill_format.json"
)
TARGET = AGENT / "workspace" / "target"
DEFAULT_RAW = TARGET / "raw_skills"
DEFAULT_IMPROVED = TARGET / "to_be_improved_skills"
_CHECKER = (
    AGENT / "common" / "skill_format_checker.py"
)
_spec = importlib.util.spec_from_file_location("skill_format_checker", _CHECKER)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


def rows(goal: dict, op_name: str) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for op in (goal.get("action") or {}).get("ops") or []:
        if not isinstance(op, dict) or op.get("op") != op_name:
            continue
        for item in op.get("skills") or []:
            if not isinstance(item, dict):
                continue
            name = checker.skill_name(item.get("skill"))
            if not name:
                continue
            found.append(
                {
                    "skill": name,
                    "sections": checker.section_records(item.get("sections") or item.get("section")),
                    "dirs": checker.dir_records(item.get("dirs")),
                }
            )
    return found


def section_present(
    skill: str,
    text: str,
    records: list[dict[str, str]],
    sections: dict[str, list[str]],
    section_aliases: dict[str, str],
    others: set[str],
    next_state: str,
) -> list[str]:
    problems: list[str] = []
    index = checker.heading_index(sections)
    _, _, known, unknown = checker.split_skill(text, index)
    unknown_headings = {heading for heading, _ in unknown}
    path = f"target/to_be_improved_skills/{skill}/SKILL.md"
    for record in records:
        requested = record["section"]
        name = section_aliases.get(checker.norm(requested), requested)
        if checker.norm(name) in others:
            heading = record["heading"]
            if not checker.norm(heading):
                problems.append(
                    block(
                        skill,
                        "sections",
                        "other section needs a heading",
                        "On the goal, set heading to the text the skill uses.",
                        "Goal",
                    )
                )
            elif checker.norm(heading) not in unknown_headings:
                problems.append(
                    block(
                        skill,
                        "sections",
                        f"heading {heading} is missing",
                        f"Add ## {heading} to {path}.",
                        next_state,
                    )
                )
            continue
        if name not in sections:
            problems.append(
                block(
                    skill,
                    "sections",
                    f"section {name} is not in skill_format.json",
                    "On the goal, use a section from skill_format.json, or set section to other and set heading.",
                    "Goal",
                )
            )
        elif name not in known:
            headings = " or ".join(sections[name]) or name
            problems.append(
                block(
                    skill,
                    "sections",
                    f"section {name} is missing",
                    f"Add a heading for {name} to {path}. Use {headings}.",
                    next_state,
                )
            )
    return problems


def section_changed(
    skill: str,
    before: str,
    after: str,
    records: list[dict[str, str]],
    sections: dict[str, list[str]],
    section_aliases: dict[str, str],
    others: set[str],
) -> list[str]:
    index = checker.heading_index(sections)
    _, _, before_known, before_unknown = checker.split_skill(before, index)
    _, _, after_known, after_unknown = checker.split_skill(after, index)
    before_free = {heading: chunk for heading, chunk in before_unknown}
    after_free = {heading: chunk for heading, chunk in after_unknown}
    problems: list[str] = []
    for record in records:
        requested = record["section"]
        name = section_aliases.get(checker.norm(requested), requested)
        if checker.norm(name) in others:
            shown = record["heading"]
            heading = checker.norm(shown)
            if heading and before_free.get(heading) == after_free.get(heading):
                problems.append(
                    block(
                        skill,
                        "sections",
                        f"heading {shown} did not change",
                        f"Edit ## {shown} in target/to_be_improved_skills/{skill}/SKILL.md so it differs from target/raw_skills/{skill}/SKILL.md.",
                        "Update",
                    )
                )
            continue
        if name in sections and before_known.get(name) == after_known.get(name):
            problems.append(
                block(
                    skill,
                    "sections",
                    f"section {name} did not change",
                    f"Edit section {name} in target/to_be_improved_skills/{skill}/SKILL.md so it differs from target/raw_skills/{skill}/SKILL.md.",
                    "Update",
                )
            )
    return problems


def dir_present(
    skill: str,
    root: Path,
    records: list[dict[str, str]],
    dirs: dict[str, str],
    others: set[str],
    next_state: str,
) -> list[str]:
    problems: list[str] = []
    for record in records:
        if checker.norm(record["dir"]) in others:
            folder = record["name"]
            if not folder:
                problems.append(
                    block(
                        skill,
                        "sections",
                        "other dir needs a name",
                        "On the goal, set name to the directory the skill uses.",
                        "Goal",
                    )
                )
            elif not (root / folder).is_dir():
                problems.append(
                    block(
                        skill,
                        "sections",
                        f"dir {folder} is missing",
                        f"Create target/to_be_improved_skills/{skill}/{folder}/.",
                        next_state,
                    )
                )
            continue
        canonical = dirs.get(checker.norm(record["dir"]))
        if canonical is None or canonical == "other":
            problems.append(
                block(
                    skill,
                    "sections",
                    f"dir {record['dir']} is not in skill_format.json",
                    "On the goal, use a dir from skill_format.json, or set dir to other and set name.",
                    "Goal",
                )
            )
        elif not (root / canonical).is_dir() and not (root / record["dir"]).is_dir():
            problems.append(
                block(
                    skill,
                    "sections",
                    f"dir {canonical} is missing",
                    f"Create target/to_be_improved_skills/{skill}/{canonical}/.",
                    next_state,
                )
            )
    return problems


def diff_line(skill: str, detail: str) -> str:
    raw = f"target/raw_skills/{skill}"
    improved = f"target/to_be_improved_skills/{skill}"
    if detail.startswith("section ") and detail.endswith(" changed"):
        name = detail.removeprefix("section ").removesuffix(" changed")
        fix = f"Restore section {name} in {improved}/SKILL.md from {raw}/SKILL.md. The goal did not claim it."
    elif detail.startswith("heading ") and "changed and is not named as other" in detail:
        fix = f"Restore that heading in {improved}/SKILL.md from {raw}/SKILL.md. If the change was intended, go back to Goal and name the heading as other."
    elif detail == "frontmatter changed":
        fix = f"Restore the frontmatter in {improved}/SKILL.md from {raw}/SKILL.md."
    elif detail.startswith("text before"):
        fix = f"Restore the text before the first heading in {improved}/SKILL.md from {raw}/SKILL.md."
    elif detail.startswith("dir ") and "is not in skill_format.json" in detail:
        return block(
            skill,
            "sections",
            detail,
            "On the goal, use a dir from skill_format.json, or set dir to other and set name.",
            "Goal",
        )
    elif detail.startswith("dir ") and "changed" in detail:
        fix = f"Restore that directory under {improved} from {raw}. The goal did not claim it."
    elif detail.startswith("file ") and detail.endswith(" changed"):
        fix = f"Restore that file under {improved} from {raw}."
    elif "no heading" in detail:
        fix = f"Add the headings the goal claims to {improved}/SKILL.md."
    elif "is not in skill_format.json" in detail:
        return block(
            skill,
            "sections",
            detail,
            "On the goal, use a name from skill_format.json, or set it to other and give heading or name.",
            "Goal",
        )
    else:
        fix = f"Fix this in {improved} without changing text the goal did not claim. The copy before the edit is {raw}."
    return block(skill, "sections", detail, fix, "Update")


def check_create(
    row: dict[str, object],
    improved_root: Path,
    sections: dict[str, list[str]],
    section_aliases: dict[str, str],
    dirs: dict[str, str],
    others: set[str],
) -> list[str]:
    name = str(row["skill"])
    root = improved_root / name
    if not root.is_dir():
        return [
            block(
                name,
                "sections",
                "created skill is missing",
                f"Create target/to_be_improved_skills/{name}/SKILL.md and the directories the create op claims.",
                "Generate",
            )
        ]
    records = row["sections"]
    problems: list[str] = []
    if not isinstance(records, list) or not records:
        problems.append(
            block(
                name,
                "sections",
                "create names no sections",
                "On the create op, name the sections this skill should contain.",
                "Goal",
            )
        )
    else:
        path = checker.skill_file(root)
        if path is None:
            problems.append(
                block(
                    name,
                    "sections",
                    "SKILL.md is missing",
                    f"Write target/to_be_improved_skills/{name}/SKILL.md with the sections the create op claims.",
                    "Generate",
                )
            )
        else:
            problems.extend(
                section_present(
                    name,
                    path.read_text(),
                    records,
                    sections,
                    section_aliases,
                    others,
                    "Generate",
                )
            )
    claimed_dirs = row["dirs"]
    if isinstance(claimed_dirs, list) and claimed_dirs:
        problems.extend(dir_present(name, root, claimed_dirs, dirs, others, "Generate"))
    return problems


def check_update(
    row: dict[str, object],
    raw_root: Path,
    improved_root: Path,
    sections: dict[str, list[str]],
    section_aliases: dict[str, str],
    dirs: dict[str, str],
    others: set[str],
) -> list[str]:
    name = str(row["skill"])
    raw = raw_root / name
    improved = improved_root / name
    if not raw.is_dir() or not improved.is_dir():
        return [
            block(
                name,
                "sections",
                "raw and improved copies must both exist",
                f"Copy the skill to target/raw_skills/{name} before editing, and write the edited copy at target/to_be_improved_skills/{name}.",
                "Update",
            )
        ]
    records = row["sections"]
    claimed_dirs = row["dirs"]
    if not records and not claimed_dirs:
        return [
            block(
                name,
                "sections",
                "update names no sections or dirs",
                "On the update op, name the sections or directories this change touches.",
                "Goal",
            )
        ]
    problems: list[str] = []
    if isinstance(records, list) and records:
        before = checker.skill_file(raw)
        after = checker.skill_file(improved)
        if before is None or after is None:
            problems.append(
                block(
                    name,
                    "sections",
                    "SKILL.md missing from raw or improved",
                    f"Write SKILL.md in both target/raw_skills/{name} and target/to_be_improved_skills/{name}.",
                    "Update",
                )
            )
        else:
            kind, details = checker.check_diff(
                before.read_text(),
                after.read_text(),
                records,
                sections,
                others,
                section_aliases,
            )
            if kind != "ok":
                problems.extend(diff_line(name, line) for line in details)
            after_text = after.read_text()
            missing = section_present(
                name,
                after_text,
                records,
                sections,
                section_aliases,
                others,
                "Update",
            )
            problems.extend(missing)
            if not missing:
                problems.extend(
                    section_changed(
                        name,
                        before.read_text(),
                        after_text,
                        records,
                        sections,
                        section_aliases,
                        others,
                    )
                )
    if isinstance(claimed_dirs, list) and claimed_dirs:
        kind, details = checker.check_dir_diff(raw, improved, claimed_dirs, dirs, others)
        if kind != "ok":
            problems.extend(diff_line(name, line) for line in details)
        problems.extend(dir_present(name, improved, claimed_dirs, dirs, others, "Update"))
    return problems


def check(
    goal: dict,
    raw_root: Path,
    improved_root: Path,
    list_path: Path,
) -> list[str]:
    sections, section_aliases, dirs, others = checker.load_list(list_path)
    problems: list[str] = []
    for row in rows(goal, "create"):
        problems.extend(
            check_create(
                row,
                improved_root,
                sections,
                section_aliases,
                dirs,
                others,
            )
        )
    for row in rows(goal, "update"):
        problems.extend(
            check_update(
                row,
                raw_root,
                improved_root,
                sections,
                section_aliases,
                dirs,
                others,
            )
        )
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("goal", nargs="?", type=Path, default=DEFAULT_GOAL)
    parser.add_argument("--list", type=Path, default=DEFAULT_LIST)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--improved", type=Path, default=DEFAULT_IMPROVED)
    parser.add_argument("--op", type=int, help="1-based action.ops index for this loop")
    args = parser.parse_args()
    goal = slice_goal(json.loads(args.goal.read_text()), args.op)
    created = rows(goal, "create")
    updated = rows(goal, "update")
    if not created and not updated:
        print("sections: no create or update skills")
        return
    problems = check(goal, args.raw, args.improved, args.list)
    if problems:
        print("sections: fail")
        for line in problems:
            print(line)
            print()
        sys.exit(1)
    names = [str(row["skill"]) for row in created + updated]
    print(f"sections: pass {', '.join(names)}")


if __name__ == "__main__":
    main()
