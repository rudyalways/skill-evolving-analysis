from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


AGENTS = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


benchmark = load(
    "benchmark_core_test", AGENTS / "evaluation/benchmark_core.py"
)


class BenchmarkCoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = benchmark.load_cases(AGENTS / "evaluation/cases")
        self.profile = json.loads(
            (AGENTS / "profiles/action-oriented-local-service.json").read_text()
        )

    def test_golden_cases_pass_contracts_and_remain_pending_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = benchmark.run_suite(
                self.cases, Path(directory), self.profile
            )
        self.assertEqual(report["overall"]["cases"], 6)
        self.assertEqual(report["overall"]["failed"], 0)
        self.assertEqual(report["overall"]["review_pending"], 6)
        self.assertEqual(report["overall"]["review_approved"], 0)
        self.assertTrue(
            {"create", "update", "merge", "split", "delete"}
            <= {
                operation
                for case in report["cases"]
                for operation in (
                    (case.get("observed") or {}).get("golden") or {}
                ).get("operation_types", [])
            }
        )

    def test_require_reviewed_blocks_unapproved_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = benchmark.run_suite(
                self.cases,
                Path(directory),
                self.profile,
                require_reviewed=True,
            )
        self.assertEqual(report["overall"]["failed"], 6)
        self.assertTrue(
            all(
                any("required approval" in failure for failure in case["failures"])
                for case in report["cases"]
            )
        )

    def test_dashboard_reports_cases_and_review_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = benchmark.run_suite(
                self.cases, Path(directory), self.profile
            )
            dashboard = Path(directory) / "benchmark.html"
            benchmark.render_dashboard(report, dashboard)
            text = dashboard.read_text()
        self.assertIn("Skill evolution benchmark", text)
        self.assertIn("golden-update-retry-guard", text)
        self.assertIn("golden-split-two-jobs", text)
        self.assertIn("Review pending", text)
        self.assertIn("pending", text)


if __name__ == "__main__":
    unittest.main()
