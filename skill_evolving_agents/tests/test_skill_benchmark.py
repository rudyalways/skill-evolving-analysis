from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.skill_benchmark.golden import GoldenSkill
from evaluation.skill_benchmark.runner import run_benchmark
from evaluation.skill_benchmark.tasks import generate_tasks


AGENTS = Path(__file__).resolve().parents[1]
SKILL_ROOT = AGENTS / "evaluation/golden_skills/report-publishing"


def _page(**overrides):
    page = {
        "slug": "quarterly-reliability-review-report",
        "title": "Quarterly reliability review report",
        "status": "published",
        "metadata": {
            "description": "A report for engineering leadership with findings, methods, sources, and next actions."
        },
        "body": (
            "## Summary\nA report.\n## Method\nReviewed data.\n"
            "## Findings\n- error budget burn\n- incident count\n- top remediation\n"
            "## Sources\n- https://example.com/source\n"
        ),
        "media": [{"url": "/media/cover.png", "alt": "cover"}],
    }
    page.update(overrides)
    return page


class SkillBenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = GoldenSkill.load(SKILL_ROOT)

    def test_golden_skill_loads(self) -> None:
        self.assertEqual(self.skill.skill_id, "report-publishing")
        self.assertEqual(self.skill.review["status"], "pending")
        self.assertEqual(self.skill.source["origin"], "synthetic")

    def test_verifier_accepts_complete_page(self) -> None:
        task = {
            "required_points": ["error budget burn", "incident count", "top remediation"]
        }
        page = _page()
        failures = self.skill.verify(page, task, [page])
        self.assertEqual(failures, [])

    def test_verifier_rejects_missing_image_and_section(self) -> None:
        task = {"required_points": ["error budget burn"]}
        page = _page(media=[], body="## Summary\nOnly a summary.")
        failures = self.skill.verify(page, task, [page])
        self.assertIn("cover_image", failures)
        self.assertIn("sections", failures)
        self.assertIn("source_link", failures)

    def test_generator_covers_variants(self) -> None:
        tasks = generate_tasks(10)
        self.assertEqual(len(tasks), 10)
        self.assertTrue(any(not task.auth for task in tasks))
        self.assertTrue(any(task.faults for task in tasks))
        self.assertTrue(any(task.seed_slug for task in tasks))
        self.assertTrue(any(task.seed_title for task in tasks))
        self.assertTrue(any(task.suggested_title and len(task.suggested_title) > 60 for task in tasks))

    def test_reference_agent_completes_all_tasks(self) -> None:
        report = run_benchmark(SKILL_ROOT, count=10)
        self.assertEqual(report["overall"]["failed"], 0)
        self.assertEqual(report["overall"]["passed"], 10)
        self.assertEqual(report["overall"]["expected_refusals"], 1)
        self.assertEqual(report["overall"]["refusals_passed"], 1)
        self.assertGreaterEqual(report["overall"]["tool_calls"], 50)

    def test_auth_boundary_is_refused_without_tool_calls(self) -> None:
        report = run_benchmark(SKILL_ROOT, count=4)
        refusal = next(
            trace for trace in report["tasks"] if trace["expected"] == "refusal"
        )
        self.assertTrue(refusal["passed"])
        self.assertTrue(refusal["agent_refused"])
        self.assertEqual(refusal["tool_call_count"], 0)
        self.assertIsNone(refusal["page"])

    def test_trace_is_multi_turn_and_tool_backed(self) -> None:
        report = run_benchmark(SKILL_ROOT, count=1)
        trace = report["tasks"][0]
        user_messages = [
            message for message in trace["messages"] if message["role"] == "user"
        ]
        self.assertGreaterEqual(len(user_messages), 2)
        self.assertGreaterEqual(trace["tool_call_count"], 6)
        self.assertTrue(trace["verification"]["passed"])
        self.assertTrue(any(
            call["tool"] == "cms_publish" for call in trace["tool_calls"]
        ))

    def test_incomplete_agent_recovers_after_feedback(self) -> None:
        report = run_benchmark(SKILL_ROOT, count=10, agent_name="incomplete")
        self.assertEqual(report["overall"]["failed"], 0)
        self.assertGreaterEqual(report["overall"]["repaired"], 8)
        first = next(
            trace for trace in report["tasks"] if trace["expected"] == "published"
        )
        self.assertTrue(first["repaired"])
        self.assertGreaterEqual(first["turns"], 4)

    def test_report_is_json_serializable(self) -> None:
        report = run_benchmark(SKILL_ROOT, count=2)
        encoded = json.dumps(report)
        self.assertIn("report-publishing", encoded)


if __name__ == "__main__":
    unittest.main()
