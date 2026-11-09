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

Policy `v4` adds an offline object/action compatibility gate on top of the
create-vs-repair check. The gate reads the task's artifact family
(presentation, workbook, DXF/CAD plan, Three.js module, XML draft, and so on)
and action family (inspect, transform, create, save, publish), then rejects a
skill that explicitly scopes itself to a disjoint family, requires a batch or
multi-variant action the task does not request, or requires a publisher action
for a single-artifact transformation. It reads the full `SKILL.md`, not the
truncated embedding document, so negative scope such as `Do not use for non-XML
formats` is visible. The gate only causes abstention; it never promotes another
candidate. Task-scoped benchmark feedback with a confirmed negative reward
delta now also abstains explicitly (`feedback-regression`), with
`feedback_min_observations` frozen in the policy. Task-scoped events are kept
out of the global skill prior: a single costly task can suppress that task/skill
pair but cannot silently suppress the skill across unrelated tasks.

The confirmed held-out regression that motivated this gate:
`pptx-reference-formatting` passed with no skill in `30` tool calls but failed
with router-selected `batch-doc-variant-publishing` in `46` calls. The pair now
abstains from both intent evidence (presentation request vs XML document
variants) and calibrated task-scoped feedback, while `threejs-to-obj` still
selects `threejs-source-mesh-export` and `ada-bathroom-plan-repair` still
selects `ada-plan-view-accessibility`.

### Executable leverage and strict trial budgets

`evaluation/executable_leverage.py` scores paired treatment evidence on a
five-stage funnel:

```text
resource discovered -> opened -> executed -> succeeded -> reduced tool calls
```

Discovery-only listings, reads without execution, failed commands, and
successful commands that do not reduce paired tool calls do not count as
executable leverage. The feedback tool records the claim
(`discovered-only`, `opened-only`, `executed-not-succeeded`,
`succeeded-no-reduction`, or `executable-leverage`) and the aggregate stage
rates. Inspect one trial directly with:

```bash
python evaluation/executable_leverage.py path/to/acp_trajectory.jsonl \
  --baseline-tool-calls 30 --treatment-tool-calls 22
```

`evaluation/trial-budgets.json` defines hard wall-time, tool-call, and cost
ceilings. `paired_benchmark_report.py` and `benchmark_resource_feedback.py`
apply them with strict `>` semantics and emit the explicit
`efficiency_failure` outcome. A pass that exceeds a budget is recorded as an
efficiency failure and excluded from the outcome pass rate; raw reward/pass
fields are retained alongside the outcome fields for audit. An
efficiency-exhausted side is excluded from benchmark feedback so budget failure
is not misread as skill-quality evidence. Override the limits with `--budgets`.

### Parallel held-out cohort runner

`evaluation/heldout_cohort_runner.py` executes a frozen cohort spec as matched
baseline/treatment repetitions with a bounded worker pool and an auditable
manifest (exact command, exit code, duration, jobs directory). The cohort is
declared before outcomes are seen; tasks may opt into baseline-only conditions,
and treatment always uses its own frozen bundle. This removes sequential
one-job-at-a-time back-and-forth from the loop.

```bash
python evaluation/heldout_cohort_runner.py --spec cohort.json --out manifest.json
python evaluation/heldout_cohort_runner.py --spec cohort.json --out manifest.json --dry-run
```

### Time and cost profiles

`evaluation/benchmark_controller.py` turns a requested wall-clock budget and
cost tier into a concrete cohort plan: task count, conditions, repetitions,
parallelism, per-trial budgets, and a worst-case cost cap. It writes a frozen
cohort spec; `--execute` hands it to the parallel runner with a hard wall-clock
cap and resume support.

| Profile | Typical plan | Default budgets |
|---|---|---|
| `smoke-15m` | 2 selected tasks, 4 trials, 2 workers | 300s / 60 calls / `$0.50` per trial |
| `quick-1h` | 6 selected tasks, 12 trials, 4 workers | 600s / 100 calls / `$1.00` |
| `standard-3h` | 16 tasks (selected treatment + abstained baseline), 22 trials, 6 workers | 900s / 120 calls / `$2.00` |
| `deep-1d` | up to 16 tasks, 3 reps per condition, 96 trials, 8 workers | 1200s / 180 calls / `$3.00` |

Cost tiers `low`, `standard`, and `high` cap trials, parallelism, repetitions,
per-trial budgets, and worst-case spend. Profiles and estimates live in
`evaluation/benchmark-profiles.json`.

```bash
python evaluation/benchmark_controller.py \
  --time-budget smoke-15m --cost-tier standard \
  --out workspace/reports/smoke-plan.json

python evaluation/benchmark_controller.py \
  --time-budget smoke-15m --cost-tier standard --execute
```

The runner enforces the wall-clock cap with a process-group kill, skips
completed trials with `resume`, and records `timed_out` / `stopped_by_wall_clock`
separately from model failures.

### Held-out iteration controller

`evaluation/heldout_iteration.py` converts a completed paired bench into a
repeatable next-round plan. It joins paired pass/reward/tool-call evidence with
trial validity, activation audit, and executable-leverage claims, then emits
typed gaps (`regression`, `router_false_positive`, `efficiency_failure`,
`activation_missing`, `no_executable_leverage`, and others). Instrumentation
gaps block the next paid round; quality gaps become the authoring work items.
`baseline_drift`, `baseline_efficiency_failure`, and `task_budget_infeasible`
are instrumentation gates:
a no-skill regression, an over-budget baseline, or a task whose failing
baseline already exceeds the hard budget cannot be attributed to a skill. Prose-only skills that reduce calls without scripts are reported as
`methodology-leverage` and are not counted as missed executable leverage.

```bash
python evaluation/heldout_iteration.py \
  --baseline workspace/skillbench/<baseline-job> \
  --treatment workspace/skillbench/<treatment-job> \
  --benchmark skillsbench@1.1 --cohort heldout-v4 \
  --selection-report workspace/skillbench/<router-report>.json \
  --out workspace/reports/<round>.json
```

The controller is read-only and never starts a paid run.

### Replay-required acceptance

`common/acceptance_gates.py` blocks acceptance of a resource-changing
operation (`scripts`, `references`, `assets`, `agents`, or `evals`) when a
behavioral replay is available but did not pass, or when a replay fixture
exists and no replay was executed. With neither a fixture nor a replay,
acceptance remains explicitly provisional. The publication records
`outcome: replay_required` and the gate artifact, so structural-only acceptance
can no longer be mistaken for behavioral evidence.


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

Use `portfolio` for the default search. It combines isolated wide probes,
posterior-guided deep search, persistent MCTS, and seeded random exploration,
then removes duplicates and selects a diverse batch. Do not optimize directly
on the final held-out cohort:

```bash
python evaluation/optimize_config.py search --algorithm portfolio \
  --knob recall.minimum_score --knob evolution.minimum_confidence \
  --knob edit.min_priority --count 16 --seed 20261109 \
  --database workspace/optimization.sqlite \
  --output workspace/search/portfolio.json
```

Every paired observation used for pipeline search must be labeled `train`,
`validation`, or `holdout`. Generalization scoring learns only from validation;
the sealed holdout is reported as a final gate and is never back-propagated to
MCTS or knob posteriors:

```bash
python evaluation/optimize_config.py generalize \
  --observations workspace/search/paired-observations.json \
  --output workspace/search/generalization-decision.json
```

After a candidate has complete validation observations, update its persistent
search posterior with the validation-only reward:

```bash
python evaluation/optimize_config.py generalize \
  --observations workspace/search/paired-observations.json \
  --database workspace/optimization.sqlite \
  --candidate-config workspace/search/candidate-07.json \
  --run-id search-round-03-candidate-07 --algorithm portfolio \
  --output workspace/search/candidate-07-decision.json
```

Even when the observation file also contains holdout rows, the recorded reward
is computed exclusively from validation. The result records
`holdout_backpropagated: false` for audit.

The default milestone is a 60% held-out pass rate across at least 16 tasks and
8 domains, with zero pass-to-fail regressions and no more than 10% efficiency
failures. Passing the milestone consumes that cohort: the next promotion must
use a newly sealed holdout. This prevents repeated tuning against the same 16
tasks from being presented as generalization.

Use `group_id` for related variants originating from one template, source
trace, or task family. The scorer rejects any `task_id` or `group_id` that
appears in more than one stage, even when the visible task names differ.

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
