from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evaluation.benchmark_skill_router import select_task_skills, tree_hash
from common.task_intent import compatibility, skill_scope, task_intent

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS = REPO_ROOT / "workspace/candidate_skills"

PPTX_TASK = """Help me detect all dangling paper titles in the slides
`/root/Awesome-Agent-Papers.pptx`, change the font type to Arial, font size to
16, adjust the box width, put the title at the bottom center of each page,
create a new slide at the end with a Reference title, and save the processed
.pptx to `/root/Awesome-Agent-Papers_processed.pptx`."""

ADA_TASK = """# Task
You are given a standardized 2D toilet-room CAD plan. Extract the original room
layout from `/root/input/ada_bath_input.dxf`, identify the plan-view ADA-derived
accessibility violations, and produce a minimally invasive repaired CAD layout.
Use `/root/input/ada_rules.json`. All coordinates and dimensions use inches."""

THREEJS_TASK = """You are a nice Three.js specialist. The file is located at
`/root/data/object.js` and contains a single `createScene()` function. Parse
this Three.js file to find the part-level structure, then save each mesh to
`/root/output/part_meshes` and `/root/output/links` as OBJ files."""

PPTX_RANKING = [
    ("batch-doc-variant-publishing", 0.476191),
    ("architectural-dxf-extraction", 0.411475),
    ("lark-doc-navigation-reference", 0.357474),
    ("audit-project-ui", 0.328147),
    ("verify-artifact-against-ground-truth", 0.319636),
]
ADA_RANKING = [
    ("ada-plan-view-accessibility", 0.700222),
    ("architectural-dxf-extraction", 0.583687),
    ("artifact-conformance-preflight", 0.417239),
    ("repair-budget-checkpoint", 0.393747),
    ("audit-project-ui", 0.364920),
]
THREEJS_RANKING = [
    ("threejs-source-mesh-export", 0.643914),
    ("artifact-conformance-preflight", 0.493244),
    ("architectural-dxf-extraction", 0.417671),
    ("verify-artifact-against-ground-truth", 0.309677),
    ("ada-plan-view-accessibility", 0.294855),
]


class FrozenRankingProvider:
    """Return the recorded v46 ranking for each task, without embeddings."""

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.documents: dict[str, str] = {}

    def search(self, queries, documents, top_k):
        self.queries = list(queries)
        self.documents = documents
        results = []
        for query in queries:
            if "dangling paper titles" in query:
                ranking = PPTX_RANKING
            elif "toilet-room" in query or "ADA" in query:
                ranking = ADA_RANKING
            else:
                ranking = THREEJS_RANKING
            results.append({
                "matches": [
                    {"id": skill, "score": score} for skill, score in ranking
                ]
            })
        return {"model": "frozen-v46", "model_revision": "r1", "results": results}


class TaskIntentCompatibilityTest(unittest.TestCase):
    def test_recorded_pptx_regression_abstains(self) -> None:
        report = select_task_skills(
            tasks={"pptx-reference-formatting": PPTX_TASK},
            skills_root=SKILLS,
            provider=FrozenRankingProvider(),
            top_k=1,
            recall_k=5,
            minimum_score=0.35,
            minimum_margin=0.04,
            document_max_chars=1200,
        )
        row = report["tasks"]["pptx-reference-formatting"]
        self.assertEqual(row["ranked"][0]["skill"], "batch-doc-variant-publishing")
        self.assertEqual(row["selected"], [])
        self.assertIn(
            "intent-mismatch:object-format-excluded",
            row["abstention_reasons"],
        )

    def test_domain_tasks_keep_their_skills(self) -> None:
        report = select_task_skills(
            tasks={
                "ada-bathroom-plan-repair": ADA_TASK,
                "threejs-to-obj": THREEJS_TASK,
                "pptx-reference-formatting": PPTX_TASK,
            },
            skills_root=SKILLS,
            provider=FrozenRankingProvider(),
            top_k=1,
            recall_k=5,
            minimum_score=0.35,
            minimum_margin=0.04,
            document_max_chars=1200,
        )
        ada = report["tasks"]["ada-bathroom-plan-repair"]
        three = report["tasks"]["threejs-to-obj"]
        pptx = report["tasks"]["pptx-reference-formatting"]
        self.assertEqual(
            [row["skill"] for row in ada["selected"]],
            ["ada-plan-view-accessibility"],
        )
        self.assertEqual(
            [row["skill"] for row in three["selected"]],
            ["threejs-source-mesh-export"],
        )
        self.assertEqual(pptx["selected"], [])

    def test_gate_generalizes_from_scope_not_task_names(self) -> None:
        xml_batch_skill = (
            "Publish several localized or copied document variants from local "
            "XML drafts. Do not use for non-XML formats."
        )
        compatible, reason = compatibility(
            "Format one spreadsheet workbook and save it.", xml_batch_skill
        )
        self.assertFalse(compatible)
        self.assertEqual(reason, "object-format-excluded")

        compatible, reason = compatibility(
            "Produce a three.js createScene export to OBJ part_meshes.",
            "Export native `.js` or `.mjs` Three.js modules to OBJ.",
        )
        self.assertTrue(compatible)
        self.assertIsNone(reason)

    def test_scope_extraction_reads_negative_scope_below_embedding_cutoff(self) -> None:
        skill_text = (SKILLS / "batch-doc-variant-publishing/SKILL.md").read_text()
        self.assertGreater(len(skill_text), 1200)
        scope = skill_scope(skill_text)
        self.assertEqual(scope["exclusive_formats"], ["xml"])
        self.assertTrue(scope["multi_variant"])
        intent = task_intent(PPTX_TASK)
        self.assertEqual(intent["formats"], ["pptx"])
        self.assertFalse(intent["multi_variant"])

    def test_negative_scope_is_exclusion_not_ownership(self) -> None:
        skill_text = (
            SKILLS / "lark-doc-navigation-reference/SKILL.md"
        ).read_text()
        scope = skill_scope(skill_text)
        self.assertIn("pptx", scope["excluded_formats"])
        self.assertNotIn("pptx", scope["exclusive_formats"])
        compatible, reason = compatibility(PPTX_TASK, skill_text)
        self.assertFalse(compatible)
        self.assertEqual(reason, "object-format-excluded")

    def test_task_scoped_regression_feedback_abstains(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skills = Path(directory) / "skills"
            for name in ("alpha", "beta"):
                skill = skills / name
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: test\n---\n"
                )
            versioned = f"alpha@{tree_hash(skills / 'alpha')}"
            report = select_task_skills(
                tasks={"task-a": "do alpha work"},
                skills_root=skills,
                provider=_SingleMatchProvider(),
                top_k=1,
                recall_k=2,
                minimum_score=0.35,
                document_max_chars=1200,
                feedback_calibration={
                    "skills": {},
                    "task_skills": {
                        f"task-a|{versioned}": {
                            "observations": 1,
                            "mean_reward_delta": -1.0,
                            "regression_rate": 1.0,
                            "no_benefit_rate": 1.0,
                            "score_adjustment": 0.0,
                        }
                    },
                },
            )
            row = report["tasks"]["task-a"]
            self.assertEqual(row["selected"], [])
            self.assertIn("feedback-regression", row["abstention_reasons"])

    def test_unrelated_task_feedback_does_not_suppress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skills = Path(directory) / "skills"
            for name in ("alpha", "beta"):
                skill = skills / name
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: test\n---\n"
                )
            versioned = f"alpha@{tree_hash(skills / 'alpha')}"
            report = select_task_skills(
                tasks={"task-b": "do alpha work"},
                skills_root=skills,
                provider=_SingleMatchProvider(),
                top_k=1,
                recall_k=2,
                minimum_score=0.35,
                document_max_chars=1200,
                feedback_calibration={
                    "skills": {},
                    "task_skills": {
                        f"task-a|{versioned}": {
                            "observations": 1,
                            "mean_reward_delta": -1.0,
                            "regression_rate": 1.0,
                            "no_benefit_rate": 1.0,
                            "score_adjustment": 0.0,
                        }
                    },
                },
            )
            row = report["tasks"]["task-b"]
            self.assertEqual([item["skill"] for item in row["selected"]], ["alpha"])


class _SingleMatchProvider:
    def search(self, queries, documents, top_k):
        return {
            "model": "fake",
            "results": [
                {"matches": [
                    {"id": "alpha", "score": 0.8},
                    {"id": "beta", "score": 0.2},
                ]}
            ],
        }


if __name__ == "__main__":
    unittest.main()
