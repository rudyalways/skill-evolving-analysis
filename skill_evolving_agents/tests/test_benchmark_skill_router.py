from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from evaluation.benchmark_skill_router import (
    fallback_embedding_runtime,
    intent_compatibility,
    load_feedback_calibration,
    materialize,
    parse_tasks,
    select_task_skills,
    tree_hash,
)


class FakeProvider:
    def search(self, queries, documents, top_k):
        self.queries = queries
        self.documents = documents
        self.top_k = top_k
        return {
            "model": "fake",
            "model_revision": "r1",
            "index_revision": "i1",
            "service_ms": 4.2,
            "cache": {"document_hits": 1, "document_misses": 1},
            "results": [
                {"matches": [{"id": "alpha", "score": 0.8}, {"id": "beta", "score": 0.2}]}
            ],
        }


class AmbiguousProvider(FakeProvider):
    def search(self, queries, documents, top_k):
        response = super().search(queries, documents, top_k)
        response["results"][0]["matches"] = [
            {"id": "alpha", "score": 0.4},
            {"id": "beta", "score": 0.38},
        ]
        return response


class BenchmarkSkillRouterTest(unittest.TestCase):
    def test_embedding_fallback_is_in_process_and_drops_model_fields(self) -> None:
        runtime = {
            "transport": "local_process",
            "backend": "sentence-transformers",
            "model": "qwen",
            "revision": "r1",
            "device": "cpu",
            "query_instruction": "query",
            "endpoint": "http://127.0.0.1:9999",
            "dimensions": 1024,
        }
        fallback = fallback_embedding_runtime(runtime)
        self.assertEqual(fallback["transport"], "in_process")
        self.assertEqual(fallback["backend"], "hashing-reference")
        for field in ("model", "revision", "device", "query_instruction", "endpoint"):
            self.assertNotIn(field, fallback)

    def test_creation_task_rejects_repair_only_skill(self) -> None:
        compatible, reason = intent_compatibility(
            "Create a new workbook with four pivot tables.",
            "Repair failing aggregate cells. Localizes the failing assertion.",
        )
        self.assertFalse(compatible)
        self.assertEqual(reason, "create-vs-repair")
        compatible, reason = intent_compatibility(
            "Recover missing data and create a repaired workbook.",
            "Repair failing aggregate cells. Localizes the failing assertion.",
        )
        self.assertTrue(compatible)
        self.assertIsNone(reason)

    def test_select_and_materialize_thresholded_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills = root / "skills"
            for name in ("alpha", "beta"):
                skill = skills / name
                (skill / "scripts").mkdir(parents=True)
                (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test\n---\n")
                (skill / "scripts" / "run.py").write_text("print('ok')\n")
            report = select_task_skills(
                tasks={"task-a": "do alpha work"},
                skills_root=skills,
                provider=FakeProvider(),
                top_k=2,
                minimum_score=0.35,
                document_max_chars=1200,
            )
            self.assertEqual(report["tasks"]["task-a"]["selected"], [{"skill": "alpha", "score": 0.8}])
            self.assertEqual(report["embedding_cache"]["document_hits"], 1)
            materialize(report, skills, root / "bundles")
            self.assertTrue((root / "bundles/task-a/alpha/scripts/run.py").is_file())
            self.assertFalse((root / "bundles/task-a/beta").exists())
            self.assertTrue(report["tasks"]["task-a"]["bundle_hash"].startswith("sha256:"))

    def test_parse_tasks_accepts_benchflow_prompt_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prompt = Path(directory) / "prompts.json"
            prompt.write_text(json.dumps(["hello task"]))
            self.assertEqual(parse_tasks([f"task-a={prompt}"]), {"task-a": "hello task"})

    def test_parse_tasks_accepts_plain_benchmark_task_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prompt = Path(directory) / "task.md"
            prompt.write_text("# Task\n\nCreate and verify the artifact.\n")
            self.assertEqual(
                parse_tasks([f"task-a={prompt}"]),
                {"task-a": "# Task\n\nCreate and verify the artifact."},
            )

    def test_parse_tasks_accepts_acp_trajectory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            trajectory = Path(directory) / "acp_trajectory.jsonl"
            trajectory.write_text(
                json.dumps({"type": "user_message", "text": "trajectory task"}) + "\n"
            )
            self.assertEqual(
                parse_tasks([f"task-a={trajectory}"]),
                {"task-a": "trajectory task"},
            )

    def test_feedback_calibration_suppresses_costly_no_benefit_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "optimization.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "CREATE TABLE feedback_events (feedback_id TEXT, run_id TEXT, "
                    "decision_id TEXT, source TEXT, signal TEXT, value_json TEXT, "
                    "confidence REAL, supersedes TEXT, created_at TEXT)"
                )
                connection.execute(
                    "INSERT INTO feedback_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "f1", "run", None, "benchmark", "skill-runtime-outcome",
                        json.dumps({
                            "skill": "alpha",
                            "skill_md_read": True,
                            "reward_delta": 0,
                            "baseline_tool_calls": 10,
                            "treatment_tool_calls": 15,
                        }),
                        1.0, None, "now",
                    ),
                )
            calibration = load_feedback_calibration(database)
            self.assertEqual(calibration["events"], 1)
            self.assertAlmostEqual(
                calibration["skills"]["alpha@unversioned"]["score_adjustment"], -0.25
            )

            skills = root / "skills"
            for name in ("alpha", "beta"):
                skill = skills / name
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: test\n---\n"
                )
            report = select_task_skills(
                tasks={"task-a": "do alpha work"},
                skills_root=skills,
                provider=FakeProvider(),
                top_k=1,
                recall_k=2,
                minimum_score=0.7,
                document_max_chars=1200,
                feedback_calibration={
                    **calibration,
                    "skills": {
                        f"alpha@{tree_hash(skills / 'alpha')}":
                            calibration["skills"]["alpha@unversioned"]
                    },
                },
            )
            row = report["tasks"]["task-a"]
            self.assertEqual(row["ranked"][0]["raw_score"], 0.8)
            self.assertEqual(row["ranked"][0]["score"], 0.55)
            self.assertEqual(row["selected"], [])

    def test_feedback_calibration_ignores_discovery_only_exposure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "optimization.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "CREATE TABLE feedback_events (feedback_id TEXT, run_id TEXT, "
                    "decision_id TEXT, source TEXT, signal TEXT, value_json TEXT, "
                    "confidence REAL, supersedes TEXT, created_at TEXT)"
                )
                connection.execute(
                    "INSERT INTO feedback_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "f1", "run", None, "benchmark", "skill-runtime-outcome",
                        json.dumps({
                            "skill": "alpha",
                            "skill_md_read": False,
                            "skill_md_injected": False,
                            "reward_delta": 0,
                            "baseline_tool_calls": 10,
                            "treatment_tool_calls": 50,
                        }),
                        1.0, None, "now",
                    ),
                )
            calibration = load_feedback_calibration(database)
            self.assertEqual(calibration["skills"], {})

    def test_feedback_calibration_keeps_exact_task_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "optimization.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "CREATE TABLE feedback_events (feedback_id TEXT, run_id TEXT, "
                    "decision_id TEXT, source TEXT, signal TEXT, value_json TEXT, "
                    "confidence REAL, supersedes TEXT, created_at TEXT)"
                )
                connection.execute(
                    "INSERT INTO feedback_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "f1", "run", None, "benchmark", "skill-runtime-outcome",
                        json.dumps({
                            "task_id": "dialogue-parser",
                            "skill": "alpha",
                            "skill_hash": "sha256:v1",
                            "skill_md_read": True,
                            "reward_delta": 0.2,
                            "baseline_tool_calls": 20,
                            "treatment_tool_calls": 15,
                        }),
                        1.0, None, "now",
                    ),
                )
            calibration = load_feedback_calibration(database)
            scoped = calibration["task_skills"][
                "dialogue-parser|alpha@sha256:v1"
            ]
            self.assertEqual(scoped["observations"], 1)
            self.assertEqual(scoped["mean_reward_delta"], 0.2)

    def test_small_semantic_margin_abstains_without_positive_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills = root / "skills"
            for name in ("alpha", "beta"):
                skill = skills / name
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: test\n---\n"
                )
            report = select_task_skills(
                tasks={"task-a": "ambiguous"},
                skills_root=skills,
                provider=AmbiguousProvider(),
                top_k=1,
                recall_k=2,
                minimum_score=0.35,
                minimum_margin=0.04,
                document_max_chars=1200,
            )
            row = report["tasks"]["task-a"]
            self.assertEqual(row["selected"], [])
            self.assertEqual(row["raw_margin"], 0.02)
            self.assertIn("insufficient-semantic-margin", row["abstention_reasons"])

    def test_feedback_from_old_skill_hash_does_not_penalize_new_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills = root / "skills"
            for name in ("alpha", "beta"):
                skill = skills / name
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: test\n---\n"
                )
            report = select_task_skills(
                tasks={"task-a": "do alpha work"},
                skills_root=skills,
                provider=FakeProvider(),
                top_k=1,
                recall_k=2,
                minimum_score=0.7,
                document_max_chars=1200,
                feedback_calibration={
                    "skills": {
                        "alpha@sha256:old": {"score_adjustment": -0.8}
                    }
                },
            )
            self.assertEqual(report["tasks"]["task-a"]["selected"][0]["skill"], "alpha")
            self.assertNotIn("feedback", report["tasks"]["task-a"]["ranked"][0])


if __name__ == "__main__":
    unittest.main()
