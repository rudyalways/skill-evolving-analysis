from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


AGENTS = Path(__file__).resolve().parents[1]
MODULE = AGENTS / "01_preprocessing_agent/trace_mining/methodology.py"
spec = importlib.util.spec_from_file_location("trace_methodology_issue1", MODULE)
methodology = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(methodology)
signals = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location(
        "trace_signals_issue1",
        AGENTS / "01_preprocessing_agent/trace_mining/signals.py",
    )
)
signals_spec = importlib.util.spec_from_file_location(
    "trace_signals_issue1",
    AGENTS / "01_preprocessing_agent/trace_mining/signals.py",
)
assert signals_spec.loader is not None
signals_spec.loader.exec_module(signals)


def event(
    sequence: int,
    status: str,
    phase: str,
    tool: str,
    arguments: str,
    target: str = "script.py",
):
    return {
        "sequence": sequence,
        "status": status,
        "phase": phase,
        "tool": tool,
        "arguments_preview": arguments,
        "result_preview": "failed" if status == "failed" else "ok",
        "targets": [target],
    }


def trajectory(events: list[dict]) -> dict:
    return {
        "trace_id": "codex:session-a:turn-a",
        "session_id": "session-a",
        "task": {"text": "Fix chart compatibility"},
        "outcome": {"status": "completed", "error": None},
        "events": events,
        "phases": [],
    }


class FailureRecoveryIssueTest(unittest.TestCase):
    def test_patch_alone_is_not_recovery(self) -> None:
        rows = [
            event(1, "failed", "execute", "exec", "run chart.py"),
            event(2, "completed", "modify", "edit", "add LineProperties import"),
        ]
        self.assertEqual(methodology._failure_recovery(trajectory(rows), "turn"), [])

    def test_repair_then_revalidation_is_the_chain(self) -> None:
        rows = [
            event(1, "failed", "execute", "exec", "run chart.py"),
            event(2, "completed", "modify", "edit", "add LineProperties import"),
            event(3, "completed", "modify", "edit", "fix DataLabel argument"),
            event(4, "completed", "verify", "exec", "run chart.py"),
        ]
        findings = methodology._failure_recovery(trajectory(rows), "turn")
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(
            finding["features"]["event_sequences"], [1, 2, 3, 4]
        )
        self.assertEqual(finding["features"]["lesson"]["kind"], "failure_recovery")
        self.assertTrue(finding["features"]["lesson"]["verified_recovery"])
        provenance = finding["features"]["provenance"]
        self.assertEqual(provenance["session_status"], "completed")
        self.assertEqual(provenance["local_verification"], "passed")
        self.assertEqual(provenance["external_evaluation"], "unknown")
        self.assertIsNone(provenance["task_accepted"])
        self.assertEqual(provenance["success_basis"], "local_verification")

    def test_external_task_failure_is_not_session_success(self) -> None:
        rows = [
            event(1, "failed", "execute", "exec", "run chart.py"),
            event(2, "completed", "modify", "edit", "fix chart.py"),
            event(3, "completed", "verify", "exec", "run chart.py"),
        ]
        state = trajectory(rows)
        state["outcome"] = {
            "status": "completed",
            "error": None,
            "external_evaluation": {
                "status": "failed",
                "source": "officeval",
            },
        }
        finding = methodology._failure_recovery(state, "turn")[0]
        provenance = finding["features"]["provenance"]
        self.assertTrue(provenance["session_completed"])
        self.assertEqual(provenance["local_verification"], "passed")
        self.assertEqual(provenance["external_evaluation"], "failed")
        self.assertFalse(provenance["task_accepted"])
        self.assertEqual(
            provenance["external_evaluation_source"], "officeval"
        )

    def test_unrelated_repair_is_not_part_of_the_chain(self) -> None:
        rows = [
            event(1, "failed", "execute", "exec", "run chart.py", "chart.py"),
            event(2, "completed", "modify", "edit", "fix unrelated.py", "unrelated.py"),
            event(3, "completed", "modify", "edit", "fix chart.py", "chart.py"),
            event(4, "completed", "verify", "exec", "run chart.py", "chart.py"),
        ]
        findings = methodology._failure_recovery(trajectory(rows), "turn")
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0]["features"]["event_sequences"], [1, 3, 4]
        )
        self.assertTrue(findings[0]["features"]["lesson"]["failure_signature"])
        self.assertTrue(findings[0]["features"]["lesson"]["verification_signature"])

    def test_multiple_independent_failure_chains_are_kept(self) -> None:
        rows = [
            event(1, "failed", "execute", "exec", "run chart.py"),
            event(2, "completed", "modify", "edit", "fix chart.py"),
            event(3, "completed", "verify", "exec", "run chart.py"),
            event(4, "failed", "execute", "exec", "run export.py"),
            event(5, "completed", "modify", "edit", "fix export.py"),
            event(6, "completed", "verify", "exec", "run export.py"),
        ]
        findings = methodology._failure_recovery(trajectory(rows), "turn")
        self.assertEqual(len(findings), 2)
        self.assertEqual(
            [row["features"]["event_sequences"] for row in findings],
            [[1, 2, 3], [4, 5, 6]],
        )

    def test_same_learning_target_is_deduplicated(self) -> None:
        config = json.loads((AGENTS / "common/preprocessing-config.json").read_text())
        detector_config = config["signals"]
        detector_config["_methodology"] = config["methodology"]
        base = {
            "detector": "method-failure-recovery",
            "severity": "high",
            "confidence": 0.9,
            "routing": "skill_evolution",
            "session_id": "session-a",
            "trace_ids": ["codex:session-a:turn-a"],
            "features": {
                "candidate_source": "methodology",
                "kind": "failure_recovery",
                "method_fingerprint": "same",
                "event_sequences": [1, 2, 3],
                "quality": {"value": 0.5},
            },
            "evidence": [{"trace_id": "codex:session-a:turn-a"}],
        }
        first = {**base, "signal_id": "sig-a"}
        second = {**base, "signal_id": "sig-b"}
        selected, decisions = signals._select_findings(
            [first, second], detector_config
        )
        self.assertEqual([row["signal_id"] for row in selected], ["sig-a"])
        self.assertTrue(any(row["disposition"] == "deduplicated" for row in decisions))

    def test_larger_same_target_candidate_replaces_smaller(self) -> None:
        config = json.loads((AGENTS / "common/preprocessing-config.json").read_text())
        detector_config = config["signals"]
        detector_config["_methodology"] = config["methodology"]
        common = {
            "detector": "method-failure-recovery",
            "severity": "high",
            "confidence": 0.9,
            "routing": "skill_evolution",
            "session_id": "session-a",
            "trace_ids": ["codex:session-a:turn-a"],
            "evidence": [{"trace_id": "codex:session-a:turn-a"}],
            "features": {
                "candidate_source": "methodology",
                "kind": "failure_recovery",
                "method_fingerprint": "same",
                "quality": {"value": 0.5},
            },
        }
        small = {
            **common,
            "signal_id": "sig-a",
            "features": {**common["features"], "event_sequences": [1, 2]},
        }
        large = {
            **common,
            "signal_id": "sig-b",
            "features": {**common["features"], "event_sequences": [1, 2, 3, 4]},
        }
        selected, decisions = signals._select_findings(
            [small, large], detector_config
        )
        self.assertEqual([row["signal_id"] for row in selected], ["sig-b"])
        superseded = next(
            row for row in decisions if row["finding_id"] == "sig-a"
        )
        self.assertEqual(superseded["reason"], "superseded-by-larger-evidence")

    def test_different_learning_targets_are_not_deduplicated(self) -> None:
        config = json.loads((AGENTS / "common/preprocessing-config.json").read_text())
        detector_config = config["signals"]
        detector_config["_methodology"] = config["methodology"]
        common = {
            "severity": "high",
            "confidence": 0.9,
            "routing": "skill_evolution",
            "session_id": "session-a",
            "trace_ids": ["codex:session-a:turn-a"],
            "evidence": [{"trace_id": "codex:session-a:turn-a"}],
        }
        failure = {
            **common,
            "signal_id": "sig-a",
            "detector": "method-failure-recovery",
            "features": {
                "candidate_source": "methodology",
                "kind": "failure_recovery",
                "method_fingerprint": "failure",
                "event_sequences": [7, 8],
                "quality": {"value": 0.5},
            },
        }
        workflow = {
            **common,
            "signal_id": "sig-b",
            "detector": "method-phase-workflow",
            "features": {
                "candidate_source": "methodology",
                "kind": "ordered_workflow",
                "method_fingerprint": "workflow",
                "event_sequences": list(range(1, 28)),
                "quality": {"value": 0.5},
            },
        }
        selected, decisions = signals._select_findings(
            [failure, workflow], detector_config
        )
        self.assertEqual({row["signal_id"] for row in selected}, {"sig-a", "sig-b"})
        self.assertFalse(any(row["disposition"] == "deduplicated" for row in decisions))


if __name__ == "__main__":
    unittest.main()
