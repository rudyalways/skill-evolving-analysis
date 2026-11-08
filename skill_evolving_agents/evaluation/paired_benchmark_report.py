#!/usr/bin/env python3
"""Build benchmark-agnostic paired baseline/treatment statistics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

from evaluation.benchmark_trial_validity import audit as audit_trial_validity


def _trial_dirs(jobs: Path | list[Path]) -> dict[str, list[Path]]:
    rows: dict[str, list[Path]] = defaultdict(list)
    for job in [jobs] if isinstance(jobs, Path) else jobs:
        for result_path in sorted(job.rglob("result.json")):
            path = result_path.parent
            if not path.is_dir() or "__" not in path.name:
                continue
            task = path.name.split("__", 1)[0]
            if (path / "result.json").is_file() and (path / "verifier/reward.txt").is_file():
                rows[task].append(path)
    return {task: sorted(paths) for task, paths in rows.items()}


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total == 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [round(max(0.0, centre - spread), 6), round(min(1.0, centre + spread), 6)]


def _two_sided_sign_test(lifts: int, regressions: int) -> float | None:
    n = lifts + regressions
    if n == 0:
        return None
    tail = sum(math.comb(n, k) for k in range(0, min(lifts, regressions) + 1)) / (2**n)
    return round(min(1.0, 2 * tail), 6)


def _number(path: Path, key: str) -> float:
    if not path.is_file():
        return 0.0
    return float(json.loads(path.read_text()).get(key) or 0)


def build_report(
    baseline: Path | list[Path],
    treatment: Path | list[Path],
    *,
    benchmark: str,
    cohort: str,
    exposure: str,
    domains: dict[str, str],
    selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = _trial_dirs(baseline)
    treated = _trial_dirs(treatment)
    common = sorted(set(base) & set(treated))
    tasks: list[dict[str, Any]] = []
    excluded_contaminated: list[dict[str, Any]] = []
    for task in common:
        # BenchFlow's directory suffix is a run UUID, not a shared seed. Pair
        # deterministic repetitions by sorted ordinal and expose any excess.
        for trial, (before, after) in enumerate(zip(base[task], treated[task]), 1):
            invalid_conditions: list[str] = []
            for condition, path in (("baseline", before), ("treatment", after)):
                trajectory = path / "trajectory/acp_trajectory.jsonl"
                if trajectory.is_file():
                    validity = audit_trial_validity(trajectory, task)
                    if not validity["valid"]:
                        invalid_conditions.append(condition)
            if invalid_conditions:
                excluded_contaminated.append({
                    "task_id": task,
                    "trial": trial,
                    "conditions": invalid_conditions,
                    "reason": "answer-or-oracle-discovery",
                })
                continue
            b_reward = float((before / "verifier/reward.txt").read_text().strip())
            a_reward = float((after / "verifier/reward.txt").read_text().strip())
            # SkillsBench can emit partial rewards. Its runner counts only a
            # complete reward as a pass, so preserve both representations.
            b_pass = b_reward >= 1.0
            a_pass = a_reward >= 1.0
            b_calls = int(_number(before / "result.json", "n_tool_calls"))
            a_calls = int(_number(after / "result.json", "n_tool_calls"))
            b_time = _number(before / "timing.json", "agent_execution")
            a_time = _number(after / "timing.json", "agent_execution")
            tasks.append({
                "task_id": task,
                "trial": trial,
                "domain": domains.get(task, "unclassified"),
                "baseline_passed": b_pass,
                "treatment_passed": a_pass,
                "pass_delta": int(a_pass) - int(b_pass),
                "baseline_reward": b_reward,
                "treatment_reward": a_reward,
                "reward_delta": a_reward - b_reward,
                "baseline_tool_calls": b_calls,
                "treatment_tool_calls": a_calls,
                "tool_call_delta": a_calls - b_calls,
                "baseline_agent_seconds": b_time,
                "treatment_agent_seconds": a_time,
                "agent_seconds_delta": a_time - b_time,
            })

    n = len(tasks)
    base_pass = sum(row["baseline_passed"] for row in tasks)
    treated_pass = sum(row["treatment_passed"] for row in tasks)
    lifts = sum(row["pass_delta"] > 0 for row in tasks)
    regressions = sum(row["pass_delta"] < 0 for row in tasks)
    domain_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in tasks:
        domain_rows[row["domain"]].append(row)
    by_domain = {
        name: {
            "tasks": len(rows),
            "baseline_pass_rate": round(sum(r["baseline_passed"] for r in rows) / len(rows), 6),
            "treatment_pass_rate": round(sum(r["treatment_passed"] for r in rows) / len(rows), 6),
            "lifts": sum(r["pass_delta"] > 0 for r in rows),
            "regressions": sum(r["pass_delta"] < 0 for r in rows),
        }
        for name, rows in sorted(domain_rows.items())
    }
    report = {
        "schema_version": 1,
        "benchmark": benchmark,
        "cohort": cohort,
        "treatment_exposure": exposure,
        "baseline_jobs": [str(path) for path in ([baseline] if isinstance(baseline, Path) else baseline)],
        "treatment_jobs": [str(path) for path in ([treatment] if isinstance(treatment, Path) else treatment)],
        "paired_tasks": n,
        "excluded_unpaired": {
            task: abs(len(base.get(task, [])) - len(treated.get(task, [])))
            for task in sorted(set(base) | set(treated))
            if len(base.get(task, [])) != len(treated.get(task, []))
        },
        "excluded_contaminated": excluded_contaminated,
        "accuracy": {
            "baseline_passes": base_pass,
            "treatment_passes": treated_pass,
            "baseline_pass_rate": round(base_pass / n, 6) if n else None,
            "treatment_pass_rate": round(treated_pass / n, 6) if n else None,
            "absolute_lift": round((treated_pass - base_pass) / n, 6) if n else None,
            "baseline_wilson_95": _wilson(base_pass, n),
            "treatment_wilson_95": _wilson(treated_pass, n),
            "lifts": lifts,
            "regressions": regressions,
            "unchanged": n - lifts - regressions,
            "discordant_exact_p": _two_sided_sign_test(lifts, regressions),
        },
        "reward": {
            "baseline_mean": round(fmean(r["baseline_reward"] for r in tasks), 6) if n else None,
            "treatment_mean": round(fmean(r["treatment_reward"] for r in tasks), 6) if n else None,
            "mean_delta": round(fmean(r["reward_delta"] for r in tasks), 6) if n else None,
            "improvements": sum(r["reward_delta"] > 0 for r in tasks),
            "regressions": sum(r["reward_delta"] < 0 for r in tasks),
        },
        "efficiency": {
            "baseline_tool_calls": sum(r["baseline_tool_calls"] for r in tasks),
            "treatment_tool_calls": sum(r["treatment_tool_calls"] for r in tasks),
            "mean_tool_call_delta": round(fmean(r["tool_call_delta"] for r in tasks), 6) if n else None,
            "baseline_agent_seconds": sum(r["baseline_agent_seconds"] for r in tasks),
            "treatment_agent_seconds": sum(r["treatment_agent_seconds"] for r in tasks),
            "mean_agent_seconds_delta": round(fmean(r["agent_seconds_delta"] for r in tasks), 6) if n else None,
        },
        "coverage": {
            "domains": len(domain_rows),
            "tasks_by_domain": dict(sorted(Counter(r["domain"] for r in tasks).items())),
        },
        "by_domain": by_domain,
        "tasks": tasks,
    }
    if selection is not None:
        report["selection"] = selection
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, nargs="+", required=True)
    parser.add_argument("--treatment", type=Path, nargs="+", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--exposure", default="selective-read")
    parser.add_argument("--domains", type=Path)
    parser.add_argument("--selection-report", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    domains = json.loads(args.domains.read_text()) if args.domains else {}
    selection = None
    if args.selection_report:
        raw = args.selection_report.read_bytes()
        source = json.loads(raw)
        selection = {
            "report": str(args.selection_report),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "strategy": source.get("strategy"),
            "model_revision": source.get("model_revision"),
            "skills_root_hash": source.get("skills_root_hash"),
            "eligible_skill_count": source.get("eligible_skill_count"),
            "excluded_skill_count": len(source.get("excluded_skills") or {}),
            "tasks": {
                task: {
                    "selected": row.get("selected") or [],
                    "selection_count": row.get("selection_count", 0),
                    "bundle_hash": row.get("bundle_hash"),
                }
                for task, row in (source.get("tasks") or {}).items()
            },
        }
    report = build_report(args.baseline, args.treatment, benchmark=args.benchmark, cohort=args.cohort, exposure=args.exposure, domains=domains, selection=selection)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
