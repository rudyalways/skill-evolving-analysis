from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.executable_leverage import aggregate, measure
from evaluation.skillsbench_skill_usage import audit


def _usage(
    *,
    discovered: list[str] | None = None,
    opened: list[str] | None = None,
    attempted: list[str] | None = None,
    succeeded: list[str] | None = None,
    skill_md_read: bool = True,
) -> dict:
    return {
        "skills": [{
            "name": "alpha",
            "skill_md_read": skill_md_read,
            "skill_md_injected": False,
            "resources_discovered": discovered or [],
            "resources_observed": opened or [],
            "script_execution": {
                "attempted": attempted or [],
                "succeeded": succeeded or [],
                "failed": [],
            },
        }]
    }


class ExecutableLeverageTest(unittest.TestCase):
    def test_discovered_only_is_not_use(self) -> None:
        row = measure(
            _usage(discovered=["scripts/run.py"], skill_md_read=False),
            baseline_tool_calls=10,
            treatment_tool_calls=10,
        )
        self.assertEqual(row["claim"], "discovered-only")
        self.assertEqual(row["highest_stage"], "discovered")
        self.assertFalse(row["stages"]["opened"])

    def test_read_without_execution_is_opened_only(self) -> None:
        row = measure(
            _usage(opened=["references/contract.md"]),
            baseline_tool_calls=10,
            treatment_tool_calls=12,
        )
        self.assertEqual(row["claim"], "opened-only")
        self.assertFalse(row["stages"]["executed"])
        self.assertFalse(row["stages"]["reduced_calls"])

    def test_failed_execution_is_not_success(self) -> None:
        row = measure(
            _usage(attempted=["scripts/run.py"], succeeded=[]),
            baseline_tool_calls=10,
            treatment_tool_calls=10,
        )
        self.assertEqual(row["claim"], "executed-not-succeeded")
        self.assertEqual(row["highest_stage"], "executed")

    def test_reported_execution_is_explicit_not_observed(self) -> None:
        usage = {
            "skills": [{
                "name": "alpha",
                "skill_md_read": True,
                "resources_discovered": ["scripts/run.py"],
                "resources_observed": ["scripts/run.py"],
                "script_execution": {
                    "attempted": [],
                    "succeeded": [],
                    "failed": [],
                    "reported": ["scripts/run.py"],
                    "reported_succeeded": ["scripts/run.py"],
                },
            }]
        }
        row = measure(usage, baseline_tool_calls=30, treatment_tool_calls=12)
        self.assertEqual(row["claim"], "reported-executable-leverage")
        self.assertEqual(row["execution_evidence"], "reported")
        self.assertTrue(row["reported_succeeded"])
        self.assertFalse(row["stages"]["executed"])
        self.assertEqual(row["tool_call_reduction"], 18)

    def test_methodology_skill_can_reduce_calls_without_scripts(self) -> None:
        row = measure(
            _usage(opened=[]),
            baseline_tool_calls=198,
            treatment_tool_calls=62,
        )
        self.assertFalse(row["executable_available"])
        self.assertEqual(row["claim"], "methodology-leverage")
        self.assertTrue(row["stages"]["reduced_calls"])
        self.assertEqual(row["applicable_stages"], [
            "discovered", "opened", "reduced_calls"
        ])

    def test_call_reduction_without_execution_is_not_leverage(self) -> None:
        row = measure(
            _usage(
                discovered=["scripts/export-scene.mjs"],
                opened=["references/verification-contract.md"],
            ),
            baseline_tool_calls=107,
            treatment_tool_calls=35,
        )
        self.assertEqual(row["claim"], "opened-only")
        self.assertEqual(row["tool_call_reduction"], 72)
        self.assertFalse(row["stages"]["reduced_calls"])

    def test_success_without_call_reduction_is_not_leverage(self) -> None:
        row = measure(
            _usage(
                attempted=["scripts/run.py"],
                succeeded=["scripts/run.py"],
            ),
            baseline_tool_calls=10,
            treatment_tool_calls=10,
        )
        self.assertEqual(row["claim"], "succeeded-no-reduction")
        self.assertEqual(row["tool_call_reduction"], 0)

    def test_success_and_reduction_is_executable_leverage(self) -> None:
        row = measure(
            _usage(
                discovered=["scripts/run.py"],
                opened=["scripts/run.py"],
                attempted=["scripts/run.py"],
                succeeded=["scripts/run.py"],
            ),
            baseline_tool_calls=30,
            treatment_tool_calls=12,
        )
        self.assertEqual(row["claim"], "executable-leverage")
        self.assertEqual(row["highest_stage"], "reduced_calls")
        self.assertEqual(row["leverage_score"], 1.0)
        self.assertEqual(row["tool_call_reduction"], 18)
        self.assertEqual(
            row["resources"]["succeeded"], ["scripts/run.py"]
        )

    def test_aggregate_keeps_partial_stages_separate(self) -> None:
        full = measure(
            _usage(
                discovered=["scripts/run.py"],
                opened=["scripts/run.py"],
                attempted=["scripts/run.py"],
                succeeded=["scripts/run.py"],
            ),
            baseline_tool_calls=30,
            treatment_tool_calls=20,
        )
        opened = measure(
            _usage(opened=["references/contract.md"]),
            baseline_tool_calls=30,
            treatment_tool_calls=30,
        )
        summary = aggregate([full, opened])
        self.assertEqual(summary["pairs"], 2)
        self.assertEqual(summary["stage_counts"]["reduced_calls"], 1)
        self.assertEqual(summary["executable_leverage_rate"], 0.5)
        self.assertEqual(summary["claims"]["executable-leverage"], 1)
        self.assertEqual(summary["claims"]["opened-only"], 1)

    def test_audit_real_trajectory_events_feed_the_funnel(self) -> None:
        events = [
            {"type": "tool_call", "title": "ls", "kind": "read",
             "text": "ls -R /skills/alpha/scripts"},
            {"type": "tool_call", "title": "read", "kind": "read",
             "text": "cat /skills/alpha/references/contract.md"},
            {"type": "tool_call", "title": "run", "kind": "execute",
             "text": "python /skills/alpha/scripts/run.py --check"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trajectory.jsonl"
            path.write_text(
                "\n".join(json.dumps(event) for event in events) + "\n"
            )
            usage = audit(path)
        row = measure(
            usage, baseline_tool_calls=40, treatment_tool_calls=25
        )
        self.assertTrue(row["stages"]["discovered"])
        self.assertTrue(row["stages"]["opened"])
        self.assertTrue(row["stages"]["executed"])
        self.assertTrue(row["stages"]["succeeded"])
        self.assertTrue(row["stages"]["reduced_calls"])
        self.assertEqual(row["claim"], "executable-leverage")


class FeedbackIntegrationTest(unittest.TestCase):
    def _trial(
        self,
        root: Path,
        name: str,
        *,
        reward: float,
        calls: int,
        trajectory: Path,
    ) -> Path:
        path = root / name
        (path / "verifier").mkdir(parents=True)
        (path / "verifier/reward.txt").write_text(f"{reward}\n")
        (path / "result.json").write_text(
            json.dumps({"task_name": name.split("__", 1)[0], "n_tool_calls": calls})
        )
        (path / "trajectory").mkdir()
        (path / "trajectory/acp_trajectory.jsonl").write_text(
            trajectory.read_text()
        )
        (path / "config.json").write_text(
            json.dumps({"requested_skills_dir": str(root / "skills")})
        )
        return path

    def _fixture(self, root: Path) -> Path:
        skills = root / "skills/alpha"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: test\n---\n"
        )
        trajectory = root / "acp.jsonl"
        trajectory.write_text(
            "\n".join(
                json.dumps(event)
                for event in (
                    {"type": "user_message",
                     "text": "<mounted-skill path=/skills/alpha/SKILL.md>"},
                    {"type": "tool_call", "title": "run", "kind": "execute",
                     "text": "python /skills/alpha/scripts/run.py"},
                )
            )
            + "\n"
        )
        return trajectory

    def test_feedback_records_leverage_and_skips_efficiency_failures(self) -> None:
        from evaluation.benchmark_resource_feedback import build_feedback

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trajectory = self._fixture(root)
            baseline = root / "baseline"
            treatment = root / "treatment"
            self._trial(
                baseline, "task-x__base", reward=1.0, calls=30,
                trajectory=trajectory,
            )
            self._trial(
                treatment, "task-x__treat", reward=1.0, calls=12,
                trajectory=trajectory,
            )
            report = build_feedback(
                baseline,
                treatment,
                run_id="unit",
                budgets={"wall_seconds": 60, "tool_calls": 40, "cost_usd": 1.0},
            )
        self.assertEqual(report["paired_tasks"], 1)
        self.assertEqual(len(report["feedback_events"]), 1)
        event = report["feedback_events"][0]["value"]
        self.assertEqual(event["executable_leverage"]["claim"], "executable-leverage")
        self.assertEqual(event["executable_leverage"]["tool_call_reduction"], 18)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trajectory = self._fixture(root)
            baseline = root / "baseline"
            treatment = root / "treatment"
            self._trial(
                baseline, "task-x__base", reward=1.0, calls=30,
                trajectory=trajectory,
            )
            self._trial(
                treatment, "task-x__treat", reward=1.0, calls=200,
                trajectory=trajectory,
            )
            report = build_feedback(
                baseline,
                treatment,
                run_id="unit",
                budgets={"wall_seconds": 60, "tool_calls": 40, "cost_usd": 1.0},
            )
        self.assertEqual(report["feedback_events"], [])
        self.assertEqual(len(report["efficiency_excluded"]), 1)


if __name__ == "__main__":
    unittest.main()
