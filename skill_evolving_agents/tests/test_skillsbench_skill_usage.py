import json
import tempfile
import unittest
from pathlib import Path

from evaluation.skillsbench_skill_usage import audit


class SkillsBenchSkillUsageTests(unittest.TestCase):
    def test_detects_skill_and_script_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            events = [
                {
                    "type": "tool_call",
                    "content": "---\nname: repair\ndescription: Repair outputs.\n---\n\nInstructions",
                },
                {"type": "tool_call", "content": "python /skills/repair/scripts/check.py output.json"},
            ]
            trace.write_text("\n".join(json.dumps(event) for event in events))
            report = audit(trace)
        self.assertTrue(report["activated"])
        self.assertEqual(report["skills"][0]["name"], "repair")
        self.assertEqual(report["skills"][0]["resources_observed"], ["scripts/check.py"])
        self.assertEqual(report["skills"][0]["resources_discovered"], ["scripts/check.py"])

    def test_listing_discovers_but_does_not_use_script(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            events = [
                {
                    "type": "tool_call",
                    "kind": "read",
                    "title": "ls",
                    "content": "['/skills/repair/scripts/check.py']",
                }
            ]
            trace.write_text("\n".join(json.dumps(event) for event in events))
            report = audit(trace)
        self.assertFalse(report["activated"])
        self.assertEqual(report["skills"][0]["resources_observed"], [])
        self.assertEqual(
            report["skills"][0]["resources_discovered"], ["scripts/check.py"]
        )

    def test_mount_listing_without_skill_read_is_not_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            trace.write_text(json.dumps({"content": "/skills/repair"}))
            report = audit(trace)
        self.assertFalse(report["activated"])
        self.assertEqual(report["skills"], [])

    def test_failed_skill_read_is_not_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            trace.write_text(
                json.dumps(
                    {
                        "type": "tool_call",
                        "content": "Error: File '/skills/repair/SKILL.md' not found",
                    }
                )
            )
            report = audit(trace)
        self.assertFalse(report["activated"])
        self.assertEqual(report["skills"], [])

    def test_full_prompt_injection_is_distinguished_from_file_read(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            trace.write_text(
                json.dumps(
                    {
                        "type": "user_message",
                        "text": "---\nname: repair\ndescription: Repair outputs.\n---\n",
                    }
                )
            )
            report = audit(trace)
        self.assertTrue(report["activated"])
        self.assertEqual(report["activation_mode"], "injected")
        self.assertFalse(report["skill_md_read_observed"])
        self.assertTrue(report["skill_md_injected"])

    def test_atif_document_steps_are_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "atif.json"
            trace.write_text(
                json.dumps(
                    {
                        "schema_version": "ATIF-v1.7",
                        "steps": [
                            {
                                "source": "agent",
                                "message": (
                                    "<mounted-skill path=/skills/repair/SKILL.md>\n"
                                    "---\nname: repair\ndescription: Repair outputs.\n---\n"
                                    "</mounted-skill>"
                                ),
                            },
                            {
                                "type": "tool_call",
                                "kind": "execute",
                                "title": "execute",
                                "content": (
                                    "python /skills/repair/scripts/check.py output.json\n"
                                    "[Command succeeded with exit code 0]"
                                ),
                            },
                        ],
                    }
                )
            )
            report = audit(trace)
        self.assertTrue(report["activated"])
        self.assertEqual(report["activation_mode"], "injected")
        self.assertEqual(
            report["skills"][0]["script_execution"]["succeeded"],
            ["scripts/check.py"],
        )

    def test_reports_failed_script_execution_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            trace.write_text(
                json.dumps(
                    {
                        "type": "tool_call",
                        "kind": "execute",
                        "title": "execute",
                        "content": (
                            "python /skills/repair/scripts/check.py\n"
                            "Permission denied\n[Command failed with exit code 1]"
                        ),
                    }
                )
            )
            report = audit(trace)
        execution = report["skills"][0]["script_execution"]
        self.assertEqual(execution["attempted"], ["scripts/check.py"])
        self.assertEqual(execution["succeeded"], [])
        self.assertEqual(execution["failed"], ["scripts/check.py"])


if __name__ == "__main__":
    unittest.main()
