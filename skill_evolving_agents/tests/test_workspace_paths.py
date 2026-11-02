from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common import pipeline_metrics
import run_pipeline as runner


class WorkspacePathTest(unittest.TestCase):
    def test_metrics_path_stays_inside_a_temporary_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.assertEqual(
                pipeline_metrics.shared_metrics_path(workspace).resolve(),
                (Path(directory) / "metrics.sqlite").resolve(),
            )

    def test_metrics_path_uses_workspace_container_for_run_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            run = root / "runs" / "run-a"
            run.mkdir(parents=True)
            self.assertEqual(
                pipeline_metrics.shared_metrics_path(run).resolve(),
                (root / "metrics.sqlite").resolve(),
            )

    def test_operation_coverage_stays_inside_a_temporary_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "run").mkdir()
            path = runner.update_operation_coverage(workspace)
            self.assertEqual(
                path.resolve(),
                (workspace / "operation-coverage.json").resolve(),
            )
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
