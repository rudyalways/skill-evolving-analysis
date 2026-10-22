#!/usr/bin/env python3
"""Summarize paired, multi-trial SkillsBench methodology evaluations.

Input is JSONL with one row per task/trial/condition. Required fields are
``task_id``, ``trial``, ``condition`` (``with-skill`` or ``no-skill``), and
``passed``. Optional efficiency and mining fields are aggregated when present.
Use ``ablation`` to separate ``full`` from detector-removal runs.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any


CONDITIONS = {"with-skill", "no-skill"}
EFFICIENCY_FIELDS = (
    "tokens",
    "tool_calls",
    "repeated_errors",
    "skill_context_tokens",
)


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: row must be an object")
        for key in ("task_id", "trial", "condition", "passed"):
            if key not in row:
                raise ValueError(f"{path}:{line_number}: missing {key}")
        if row["condition"] not in CONDITIONS:
            raise ValueError(
                f"{path}:{line_number}: condition must be one of {sorted(CONDITIONS)}"
            )
        rows.append(row)
    return rows


def _number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cells: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        ablation = str(row.get("ablation") or "full")
        key = (ablation, str(row["task_id"]), str(row["trial"]))
        condition = str(row["condition"])
        if condition in cells[key]:
            raise ValueError(f"duplicate evaluation cell: {key} {condition}")
        cells[key][condition] = row

    paired = {
        key: value
        for key, value in cells.items()
        if CONDITIONS.issubset(value)
    }
    by_ablation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (ablation, task_id, trial), cell in paired.items():
        with_skill = cell["with-skill"]
        no_skill = cell["no-skill"]
        record: dict[str, Any] = {
            "task_id": task_id,
            "trial": trial,
            "with_skill_passed": bool(with_skill["passed"]),
            "no_skill_passed": bool(no_skill["passed"]),
            "pass_lift": int(bool(with_skill["passed"]))
            - int(bool(no_skill["passed"])),
        }
        for field in EFFICIENCY_FIELDS:
            with_value = _number(with_skill, field)
            without_value = _number(no_skill, field)
            if with_value is not None and without_value is not None:
                record[f"{field}_delta"] = with_value - without_value
        by_ablation[ablation].append(record)

    summaries: dict[str, Any] = {}
    for ablation, records in sorted(by_ablation.items()):
        task_rates: dict[str, list[float]] = defaultdict(list)
        no_skill_rates: dict[str, list[float]] = defaultdict(list)
        for record in records:
            task_rates[record["task_id"]].append(
                float(record["with_skill_passed"])
            )
            no_skill_rates[record["task_id"]].append(
                float(record["no_skill_passed"])
            )
        with_macro = fmean(
            fmean(values) for values in task_rates.values()
        )
        without_macro = fmean(
            fmean(no_skill_rates[task]) for task in task_rates
        )
        efficiency: dict[str, float] = {}
        for field in EFFICIENCY_FIELDS:
            values = [
                float(record[f"{field}_delta"])
                for record in records
                if f"{field}_delta" in record
            ]
            if values:
                efficiency[f"mean_{field}_delta"] = round(fmean(values), 6)
        summaries[ablation] = {
            "paired_trials": len(records),
            "distinct_tasks": len(task_rates),
            "with_skill_macro_pass_rate": round(with_macro, 6),
            "no_skill_macro_pass_rate": round(without_macro, 6),
            "pass_rate_lift": round(with_macro - without_macro, 6),
            **efficiency,
        }

    full_rate = (
        summaries.get("full", {}).get("with_skill_macro_pass_rate")
    )
    ablation_effects = {}
    if isinstance(full_rate, (int, float)):
        for name, summary in summaries.items():
            if name == "full":
                continue
            ablation_effects[name] = round(
                float(full_rate) - summary["with_skill_macro_pass_rate"], 6
            )

    candidate_total = sum(
        int(row.get("candidate_count") or 0) for row in rows
        if row["condition"] == "with-skill"
    )
    candidate_correct = sum(
        int(row.get("candidate_correct") or 0) for row in rows
        if row["condition"] == "with-skill"
    )
    false_positive = sum(
        int(row.get("false_positive_creations") or 0) for row in rows
        if row["condition"] == "with-skill"
    )
    novelty = [
        float(row["candidate_novelty"])
        for row in rows
        if row["condition"] == "with-skill"
        and isinstance(row.get("candidate_novelty"), (int, float))
        and not isinstance(row.get("candidate_novelty"), bool)
    ]
    return {
        "schema_version": 1,
        "input_rows": len(rows),
        "paired_cells": len(paired),
        "unpaired_cells": len(cells) - len(paired),
        "conditions": summaries,
        "ablation_pass_rate_loss_vs_full": ablation_effects,
        "mining": {
            "candidate_precision": (
                round(candidate_correct / candidate_total, 6)
                if candidate_total
                else None
            ),
            "candidate_count": candidate_total,
            "false_positive_creations": false_positive,
            "mean_candidate_novelty": (
                round(fmean(novelty), 6) if novelty else None
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = summarize(load_rows(args.results))
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
