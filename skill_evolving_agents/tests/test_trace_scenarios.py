from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


AGENTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "trace_signals_scenarios",
    AGENTS / "01_preprocessing_agent/trace_mining/signals.py",
)
signals = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(signals)

spec = importlib.util.spec_from_file_location(
    "trace_methodology_scenarios",
    AGENTS / "01_preprocessing_agent/trace_mining/methodology.py",
)
methodology = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(methodology)


def finding(detector: str, lesson: dict) -> dict:
    return {
        "signal_id": "sig-test",
        "detector": detector,
        "session_id": "session-a",
        "confidence": 0.9,
        "features": {"lesson": lesson, "scenario": signals._scenario_for({"detector": detector})},
    }


class ScenarioAndReflectionTest(unittest.TestCase):
    def test_reflection_cues_cover_user_phrases(self) -> None:
        text = "No, wait. Let me think. Actually, try another approach."
        markers = [
            name for name, pattern in methodology.REFLECTION_PATTERNS.items()
            if pattern.search(text)
        ]
        self.assertIn("reconsider", markers)
        self.assertIn("pivot", markers)

    def test_reflection_bank_extracts_functional_reflection(self) -> None:
        row = finding(
            "method-functional-reflection",
            {
                "kind": "functional_reflection",
                "marker_categories": ["reconsider"],
                "cue_phrases": ["wait"],
                "reflection_quote": "Wait, that did not work.",
                "rule": "Change the action after a failed observation.",
            },
        )
        entries = signals.reflection_bank_entries([row])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["scenario"], "reasoning_pivot")
        self.assertEqual(entries[0]["marker_categories"], ["reconsider"])
        self.assertEqual(entries[0]["reflection_quote"], "Wait, that did not work.")

    def test_reflection_bank_includes_verified_recovery(self) -> None:
        row = finding(
            "method-failure-recovery",
            {
                "kind": "failure_recovery",
                "verified_recovery": True,
                "failure_signature": "f",
                "rule": "Repair and revalidate.",
            },
        )
        entries = signals.reflection_bank_entries([row])
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["verified_recovery"])
        self.assertEqual(entries[0]["scenario"], "failure_recovery")

    def test_reasoning_bank_contains_lessons(self) -> None:
        row = finding(
            "method-phase-workflow",
            {
                "kind": "ordered_workflow",
                "rule": "Preserve the observed phase ordering.",
            },
        )
        entries = signals.reasoning_bank_entries([row])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["scenario"], "verified_workflow")
        self.assertEqual(entries[0]["lesson_kind"], "ordered_workflow")

    def test_reflection_bank_uses_evidence_cues(self) -> None:
        row = finding(
            "method-phase-workflow",
            {
                "kind": "ordered_workflow",
                "rule": "Preserve the observed ordering.",
            },
        )
        row["evidence"] = [
            {"quote": "Wait, the previous approach failed. Let me think."}
        ]
        entries = signals.reflection_bank_entries([row])
        self.assertEqual(len(entries), 1)
        self.assertIn("reconsider", entries[0]["marker_categories"])

    def test_reflection_bank_ignores_tool_output_cues(self) -> None:
        row = finding(
            "method-critical-path",
            {
                "kind": "critical_path",
                "rule": "Choose the critical path.",
            },
        )
        row["evidence"] = [
            {
                "quote": json.dumps(
                    {
                        "assistant_observations": [],
                        "events": [
                            {"result_preview": "wait, verify this output"}
                        ],
                    }
                )
            }
        ]
        entries = signals.reflection_bank_entries([row])
        self.assertEqual(entries, [])

    def test_scenario_mapping_covers_core_detectors(self) -> None:
        expected = {
            "method-failure-recovery": "failure_recovery",
            "method-functional-reflection": "reasoning_pivot",
            "method-phase-workflow": "verified_workflow",
            "repeated-instructions": "repeated_instruction",
            "resource-references-opportunity": "reference_reuse",
        }
        for detector, scenario in expected.items():
            self.assertEqual(signals._scenario_for({"detector": detector}), scenario)


if __name__ == "__main__":
    unittest.main()
