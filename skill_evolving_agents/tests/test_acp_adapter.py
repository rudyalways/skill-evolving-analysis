import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = (
    ROOT / "01_preprocessing_agent/trace_mining/source_adapters.py"
)
SPEC = importlib.util.spec_from_file_location("source_adapters", ADAPTER_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AcpAdapterTests(unittest.TestCase):
    def test_trajectory_is_normalized_as_one_tool_evidenced_turn(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        trace = Path(temporary.name) / "trajectory.jsonl"
        rows = [
        {"type": "user_message", "text": "repair the plan"},
        {
            "type": "tool_call",
            "tool_call_id": "call-1",
            "kind": "execute",
            "title": "execute",
            "status": "completed",
            "content": [
                {
                    "type": "content",
                    "content": {"type": "text", "text": "done"},
                }
            ],
        },
        {"type": "agent_message", "text": "finished"},
        ]
        trace.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

        self.assertTrue(MODULE.detects_acp(rows[0]))
        session, counters = MODULE.parse_acp(trace)
        turn = next(iter(session["turns"].values()))

        self.assertEqual(counters["raw_records"], 3)
        self.assertTrue(turn["timestamp"])
        self.assertEqual(turn["status"], "completed")
        self.assertEqual(turn["user"][0]["text"], "repair the plan")
        self.assertEqual(turn["assistant_final"], ["finished"])
        self.assertEqual(
            turn["tools"],
            [
                {
                    "call_id": "call-1",
                    "sequence": 1,
                    "tool": "execute",
                    "arguments": {},
                    "result": "done",
                    "status": "completed",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
