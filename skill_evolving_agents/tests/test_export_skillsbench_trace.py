from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.export_skillsbench_trace import export


class ExportSkillsBenchTraceTest(unittest.TestCase):
    def test_appends_structured_objective_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trial = Path(directory) / "trial"
            (trial / "trajectory").mkdir(parents=True)
            (trial / "verifier").mkdir()
            (trial / "trajectory/acp_trajectory.jsonl").write_text(
                json.dumps({"type": "user_message", "text": "task"}) + "\n"
                + json.dumps({
                    "type": "agent_message",
                    "text": "<mounted-skill path=/skills/value-check/SKILL.md>\n---",
                }) + "\n"
            )
            (trial / "result.json").write_text(
                json.dumps(
                    {
                        "rewards": {"reward": 0.0},
                        "skill_mode": "with-skill",
                        "n_tool_calls": 4,
                        "verifier_error": None,
                    }
                )
            )
            (trial / "verifier/ctrf.json").write_text(
                json.dumps(
                    {
                        "results": {
                            "tests": [
                                {
                                    "name": "::test_value",
                                    "status": "failed",
                                    "trace": "E AssertionError: expected null, got raw-token",
                                }
                            ]
                        }
                    }
                )
            )
            (trial / "verifier/test-stdout.txt").write_text("failed output")
            output = Path(directory) / "export.jsonl"
            payload = export(trial, output)
            self.assertEqual(payload["verifier_failures"][0]["test"], "::test_value")
            self.assertEqual(
                payload["verifier_failures"][0]["assertion"],
                "expected null, got raw-token",
            )
            self.assertEqual(payload["activated_skills"], ["value-check"])
            event = json.loads(output.read_text().splitlines()[-1])
            self.assertEqual(event["title"], "skillsbench_objective_verifier")
            self.assertEqual(event["status"], "failed")


if __name__ == "__main__":
    unittest.main()
