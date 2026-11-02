from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_pipeline as runner


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, queries, documents, top_k):
        self.queries = list(queries)
        self.documents = dict(documents)
        return {
            "results": [{"matches": []} for _ in queries],
            "model_revision": "fake",
            "index_revision": "fake",
        }


class RecallImprovementTest(unittest.TestCase):
    def test_finding_context_is_included_in_recall_query(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            skill = root / "chart-helper"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "Nested category chart compatibility. "
                "DataLabel does not accept tx. Use c:tx/c:rich and showVal.\n"
            )
            diagnosis = {
                "skill_capabilities_missing": [
                    {
                        "type": "form/technique",
                        "description": "nested category chart label compatibility",
                        "reasoning": "DataLabel tx is unsupported",
                    }
                ]
            }
            finding = {
                "detector": "method-failure-recovery",
                "features": {
                    "lesson": {
                        "kind": "failure_recovery",
                        "rule": "Use c:tx/c:rich and enable showVal.",
                    }
                },
                "evidence": [{"quote": "GraphicalProperties.ln received dict"}],
            }
            provider = FakeEmbeddingProvider()
            with patch.object(runner, "ACTIVE_EMBEDDING_PROVIDER", provider):
                result = runner.embedding_recall(
                    diagnosis,
                    {"skills_metadata": [{"skill": "chart-helper"}]},
                    ["chart-helper"],
                    {
                        "skills_root": str(root),
                        "document_max_chars": 1200,
                        "top_k": 5,
                        "minimum_score": 0.3,
                        "algorithm": "test",
                    },
                    finding,
                )
            self.assertEqual(result["matching"]["query_context"], "diagnosis+finding")
            self.assertEqual(result["matching"]["hybrid_lexical"], True)
            self.assertIn("finding_context", provider.queries[0])
            self.assertIn("c:tx/c:rich", provider.queries[0])
            self.assertIn(
                "chart-helper",
                [row["skill"] for row in result["clusters"][0]["skills"]],
            )
            self.assertEqual(
                next(
                    row for row in result["clusters"][0]["skills"]
                    if row["skill"] == "chart-helper"
                )["retrieval"],
                "lexical",
            )

    def test_section_aware_document_keeps_late_sections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            skill = root / "long-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "x" * 1500
                + "\n## Chart compatibility\n"
                + "Use c:tx/c:rich and showVal for nested category labels.\n"
            )
            provider = FakeEmbeddingProvider()
            with patch.object(runner, "ACTIVE_EMBEDDING_PROVIDER", provider):
                result = runner.embedding_recall(
                    {"skill_capabilities_missing": []},
                    {"skills_metadata": [{"skill": "long-skill"}]},
                    ["long-skill"],
                    {
                        "skills_root": str(root),
                        "document_max_chars": 800,
                        "top_k": 5,
                        "minimum_score": 0.3,
                        "algorithm": "test",
                    },
                    None,
                )
            self.assertIn(
                "Chart compatibility",
                provider.documents["long-skill"],
            )
            self.assertEqual(
                result["matching"]["document_strategy"],
                "head+section-samples",
            )

    def test_truncated_documents_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            skill = root / "long-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("x" * 2000)
            provider = FakeEmbeddingProvider()
            with patch.object(runner, "ACTIVE_EMBEDDING_PROVIDER", provider):
                result = runner.embedding_recall(
                    {"skill_capabilities_missing": []},
                    {"skills_metadata": [{"skill": "long-skill"}]},
                    ["long-skill"],
                    {
                        "skills_root": str(root),
                        "document_max_chars": 1200,
                        "top_k": 5,
                        "minimum_score": 0.3,
                        "algorithm": "test",
                    },
                    None,
                )
            self.assertEqual(
                result["matching"]["truncated_documents"], ["long-skill"]
            )


if __name__ == "__main__":
    unittest.main()
