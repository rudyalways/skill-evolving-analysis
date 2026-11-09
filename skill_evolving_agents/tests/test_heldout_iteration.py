from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.heldout_iteration import build_iteration


def _trial(
    root: Path,
    name: str,
    *,
    reward: float,
    calls: int,
    seconds: float,
    activated: bool = True,
) -> Path:
    path = root / name
    (path / "verifier").mkdir(parents=True)
    (path / "verifier/reward.txt").write_text(f"{reward}\n")
    (path / "result.json").write_text(
        json.dumps({"task_name": name.split("__", 1)[0], "n_tool_calls": calls})
    )
    (path / "timing.json").write_text(json.dumps({"agent_execution": seconds}))
    events = [
        {"type": "tool_call", "title": "read", "kind": "read",
         "text": "cat /root/task.md"},
        {"type": "tool_call", "title": "read", "kind": "read",
         "text": "cat /skills/alpha/scripts/run.py"},
    ]
    if activated:
        events.insert(0, {
            "type": "user_message",
            "text": "<mounted-skill path=/skills/alpha/SKILL.md>",
        })
    (path / "trajectory").mkdir()
    (path / "trajectory/acp_trajectory.jsonl").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n"
    )
    return path


class HeldoutIterationTest(unittest.TestCase):
    def test_regression_routing_and_efficiency_gaps_are_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline"
            treatment = root / "treatment"
            _trial(baseline, "task-a__base", reward=1.0, calls=10, seconds=10)
            _trial(treatment, "task-a__treat", reward=0.0, calls=20, seconds=10)
            selection = root / "selection.json"
            selection.write_text(json.dumps({
                "tasks": {
                    "task-a": {
                        "selected": [{"skill": "alpha", "score": 0.9}],
                        "abstention_reasons": [],
                    }
                }
            }))
            report = build_iteration(
                baseline,
                treatment,
                benchmark="skillsbench@1.1",
                cohort="unit",
                budgets={"wall_seconds": 60, "tool_calls": 15, "cost_usd": 1.0},
                selection=selection,
            )
        codes = {gap["code"] for gap in report["gaps"]}
        self.assertIn("regression", codes)
        self.assertIn("router_false_positive", codes)
        self.assertIn("efficiency_failure", codes)
        self.assertIn("no_executable_leverage", codes)
        self.assertTrue(report["ready_for_next_round"])
        self.assertEqual(report["gaps_by_code"]["regression"], 1)

    def test_router_abstention_does_not_require_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline"
            treatment = root / "treatment"
            _trial(baseline, "task-a__base", reward=1.0, calls=10, seconds=10)
            _trial(
                treatment,
                "task-a__treat",
                reward=0.0,
                calls=12,
                seconds=10,
                activated=False,
            )
            selection = root / "selection.json"
            selection.write_text(json.dumps({
                "tasks": {
                    "task-a": {
                        "selected": [],
                        "abstention_reasons": ["intent-mismatch"],
                    }
                }
            }))
            report = build_iteration(
                baseline,
                treatment,
                benchmark="skillsbench@1.1",
                cohort="unit",
                budgets={"wall_seconds": 60, "tool_calls": 15, "cost_usd": 1.0},
                selection=selection,
            )
        codes = {gap["code"] for gap in report["gaps"]}
        self.assertNotIn("activation_missing", codes)
        self.assertIn("baseline_drift", codes)
        self.assertFalse(report["ready_for_next_round"])
        self.assertEqual(report["next_round_blocked_by"], ["baseline_drift"])

    def test_baseline_budget_overage_blocks_quality_attribution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline"
            treatment = root / "treatment"
            _trial(baseline, "task-a__base", reward=0.0, calls=20, seconds=10)
            _trial(treatment, "task-a__treat", reward=0.0, calls=10, seconds=10)
            report = build_iteration(
                baseline,
                treatment,
                benchmark="skillsbench@1.1",
                cohort="unit",
                budgets={"wall_seconds": 60, "tool_calls": 15, "cost_usd": 1.0},
            )
        codes = {gap["code"] for gap in report["gaps"]}
        self.assertIn("task_budget_infeasible", codes)
        self.assertFalse(report["ready_for_next_round"])
        self.assertEqual(
            report["next_round_blocked_by"], ["task_budget_infeasible"]
        )

    def test_quality_neutral_cost_regression_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline"
            treatment = root / "treatment"
            _trial(baseline, "task-a__base", reward=1.0, calls=10, seconds=10)
            _trial(treatment, "task-a__treat", reward=1.0, calls=30, seconds=10)
            report = build_iteration(
                baseline,
                treatment,
                benchmark="skillsbench@1.1",
                cohort="unit",
                budgets={"wall_seconds": 60, "tool_calls": 40, "cost_usd": 1.0},
            )
        codes = {gap["code"] for gap in report["gaps"]}
        self.assertIn("efficiency_regression", codes)

    def test_missing_activation_blocks_the_next_round(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline"
            treatment = root / "treatment"
            _trial(baseline, "task-a__base", reward=0.0, calls=10, seconds=10)
            _trial(
                treatment,
                "task-a__treat",
                reward=0.0,
                calls=9,
                seconds=10,
                activated=False,
            )
            report = build_iteration(
                baseline,
                treatment,
                benchmark="skillsbench@1.1",
                cohort="unit",
                budgets={"wall_seconds": 60, "tool_calls": 15, "cost_usd": 1.0},
            )
        self.assertFalse(report["ready_for_next_round"])
        self.assertEqual(report["next_round_blocked_by"], ["activation_missing"])


if __name__ == "__main__":
    unittest.main()
