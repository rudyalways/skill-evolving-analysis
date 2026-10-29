# SkillsBench methodology evaluation

Use held-out tasks that were not used to mine or author the evaluated skill.
For each task, run at least three trials in both matched conditions:

```bash
bench eval run --tasks-dir tasks/<task-id> --agent <agent> --model <model> \
  --skill-mode no-skill

bench eval run --tasks-dir tasks/<task-id> --agent <agent> --model <model> \
  --skill-mode with-skill --skills-dir <evolved-skills>
```

Convert run results into one JSONL row per task, trial, and condition. Required
fields are `task_id`, `trial`, `condition`, and `passed`. Optional fields are
`tokens`, `tool_calls`, `repeated_errors`, `skill_context_tokens`,
`candidate_count`, `candidate_correct`, `false_positive_creations`, and
`candidate_novelty`.

Set `ablation` to `full` for the complete miner. Repeat the same paired cells
with one strategy disabled at a time and name that removal, for example
`without_failure_recovery`. Summarize all matched cells with:

```bash
python evaluation/skillsbench_methodology_eval.py results.jsonl \
  --out methodology-report.json
```

The report uses task-macro pass rate, paired efficiency deltas, mining
precision, false-positive creations, novelty, context size, and pass-rate loss
for each ablation. Unpaired cells are reported but excluded from comparisons.

# Configuration research

`optimize_config.py` provides the bounded offline optimization control plane.
It validates the knob and metric registries, generates reproducible constrained
grids, and evaluates recorded results using hard safety constraints before
Pareto-style cost and quality objectives.

It does not promote production configuration. An eligible offline candidate is
authorized only to enter shadow evaluation.

Available search algorithms are bounded grid, seeded random, wide-and-deep,
and persistent UCB/MCTS. Reviewed trial outcomes update a Beta success
posterior and reward exponential moving average for each knob/value choice in
`workspace/optimization.sqlite`.

# Deterministic funnel benchmark

`funnel_benchmark.py` measures the cheap boundaries before hosted agent calls:

```text
raw trace -> normalized turns -> findings -> selection -> evolution-gate
admission -> resource decisions -> exact-finding idempotency
```

It also checks the semantic category policy with synthetic embedding scores,
the deterministic single-session creation policy, and resource-usefulness
scoring with observed use. Cases are synthetic and privacy-safe. Workspaces are
created under a temporary directory unless `--keep-workspaces` is supplied.

```bash
python3 evaluation/funnel_benchmark.py --out /tmp/funnel-scorecard.json
```

`funnel_cases.json` has labeled calibration and held-out cases. The runner
reports pass rate by split and case kind, funnel boundary counts, and one
failure reason per unmet expectation. It also replays every selected generic
finding through `previously_applied_finding_skills`; resource findings must
remain replayable only when their authored effect exists.

The 2026-10-28 reference run on `origin/main` passed 20/23 cases (11/12
calibration, 9/11 held-out). All three failures were cross-session supporting
resources: a reference, starter, or delegated prompt used once in each of
three sessions produced no finding because repetition was grouped by session.
The corrected detector groups by resource fingerprint across sessions, so the
same case set passes 23/23 and the selected findings flow through the
evolution gate and idempotent replay checks.

A benchmark pass is evidence about deterministic routing and labeled
expectations, not proof that a hosted mutation is useful. The cross-session
fix above was diagnosed from both calibration and held-out failures, so the
23/23 result is regression coverage rather than an unbiased held-out estimate;
add unseen cases before treating it as a generalization claim. The runner does
not start the embedding service or a hosted agent: it measures the semantic
decision policy with labeled scores and the deterministic boundaries that
decide whether those paid stages should run.

# Stage-addressable golden benchmark

`benchmark_core.py` is the reusable stage runner. It separates:

1. stage contract validation,
2. targeted behavioral labels,
3. golden diagnosis and action review,
4. optional end-to-end composition.

Cases live under `evaluation/cases/` and are addressed by `stage`, not by a
fixed workflow position. Move or add workflow stages without rewriting the
stage cases. Golden actions are compiled into valid Goal documents and checked
against `common/pipeline_contracts.py`; invalid labels fail before review.

Every case carries a review state. The default is `pending`; use
`--require-reviewed` to make unapproved cases fail. The generated HTML dashboard
shows pass/fail, review state, failure reasons, and each case's golden diagnosis
and action.

See `evaluation/cases/README.md` for the case schema, review workflow, and
commands.
