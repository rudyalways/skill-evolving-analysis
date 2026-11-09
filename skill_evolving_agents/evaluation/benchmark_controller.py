#!/usr/bin/env python3
"""Plan or execute a held-out benchmark under an explicit time/cost profile.

Profiles:
  smoke-15m, quick-1h, standard-3h, deep-1d

Cost tiers:
  low, standard, high

The planner chooses tasks, conditions, repetitions, parallelism, and per-trial
budgets from the frozen router selection. It writes a cohort spec first; with
``--execute`` it hands that spec to the parallel runner, which enforces the
wall-clock cap and resumes completed trials.

This tool never edits skills and never chooses tasks from outcomes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.heldout_cohort_runner import run as run_cohort

DEFAULT_PROFILES = Path(__file__).with_name("benchmark-profiles.json")
DEFAULT_SELECTION = REPO_ROOT / "workspace/skillbench/v8-heldout16-router-report.json"
DEFAULT_TASKS = REPO_ROOT / "workspace/skillbench/v8-tasks"
DEFAULT_BUNDLES = REPO_ROOT / "workspace/skillbench/v8-heldout16-router-bundles"


def load_profiles(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1:
        raise ValueError("benchmark profiles schema_version must be 1")
    if not isinstance(data.get("time_profiles"), dict):
        raise ValueError("benchmark profiles needs time_profiles")
    if not isinstance(data.get("cost_tiers"), dict):
        raise ValueError("benchmark profiles needs cost_tiers")
    return data


def resolve_profile(profiles: dict[str, Any], name: str) -> str:
    aliases = profiles.get("aliases") or {}
    resolved = aliases.get(name, name)
    if resolved not in profiles["time_profiles"]:
        raise ValueError(
            f"unknown time profile {name!r}; choose "
            + ", ".join(sorted(profiles["time_profiles"]))
        )
    return resolved


def _budget(base: dict[str, Any], multiplier: float) -> dict[str, Any]:
    return {
        "wall_seconds": round(float(base["wall_seconds"]) * multiplier, 3),
        "tool_calls": int(float(base["tool_calls"]) * multiplier),
        "cost_usd": round(float(base["cost_usd"]) * multiplier, 6),
        "exceeded_outcome": "efficiency_failure",
    }


def build_plan(
    *,
    profiles: dict[str, Any],
    selection_report: Path,
    tasks_root: Path,
    bundles_root: Path,
    time_profile: str,
    cost_tier: str,
    jobs_root: Path,
) -> dict[str, Any]:
    profile_name = resolve_profile(profiles, time_profile)
    if cost_tier not in profiles["cost_tiers"]:
        raise ValueError(
            f"unknown cost tier {cost_tier!r}; choose "
            + ", ".join(sorted(profiles["cost_tiers"]))
        )
    profile = profiles["time_profiles"][profile_name]
    tier = profiles["cost_tiers"][cost_tier]
    max_trials = min(int(profile["max_trials"]), int(tier["max_trials"]))
    max_parallel = min(int(profile["max_parallel"]), int(tier["max_parallel"]))
    repetitions = min(
        int(profile["repetitions"]),
        int(tier.get("max_repetitions", profile["repetitions"])),
    )
    budgets = _budget(profile["budgets"], float(tier["budget_multiplier"]))
    estimates = profiles.get("task_runtime_seconds") or {}
    build_estimates = profiles.get("task_build_seconds") or {}
    build_overhead = float(profiles.get("build_overhead_seconds") or 120)

    selection = json.loads(selection_report.read_text()).get("tasks") or {}
    selected = [task for task, row in selection.items() if row.get("selected")]
    abstained = [task for task, row in selection.items() if not row.get("selected")]
    def estimate(task: str) -> float:
        return float(estimates.get(task, 300)) + float(build_estimates.get(task, 120))

    selected.sort(key=estimate)
    abstained.sort(key=estimate)

    ordered: list[tuple[str, list[str]]] = []
    for task in selected:
        ordered.append((task, ["baseline", "treatment"]))
    if profile.get("full_coverage", False):
        for task in abstained:
            ordered.append((task, ["baseline"]))

    rows: list[dict[str, Any]] = []
    for task, conditions in ordered:
        needed = len(conditions) * repetitions
        if len(rows) + needed > max_trials:
            continue
        for condition in conditions:
            for repetition in range(1, repetitions + 1):
                rows.append({
                    "id": task,
                    "condition": condition,
                    "repetition": repetition,
                    "estimated_seconds": estimate(task),
                })

    # Trim from the end if the worst-case per-trial cap exceeds the tier cap.
    estimated_cost = round(len(rows) * budgets["cost_usd"], 6)
    while rows and estimated_cost > float(tier["max_cost_usd"]):
        dropped = rows.pop()
        estimated_cost = round(len(rows) * budgets["cost_usd"], 6)

    def estimated_wall_seconds() -> float:
        return round(
            sum(row["estimated_seconds"] for row in rows) / max(1, max_parallel)
            + build_overhead,
            1,
        )

    estimated_wall = estimated_wall_seconds()
    while rows and estimated_wall > float(profile["time_seconds"]):
        rows.pop()
        estimated_wall = estimated_wall_seconds()

    task_specs: dict[str, dict[str, Any]] = {}
    for row in rows:
        task = row["id"]
        spec = task_specs.setdefault(
            task,
            {
                "id": task,
                "tasks_dir": str(tasks_root / task),
                "conditions": [],
                "repetitions": repetitions,
            },
        )
        if row["condition"] == "treatment":
            spec["bundle"] = str(bundles_root / task)
        if row["condition"] not in spec["conditions"]:
            spec["conditions"].append(row["condition"])

    specs = list(task_specs.values())
    estimated_wall = estimated_wall_seconds()
    plan = {
        "schema_version": 1,
        "time_profile": profile_name,
        "cost_tier": cost_tier,
        "time_budget_seconds": int(profile["time_seconds"]),
        "estimated_wall_seconds": round(estimated_wall, 1),
        "estimated_worst_case_cost_usd": estimated_cost,
        "max_trials": max_trials,
        "max_parallel": max_parallel,
        "repetitions": repetitions,
        "budgets": budgets,
        "selected_tasks": selected,
        "abstained_tasks": abstained,
        "planned_trials": len(rows),
        "planned_tasks": len(specs),
        "full_coverage": bool(profile.get("full_coverage", False)),
        "jobs_root": str(jobs_root),
        "trials": rows,
        "cohort": {
            "schema_version": 1,
            "jobs_root": str(jobs_root),
            "max_parallel": max_parallel,
            "max_wall_seconds": int(profile["time_seconds"]),
            "per_trial_timeout_seconds": budgets["wall_seconds"],
            "resume": True,
            "agent": "deepagents",
            "model": "deepseek/deepseek-chat",
            "sandbox": "docker",
            "common_args": [
                "--concurrency", "1",
                "--agent-idle-timeout", "600",
                "--usage-tracking", "auto",
                "--loop-strategy", "single-shot",
            ],
            "tasks": specs,
        },
    }
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--time-budget", default="smoke-15m")
    parser.add_argument("--cost-tier", default="standard")
    parser.add_argument("--selection-report", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--tasks-root", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--bundles-root", type=Path, default=DEFAULT_BUNDLES)
    parser.add_argument("--jobs-root", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    profiles = load_profiles(args.profiles)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    jobs_root = args.jobs_root or (
        REPO_ROOT
        / "workspace/skillbench"
        / f"controller-{args.time_budget}-{args.cost_tier}-{stamp}"
    )
    out = args.out or (jobs_root.parent / f"{jobs_root.name}-plan.json")
    plan = build_plan(
        profiles=profiles,
        selection_report=args.selection_report,
        tasks_root=args.tasks_root,
        bundles_root=args.bundles_root,
        time_profile=args.time_budget,
        cost_tier=args.cost_tier,
        jobs_root=jobs_root,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    spec_path = jobs_root.parent / f"{jobs_root.name}-spec.json"
    spec_path.write_text(json.dumps(plan["cohort"], indent=2, sort_keys=True) + "\n")
    summary = {
        "time_profile": plan["time_profile"],
        "cost_tier": plan["cost_tier"],
        "planned_trials": plan["planned_trials"],
        "planned_tasks": plan["planned_tasks"],
        "max_parallel": plan["max_parallel"],
        "estimated_wall_seconds": plan["estimated_wall_seconds"],
        "estimated_worst_case_cost_usd": plan["estimated_worst_case_cost_usd"],
        "budgets": plan["budgets"],
        "plan": str(out),
        "spec": str(spec_path),
        "executed": False,
    }
    if args.execute:
        manifest = run_cohort(plan["cohort"])
        manifest_path = jobs_root.parent / f"{jobs_root.name}-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        summary.update({
            "executed": True,
            "manifest": str(manifest_path),
            "elapsed_seconds": manifest.get("elapsed_seconds"),
            "timed_out": manifest.get("timed_out"),
            "stopped_by_wall_clock": manifest.get("stopped_by_wall_clock"),
            "failed": [
                row["task_id"] for row in manifest["runs"]
                if row.get("exit_code") not in (None, 0)
            ],
        })
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
