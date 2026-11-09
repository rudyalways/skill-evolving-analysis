from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from evaluation.heldout_cohort_runner import commands, load_spec, run


def _spec(root: Path) -> dict:
    return {
        "schema_version": 1,
        "jobs_root": str(root / "jobs"),
        "max_parallel": 2,
        "agent": "deepagents",
        "model": "deepseek/deepseek-chat",
        "sandbox": "docker",
        "common_args": ["--concurrency", "1"],
        "tasks": [
            {
                "id": "task-a",
                "tasks_dir": str(root / "tasks/a"),
                "bundle": str(root / "bundles/a"),
                "repetitions": 2,
            },
            {
                "id": "task-b",
                "tasks_dir": str(root / "tasks/b"),
                "repetitions": 1,
                "conditions": ["baseline"],
            },
        ],
    }


class HeldoutCohortRunnerTest(unittest.TestCase):
    def test_expands_matched_conditions_and_repetitions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = commands(_spec(root))
        self.assertEqual(len(rows), 5)
        baseline = [r for r in rows if r["task_id"] == "task-a" and r["condition"] == "baseline"]
        treatment = [r for r in rows if r["task_id"] == "task-a" and r["condition"] == "treatment"]
        self.assertEqual([r["repetition"] for r in baseline], [1, 2])
        self.assertIn("--skill-mode", baseline[0]["command"])
        self.assertIn("no-skill", baseline[0]["command"])
        self.assertIn("with-skill", treatment[0]["command"])
        self.assertIn(str(root / "bundles/a"), treatment[0]["command"])

    def test_dry_run_never_executes_bench(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = _spec(root)
            manifest = run(spec, dry_run=True)
        self.assertTrue(manifest["dry_run"])
        self.assertEqual(len(manifest["runs"]), 5)
        self.assertTrue(all(row["exit_code"] is None for row in manifest["runs"]))

    def test_rejects_treatment_without_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = _spec(root)
            spec["tasks"][0].pop("bundle")
            with self.assertRaises(ValueError):
                commands(spec)

    def test_spec_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spec.json"
            path.write_text('{"schema_version": 1, "tasks": []}')
            with self.assertRaises(ValueError):
                load_spec(path)

    def test_wall_clock_cap_marks_timed_out(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sleeper = root / "sleep.sh"
            sleeper.write_text("#!/bin/sh\nsleep 5\n")
            sleeper.chmod(0o755)
            spec = {
                "schema_version": 1,
                "jobs_root": str(root / "jobs"),
                "max_parallel": 1,
                "bench": str(sleeper),
                "max_wall_seconds": 1,
                "tasks": [
                    {"id": "task-a", "tasks_dir": "unused", "conditions": ["baseline"]}
                ],
            }
            started = time.time()
            manifest = run(spec)
            elapsed = time.time() - started
        self.assertEqual(manifest["timed_out"], 1)
        self.assertEqual(manifest["runs"][0]["status"], "timed-out")
        self.assertLess(elapsed, 4)

    def test_resume_skips_valid_existing_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jobs_dir = root / "jobs/task-a-baseline-r1"
            (jobs_dir / "trial").mkdir(parents=True)
            (jobs_dir / "trial/result.json").write_text(
                json.dumps({"rewards": {"reward": 1.0}, "error": None})
            )
            failing = root / "fail.sh"
            failing.write_text("#!/bin/sh\nexit 1\n")
            failing.chmod(0o755)
            spec = {
                "schema_version": 1,
                "jobs_root": str(root / "jobs"),
                "max_parallel": 1,
                "bench": str(failing),
                "resume": True,
                "tasks": [
                    {"id": "task-a", "tasks_dir": "unused", "conditions": ["baseline"]}
                ],
            }
            manifest = run(spec)
        self.assertEqual(manifest["skipped_existing"], 1)
        self.assertEqual(manifest["runs"][0]["status"], "skipped-existing")


if __name__ == "__main__":
    unittest.main()
