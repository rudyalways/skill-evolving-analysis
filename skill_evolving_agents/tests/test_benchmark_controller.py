from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.benchmark_controller import build_plan, load_profiles

PROFILES = load_profiles(Path(__file__).resolve().parents[1] / "evaluation/benchmark-profiles.json")


def _selection(root: Path) -> Path:
    path = root / "selection.json"
    path.write_text(json.dumps({
        "tasks": {
            "fast-selected": {"selected": [{"skill": "a"}]},
            "slow-selected": {"selected": [{"skill": "b"}]},
            "abstained-a": {"selected": []},
            "abstained-b": {"selected": []},
        }
    }))
    return path


class BenchmarkControllerTest(unittest.TestCase):
    def _plan(self, root: Path, time_profile: str, cost_tier: str):
        return build_plan(
            profiles=PROFILES,
            selection_report=_selection(root),
            tasks_root=root / "tasks",
            bundles_root=root / "bundles",
            time_profile=time_profile,
            cost_tier=cost_tier,
            jobs_root=root / "jobs",
        )

    def test_smoke_plan_is_small_and_within_wall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = self._plan(Path(directory), "smoke-15m", "standard")
        self.assertLessEqual(plan["planned_trials"], 4)
        self.assertGreaterEqual(plan["planned_tasks"], 1)
        self.assertEqual(plan["max_parallel"], 2)
        self.assertLessEqual(plan["estimated_wall_seconds"], 900)
        self.assertEqual(plan["budgets"]["tool_calls"], 60)

    def test_standard_plan_covers_all_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = self._plan(Path(directory), "standard-3h", "standard")
        self.assertEqual(plan["planned_trials"], 6)  # 2 selected pairs + 2 abstained baselines
        conditions: dict[str, set[str]] = {}
        for row in plan["trials"]:
            conditions.setdefault(row["id"], set()).add(row["condition"])
        self.assertIn("baseline", conditions["fast-selected"])
        self.assertIn("treatment", conditions["fast-selected"])
        self.assertEqual(conditions["abstained-a"], {"baseline"})
        self.assertEqual(
            sum(1 for row in plan["trials"] if row["condition"] == "treatment"),
            2,
        )

    def test_low_cost_tier_caps_trials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = self._plan(Path(directory), "deep-1d", "low")
        self.assertEqual(plan["planned_trials"], 4)
        self.assertEqual(plan["max_parallel"], 2)
        self.assertEqual(plan["budgets"]["tool_calls"], 90)

    def test_deep_plan_repeats_selected_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = self._plan(Path(directory), "deep-1d", "high")
        selected_rows = [
            row for row in plan["trials"]
            if row["condition"] == "treatment"
        ]
        self.assertEqual(len(selected_rows), 6)  # 2 selected tasks x 3 repetitions
        self.assertEqual(plan["max_parallel"], 8)
        self.assertGreaterEqual(plan["budgets"]["tool_calls"], 180)

    def test_unknown_profile_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                self._plan(Path(directory), "whenever", "standard")


if __name__ == "__main__":
    unittest.main()
