#!/usr/bin/env python3
"""Validate and aggregate evidence-backed skill evaluations."""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path
from typing import Any


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_evals_data(data: object, skill_name: str) -> list[str]:
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["evals.json must contain an object"]
    if data.get("skill_name") != skill_name:
        problems.append("skill_name must match SKILL.md frontmatter")
    rows = data.get("evals")
    if not isinstance(rows, list) or not rows:
        return [*problems, "evals must be a non-empty list"]
    seen: set[int | str] = set()
    kinds: set[str] = set()
    for index, row in enumerate(rows):
        prefix = f"evals[{index}]"
        if not isinstance(row, dict):
            problems.append(f"{prefix} must be an object")
            continue
        identifier = row.get("id")
        if not isinstance(identifier, (int, str)) or isinstance(identifier, bool):
            problems.append(f"{prefix}.id must be an integer or string")
        elif identifier in seen:
            problems.append(f"{prefix}.id is duplicated")
        else:
            seen.add(identifier)
        for field in ("prompt", "expected_output"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                problems.append(f"{prefix}.{field} must be a non-empty string")
        expectations = row.get("expectations")
        if expectations is not None and (
            not isinstance(expectations, list)
            or not expectations
            or any(not isinstance(item, str) or not item.strip() for item in expectations)
        ):
            problems.append(
                f"{prefix}.expectations must be a non-empty list of strings"
            )
        files = row.get("files")
        if files is not None and (
            not isinstance(files, list)
            or any(not isinstance(item, str) or not item.strip() for item in files)
        ):
            problems.append(f"{prefix}.files must be a list of paths")
        kind = row.get("kind")
        if kind is not None:
            if kind not in {"should_apply", "should_not_apply"}:
                problems.append(
                    f"{prefix}.kind must be should_apply or should_not_apply"
                )
            else:
                kinds.add(kind)
    if kinds and kinds != {"should_apply", "should_not_apply"}:
        problems.append(
            "typed evals must include both should_apply and should_not_apply cases"
        )
    return problems


def validate_evals_file(path: Path, skill_name: str) -> list[str]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        return [f"cannot read evals.json: {error}"]
    problems = validate_evals_data(data, skill_name)
    if isinstance(data, dict):
        for index, row in enumerate(data.get("evals") or []):
            if not isinstance(row, dict):
                continue
            for rel in row.get("files") or []:
                if not isinstance(rel, str):
                    continue
                target = path.parent.parent / rel
                try:
                    target.resolve().relative_to(path.parent.parent.resolve())
                except ValueError:
                    problems.append(f"evals[{index}].files escapes the skill root")
                    continue
                if not target.is_file():
                    problems.append(f"evals[{index}].files is missing: {rel}")
    return problems


def source_trace_ids(data: object) -> set[str]:
    if not isinstance(data, dict):
        return set()
    return {
        trace_id
        for row in data.get("evals") or []
        if isinstance(row, dict)
        for trace_id in row.get("source_trace_ids") or []
        if isinstance(trace_id, str) and trace_id
    }


def validate_held_out_evals_data(
    data: object,
    skill_name: str,
    development_data: object,
) -> list[str]:
    problems = validate_evals_data(data, skill_name)
    if not isinstance(data, dict) or not isinstance(development_data, dict):
        return problems
    development_prompts = {
        str(row.get("prompt", "")).strip().casefold()
        for row in development_data.get("evals") or []
        if isinstance(row, dict)
    }
    held_out_prompts = {
        str(row.get("prompt", "")).strip().casefold()
        for row in data.get("evals") or []
        if isinstance(row, dict)
    }
    overlap = sorted(
        value for value in development_prompts & held_out_prompts if value
    )
    if overlap:
        problems.append("held-out prompts overlap development prompts")
    trace_overlap = sorted(
        source_trace_ids(data) & source_trace_ids(development_data)
    )
    if trace_overlap:
        problems.append("held-out evidence overlaps development trace IDs")
    kinds = {
        row.get("kind")
        for row in data.get("evals") or []
        if isinstance(row, dict)
    }
    if kinds != {"should_apply", "should_not_apply"}:
        problems.append("held-out evals must include positive and near-miss cases")
    return problems


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": statistics.fmean(values),
        "stddev": statistics.pstdev(values),
        "min": min(values),
        "max": max(values),
    }


def aggregate_benchmark(runs: list[dict[str, Any]]) -> dict[str, object]:
    """Aggregate repeat runs without hiding variance or failures."""
    configurations = ("with_skill", "without_skill")
    summary: dict[str, object] = {}
    for configuration in configurations:
        selected = [
            row for row in runs if row.get("configuration") == configuration
        ]
        summary[configuration] = {
            metric: _stats(
                [
                    float(row["result"][metric])
                    for row in selected
                    if isinstance(row.get("result"), dict)
                    and _number(row["result"].get(metric))
                ]
            )
            for metric in ("pass_rate", "time_seconds", "tokens", "tool_calls")
        }
        summary[configuration]["runs"] = len(selected)  # type: ignore[index]
        summary[configuration]["errors"] = sum(  # type: ignore[index]
            int(row["result"].get("errors", 0))
            for row in selected
            if isinstance(row.get("result"), dict)
            and _number(row["result"].get("errors", 0))
        )
    before = summary["without_skill"]
    after = summary["with_skill"]
    assert isinstance(before, dict) and isinstance(after, dict)
    summary["delta"] = {
        metric: after[metric]["mean"] - before[metric]["mean"]  # type: ignore[index]
        for metric in ("pass_rate", "time_seconds", "tokens", "tool_calls")
    }
    return summary


def aggregate_activation(rows: list[dict[str, Any]]) -> dict[str, object]:
    """Measure skill selection separately from task execution quality."""
    positive = [row for row in rows if row.get("kind") == "should_apply"]
    negative = [row for row in rows if row.get("kind") == "should_not_apply"]
    true_positive = sum(row.get("activated") is True for row in positive)
    false_negative = len(positive) - true_positive
    false_positive = sum(row.get("activated") is True for row in negative)
    true_negative = len(negative) - false_positive
    selected = true_positive + false_positive
    return {
        "cases": len(rows),
        "confusion_matrix": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "true_negative": true_negative,
            "false_negative": false_negative,
        },
        "recall": true_positive / len(positive) if positive else None,
        "precision": true_positive / selected if selected else None,
        "false_positive_rate": (
            false_positive / len(negative) if negative else None
        ),
    }


def validate_activation_data(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["activation results must contain an object"]
    rows = data.get("results")
    if not isinstance(rows, list) or not rows:
        return ["activation results must be a non-empty list"]
    problems: list[str] = []
    kinds: set[str] = set()
    for index, row in enumerate(rows):
        prefix = f"results[{index}]"
        if not isinstance(row, dict):
            problems.append(f"{prefix} must be an object")
            continue
        kind = row.get("kind")
        if kind not in {"should_apply", "should_not_apply"}:
            problems.append(f"{prefix}.kind has an unknown value")
        else:
            kinds.add(kind)
        if not isinstance(row.get("activated"), bool):
            problems.append(f"{prefix}.activated must be boolean")
        if "eval_id" not in row:
            problems.append(f"{prefix}.eval_id is required")
    if kinds != {"should_apply", "should_not_apply"}:
        problems.append("activation results must include positive and near-miss cases")
    expected = aggregate_activation(
        [row for row in rows if isinstance(row, dict)]
    )
    if data.get("summary") != expected:
        problems.append(
            "summary must equal deterministic aggregate_activation output"
        )
    return problems


def validate_replay_manifest_data(data: object) -> list[str]:
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["replay manifest must contain an object"]
    for field in (
        "run_id",
        "skill",
        "backend",
        "model",
        "generated_at",
        "candidate_sha256",
        "held_out_sha256",
    ):
        if not isinstance(data.get(field), str) or not data[field]:
            problems.append(f"{field} must be a non-empty string")
    for field in (
        "candidate_sha256",
        "baseline_sha256",
        "held_out_sha256",
    ):
        value = data.get(field)
        if value is not None and (
            not isinstance(value, str)
            or not re.fullmatch(r"[0-9a-f]{64}", value)
        ):
            problems.append(f"{field} must be 64 lowercase hex characters")
    configurations = data.get("configurations")
    if configurations != ["without_skill", "with_skill"]:
        problems.append(
            "configurations must be ['without_skill', 'with_skill']"
        )
    trials = data.get("trials_per_configuration")
    if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
        problems.append("trials_per_configuration must be a positive integer")
    eval_ids = data.get("eval_ids")
    if (
        not isinstance(eval_ids, list)
        or not eval_ids
        or any(not isinstance(value, (int, str)) for value in eval_ids)
    ):
        problems.append("eval_ids must be a non-empty list")
    held_out_eval_ids = data.get("held_out_eval_ids")
    if (
        not isinstance(held_out_eval_ids, list)
        or not held_out_eval_ids
        or any(
            not isinstance(value, (int, str))
            for value in held_out_eval_ids
        )
    ):
        problems.append("held_out_eval_ids must be a non-empty list")
    elif (
        isinstance(eval_ids, list)
        and all(isinstance(value, (int, str)) for value in eval_ids)
        and set(eval_ids) & set(held_out_eval_ids)
    ):
        problems.append("development and held-out eval IDs must be disjoint")
    if data.get("executed") is not True:
        problems.append("executed must be true; do not write manifests for planned runs")
    return problems


def validate_benchmark_data(data: object) -> list[str]:
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["benchmark must contain an object"]
    runs = data.get("runs")
    if not isinstance(runs, list) or not runs:
        return ["benchmark runs must be a non-empty list"]
    configurations: set[str] = set()
    for index, row in enumerate(runs):
        prefix = f"runs[{index}]"
        if not isinstance(row, dict):
            problems.append(f"{prefix} must be an object")
            continue
        configuration = row.get("configuration")
        if configuration not in {"with_skill", "without_skill"}:
            problems.append(f"{prefix}.configuration has an unknown value")
        else:
            configurations.add(configuration)
        if row.get("split") not in {"development", "held_out"}:
            problems.append(f"{prefix}.split has an unknown value")
        if not isinstance(row.get("run_number"), int):
            problems.append(f"{prefix}.run_number must be an integer")
        result = row.get("result")
        if not isinstance(result, dict):
            problems.append(f"{prefix}.result must be an object")
            continue
        for field in (
            "pass_rate",
            "time_seconds",
            "tokens",
            "tool_calls",
            "errors",
        ):
            if not _number(result.get(field)):
                problems.append(f"{prefix}.result.{field} must be numeric")
    if configurations != {"with_skill", "without_skill"}:
        problems.append("benchmark must include both skill configurations")
    held_out_configurations = {
        row.get("configuration")
        for row in runs
        if isinstance(row, dict) and row.get("split") == "held_out"
    }
    if held_out_configurations != {"with_skill", "without_skill"}:
        problems.append(
            "benchmark must include both configurations for held-out cases"
        )
    expected = aggregate_benchmark(
        [row for row in runs if isinstance(row, dict)]
    )
    if data.get("run_summary") != expected:
        problems.append(
            "run_summary must equal deterministic aggregate_benchmark output"
        )
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("evals", type=Path)
    validate.add_argument("--skill", required=True)
    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("benchmark", type=Path)
    activation = subparsers.add_parser("activation")
    activation.add_argument("results", type=Path)
    args = parser.parse_args()
    if args.command == "validate":
        problems = validate_evals_file(args.evals, args.skill)
        for problem in problems:
            print(problem)
        raise SystemExit(1 if problems else 0)
    if args.command == "aggregate":
        data = json.loads(args.benchmark.read_text())
        data["run_summary"] = aggregate_benchmark(data.get("runs") or [])
        args.benchmark.write_text(json.dumps(data, indent=2) + "\n")
        return
    data = json.loads(args.results.read_text())
    data["summary"] = aggregate_activation(data.get("results") or [])
    args.results.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()
