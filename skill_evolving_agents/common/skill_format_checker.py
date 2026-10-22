#!/usr/bin/env python3
"""Check goal sections and dirs against skill_format.json.

skill_format.json is the list. A section name is one of its name fields or aliases.
A directory name is one of its dir names or aliases. Angle brackets
around a fill-in value are ignored.

Create, update, merge, split, and `<other>` each name dirs. A dir is
an object with `dir` and `goal`, or a plain name. An update names a
list of sections. Each item is `section` and `goal`. `other` and
`ood` name a heading or directory that is not on the closed list:
a section also needs `heading`, and a dir also needs `name`.

With --before and --after, the checker compares two SKILL.md texts.
Frontmatter and every section that was not named must stay put. A
heading named under `other` may change. A heading outside the list
that was not named fails only when its text changes.

With --before-dir and --after-dir, the checker compares two skill
directories. Only the dirs named on the goal may change, including a
directory named under `other`. Pass --dir to check one of them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENT = ROOT.parent
DEFAULT_LIST = ROOT / "skill_format.json"
DEFAULT_GOAL = AGENT / "workspace" / "run" / "evolve-goal.json"
TARGET = AGENT / "workspace" / "target"
DEFAULT_RAW = TARGET / "raw_skills"
DEFAULT_IMPROVED = TARGET / "to_be_improved_skills"

FRONT = re.compile(r"^---\s*\n.*?\n---\s*\n?", re.S)
H2 = re.compile(r"^##[ \t]+(.+?)\s*#*\s*$", re.M)


def bare(value: str) -> str:
    if value.startswith("<") and value.endswith(">") and len(value) > 2:
        return value[1:-1]
    return value


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def load_list(
    path: Path,
) -> tuple[dict[str, list[str]], dict[str, str], dict[str, str], set[str]]:
    data = json.loads(path.read_text())
    sections: dict[str, list[str]] = {}
    section_aliases: dict[str, str] = {}
    others: set[str] = set()
    for item in data.get("sections") or []:
        name = item.get("name")
        headings = item.get("headings") or []
        if not isinstance(name, str) or not name:
            continue
        sections[name] = [h for h in headings if isinstance(h, str)]
        aliases = [name]
        aliases.extend(a for a in (item.get("aliases") or []) if isinstance(a, str))
        for alias in aliases:
            section_aliases[norm(alias)] = name
        if name == "other":
            others.update(norm(a) for a in aliases)
    dirs: dict[str, str] = {}
    for item in data.get("dirs") or []:
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        dirs[norm(name)] = name
        aliases = [name]
        aliases.extend(a for a in (item.get("aliases") or []) if isinstance(a, str))
        for alias in aliases:
            dirs[norm(alias)] = name
        if name == "other":
            others.update(norm(a) for a in aliases)
    return sections, section_aliases, dirs, others


def heading_index(sections: dict[str, list[str]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for name, headings in sections.items():
        for heading in headings:
            index[norm(heading)] = name
    return index


def section_records(value: object) -> list[dict[str, str]]:
    if isinstance(value, list):
        found: list[dict[str, str]] = []
        for item in value:
            found.extend(section_records(item))
        return found
    if isinstance(value, str) and value.strip():
        return [{"section": bare(value), "heading": ""}]
    if isinstance(value, dict):
        section = value.get("section")
        heading = value.get("heading")
        if not isinstance(section, str) or not section.strip():
            return []
        return [
            {
                "section": bare(section),
                "heading": bare(heading) if isinstance(heading, str) else "",
            }
        ]
    return []


def dir_records(value: object) -> list[dict[str, str]]:
    if isinstance(value, list):
        found: list[dict[str, str]] = []
        for item in value:
            found.extend(dir_records(item))
        return found
    if isinstance(value, str) and value.strip():
        return [{"dir": bare(value), "name": ""}]
    if isinstance(value, dict):
        directory = value.get("dir")
        custom = value.get("name")
        if not isinstance(directory, str) or not directory.strip():
            return []
        return [
            {
                "dir": bare(directory),
                "name": bare(custom) if isinstance(custom, str) else "",
            }
        ]
    return []


def names_in(value: object) -> list[str]:
    if isinstance(value, dict):
        return names_in(value.get("dir"))
    if isinstance(value, list):
        found: list[str] = []
        for item in value:
            found.extend(names_in(item))
        return found
    if not isinstance(value, str) or not value.strip():
        return []
    return [part for part in bare(value).split("|") if part]


def skill_name(value: object) -> str | None:
    if isinstance(value, dict):
        return skill_name(value.get("skill"))
    if not isinstance(value, str) or not value.strip():
        return None
    name = bare(value).strip()
    return name or None


def skill_file(directory: Path) -> Path | None:
    for name in ("SKILL.md", "skill.md"):
        path = directory / name
        if path.is_file():
            return path
    return None


def updates(goal: dict) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for op in (goal.get("action") or {}).get("ops") or []:
        if not isinstance(op, dict) or op.get("op") != "update":
            continue
        for item in op.get("skills") or []:
            if not isinstance(item, dict):
                continue
            name = skill_name(item.get("skill"))
            if not name:
                continue
            rows.append(
                {
                    "skill": name,
                    "sections": section_records(item.get("sections") or item.get("section")),
                    "dirs": dir_records(item.get("dirs")),
                }
            )
    return rows


def compare_stored(
    goal: dict,
    sections: dict[str, list[str]],
    section_aliases: dict[str, str],
    dirs: dict[str, str],
    others: set[str],
    raw_root: Path,
    improved_root: Path,
) -> list[str]:
    """Compare raw_skills/<skill> with to_be_improved_skills/<skill>."""
    problems: list[str] = []
    for row in updates(goal):
        name = str(row["skill"])
        raw = raw_root / name
        improved = improved_root / name
        if not raw.exists() and not improved.exists():
            continue
        if not raw.is_dir() or not improved.is_dir():
            problems.append(f"{name}: raw and improved copies must both exist")
            continue
        records = row["sections"]
        if isinstance(records, list) and records:
            before_md = skill_file(raw)
            after_md = skill_file(improved)
            if before_md is None or after_md is None:
                problems.append(f"{name}: SKILL.md missing from raw or improved")
            else:
                kind, details = check_diff(
                    before_md.read_text(),
                    after_md.read_text(),
                    records,
                    sections,
                    others,
                    section_aliases,
                )
                if kind == "changed":
                    problems.extend(f"{name}: {line}" for line in details)
                else:
                    print(f"{name}: {details[0]}")
        allowed = row["dirs"]
        if isinstance(allowed, list) and allowed:
            kind, details = check_dir_diff(raw, improved, allowed, dirs, others)
            if kind == "changed":
                problems.extend(f"{name}: {line}" for line in details)
            else:
                print(f"{name}: {details[0]}")
    return problems


def goal_dirs(goal: dict) -> list[dict[str, str]]:
    found: list[str] = []
    for op in (goal.get("action") or {}).get("ops") or []:
        if not isinstance(op, dict):
            continue
        found.extend(dir_records(op.get("dirs")))
        into = op.get("into")
        if isinstance(into, dict):
            found.extend(dir_records(into.get("dirs")))
        elif isinstance(into, list):
            for part in into:
                if isinstance(part, dict):
                    found.extend(dir_records(part.get("dirs")))
        for item in op.get("skills") or []:
            if isinstance(item, dict):
                found.extend(dir_records(item.get("dirs")))
    return found


def check_sections(
    value: object,
    sections: dict[str, list[str]],
    others: set[str],
    section_aliases: dict[str, str] | None = None,
) -> list[str]:
    aliases = section_aliases or {norm(name): name for name in sections}
    bad = []
    for record in section_records(value):
        name = record["section"]
        if not name:
            continue
        if norm(name) in others:
            if not record["heading"]:
                bad.append("other section needs a heading")
            continue
        if norm(name) not in aliases:
            bad.append(f"section {name} is not in skill_format.json")
    return bad


def check_goal(
    goal_path: Path,
    sections: dict[str, list[str]],
    dirs: dict[str, str],
    others: set[str],
    section_aliases: dict[str, str] | None = None,
) -> list[str]:
    goal = json.loads(goal_path.read_text())
    ops = ((goal.get("action") or {}).get("ops")) or []
    if not isinstance(ops, list):
        raise SystemExit("action.ops must be a list")
    errors: list[str] = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        if kind == "update":
            for item in op.get("skills") or []:
                if not isinstance(item, dict):
                    continue
                errors.extend(
                    check_sections(
                        item.get("sections") or item.get("section"),
                        sections,
                        others,
                        section_aliases,
                    )
                )
                errors.extend(check_dirs(item.get("dirs"), dirs, others))
        elif kind == "create":
            for item in op.get("skills") or []:
                if not isinstance(item, dict):
                    continue
                errors.extend(
                    check_sections(
                        item.get("sections"),
                        sections,
                        others,
                        section_aliases,
                    )
                )
                errors.extend(check_dirs(item.get("dirs"), dirs, others))
        elif kind == "merge":
            into = op.get("into")
            if isinstance(into, dict):
                errors.extend(check_dirs(into.get("dirs"), dirs, others))
        elif kind == "split":
            into = op.get("into")
            if isinstance(into, list):
                for part in into:
                    if isinstance(part, dict):
                        errors.extend(check_dirs(part.get("dirs"), dirs, others))
        elif isinstance(kind, str) and kind not in {"delete"}:
            errors.extend(check_dirs(op.get("dirs"), dirs, others))
    return errors


def check_dirs(value: object, dirs: dict[str, str], others: set[str]) -> list[str]:
    bad = []
    for record in dir_records(value):
        name = record["dir"]
        if not name:
            continue
        if norm(name) in others:
            if not record["name"]:
                bad.append("other dir needs a name")
            continue
        if norm(name) not in dirs:
            bad.append(f"dir {name} is not in skill_format.json")
    return bad


def one_name(
    kind: str,
    value: object,
    known: dict,
    canonical: dict[str, str] | None = None,
) -> list[str]:
    if value is None:
        return []
    found = names_in(value)
    if not found:
        return []
    bad = []
    for name in found:
        key = name if canonical is None else norm(name)
        table = known if canonical is None else canonical
        if key not in table:
            bad.append(f"{kind} {name} is not in skill_format.json")
    return bad


def split_skill(text: str, index: dict[str, str]) -> tuple[str, str, dict[str, str], list[tuple[str, str]]]:
    front = ""
    match = FRONT.match(text)
    body = text
    if match:
        front = match.group(0)
        body = text[match.end() :]
    marks = list(H2.finditer(body))
    preamble = body[: marks[0].start()] if marks else body
    known: dict[str, str] = {}
    unknown: list[tuple[str, str]] = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        heading = mark.group(1).strip()
        chunk = body[mark.start() : end]
        section = index.get(norm(heading))
        if section is None:
            unknown.append((norm(heading), chunk))
        else:
            known[section] = known.get(section, "") + chunk
    return front, preamble, known, unknown


def check_diff(
    before: str,
    after: str,
    records: list[dict[str, str]] | str,
    sections: dict[str, list[str]],
    others: set[str] | None = None,
    section_aliases: dict[str, str] | None = None,
) -> tuple[str, list[str]]:
    """Return (status, details). status is ok, skipped, or changed."""
    free = others or {"other", "ood"}
    if isinstance(records, str):
        records = [{"section": records, "heading": ""}]
    aliases = section_aliases or {norm(name): name for name in sections}
    allowed = {
        aliases.get(norm(record["section"]), record["section"])
        for record in records
        if norm(record["section"]) not in free
    }
    other_headings = {
        norm(record["heading"])
        for record in records
        if record["heading"] and norm(record["section"]) in free
    }
    missing = [name for name in allowed if name not in sections]
    if missing:
        return "changed", [f"section {name} is not in skill_format.json" for name in missing]
    index = heading_index(sections)
    b_front, b_pre, b_known, b_unknown = split_skill(before, index)
    a_front, a_pre, a_known, a_unknown = split_skill(after, index)
    named = {norm(h) for h, _ in b_unknown} | {norm(h) for h, _ in a_unknown}
    if not (allowed & (set(b_known) | set(a_known))) and not (other_headings & named):
        return "skipped", ["skill has no heading for the named sections; section diff skipped"]
    problems = []
    if b_front != a_front:
        problems.append("frontmatter changed")
    if b_pre != a_pre:
        problems.append("text before the first section changed")
    for name in sorted(set(b_known) | set(a_known)):
        if name in allowed:
            continue
        if b_known.get(name) != a_known.get(name):
            problems.append(f"section {name} changed")
    b_free = {norm(h): chunk for h, chunk in b_unknown}
    a_free = {norm(h): chunk for h, chunk in a_unknown}
    for heading in sorted(set(b_free) | set(a_free)):
        if heading in other_headings:
            continue
        if b_free.get(heading) != a_free.get(heading):
            problems.append(f"heading {heading} changed and is not named as other")
    if problems:
        return "changed", problems
    named_ok = ", ".join(sorted(allowed | {h for h in other_headings}))
    return "ok", [f"only {named_ok} changed"]


def snapshot(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    if not root.is_dir():
        raise SystemExit(f"{root} is not a skill directory")
    for path in root.rglob("*"):
        if path.is_file() and path.name != ".DS_Store":
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def top_dir(rel: str) -> str | None:
    if "/" not in rel:
        return None
    return rel.split("/", 1)[0]


def check_dir_diff(
    before: Path,
    after: Path,
    allowed: list[str] | list[dict[str, str]],
    dirs: dict[str, str],
    others: set[str] | None = None,
) -> tuple[str, list[str]]:
    """Return (status, details). status is ok, skipped, or changed."""
    free = others or {"other", "ood"}
    records = dir_records(allowed)
    allowed_ids = set()
    extra: set[str] = set()
    for record in records:
        if norm(record["dir"]) in free:
            if record["name"]:
                extra.add(norm(record["name"]))
            continue
        canonical = dirs.get(norm(record["dir"]))
        if canonical is None or canonical == "other":
            return "changed", [f"dir {record['dir']} is not in skill_format.json"]
        allowed_ids.add(canonical)
    before_files = snapshot(before)
    after_files = snapshot(after)
    problems: list[str] = []
    seen: set[str] = set()

    def add(message: str) -> None:
        if message not in seen:
            seen.add(message)
            problems.append(message)

    changed = set(before_files) ^ set(after_files)
    for rel in set(before_files) & set(after_files):
        if before_files[rel] != after_files[rel]:
            changed.add(rel)
    for rel in sorted(changed):
        head = top_dir(rel)
        if head is None:
            if rel.casefold() != "skill.md":
                add(f"file {rel} changed")
            continue
        canonical = dirs.get(norm(head))
        if canonical in (None, "other"):
            if norm(head) in extra:
                continue
            add(f"dir {head} changed and is not named as other")
            continue
        if canonical not in allowed_ids:
            add(f"dir {canonical} changed")
    if problems:
        return "changed", problems
    listed = ", ".join(sorted(allowed_ids | extra)) or "(none)"
    return "ok", [f"changes stay inside {listed}"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("goal", nargs="?", type=Path, default=DEFAULT_GOAL)
    parser.add_argument("--list", type=Path, default=DEFAULT_LIST)
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--section", help="section name to allow in the diff")
    parser.add_argument("--before-dir", type=Path)
    parser.add_argument("--after-dir", type=Path)
    parser.add_argument("--dir", help="dir name to allow; default is the dirs named on the goal")
    args = parser.parse_args()
    sections, section_aliases, dirs, others = load_list(args.list)
    errors = check_goal(args.goal, sections, dirs, others, section_aliases)
    for error in errors:
        print(error)
    status = 1 if errors else 0
    if not errors:
        print("every goal section and dir is on the list or named as other")
    if args.before_dir or args.after_dir:
        if not (args.before_dir and args.after_dir):
            print("dir diff needs --before-dir and --after-dir")
            status = 1
        else:
            allowed = dir_records(args.dir) if args.dir else goal_dirs(json.loads(args.goal.read_text()))
            kind, details = check_dir_diff(args.before_dir, args.after_dir, allowed, dirs, others)
            for line in details:
                print(line)
            if kind == "changed":
                status = 1
    if args.before or args.after:
        if not (args.before and args.after and args.section):
            print("diff needs --before, --after, and --section")
            status = 1
        else:
            kind, details = check_diff(
                args.before.read_text(),
                args.after.read_text(),
                bare(args.section),
                sections,
                others,
                section_aliases,
            )
            for line in details:
                print(line)
            if kind == "changed":
                status = 1
    if not any((args.before, args.after, args.before_dir, args.after_dir)):
        stored = compare_stored(
            json.loads(args.goal.read_text()),
            sections,
            section_aliases,
            dirs,
            others,
            DEFAULT_RAW,
            DEFAULT_IMPROVED,
        )
        for line in stored:
            print(line)
        if stored:
            status = 1
    sys.exit(status)


if __name__ == "__main__":
    main()
