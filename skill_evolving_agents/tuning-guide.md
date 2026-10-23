# Pipeline scoring and threshold guide

For the planned transformer policy with typed multi-head MLP outputs, see
[`learned-policy-architecture.md`](learned-policy-architecture.md). The search
and online-learning system here is both the current optimizer and the
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
| methodology value | 0.12 | Removes weak recipes while retaining useful observed values |
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
