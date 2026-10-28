# Pipeline scoring and threshold guide

The planned transformer policy is maintained as private product strategy. The
search and online-learning system here is both the current optimizer and the
data-collection and exploration layer for that learned policy.

This file is the baseline policy for the cost-aware pipeline. The numbers are
bootstrap settings, not timeless constants. Tune them from labeled outcomes and
retain the phase envelopes so a change can be replayed and audited.

## Decision order

1. Deterministic detectors produce findings and evidence.
2. The embedding prefilter may accept a clearly relevant category or reject
   only a clearly dominant `noise` category. All ambiguous cases escalate.
3. The evolution gate admits recurrent, strong, or protected findings.
4. Recall selects a small set of existing skills.
5. The bounded priority score chooses edits when several operations target the
   same skill.
6. Verification and held-out promotion remain hard safety gates.

Critical findings and configured immediate detectors are protected from a
semantic rejection. Service errors fail open to escalation.

## Tuned defaults

| Knob | Default | Reason |
|---|---:|---|
| detector selection confidence | 0.60 | Broad deterministic recall before later gates |
| methodology value | 0.30 | Rejects marginal single-run recipes before a paid diagnosis call |
| methodology confidence | 0.68 | Existing detectors are structured but still heuristic |
| semantic relevant accept | 0.70 | Automation only on a strong category match |
| semantic noise accept | 0.75 | Rejection requires stronger evidence than acceptance |
| semantic top-two margin | 0.08 | Avoids acting on nearly tied categories |
| embedding recall minimum | 0.35 | Conservative starting point for Qwen3-Embedding-0.6B |
| embedding recall top-k | 5 | Bounds downstream context and agent cost |
| evolution distinct sessions | 2 | Avoids evolving from an isolated event |
| evolution evidence records | 3 | Allows a strong within-session pattern |
| evolution confidence | 0.80 | Required with the within-session evidence exception |
| edit priority threshold | 0.65 | Passes a typical high/0.9-confidence/raw-4 finding |
| max operations per skill | 3 | Limits churn and verification fanout |
| promotion held-out cases | 5 | Two cases were too unstable for an 80% pass-rate estimate |
| promotion pass rate | 0.80 | Requires four of five initial held-out cases |
| promotion max false-positive rate | 0.10 | Skill activation should be conservative |

Single-session generic and out-of-distribution creation are disabled. The
explicit repeated-pattern and methodology exceptions remain available, with
their higher confidence and evidence requirements.

## Resource-discovery bias

The current resource contract is intentionally evidence-gated, but that makes
prose plus evals the path of least resistance. Goal must authorize a resource
before Optimize may create it, and Goal normally sees one finding at a time.
Consequently, a methodology can repeat the same mechanical steps across many
runs without any single finding containing a finished reusable script,
reference, asset, or delegated prompt. The complete Optimize template does not
correct this bias because it is file-shape guidance, not authorization.

This is a selection bias, not evidence that methodology skills never need
resources. Methodologies should accumulate resources when repeated mechanics
stabilize. Examples include:

- promoting repeated parsing, polling, normalization, comparison, or validation
  code into a tested script;
- moving a growing provider matrix, schema, or decision table into references;
- extracting a repeatedly regenerated starter deliverable into assets;
- extracting a stable, bounded subtask into a delegated-agent prompt;
- adding evals when a repeated failure and successful correction provide
  observable cases.

Do not solve the bias by creating all five directories. Empty or speculative
resources increase maintenance cost and context noise. The planner needs
cross-trace evidence and an explicit opportunity-search mode.

The deterministic `resource-script-opportunity` detector now handles the
highest-value evidence-only case: repeated polling mechanics. It normalizes
supported status-command families, recognizes bounded shell loops, and emits a
first-class `resource_opportunity` finding. One selection slot is reserved so
an unrelated behavioral finding from the same trace cannot deduplicate or
crowd it out.

False positives are controlled before an agent call. A script opportunity must
have at least three independent invocations, a provable finite loop bound,
explicit pacing or backoff, an explicit terminal condition, non-destructive
semantics, and confidence above the configured threshold. Every rejected and
emitted candidate is written to
`traces/derived/signals/resource-opportunity-decisions.jsonl` with reason codes
for labeling and threshold search.
Before emission, the detector also scans existing skill `scripts/` resources
for the same provider/status family with pacing and termination behavior; an
equivalent existing helper is rejected as duplication rather than proposed
again.

The initial detector deliberately covers polling/status families rather than
all repeated shell commands. Expand command families only with labeled
positive and near-miss fixtures; generic test, install, formatting, and one-off
administration commands should not become wrapper scripts.

### Proposed run control

Add a profile-backed run parameter:

```bash
python3 run_pipeline.py RUN_ID --resource-discovery accumulate
```

Proposed values:

| Mode | Behavior | Cost and risk |
|---|---|---|
| `evidence-only` | Current behavior. A resource requires direct support in the active finding. | Lowest cost; strongest prose-only bias. |
| `accumulate` | Combine the finding with prior changelog observations and resource-opportunity counters for the same skill. Authorize a resource after recurrence and stability gates pass. | Recommended default after enough history exists. |
| `prototype` | Ask a bounded planner to propose and test one high-value resource when traces show repeated mechanics but no finished file. | Highest cost; requires execution or use evidence and strict unused-resource penalties. |

The selected mode must be snapshotted in `run/config`, included in each
resource plan, and included in the learning-run configuration digest. It must
not silently change between replay candidates.

Suggested companion knobs:

| Knob | Initial value | Meaning |
|---|---:|---|
| `resource.min_occurrences` | 3 | Repeated observations required before accumulated promotion |
| `resource.min_distinct_sessions` | 2 | Prevent one long trace from looking like broad reuse |
| `resource.max_prototypes_per_run` | 1 | Bound extra agent and verification cost |
| `resource.allowed_kinds` | all five | Optional allowlist for scripts, references, assets, agents, and evals |
| `resource.script_fixture_required` | true | A new script must run successfully on a representative fixture |
| `resource.max_unused_rate` | 0.0 | Reject newly created resources that are neither routed nor exercised |

Evidence-only polling detector knobs live under `resource_opportunities` in
`common/preprocessing-config.json`: `min_invocations`,
`min_loop_iterations`, `min_confidence`, `max_evidence_records`, and
`reserved_selection_slots`.

### Accumulation and promotion

Each Goal decision should update a per-skill resource-opportunity record even
when the decision is negative. Store the normalized mechanic, resource kind,
evidence IDs, distinct sessions, confidence, stability, and the reason it was
not yet promoted. Merge similar opportunities across runs.

In `accumulate` mode, promote an opportunity only when:

1. recurrence and distinct-session thresholds pass;
2. inputs, outputs, and failure behavior are stable enough to specify;
3. the resource reduces regeneration, instruction tokens, or observed errors;
4. it does not duplicate an existing resource or baseline model capability;
5. its validation contract is executable or otherwise observable.

For scripts, Optimize must create a safe fixture and execute the script. For
references, `SKILL.md` must route to the file conditionally. For assets, an
eval must demonstrate reuse rather than mere presence. For delegated agents,
the prompt must have a bounded responsibility and explicit handoff contract.
Failed prototypes remain opportunity records; they do not enter the candidate
skill inventory.

Do not optimize acceptance rates against an unvalidated inventory. Seed and
publication validation reports are first-class experiment artifacts. Count an
excluded seed as an inventory-integrity failure, not as model recall, goal, or
verification behavior. For run-level optimization, use the `outcome` object in
`pipeline-summary.json`: inherited skill count is context, while accepted
operation count and accepted changed skills are the treatment result. This
prevents inherited directories from inflating apparent pipeline yield.

Track at least these metrics by discovery mode: resource proposal rate,
acceptance rate, execution or use rate, unused-resource rate,
duplicated-content penalty, instruction-token reduction, behavioral lift,
additional agent calls, and wall time. Use reviewed outcomes before changing
the default mode.

## Semantic decision formula

Let `s1` and `s2` be the top two cosine similarities and `m = s1 - s2`.

- Reject only when the top category is `noise`, `s1 >= 0.75`, and `m >= 0.08`.
- Select when the top category is not `noise`, `s1 >= 0.70`, and `m >= 0.08`.
- Otherwise escalate.

Low similarity is uncertainty, not negative evidence. `reject_below` remains in
the shared profile contract for compatible embedding adapters, but this
category classifier does not use it to discard findings.

## Edit priority formula

All components are normalized to `[0, 1]`:

```text
severity = low .25, medium .50, high .75, critical 1.00
detector_strength = abs(raw_detector_score) / (abs(raw_detector_score) + 4)
skill_match = clamp(raw_skill_match, 0, 1)

priority = .40*severity
         + .30*confidence
         + .20*detector_strength
         + .10*skill_match
```

The threshold is `0.65`. The saturation transform prevents arbitrary detector
score ranges from overwhelming confidence and severity. Each normalized
component is written as `score_components` beside `super_score` for audit.

## Calibration procedure

Collect at least 100 reviewed findings, including at least 20 noise findings,
before changing automatic semantic decisions. Split them by session, not by
finding, to avoid leakage. For each candidate configuration report:

- recall of critical/high findings before agent phases;
- precision of automatic noise rejection;
- false-negative count, with critical false negatives reported separately;
- agent calls and wall time per admitted finding;
- recall precision@5 and no-match rate;
- edit acceptance, held-out pass rate, and activation false-positive rate.

Prefer a semantic rejection threshold with at least 98% reviewed precision.
If that cannot be achieved, set the phase to `observe`. Adjust thresholds by at
most 0.05 per release and compare the same replay set. Do not tune against raw
embedding score averages across model revisions; record the model revision and
recalibrate after changing it.

## Automated research control plane

The machine-readable search space is
[`config/knob-registry.json`](config/knob-registry.json). It separates mutable
knobs from locked invariants, declares discrete or bounded domains, and encodes
cross-knob constraints. A candidate can modify only a registered path.

Metric semantics and promotion constraints live in
[`config/metric-spec.json`](config/metric-spec.json). Safety metrics are hard
constraints and are evaluated before cost objectives. A candidate advances
from offline replay to shadow only when all required sample sizes and safety
constraints pass, at least one objective improves, and no objective regresses.

Generate a small reproducible grid:

```bash
python3 evaluation/optimize_config.py grid \
  --knob semantic.accept_at \
  --knob semantic.noise_accept_at \
  --max-candidates 64 \
  --code-revision GIT_SHA \
  --dataset-revision DATASET_SHA \
  --profile-digest PROFILE_SHA \
  --model-revisions model-revisions.json \
  --output experiments/semantic-grid.json
```

An experiment manifest binds the dataset, code, profile, model revisions,
random seed, registry digest, metric-spec digest, and exact candidate values.
This makes replay comparisons reproducible and prevents results from silently
crossing model or dataset revisions.

After replay writes baseline and candidate metric documents in the form
`{"metric_name": {"value": 0.9, "samples": 100}}`, evaluate promotion:

Per-example replay output should first be summarized by the controller. Each
JSONL row has an `example_id` and a `metrics` object whose values are binary
outcomes or numeric measurements:

```bash
python3 evaluation/optimize_config.py summarize \
  --observations experiments/candidate-observations.jsonl \
  --output experiments/candidate-metrics.json
```

The summary records the sample count and a 95% interval. Binary outcomes use a
Wilson interval; continuous measurements use an interval for the sample mean.

```bash
python3 evaluation/optimize_config.py decide \
  --baseline experiments/baseline-metrics.json \
  --candidate experiments/candidate-metrics.json \
  --output experiments/promotion-decision.json
```

The current controller intentionally stops at `advance_to_shadow`. Production
canarying, rollback, and final promotion require a separate deployment control
plane and must not be inferred from an offline win.

## Persistent online feedback

Every completed pipeline run records its configuration digest and runtime
report in `workspace/optimization.sqlite`. Reviewed candidate results are added
with the `learn` command. The database keeps:

- `learning_runs`: immutable run/config/metric records;
- `search_trials`: candidate, search algorithm, reward, and safety decision;
- `choice_posteriors`: per knob/value Beta confidence and reward EMA;
- `policy_versions`: reversible policy lineage, currently through shadow only.

An eligible trial increments the choice's Beta `alpha`; a rejected trial
increments `beta`. The posterior mean is the learned probability that the
choice passes all promotion constraints. Objective reward uses a bounded,
weighted relative improvement and updates an exponential moving average:

```text
ema_next = ema_alpha * reward + (1 - ema_alpha) * ema_previous
```

The default `ema_alpha` is `0.2`. This is credit assignment over configuration
choices, not gradient backpropagation through an LLM. It remains interpretable,
versioned, and reversible.

```bash
python3 evaluation/optimize_config.py learn \
  --database workspace/optimization.sqlite \
  --run-id RUN_ID \
  --algorithm mcts \
  --candidate-config experiments/candidate-config.json \
  --baseline experiments/baseline-metrics.json \
  --candidate experiments/candidate-metrics.json \
  --config-digest PROFILE_SHA \
  --output experiments/learning-decision.json
```

## Search algorithms

Four search modes are implemented:

- `grid`: exhaustive combinations up to an explicit candidate cap;
- `random`: reproducible sampling with cross-knob constraint rejection;
- `wide-deep`: wide single-knob probes followed by joint search around the
  best learned choices;
- `mcts`: a persistent configuration-prefix tree with UCB selection and random
  rollout for unexplored paths. Evaluated descendant rewards are aggregated at
  every prefix, providing backpropagation from complete configurations to each
  ancestor choice.

Example:

```bash
python3 evaluation/optimize_config.py search \
  --algorithm mcts \
  --knob semantic.accept_at \
  --knob semantic.noise_accept_at \
  --count 16 \
  --seed 42 \
  --database workspace/optimization.sqlite \
  --output experiments/mcts-candidates.json
```

Priority-score weights and detector saturation are now searchable knobs. The
four weights are constrained to sum to approximately one. The runtime
normalizes them defensively as well, so an invalid external override cannot
silently inflate the score scale.

### Methodology value floor

`methodology.min_value_score` rejects weak methodology candidates before they
consume a diagnosis call. `evolution_policy.min_methodology_value` applies the
same floor again before a methodology edit can pass the quality gate. Keep the
two values aligned. The default is `0.30`: trace trials showed that single-run
phase-order findings at `0.2733` and `0.297889` both produced no-change after
roughly one minute of DeepSeek diagnosis, while adding no reusable capability.
Lower this only for research profiles that intentionally study marginal
methodology candidates; do not lower it merely to increase operation count.

### Cost and latency controls

These defaults reduce duplicate work without weakening semantic or executable
verification:

- Reference findings in the same source directory consolidate before selection;
  one index is selected for the tree and the rest are recorded as
  `overlapping-reference-source`.
- A resource finding with confidence at or above `0.94`, a complete contract,
  and all detector guards uses deterministic Diagnosis. Set
  `resource_opportunities.deterministic_diagnosis` to `false` to restore a
  hosted call for every resource finding.
- Exact-finding replay is detected before Diagnosis. The run writes the
  idempotent no-change Goal without a Diagnosis or Goal agent call.
- Goal evidence defaults to 1,800 characters per recalled skill and 1,600 per
  resource. Increase those arguments only for a measured recall or decision
  regression.
- Verifier evidence defaults to 18,000 characters with 8,000-character
  resource excerpts. `SKILL_EVOLVER_VERIFIER_EVIDENCE_CHARS` overrides the
  bundle ceiling without changing the contract.
- Optimize prompts require edits and a final message under 150 words; the
  response budget is a behavior instruction, not a correctness claim.

Measure both token and wall-time effects. Fewer calls reduce token volume
predictably, while wall time remains dominated by the slowest individual
agent call and can vary between runs with the same evidence.
