import tempfile
import unittest
import ast
from pathlib import Path

from evaluation.patch_benchflow_deepagents_skills import (
    AGENT_NEW,
    HELPER,
    NEW,
    OLD,
    STREAM_NEW,
    patch,
)


class BenchFlowDeepAgentsSkillPatchTests(unittest.TestCase):
    def test_patch_is_idempotent_and_adds_skill_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            shim = Path(tmp) / "shim.py"
            shim.write_text(
                "from pathlib import Path\n"
                + OLD
                + "def run_deep_agent(\n"
                + "    pass\n"
                + "    agent = build_deep_agent(model_id, cwd, env)\n"
                + '    payload = {"messages": [{"role": "user", "content": instruction}]},\n'
            )
            self.assertEqual(patch(shim), "patched")
            patched = shim.read_text()
            self.assertIn("/skills", patched)
            self.assertIn("SKILL.md", patched)
            self.assertIn("solution repository", patched)
            self.assertIn(HELPER, patched)
            self.assertIn(AGENT_NEW, patched)
            self.assertIn(STREAM_NEW, patched)
            ast.parse(
                "def probe(model_id, cwd, env, instruction, session_id):\n"
                + AGENT_NEW
                + "    return effective_instruction\n"
            )
            self.assertEqual(patch(shim), "already-patched")
            self.assertEqual(shim.read_text().count(NEW), 1)


if __name__ == "__main__":
    unittest.main()
