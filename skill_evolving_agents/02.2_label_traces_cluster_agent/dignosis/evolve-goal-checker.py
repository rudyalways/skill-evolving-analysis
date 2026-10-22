#!/usr/bin/env python3
"""Check a traces diagnosis against the skill capability tree.

Each item in skill_capabilities_missing is one record: type (a relative path
under skill_capabilites), description (the problem), confidence, reasoning,
and evidence_list (quotes). The path is a directory, or a markdown file without
the suffix. Angle brackets around the path are ignored. A record whose type
is not that path is out of distribution. The checker moves that whole record
into newly_detected_skill_capabilites_missing and writes the diagnosis back.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_TYPE_CHECKER = ROOT.parents[1] / "common" / "skill_type_checker.py"
_spec = importlib.util.spec_from_file_location("skill_type_checker", _TYPE_CHECKER)
skill_type_checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skill_type_checker)

DEFAULT_DIAGNOSIS = (
    ROOT.parents[1] / "workspace" / "run" / "diagnosis.json"
)
DEFAULT_TREE = skill_type_checker.DEFAULT_TREE
MISSING = "skill_capabilities_missing"
OOD = "newly_detected_skill_capabilites_missing"


def leaf_key(record: dict) -> str | None:
    key = record.get("type")
    if not isinstance(key, str) or not key:
        return None
    return skill_type_checker.bare(key) or None


def check(diagnosis_path: Path, tree: Path) -> list[str]:
    diagnosis = json.loads(diagnosis_path.read_text())
    if not isinstance(diagnosis, dict):
        raise SystemExit("diagnosis file must be an object")
    missing = diagnosis.get(MISSING) or []
    if not isinstance(missing, list):
        raise SystemExit(f"{MISSING} must be a list of records")
    detected = diagnosis.get(OOD) or []
    if not isinstance(detected, list):
        raise SystemExit(f"{OOD} must be a list of records")

    leaves = skill_type_checker.leaf_paths(tree)
    kept = []
    moved = []
    for record in missing:
        if not isinstance(record, dict):
            raise SystemExit(f"each {MISSING} item must be an object")
        key = leaf_key(record)
        if key in leaves:
            kept.append(record)
        else:
            detected.append(record)
            moved.append(key or "(no type)")

    diagnosis[MISSING] = kept
    diagnosis[OOD] = detected
    diagnosis_path.write_text(json.dumps(diagnosis, indent=2, ensure_ascii=False) + "\n")
    return moved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnosis", nargs="?", type=Path, default=DEFAULT_DIAGNOSIS)
    parser.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    args = parser.parse_args()
    moved = check(args.diagnosis, args.tree)
    if moved:
        print(f"moved {len(moved)} to {OOD}:")
        for key in moved:
            print(f"  {key}")
    else:
        print(f"every type in {MISSING} is a path under skill_capabilites")


if __name__ == "__main__":
    main()
