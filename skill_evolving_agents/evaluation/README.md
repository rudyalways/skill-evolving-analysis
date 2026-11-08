# SkillsBench methodology evaluation

## Reproducible pipeline and benchmark statistics

Pipeline runs and benchmark trials are different experimental units and must
not be mixed into one success rate. Aggregate pipeline funnel, operation,
resource, and avoided-agent-call measurements with:

```bash
python evaluation/pipeline_stats.py workspace/runs/<run> [workspace/runs/<run> ...] \
  --out workspace/reports/pipeline-stats.json
```

For matched no-skill and evolved-skill jobs, build a paired report with strict
pass rates, raw/partial reward lift, Wilson intervals, exact discordant-pair test, regressions, per-domain
coverage, tool calls, and agent time:

```bash
python evaluation/paired_benchmark_report.py \
  --baseline workspace/skillbench/<baseline-job> [workspace/skillbench/<baseline-job-2> ...] \
  --treatment workspace/skillbench/<treatment-job> [workspace/skillbench/<treatment-job-2> ...] \
  --benchmark skillsbench@1.1 --cohort heldout-v1 \
  --exposure selective-read --domains evaluation/heldout-domains.json \
  --out workspace/reports/heldout-v1.json
```

The reporter retains repeated trials instead of collapsing them by task. Run
at least three matched trials per cell before promotion. A mounted skill is not
an activated skill: `selective-read` requires an audited applicable SKILL.md
read. Full prompt injection is a useful stress test, but its context and cost
overhead must be reported and it is not the preferred production treatment.

Do not inject one broad skill (or the entire inventory) into every treatment
task. Build a frozen, task-specific bundle with the same low-cost embedding
recall used by the pipeline, then run each task against its own bundle:

```bash
python evaluation/benchmark_skill_router.py \
  --policy evaluation/router-policy.json \
  --skills-root workspace/candidate_skills \
  --feedback-database workspace/optimization.sqlite \
  --task task-a=path/to/task-a/prompts.json \
  --task task-b=path/to/task-b/prompts.json \
  --out-root workspace/skillbench/heldout-v1-bundles \
  --report workspace/skillbench/heldout-v1-selection.json
```

The router recalls five candidates with Qwen embeddings but exposes at most one.
It keeps embedding order, calibrates the best match with immutable paired
benchmark feedback, and abstains when its adjusted score is below threshold or
its raw semantic margin is under `0.04` without positive prior lift. Negative
feedback may suppress a candidate but never promotes an unrelated runner-up.
An asymmetric low-cost intent gate also rejects repair-only methods for clean
creation requests; uncertain intent combinations remain eligible. Thresholds,
recall width, document size, and feedback weights are frozen in
`evaluation/router-policy.json` and its digest is included in every report.
The selection report freezes the inventory hash, embedding revision, raw and
adjusted scores, semantic margin, feedback-event digest and formula, thresholds,
cache hits/misses, abstention reasons, and each materialized bundle hash. This makes
selection cost and false-positive exposure part of the benchmark evidence.
Use the same selection policy for every held-out cell; do not hand-pick skills
after seeing verifier outcomes.

### Generalization and future cross-benchmark gate

Freeze trace hashes, generated skill hashes, task IDs, domains, benchmark
version, model, harness, budgets, and seeds before evaluation. Keep mining,
calibration, and held-out IDs disjoint. Quarantine environment/download errors
rather than scoring them as model failures. Require multi-domain coverage,
negative controls, per-domain regressions, confidence intervals, paired tests,
and efficiency deltas; do not promote from aggregate accuracy alone.

Other benchmarks should use an adapter that emits the same normalized trial
fields: `benchmark`, `benchmark_version`, `task_id`, `domain`, `trial`,
`condition`, `exposure`, `passed`, `tool_calls`, `agent_seconds`, plus optional
token/cost and activation evidence. Cross-benchmark holdout means the adapter,
tasks, and scoring verifier are unseen during pipeline tuning. Success on a
small SkillsBench slice is transfer evidence, not proof of no overfitting.

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

Do not infer skill use from `skill_mode: with-skill`, a mounted `/skills`
directory, or the harness's `n_skill_invocations` field. Some generic harnesses
mount skills without advertising them to the model, and shell-based reads are
not necessarily counted as native skill invocations. Audit each with-skill ACP
trajectory before admitting it to a paired comparison:

```bash
python evaluation/skillsbench_skill_usage.py path/to/acp_trajectory.jsonl \
  --require-activation --out path/to/skill-activation.json
```

The audit distinguishes full prompt injection from an observed `SKILL.md`
read, resource discovery from use, and explicit script execution failures from
successful execution. Do not count a mount listing as resource use.

After a paired benchmark, join the treatment's observed activation/resource
evidence to the baseline/treatment reward and tool-call deltas, and optionally
persist immutable benchmark feedback in the policy database:

```bash
python evaluation/benchmark_resource_feedback.py \
  --baseline path/to/baseline-job --treatment path/to/treatment-job \
  --run-id pipeline-run-id --database workspace/optimization.sqlite \
  --out path/to/resource-feedback.json
```

These events are post-publication runtime evidence. Authoring logs alone must
not be promoted into script-success, resource-use, or benchmark-lift signals.
Feedback is keyed by the exact skill-tree SHA-256 rather than merely the skill
name. An evolved version receives a fresh evaluation prior while unchanged
versions retain their evidence; unversioned legacy events remain auditable but
do not calibrate current routing.

A valid treatment run must contain an observed read of at least one applicable
`SKILL.md`. Resource use is reported separately. A failed activation audit is
harness/instrumentation failure, not evidence that the evolved skill had no
effect; fix discovery and rerun the cell.

The tested BenchFlow DeepAgents release mounts custom skills at `/skills` but
does not advertise that external mount to the agent. Apply the idempotent
compatibility patch before treatment trials and re-run it after BenchFlow
upgrades (it fails loudly on an unknown shim layout):

```bash
python evaluation/patch_benchflow_deepagents_skills.py \
  /path/to/site-packages/benchflow/agents/deepagents_acp_shim.py
```

The patch instructs DeepAgents to discover and read skills through the shell,
because its virtual filesystem tool cannot see `/skills`. The trajectory audit,
not successful patch execution, remains the admission criterion.

Reject answer-contaminated trials before pairing. Public-network tasks can leak
their benchmark name, oracle, or solution repository through search:

```bash
python evaluation/benchmark_trial_validity.py path/to/acp_trajectory.jsonl \
  --task-id task-a --require-valid --out path/to/trial-validity.json
```

Dependency installation and generic technical documentation remain allowed;
task-specific answer discovery excludes the trial rather than counting it as a
pass or failure.

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

Every case carries a review state and a label grade. Agent-authored cases start
as `draft` and are not treated as human-need ground truth. Two independent
reviewers with domain-expert and user-advocate roles are required for `gold`;
`--require-gold` enforces that grade, while `--require-reviewed` enforces at
least one approval. The generated HTML dashboard shows pass/fail, review state,
label grade, failure reasons, and each case's proposed diagnosis and action.

See `evaluation/cases/README.md` for the case schema, review workflow, and
commands.

## Source selection

Benchmark source and design notes are maintained privately until they are
privacy-reviewed for publication. Public benchmark cases must cite their
sources and record review provenance.

## Golden-skill benchmark slice

The first executable golden-skill benchmark lives under
`evaluation/skill_benchmark/` with the draft bundle at
`evaluation/golden_skills/report-publishing/`. Each golden skill is a directory
with `SKILL.md`, `skill.json`, frozen `evals/tasks.json`, environment notes,
simulator personas, optional scripts, and references. The runner drives a
multi-turn user simulator, executes a sandbox CMS, and verifies the published
page with the skill's verification section.

See `evaluation/skill_benchmark/README.md`.
