#!/usr/bin/env python3
"""Check skill_types against the skill capability tree.

Each entry in skills_metadata[].skill_types is a path in the normalized
skill_capabilites JSON, or an object with type and weight.
Angle brackets around the path are ignored. A path that is not in the tree
cannot select a skill to improve. The checker moves that string into
unmatched_skill_types on the same skill and writes the metadata back.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENT = ROOT.parent
DEFAULT_METADATA = (
    AGENT
    / "workspace"
    / "target"
    / "to_be_improved_skills_metadata"
    / "metadata.json"
)
DEFAULT_TREE = AGENT / "skill_capabilites" / "skill_capabilites.json"
TYPES = "skill_types"
UNMATCHED = "unmatched_skill_types"


def leaf_paths(tree: Path) -> set[str]:
    if tree.is_file():
        try:
            document = json.loads(tree.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise SystemExit(f"invalid skill capability taxonomy: {tree}: {error}")
        dimensions = document.get("dimensions") if isinstance(document, dict) else None
        if not isinstance(dimensions, dict):
            raise SystemExit("skill capability taxonomy dimensions must be an object")
        paths: set[str] = set()
        for dimension, values in dimensions.items():
            if not isinstance(dimension, str) or not dimension or "/" in dimension:
                raise SystemExit("skill capability dimension names must be path segments")
            if not isinstance(values, dict):
                raise SystemExit(f"skill capability dimension {dimension} must be an object")
            for value, children in values.items():
                if not isinstance(value, str) or not value or "/" in value:
                    raise SystemExit(
                        f"skill capability value in {dimension} must be a path segment"
                    )
                parent = f"{dimension}/{value}"
                paths.add(parent)
                if not isinstance(children, list):
                    raise SystemExit(f"skill capability children for {parent} must be a list")
                for child in children:
                    if not isinstance(child, str) or not child or "/" in child:
                        raise SystemExit(
                            f"skill capability child under {parent} must be a path segment"
                        )
                    paths.add(f"{parent}/{child}")
        if not paths:
            raise SystemExit(f"skill capability taxonomy has no paths: {tree}")
        return paths
    if not tree.is_dir():
        raise SystemExit(f"skill capability taxonomy is missing: {tree}")
    paths: set[str] = set()
    for path in tree.rglob("*"):
        if path.name == "readme.md":
            continue
        rel = path.relative_to(tree)
        if path.is_dir():
            paths.add(rel.as_posix())
        elif path.suffix == ".md":
            paths.add(rel.with_suffix("").as_posix())
    if not paths:
        raise SystemExit(f"skill capability tree has no paths: {tree}")
    return paths


def bare(value: str) -> str:
    if value.startswith("<") and value.endswith(">") and len(value) > 2:
        return value[1:-1]
    return value


def type_path(item: object) -> str | None:
    if isinstance(item, str):
        return item or None
    if isinstance(item, dict):
        path = item.get("type")
        if isinstance(path, str) and path:
            return path
    return None


def check(metadata_path: Path, tree: Path) -> list[str]:
    metadata = json.loads(metadata_path.read_text())
    skills = metadata.get("skills_metadata")
    if not isinstance(skills, list):
        raise SystemExit("skills_metadata must be a list")

    leaves = leaf_paths(tree)
    moved = []
    for skill in skills:
        if not isinstance(skill, dict):
            raise SystemExit("each skills_metadata item must be an object")
        types = skill.get(TYPES) or []
        if not isinstance(types, list):
            raise SystemExit(f"{TYPES} must be a list of paths")
        unmatched = skill.get(UNMATCHED) or []
        if not isinstance(unmatched, list):
            raise SystemExit(f"{UNMATCHED} must be a list")
        kept = []
        for item in types:
            path = type_path(item)
            if path is None or not bare(path):
                unmatched.append(item)
                moved.append(str(item))
                continue
            if bare(path) in leaves:
                kept.append(item)
            else:
                unmatched.append(item)
                moved.append(bare(path))
        skill[TYPES] = kept
        if unmatched:
            skill[UNMATCHED] = unmatched
        else:
            skill.pop(UNMATCHED, None)

    if moved:
        metadata_path.write_text(json.dumps(metadata, indent=4, ensure_ascii=False) + "\n")
    return moved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", nargs="?", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    args = parser.parse_args()
    moved = check(args.metadata, args.tree)
    if moved:
        print(f"moved {len(moved)} to {UNMATCHED}:")
        for key in moved:
            print(f"  {key}")
    else:
        print(f"every {TYPES} entry is a path under skill_capabilites")


if __name__ == "__main__":
    main()
