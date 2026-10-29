from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "01_preprocessing_agent/trace_mining/methodology.py"
spec = importlib.util.spec_from_file_location("trace_methodology", MODULE)
methodology = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(methodology)


class SleepRetryTest(unittest.TestCase):
    def test_deliberate_sleeps_are_not_retry_oscillation(self) -> None:
        events = [
            {
                "sequence": index,
                "phase": "execute",
                "tool": "sleep",
                "arguments_preview": '{"duration_ms":60000}',
                "result_preview": "Wall time: 60.0037 seconds\nSleep completed.",
                "status": "completed",
                "targets": [],
            }
            for index in (1, 2, 3, 4)
        ]
        self.assertEqual(methodology._analyze_retries(events, {}), [])

    def test_repeated_non_sleep_action_is_still_classified(self) -> None:
        events = [
            {
                "sequence": index,
                "phase": "execute",
                "tool": "exec",
                "arguments_preview": '{"cmd":"status"}',
                "result_preview": "unchanged",
                "status": "completed",
                "targets": [],
            }
            for index in (1, 2)
        ]
        records = methodology._analyze_retries(events, {})
        self.assertTrue(records)
        self.assertFalse(records[0]["necessary"])


if __name__ == "__main__":
    unittest.main()
