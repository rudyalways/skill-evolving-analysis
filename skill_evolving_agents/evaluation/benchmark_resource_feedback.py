#!/usr/bin/env python3
"""Convert paired benchmark outcomes and observed skill use into feedback events."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.skillsbench_skill_usage import audit  # noqa: E402
from evaluation.executable_leverage import aggregate as aggregate_leverage  # noqa: E402
from evaluation.executable_leverage import measure as measure_leverage  # noqa: E402
from common.execution_budget import evaluate as evaluate_budget  # noqa: E402
from policy.contracts import stable_digest  # noqa: E402
from policy.store import PolicyStore  # noqa: E402

DEFAULT_BUDGET_PATH = ROOT / "evaluation/trial-budgets.json"


def _usage(path: Path) -> dict[str, Any]:
    result = _result(path)
    try:
        timing = json.loads((path / "timing.json").read_text())
    except (OSError, json.JSONDecodeError):
        timing = {}
    agent_result = result.get("agent_result") or {}
    final_metrics = result.get("final_metrics") or {}
    return {
        "agent_seconds": timing.get("agent_execution"),
        "n_tool_calls": result.get("n_tool_calls"),
        "cost_usd": agent_result.get("cost_usd")
        if agent_result.get("cost_usd") is not None
        else final_metrics.get("total_cost_usd"),
    }


def _trials(root: Path) -> dict[str, Path]:
    rows: dict[str, Path] = {}
    for result_path in sorted(root.rglob("result.json")):
        path = result_path.parent
        if not path.is_dir() or "__" not in path.name:
            continue
        if not (path / "verifier/reward.txt").is_file():
            continue
        result = json.loads(result_path.read_text())
        if result.get("error") or result.get("verifier_error"):
            continue
        task = path.name.split("__", 1)[0]
        if task in rows:
            raise ValueError(f"multiple trials for {task}; aggregate repetitions separately")
        rows[task] = path
    return rows


def _result(path: Path) -> dict[str, Any]:
    return json.loads((path / "result.json").read_text())


def _reward(path: Path) -> float:
    reward = path / "verifier/reward.txt"
    if not reward.is_file():
        raise ValueError(f"missing verifier reward: {reward}")
    return float(reward.read_text().strip())


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _skill_hashes(trial: Path) -> dict[str, str]:
    config_path = trial / "config.json"
    if not config_path.is_file():
        return {}
    config = json.loads(config_path.read_text())
    requested = config.get("requested_skills_dir") or config.get("effective_skills_dir")
    if not isinstance(requested, str) or not requested:
        return {}
    root = Path(requested)
    if not root.is_absolute():
        root = ROOT / root
    if not root.is_dir():
        return {}
    return {
        path.name: _tree_hash(path)
        for path in root.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }


def build_feedback(
    baseline: Path,
    treatment: Path,
    *,
    run_id: str,
    budgets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_budgets = (
        budgets
        if budgets is not None
        else json.loads(DEFAULT_BUDGET_PATH.read_text())
        if DEFAULT_BUDGET_PATH.is_file()
        else {}
    )
    before = _trials(baseline)
    after = _trials(treatment)
    tasks: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    leverage_rows: list[dict[str, Any]] = []
    efficiency_excluded: list[dict[str, Any]] = []
    for task in sorted(set(before) & set(after)):
        b_path, a_path = before[task], after[task]
        trajectory = a_path / "trajectory/acp_trajectory.jsonl"
        if not trajectory.is_file():
            continue
        usage = audit(trajectory)
        hashes = _skill_hashes(a_path)
        b_result, a_result = _result(b_path), _result(a_path)
        b_reward, a_reward = _reward(b_path), _reward(a_path)
        b_budget = evaluate_budget(
            _usage(b_path), active_budgets, passed=b_reward >= 1.0
        )
        a_budget = evaluate_budget(
            _usage(a_path), active_budgets, passed=a_reward >= 1.0
        )
        leverage = measure_leverage(
            usage,
            baseline_tool_calls=int(b_result.get("n_tool_calls") or 0),
            treatment_tool_calls=int(a_result.get("n_tool_calls") or 0),
        )
        task_row = {
            "task_id": task,
            "baseline_reward": b_reward,
            "treatment_reward": a_reward,
            "reward_delta": a_reward - b_reward,
            "baseline_tool_calls": int(b_result.get("n_tool_calls") or 0),
            "treatment_tool_calls": int(a_result.get("n_tool_calls") or 0),
            "baseline_outcome": b_budget["outcome"],
            "treatment_outcome": a_budget["outcome"],
            "budget": {"baseline": b_budget, "treatment": a_budget},
            "executable_leverage": leverage,
            "activation_mode": usage.get("activation_mode"),
            "skills": usage.get("skills") or [],
        }
        tasks.append(task_row)
        if (
            b_budget["outcome"] == "efficiency_failure"
            or a_budget["outcome"] == "efficiency_failure"
        ):
            # A budget-exhausted side is not evidence about skill quality.
            efficiency_excluded.append({
                "task_id": task,
                "baseline_outcome": b_budget["outcome"],
                "treatment_outcome": a_budget["outcome"],
            })
            continue
        leverage_rows.append(leverage)
        for skill in task_row["skills"]:
            value = {
                **{key: task_row[key] for key in (
                    "task_id",
                    "baseline_reward",
                    "treatment_reward",
                    "reward_delta",
                    "baseline_tool_calls",
                    "treatment_tool_calls",
                    "baseline_outcome",
                    "treatment_outcome",
                    "activation_mode",
                )},
                "skill": skill["name"],
                "skill_hash": hashes.get(skill["name"]),
                "skill_md_read": skill.get("skill_md_read", False),
                "skill_md_injected": skill.get("skill_md_injected", False),
                "resources_observed": skill.get("resources_observed") or [],
                "script_execution": skill.get("script_execution") or {},
                "executable_leverage": {
                    "claim": leverage["claim"],
                    "highest_stage": leverage["highest_stage"],
                    "leverage_score": leverage["leverage_score"],
                    "tool_call_reduction": leverage["tool_call_reduction"],
                },
            }
            identity = {
                "run_id": run_id,
                "source": "benchmark",
                "signal": "skill-runtime-outcome",
                "value": value,
            }
            events.append({
                "feedback_id": "feedback-" + stable_digest(identity)[7:23],
                **identity,
                "confidence": 1.0,
            })
    return {
        "schema_version": 3,
        "run_id": run_id,
        "baseline": str(baseline),
        "treatment": str(treatment),
        "budgets": active_budgets,
        "paired_tasks": len(tasks),
        "feedback_events": events,
        "efficiency_excluded": efficiency_excluded,
        "executable_leverage": aggregate_leverage(leverage_rows),
        "tasks": tasks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--treatment", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--budgets", type=Path, default=DEFAULT_BUDGET_PATH)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    budgets = (
        json.loads(args.budgets.read_text()) if args.budgets.is_file() else {}
    )
    report = build_feedback(
        args.baseline, args.treatment, run_id=args.run_id, budgets=budgets
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.database:
        store = PolicyStore(args.database)
        for event in report["feedback_events"]:
            store.record_feedback(event)
    print(f"recorded {len(report['feedback_events'])} benchmark feedback events")


if __name__ == "__main__":
    main()
