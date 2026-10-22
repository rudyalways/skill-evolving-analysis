# Evaluation artifact contracts

Keep these artifacts beside the operation that produced them. Every verdict
must be traceable to a run, transcript, output, and expectation.

## manifest.json

```json
{
  "run_id": "run-example",
  "skill": "example-skill",
  "backend": "codex",
  "model": "model-name",
  "generated_at": "2026-10-22T00:00:00Z",
  "executed": true,
  "candidate_sha256": "64 lowercase hex characters",
  "baseline_sha256": "64 lowercase hex characters",
  "held_out_sha256": "64 lowercase hex characters",
  "configurations": ["without_skill", "with_skill"],
  "trials_per_configuration": 3,
  "eval_ids": [1, 2],
  "held_out_eval_ids": [101, 102]
}
```

Write this only after real execution. A plan is not a replay manifest.
Held-out cases live at `workspace/run/replay/held-out-evals.json`, outside the
candidate skill, and must not reuse development prompts or trace IDs.

## grading.json

```json
{
  "expectations": [
    {"text": "Observable requirement", "passed": true, "evidence": "output/file.md:12"}
  ],
  "summary": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0},
  "execution_metrics": {
    "tool_calls": {},
    "total_tool_calls": 0,
    "errors_encountered": 0,
    "output_chars": 0,
    "transcript_chars": 0
  },
  "timing": {"executor_duration_seconds": 0.0, "grader_duration_seconds": 0.0},
  "claims": [
    {"claim": "Claim made by output", "type": "factual", "verified": true, "evidence": "source"}
  ],
  "eval_feedback": {"suggestions": [], "overall": "No material gap found"}
}
```

## comparison.json

```json
{
  "winner": "A",
  "reasoning": "Evidence-based reason",
  "rubric": {
    "A": {"content_score": 5.0, "structure_score": 4.0, "overall_score": 9.0},
    "B": {"content_score": 3.0, "structure_score": 3.0, "overall_score": 6.0}
  },
  "expectation_results": {
    "A": {"passed": 4, "total": 4, "pass_rate": 1.0, "details": []},
    "B": {"passed": 2, "total": 4, "pass_rate": 0.5, "details": []}
  }
}
```

`winner` is `A`, `B`, or `TIE`. The A/B-to-configuration mapping is stored
separately until comparison completes.

## analysis.json

```json
{
  "comparison_summary": {
    "winner": "A",
    "winner_skill": "candidate",
    "loser_skill": "baseline",
    "comparator_reasoning": "Evidence-based reason"
  },
  "winner_strengths": [],
  "loser_weaknesses": [],
  "instruction_following": {
    "winner": {"score": 9, "issues": []},
    "loser": {"score": 6, "issues": []}
  },
  "improvement_suggestions": [
    {
      "priority": "high",
      "category": "instructions",
      "suggestion": "Concrete edit",
      "expected_impact": "Observed failure it should prevent"
    }
  ],
  "transcript_insights": {}
}
```

Suggestion categories are `instructions`, `tools`, `examples`,
`error_handling`, `structure`, and `references`.

## benchmark.json

```json
{
  "metadata": {
    "skill_name": "example-skill",
    "evals_run": [1],
    "runs_per_configuration": 3
  },
  "runs": [
    {
      "eval_id": 1,
      "configuration": "with_skill",
      "split": "held_out",
      "run_number": 1,
      "result": {
        "pass_rate": 1.0,
        "time_seconds": 10.0,
        "tokens": 1000,
        "tool_calls": 4,
        "errors": 0
      },
      "expectations": []
    }
  ],
  "run_summary": {},
  "notes": []
}
```

`configuration` must be exactly `with_skill` or `without_skill`.
`common/skill_evaluation.py aggregate` writes `run_summary`, including means,
population standard deviation, extrema, run counts, errors, and deltas.

## activation-results.json

```json
{
  "results": [
    {"eval_id": 1, "kind": "should_apply", "activated": true},
    {"eval_id": 2, "kind": "should_not_apply", "activated": false}
  ],
  "summary": {}
}
```

Run `common/skill_evaluation.py activation activation-results.json` to write
the confusion matrix, recall, precision, and false-positive rate. Activation
quality is distinct from execution quality: a useful workflow with a vague
description can still be a poor skill.
