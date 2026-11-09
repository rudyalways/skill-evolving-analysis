from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_pipeline as runner

from common.acceptance_gates import replay_acceptance, resource_change_directories


def _operation(directories: list[str]) -> dict:
    return {
        "op": "update",
        "skills": [
            {
                "skill": "alpha",
                "goal": "add a producer",
                "facet": "workflow",
                "sections": [{"section": "workflow", "goal": "add a producer"}],
                "resource_plan": [],
                "directories": [{"dir": name} for name in directories],
            }
        ],
    }


def _write_changelog(operation_directory: Path, directories: list[str]) -> None:
    operation_directory.mkdir(parents=True, exist_ok=True)
    (operation_directory / "changelog.json").write_text(
        json.dumps({
            "schema_version": 1,
            "changes": [{
                "id": "run:alpha:1:alpha",
                "skill": "alpha",
                "operation": "update",
                "run_id": "run",
                "finding_id": "alpha",
                "op_index": 1,
                "date": "2026-11-08",
                "sections": ["workflow"],
                "directories": directories,
                "before_sha256": "a" * 64,
                "after_sha256": "b" * 64,
                "status": "accepted",
            }],
        })
    )


class ReplayAcceptanceGateTest(unittest.TestCase):
    def test_section_only_change_does_not_require_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            operation_directory = workspace / "run/sig/ops/1"
            _write_changelog(operation_directory, [])
            report = replay_acceptance(
                workspace,
                operation_directory=operation_directory,
                op=_operation([]),
                verification={},
            )
            self.assertFalse(report["required"])
            self.assertEqual(report["decision"], "not-required")

    def test_resource_change_with_passing_replay_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            operation_directory = workspace / "run/sig/ops/1"
            _write_changelog(operation_directory, ["scripts"])
            report = replay_acceptance(
                workspace,
                operation_directory=operation_directory,
                op=_operation(["scripts"]),
                verification={
                    "feedback": {
                        "replay": {
                            "available": True,
                            "status": "pass",
                            "kind": "paired_skill_eval",
                        }
                    }
                },
            )
            self.assertTrue(report["required"])
            self.assertEqual(report["decision"], "accept")
            self.assertEqual(report["resource_directories"], ["scripts"])

    def test_resource_change_with_failing_replay_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            operation_directory = workspace / "run/sig/ops/1"
            _write_changelog(operation_directory, ["references"])
            report = replay_acceptance(
                workspace,
                operation_directory=operation_directory,
                op=_operation(["references"]),
                verification={
                    "feedback": {
                        "replay": {
                            "available": True,
                            "status": "fail",
                            "kind": "paired_skill_eval",
                        }
                    }
                },
            )
            self.assertEqual(report["decision"], "reject")
            self.assertEqual(report["reason"], "replay-failed")

    def test_fixture_without_executed_replay_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            fixture = workspace / "evaluation/held_out/alpha.json"
            fixture.parent.mkdir(parents=True)
            fixture.write_text("{}")
            operation_directory = workspace / "run/sig/ops/1"
            _write_changelog(operation_directory, ["evals"])
            report = replay_acceptance(
                workspace,
                operation_directory=operation_directory,
                op=_operation(["evals"]),
                verification={
                    "feedback": {
                        "replay": {
                            "available": False,
                            "status": "not_run",
                            "reason": "not configured",
                        }
                    }
                },
            )
            self.assertEqual(report["decision"], "reject")
            self.assertEqual(
                report["reason"], "replay-required-fixture-available"
            )

    def test_missing_fixture_stays_provisional(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            operation_directory = workspace / "run/sig/ops/1"
            _write_changelog(operation_directory, ["assets"])
            report = replay_acceptance(
                workspace,
                operation_directory=operation_directory,
                op=_operation(["assets"]),
                verification={},
            )
            self.assertEqual(report["decision"], "accept-provisional")
            self.assertEqual(report["reason"], "no-replay-fixture")

    def test_resource_plan_fallback_ignores_unused_kinds(self) -> None:
        op = {
            "op": "create",
            "skills": [
                {
                    "skill": "alpha",
                    "resource_plan": [
                        {"resource": "scripts", "decision": "use"},
                        {"resource": "assets", "decision": "skip"},
                        {"resource": "evals", "decision": "use"},
                    ],
                }
            ],
        }
        self.assertEqual(
            resource_change_directories(op), ["evals", "scripts"]
        )

    def test_nested_resource_directory_maps_to_its_family(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            operation_directory = workspace / "run/sig/ops/1"
            _write_changelog(operation_directory, ["scripts/checks"])
            self.assertEqual(
                resource_change_directories(
                    _operation(["scripts"]), operation_directory
                ),
                ["scripts"],
            )


class PublicationReplayGateTest(unittest.TestCase):
    def test_publication_rejects_resource_change_with_unexecuted_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            worker = root / "worker"
            operation = worker / "run/sig/ops/1"
            operation.mkdir(parents=True)
            _write_changelog(operation, ["scripts"])
            (operation / "verification.json").write_text(
                json.dumps({
                    "feedback": {
                        "replay": {
                            "available": False,
                            "status": "not_run",
                            "reason": "evaluator not configured",
                        }
                    }
                })
            )
            fixture = workspace / "evaluation/held_out/alpha.json"
            fixture.parent.mkdir(parents=True)
            fixture.write_text("{}")
            result = {
                "cluster": "sig",
                "op_index": 1,
                "worker": worker,
                "op": _operation(["scripts"]),
                "affected": {"alpha"},
                "suffixes": [],
                "judge_action": "pass",
            }
            with patch.object(runner, "_archive_operation_records"):
                runner.publish_operation_result(workspace, result)
            publication = json.loads(
                (workspace / "run/sig/ops/1/publication.json").read_text()
            )
            self.assertFalse(publication["accepted"])
            self.assertTrue(
                publication["reason"].startswith("replay-required:")
            )
            self.assertEqual(publication["outcome"], "replay_required")
            gate = json.loads(
                (workspace / "run/sig/ops/1/replay-acceptance-gate.json").read_text()
            )
            self.assertEqual(
                gate["reason"], "replay-required-fixture-available"
            )


if __name__ == "__main__":
    unittest.main()
