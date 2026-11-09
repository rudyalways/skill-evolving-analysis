from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from common.run_identity import (
    is_stamped,
    resolve_run_workspace,
    session_slug,
    validate_run_id,
)
import run_pipeline as runner

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline_contracts import valid_goal  # noqa: E402


class RunIdentityTest(unittest.TestCase):
    def test_accepts_plain_and_timestamped_ids(self) -> None:
        for value in (
            "run-codex",
            "run_codex.v2",
            "run@2026-11-08T20:52",
            "run@2026-11-08T20:52:33",
            "run@2026-11-08T20:52-2",
            "run@2026-11-08T20:52:33-2",
        ):
            self.assertEqual(validate_run_id(value), value)
        self.assertTrue(is_stamped("run@2026-11-08T20:52"))
        self.assertTrue(is_stamped("run@2026-11-08T20:52:33-2"))
        self.assertFalse(is_stamped("run"))

    def test_rejects_traversal_absolute_and_malformed_stamps(self) -> None:
        for value in (
            "../escape",
            "/absolute",
            "a/b",
            "a\\b",
            "",
            "@2026-11-08T20:52",
            "run@bad",
            "run@2026-13-40T99:99",
        ):
            with self.assertRaises(ValueError):
                validate_run_id(value)

    def test_require_stamped_rejects_plain_id(self) -> None:
        with self.assertRaises(ValueError):
            validate_run_id("run", require_stamped=True)

    def test_resolution_stays_inside_the_runs_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "runs"
            root.mkdir()
            resolved = resolve_run_workspace(
                root, "run@2026-11-08T20:52"
            )
            self.assertEqual(resolved, (root.resolve() / "run@2026-11-08T20:52"))
            with self.assertRaises(ValueError):
                resolve_run_workspace(root, "../outside")

    def test_session_slug_removes_stamp_punctuation(self) -> None:
        self.assertEqual(
            session_slug("run@2026-11-08T20:52:33"),
            "run-2026-11-08T20-52-33",
        )

    def test_parse_args_auto_resumes_stamped_run(self) -> None:
        with patch.object(
            sys, "argv", ["run_pipeline.py", "run@2026-11-08T20:52"]
        ):
            args = runner.parse_args()
        self.assertEqual(args.resume_from, "auto")
        with patch.object(
            sys, "argv", ["run_pipeline.py", "run@2026-11-08T20:52", "--from", "judge"]
        ):
            args = runner.parse_args()
        self.assertEqual(args.resume_from, "judge")

    def _workspace(self, root: Path) -> Path:
        workspace = root / "runs/run@2026-11-08T20:52"
        scope = workspace / "run/sig/ops/1"
        scope.mkdir(parents=True)
        (scope / "evolve-goal.json").write_text(
            json.dumps(valid_goal())
        )
        (scope / "changelog.json").write_text(
            json.dumps({
                "schema_version": 1,
                "changes": [],
                "phase_markers": [],
                "phase_events": [],
            })
        )
        return workspace

    def test_resume_phase_prefers_the_earliest_saved_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self._workspace(Path(directory))
            self.assertEqual(runner.resume_phase(workspace), "optimize")

    def test_resume_phase_returns_none_without_saved_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "run@2026-11-08T20:52"
            (workspace / "run").mkdir(parents=True)
            self.assertIsNone(runner.resume_phase(workspace))


if __name__ == "__main__":
    unittest.main()
