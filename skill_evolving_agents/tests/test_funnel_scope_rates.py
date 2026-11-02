from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import run_pipeline as runner


class ScopeRateTest(unittest.TestCase):
    def test_multiple_operations_do_not_exceed_scope_rates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "traces/derived/signals").mkdir(parents=True)
            (workspace / "traces/derived/normalized").mkdir(parents=True)
            (workspace / "run/sig-a").mkdir(parents=True)
            (workspace / "run/config").mkdir(parents=True)

            (workspace / "traces/derived/signals/findings.jsonl").write_text(
                json.dumps({"signal_id": "sig-a"}) + "\n"
            )
            (workspace / "traces/derived/signals/selection-decisions.jsonl").write_text(
                json.dumps({"disposition": "selected"}) + "\n"
            )
            (workspace / "traces/derived/normalized/manifest.json").write_text(
                json.dumps({"turn_count": 1})
            )
            (workspace / "run/sig-a/diagnosis.json").write_text(
                json.dumps(
                    {
                        "skill_capabilities_missing": [
                            {"type": "form/technique", "description": "gap"}
                        ]
                    }
                )
            )
            (workspace / "run/sig-a/label-matching.json").write_text(
                json.dumps(
                    {
                        "matching": {"query_context": "diagnosis+finding"},
                        "clusters": [
                            {
                                "cluster": "sig-a",
                                "labels": [],
                                "skills": [{"skill": "one", "score": 1.0}],
                            }
                        ],
                    }
                )
            )
            (workspace / "run/pipeline-summary.json").write_text(
                json.dumps(
                    {
                        "scopes": [
                            {
                                "scope": "sig-a",
                                "disposition": "change",
                                "operation_count": 2,
                            }
                        ],
                        "operations": [
                            {"op": "create", "accepted": True},
                            {"op": "update", "accepted": True},
                        ],
                    }
                )
            )
            (workspace / "run/config/pipeline-profile.json").write_text(
                json.dumps({"funnel_targets": {}})
            )

            metrics = runner.pipeline_metrics.collect_phase_metrics(workspace)
            rates = metrics["funnel"]["rates"]
            self.assertEqual(rates["proposal_rate"], 1.0)
            self.assertEqual(rates["final_acceptance_rate"], 1.0)
            self.assertEqual(rates["acceptance_given_goal_rate"], 1.0)
            self.assertEqual(rates["actionable_proposal_rate"], 1.0)
            self.assertEqual(rates["proposal_acceptance_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
