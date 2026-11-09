from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from common.execution_budget import (
    ExecutionBudgetExceeded,
    evaluate,
    normalize_limits,
)
import run_pipeline as runner
from evaluation.paired_benchmark_report import build_report


def _trial(
    root: Path,
    name: str,
    *,
    reward: float,
    calls: int,
    seconds: float,
    cost: float | None = None,
) -> Path:
    path = root / name
    (path / "verifier").mkdir(parents=True)
    (path / "verifier/reward.txt").write_text(f"{reward}\n")
    (path / "result.json").write_text(
        json.dumps({
            "task_name": name.split("__", 1)[0],
            "n_tool_calls": calls,
            "agent_result": {"cost_usd": cost},
            "final_metrics": {"total_cost_usd": cost},
        })
    )
    (path / "timing.json").write_text(json.dumps({"agent_execution": seconds}))
    return path


class ExecutionBudgetTest(unittest.TestCase):
    def test_within_budget_returns_task_outcome(self) -> None:
        budget = evaluate(
            {"agent_seconds": 10, "n_tool_calls": 20, "cost_usd": 0.4},
            {"wall_seconds": 60, "tool_calls": 40, "cost_usd": 1.0},
            passed=True,
        )
        self.assertEqual(budget["outcome"], "passed")
        self.assertTrue(budget["within_budget"])

    def test_wall_overage_is_efficiency_failure_even_when_passed(self) -> None:
        budget = evaluate(
            {"agent_seconds": 61, "n_tool_calls": 5, "cost_usd": 0.1},
            {"wall_seconds": 60, "tool_calls": 40, "cost_usd": 1.0},
            passed=True,
        )
        self.assertEqual(budget["outcome"], "efficiency_failure")
        self.assertEqual(budget["violations"][0]["metric"], "wall_seconds")

    def test_tool_call_overage_is_efficiency_failure(self) -> None:
        budget = evaluate(
            {"agent_seconds": 1, "n_tool_calls": 41},
            {"wall_seconds": 60, "tool_calls": 40},
            passed=True,
        )
        self.assertEqual(budget["outcome"], "efficiency_failure")
        self.assertEqual(budget["violations"][0]["metric"], "tool_calls")

    def test_cost_overage_is_efficiency_failure(self) -> None:
        budget = evaluate(
            {"agent_seconds": 1, "n_tool_calls": 1, "cost_usd": 1.01},
            {"wall_seconds": 60, "tool_calls": 40, "cost_usd": 1.0},
            passed=True,
        )
        self.assertEqual(budget["outcome"], "efficiency_failure")
        self.assertEqual(budget["violations"][0]["metric"], "cost_usd")

    def test_unknown_cost_is_unavailable_not_zero(self) -> None:
        budget = evaluate(
            {"agent_seconds": 1, "n_tool_calls": 1, "cost_usd": None},
            {"wall_seconds": 60, "tool_calls": 40, "cost_usd": 1.0},
            passed=True,
        )
        self.assertEqual(budget["outcome"], "passed")
        self.assertFalse(budget["cost_available"])
        self.assertIsNone(budget["observed"]["cost_usd"])

    def test_exact_limit_is_within_budget(self) -> None:
        budget = evaluate(
            {"agent_seconds": 60, "n_tool_calls": 40, "cost_usd": 1.0},
            {"wall_seconds": 60, "tool_calls": 40, "cost_usd": 1.0},
            passed=True,
        )
        self.assertTrue(budget["within_budget"])
        self.assertEqual(budget["outcome"], "passed")

    def test_usage_aliases_are_normalized(self) -> None:
        budget = evaluate(
            {"agent_seconds": 5, "n_tool_calls": 2, "total_cost_usd": 0.1},
            normalize_limits({"wall_seconds": 10, "tool_calls": 3}),
            passed=False,
        )
        self.assertEqual(budget["outcome"], "failed")
        self.assertEqual(budget["observed"]["tool_calls"], 2)


class PairedReportBudgetTest(unittest.TestCase):
    def test_treatment_efficiency_failure_is_explicit_and_counted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline"
            treatment = root / "treatment"
            _trial(
                baseline,
                "task-a__base",
                reward=1.0,
                calls=4,
                seconds=5,
            )
            _trial(
                treatment,
                "task-a__treat",
                reward=1.0,
                calls=9,
                seconds=5,
            )
            report = build_report(
                baseline,
                treatment,
                benchmark="skillsbench@1.1",
                cohort="unit",
                exposure="selective-read",
                domains={"task-a": "office"},
                budgets={"wall_seconds": 60, "tool_calls": 5, "cost_usd": 1.0},
            )
        self.assertEqual(report["paired_tasks"], 1)
        row = report["tasks"][0]
        self.assertEqual(row["baseline_outcome"], "passed")
        self.assertEqual(row["treatment_outcome"], "efficiency_failure")
        self.assertEqual(report["accuracy"]["baseline_passes"], 1)
        self.assertEqual(report["accuracy"]["treatment_passes"], 1)
        self.assertEqual(report["accuracy"]["treatment_outcome_passes"], 0)
        self.assertEqual(report["efficiency"]["treatment_efficiency_failures"], 1)
        self.assertEqual(report["efficiency"]["efficiency_failure_rate"], 1.0)
        self.assertEqual(
            report["budgets"]["tool_calls"],
            5,
        )

    def test_cost_budget_can_fail_a_passed_trial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline"
            treatment = root / "treatment"
            _trial(
                baseline,
                "task-a__base",
                reward=1.0,
                calls=1,
                seconds=1,
                cost=0.1,
            )
            _trial(
                treatment,
                "task-a__treat",
                reward=1.0,
                calls=1,
                seconds=1,
                cost=2.5,
            )
            report = build_report(
                baseline,
                treatment,
                benchmark="skillsbench@1.1",
                cohort="unit",
                exposure="selective-read",
                domains={"task-a": "office"},
                budgets={"wall_seconds": 60, "tool_calls": 5, "cost_usd": 1.0},
            )
        self.assertEqual(
            report["tasks"][0]["treatment_outcome"], "efficiency_failure"
        )
        self.assertEqual(
            report["tasks"][0]["treatment_budget"]["violations"][0]["metric"],
            "cost_usd",
        )


class PipelineBudgetTest(unittest.TestCase):
    def test_tool_call_budget_accumulates_and_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with patch.object(
                runner, "ACTIVE_EXECUTION_CONFIG",
                {"budgets": {"hard_tool_calls": 2}},
            ):
                runner.record_tool_usage(workspace, 1)
                runner.record_tool_usage(workspace, 1)
                with self.assertRaises(ExecutionBudgetExceeded):
                    runner.record_tool_usage(workspace, 1)
            state = json.loads(
                (workspace / "logs/tool-call-budget.json").read_text()
            )
            self.assertEqual(state["used"], 3)
            self.assertEqual(state["remaining"], 0)

    def test_wall_budget_exhaustion_is_explicit(self) -> None:
        with patch.object(runner, "ACTIVE_RUN_DEADLINE_MONOTONIC", 0.0):
            self.assertTrue(runner.run_budget_exhausted())
        with patch.object(runner, "ACTIVE_RUN_DEADLINE_MONOTONIC", None):
            self.assertFalse(runner.run_budget_exhausted())

    def test_efficiency_failure_classification(self) -> None:
        self.assertTrue(
            runner.is_efficiency_failure(ExecutionBudgetExceeded("tool cap"))
        )
        with patch.object(runner, "run_budget_exhausted", return_value=True):
            self.assertTrue(
                runner.is_efficiency_failure(
                    subprocess.TimeoutExpired("agent", 30)
                )
            )
        with patch.object(runner, "run_budget_exhausted", return_value=False):
            self.assertFalse(
                runner.is_efficiency_failure(
                    subprocess.TimeoutExpired("agent", 30)
                )
            )
        self.assertFalse(runner.is_efficiency_failure(RuntimeError("boom")))


if __name__ == "__main__":
    unittest.main()
