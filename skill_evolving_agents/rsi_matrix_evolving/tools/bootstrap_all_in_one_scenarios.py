#!/usr/bin/env python3
"""Build life/work bootstrap scenarios from Evolvent's all-in-one scenario matrix."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SECTIONS = (
    ("workplace_tools", "## 2.", "## 3.", "workplace_tool_use"),
    ("occupational_work", "## 3.", "## 4.", "professional_work"),
    ("personal_consumer_life", "## 5.", "## 6.", "consumer_life"),
)
EXCLUDED_STATS = {"silent", "absent", "not_found"}


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def objects(chunk: str):
    for raw in re.findall(r"\{[^\n]*?\}", chunk):
        try:
            yield json.loads(raw)
        except json.JSONDecodeError:
            continue


def strongest(current: dict | None, candidate: dict) -> dict:
    rank = {"count": 5, "avg@3": 5, "unsplit": 4, "named": 3, "inferred": 2, "note": 1, None: 0}
    if current is None or rank.get(candidate.get("stat"), 0) > rank.get(current.get("stat"), 0):
        return candidate
    return current


def make_scenario(l1: str, capability_family: str, cell: dict, matrix: Path, bundle: Path) -> dict:
    benchmark = str(cell["bench"])
    sub = str(cell["sub"])
    key = slug(f"{l1}-{benchmark}-{sub}")
    stat = cell.get("stat") or "named"
    count = cell.get("n")
    grade = cell.get("grade") or "stated"
    evidence = f"{stat}" + (f"={count}" if count is not None else "") + f", evidence grade={grade}"
    prompt = (
        f"All-in-one scenario probe for {sub} in {benchmark}, under {l1.replace('_', ' ')}. "
        f"The source matrix records this cell as {evidence}. For difficulty {{difficulty}}, describe one realistic user request, "
        "a concise execution plan, the external state that must be verified, and one observable success criterion. "
        "Do not claim to have used tools or accessed data that are unavailable."
    )
    return {
        "schema_version": 1,
        "scenario_id": f"allinone.{key}.v1",
        "title": f"{benchmark} · {sub}",
        "domain": [l1, slug(benchmark), slug(sub)],
        "distribution": {
            "status": "id_declared",
            "reference_population": "Evolvent benchmark all-in-one scenario matrix",
            "reason_codes": ["all_in_one_matrix_cell", grade],
            "confidence": 1.0 if grade == "stated" else 0.7,
            "axis": "life_work_scenario",
        },
        "capabilities": {
            "required": [f"{capability_family}:{slug(sub)}"],
            "prohibited": ["fabricate_tool_result"],
            "optional": ["clarify_missing_state", "verify_external_state"],
        },
        "interface_requirements": [capability_family],
        "risk": {"level": "low", "sandbox_required": True},
        "generator": {
            "kind": "all_in_one_scenario_probe",
            "template_id": f"all-in-one-{key}-v1",
            "prompt": prompt,
            "parameter_schema": {"difficulty": ["easy", "medium", "hard"]},
        },
        "oracle": {"kind": "evidence_capture", "checks": ["nonempty_response", "no_fabricated_access"]},
        "tags": [
            "bootstrap", "all-in-one", "life-work", f"benchmark:{benchmark}",
            f"matrix_stat:{stat}", f"evidence_grade:{grade}",
            f"matrix_source:{matrix.resolve()}", f"bundle_source:{bundle.resolve()}",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=Path, help="Canonical scenarios-matrix.md used by the all-in-one bundle")
    parser.add_argument("bundle", type=Path, help="benchmark-all-in-one.html provenance source")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    text = args.matrix.read_text()
    scenarios = []
    counts = {}
    for l1, start, end, capability_family in SECTIONS:
        chunk = text.split(start, 1)[1].split(end, 1)[0]
        cells = {}
        for cell in objects(chunk):
            if "bench" not in cell or "sub" not in cell or cell.get("stat") in EXCLUDED_STATS:
                continue
            identity = (str(cell["bench"]), str(cell["sub"]))
            cells[identity] = strongest(cells.get(identity), cell)
        counts[l1] = len(cells)
        scenarios.extend(make_scenario(l1, capability_family, cell, args.matrix, args.bundle) for cell in cells.values())
    payload = {
        "schema_version": 1,
        "name": "Evolvent all-in-one life and work scenario bootstrap",
        "source_bundle": str(args.bundle.resolve()),
        "source_matrix": str(args.matrix.resolve()),
        "section_counts": counts,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(scenarios)} scenarios ({counts}) to {args.output}")


if __name__ == "__main__":
    main()
