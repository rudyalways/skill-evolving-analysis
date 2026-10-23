# Learned configuration policy

Implementation status: typed policy contracts, the feature extractor, fixed,
search, and model-provider adapters, deterministic compiler, and append-only
policy store now exist under [`policy/`](policy/README.md). Transformer training
and serving are intentionally not implemented yet.

Dynamic routing is implemented by the constrained state machine described in
[`state-machine-architecture.md`](state-machine-architecture.md). The learned
policy may select only registered transitions and implementations.

## Goal

Replace hand-tuned configuration selection with a learned policy that maps a
trace, accumulated runtime history, deployment constraints, and available
algorithms to a complete structured pipeline configuration.

The model does not emit arbitrary JSON. It emits a typed action vector whose
heads correspond to registered configuration fields. A deterministic compiler
validates, constrains, and converts that vector into the existing profile,
preprocessing, recall, and scoring configuration documents.

```text
trace/session features + historical state + requested operating point
                              │
                              ▼
                    learned configuration policy
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
         binary heads    categorical heads  numeric heads
         gates/flags      algorithms/modes   thresholds/weights
             └────────────────┼────────────────┘
                              ▼
                  deterministic policy compiler
                              ▼
                 validated configuration candidate
                              ▼
             replay → shadow → canary → production
                              │
                              ▼
             human + verifier + benchmark feedback
                              │
                              └──────── training store
```

## Model inputs

The policy input is a versioned feature record. Raw private trace content is
not required after feature extraction.

### Trace and workload features

- detector counts and normalized strengths;
- finding severity and confidence distributions;
- evidence count, recurrence, and distinct sessions;
- trace length, tool-event count, failure rate, and retry structure;
- embedding summaries for task, finding, and candidate skills;
- skill-recall score distribution and top-result margin;
- known category, unknown-category score, and OOD distance;
- language, source adapter, repository type, and task family when available.

### Historical state

- moving averages for cost, latency, quality, and human acceptance;
- Beta confidence for prior knob/value choices;
- recent phase failure and fallback rates;
- algorithm/model/index revisions;
- data-volume and confidence indicators;
- current policy version and recent configuration changes.

### Requested operating point

`low-cost`, `balanced`, and `full-quality` become model inputs rather than
separate hand-authored policies. The input includes explicit budgets:

- maximum cost tier;
- token or monetary budget;
- latency target;
- agent-call cap;
- minimum quality and safety constraints;
- local-only or remote-service availability;
- allowed model and algorithm inventory.

The same trace can therefore produce different valid configurations for
different operating points.

## Typed output space

Each mutable knob in `config/knob-registry.json` receives one output head.
Heads are grouped by type.

### Binary heads

Binary heads use a sigmoid and represent phase gates, feature flags, embedding
recall, safe fallbacks, and escalation to a more expensive tier. The compiler
applies a calibrated threshold or samples the Bernoulli during exploration. It
records both the selected value and probability.

### Categorical heads

Categorical heads use masked softmax distributions for phase algorithm,
execution mode, service tier, model family, recall strategy, and detector
family. The mask comes from the super-config, canonical contracts, available
services, cost ceiling, and deployment capabilities. The model cannot select
an unavailable or schema-incompatible algorithm.

### Numeric heads

Numeric knobs are represented in normalized `[0, 1]` space:

```text
bounded value = minimum + model_value * (maximum - minimum)
```

Discrete numeric domains use an ordinal categorical head rather than rounded
continuous output. Examples include `top_k`, evidence counts, agent caps,
thresholds, margins, and detector saturation.

### Simplex and coupled heads

Scoring-table weights use a softmax head so they are non-negative and sum to
one. Coupled thresholds preserve their ordering by construction:

```text
accept_at = lower + a * available_range
noise_accept_at = accept_at + b * (upper - accept_at)
```

This is preferable to generating invalid independent values and repairing most
of the output afterward.

## Recommended model architecture

The intended architecture is a compact transformer encoder followed by typed,
multi-head MLP output layers. A pure MLP remains useful only as a bootstrap
baseline and ablation.

```text
trace-event tokens ──────────────┐
phase-decision tokens ───────────┤
feedback-history tokens ─────────┤
algorithm/service tokens ────────┤
skill/category embedding tokens ─┤
dense context and budget token ──┘
                 │
                 ▼
       transformer policy encoder
   token/type/position/time embeddings
   masked self-attention + feed-forward blocks
                 │
        ┌────────┴─────────┐
        ▼                  ▼
  pooled policy state   contextual token states
        │                  │
        └────────┬─────────┘
                 ▼
          typed MLP output heads
   ┌────────┬───────────┬─────────┬──────────┐
   ▼        ▼           ▼         ▼          ▼
 binary  categorical  numeric   simplex   value/OOD
 heads      heads       heads     heads      heads
```

### Why a transformer

Pipeline decisions depend on order, interaction, and variable-length context.
A transformer can represent that a correction followed a failed retry, that a
verifier failure appeared after a particular algorithm choice, or that recent
feedback contradicts an older moving average. A flat MLP would require those
relationships to be fully pre-engineered into aggregate features.

The transformer also permits a variable inventory of algorithms, services,
skills, and categories. Candidate algorithms can be encoded as tokens and
scored against the current trace state instead of requiring a permanently
fixed output neuron for every future algorithm.

### Input token families

Each input token has a token-type embedding and only the fields relevant to its
family:

- `TRACE_EVENT`: phase, tool, status, elapsed time, detector strength, and a
  projected semantic embedding;
- `FINDING`: severity, confidence, recurrence, evidence count, and category;
- `DECISION`: phase, selected algorithm, knob values, and action probability;
- `FEEDBACK`: source, target decision, label/rating, confidence, and delay;
- `ALGORITHM`: phase, cost tier, capabilities, availability, and learned
  algorithm embedding;
- `SKILL` or `CATEGORY`: identity embedding, retrieval score, support, and OOD
  distance;
- `CONTEXT`: requested operating point, budgets, deployment capabilities,
  current policy revision, and historical moving averages.

Long raw traces should first be converted into bounded event tokens. Important
events, failures, corrections, and decisions are preserved; repetitive spans
may be summarized into count/statistic tokens. The tokenizer and truncation
policy are versioned parts of the model.

### Attention structure

Begin with a bidirectional encoder because the complete trace is normally
available before configuration selection. Use attention masks to prevent
padding and unavailable algorithms from contributing. Add relative position
or elapsed-time embeddings so widely separated events are distinguishable.

For long multi-trace training examples, use hierarchical encoding:

```text
events within each trace → trace summary tokens
trace summaries + feedback history → policy transformer
```

This avoids quadratic attention over every event from every historical trace.
Cross-attention from policy query tokens to trace tokens is another suitable
later optimization.

### Typed multi-head output layer

The final transformer state feeds small MLP heads specialized by output type:

- a shared binary head can score registered Boolean knob query embeddings;
- categorical selection uses a pointer or compatibility score over available
  algorithm tokens, followed by a masked softmax;
- numeric heads produce bounded distribution parameters rather than only point
  estimates;
- scoring weights use a simplex/softmax head;
- value heads predict human utility, verifier success, benchmark performance,
  latency, cost, and rollback risk separately;
- an OOD head predicts whether the current state is outside supported policy
  conditions;
- an uncertainty head or ensemble disagreement estimate controls escalation.

Knob query embeddings make the design extensible: a newly registered knob can
be represented by its type, phase, range, description embedding, and dependency
metadata. It still requires evaluation before the model may control it, but it
does not necessarily require redesigning the shared encoder.

### Model sizes and baselines

Start with a compact encoder, for example 4–8 transformer blocks and a hidden
size appropriate to local serving. Select the exact size from latency and data
volume rather than assuming a larger model is better. Compare at least:

1. fixed configuration;
2. existing EMA/Beta/MCTS policy;
3. dense-feature MLP baseline;
4. transformer encoder with typed MLP heads;
5. transformer plus hierarchical multi-trace history, when enough data exists.

The MLP baseline is important: if the transformer cannot outperform it on
time-separated traces, sequential complexity has not justified its cost.

Each output artifact records logits or distribution parameters, action
probabilities, compiled knob values, uncertainty, calibration version,
tokenizer and feature-schema revisions, checkpoint revision, attention masks,
availability masks, and compiler constraints.

## Training signals

Training examples connect a feature record and selected configuration to one or
more outcomes. Preserve each signal rather than immediately collapsing all
feedback into one reward.

### Primary human signals

- explicit yes/no approval;
- good/bad judgment;
- 1–5 stars or another ordinal rating;
- corrected category, operation, or algorithm choice;
- accepted, edited, reverted, or rejected skill change;
- preference between two configurations;
- free-text feedback linked to a later structured label.

Human signals retain provenance, reviewer class, timestamp, and confidence. A
correction or revert normally carries more weight than absence of complaint.

### Secondary signals

- verifier result and per-check scores;
- held-out benchmark pass rate;
- skill activation false-positive rate;
- critical/high finding recall;
- semantic-rejection precision;
- recall@k and ranking quality;
- agent calls, token cost, latency, and timeout rate;
- publication success, later rollback, and regression reports.

Secondary signals scale well but are not equivalent to human preference. A
verifier can itself drift or be gamed.

## Multi-task objectives

Use separate prediction losses:

- binary cross-entropy for yes/no and good/bad;
- ordinal loss for star ratings;
- pairwise ranking loss for preferences;
- cross-entropy for corrected categories or algorithms;
- regression or quantile loss for latency and cost;
- auxiliary verifier and benchmark prediction;
- calibration loss for confidence estimates.

Optimize human utility and benchmark quality while minimizing cost, latency,
and review burden under hard safety, compatibility, and authorization
constraints. Safety metrics remain constraints; cost savings cannot cancel a
safety regression.

## Credit assignment

One run contains many phase decisions, while feedback may arrive only for the
final skill. Store the complete trajectory:

```text
run → phase decisions → knob probabilities → artifacts → final outcomes
```

Use direct supervision for corrected decisions, phase-local outcomes, delayed
run-level reward, counterfactual replay on the same trace, and conservative
off-policy estimation using the probability of the recorded action.

The existing EMA, Beta posterior, wide/deep search, and MCTS results become
features and exploration priors. MCTS backpropagation is not the same as neural
gradient backpropagation; both can coexist.

## Learning database

| Table | Purpose |
|---|---|
| `feature_records` | Immutable normalized vectors and presence masks |
| `policy_decisions` | Per-head logits, probabilities, masks, and compiled values |
| `feedback_events` | Human, verifier, benchmark, cost, and rollback signals |
| `decision_outcomes` | Attribution from feedback to run, phase, and decision |
| `training_examples` | Materialized examples with split and label revisions |
| `model_checkpoints` | Model, optimizer, schema, and training-data revisions |
| `calibration_reports` | Per-head reliability and OOD performance |
| `policy_deployments` | Offline, shadow, canary, production, rollback lineage |

Never overwrite feedback. A correction appends an event that supersedes the
previous event while retaining audit history.

## OOD and category growth

Do not force every input into the nearest fixed category. Mark it unknown when
embedding distance is high, categorical entropy is high, ensemble or dropout
disagreement is high, every head has low confidence, or the feature vector is
outside the training envelope.

Unknown cases escalate into an OOD review queue. Cluster reviewed unknowns with
embeddings and structured features. A category proposal requires minimum
support, distinct sessions, separation from existing categories, a stable
description, and human approval. Addition creates a new taxonomy and output
schema version. Old checkpoints retain their original taxonomy unless an
explicit adapter is provided.

Expandable categories should use learned category embeddings or retrieval.
Stable, high-volume categories may retain dedicated softmax outputs.

## Training and deployment lifecycle

```text
collect immutable decisions and feedback
  → validate provenance and join delayed outcomes
  → split by session/project/time
  → train candidate checkpoints
  → calibrate every output family
  → offline replay against frozen baselines
  → shadow inference
  → bounded canary
  → production or rollback
```

Training, evaluation, and deployment datasets are separately versioned. Never
split findings from the same session across training and testing.

Exploration proceeds from offline grid/random/wide-deep/MCTS, to shadow model
comparison, to contextual-bandit exploration within safety-equivalent choices,
and finally to a small canary with automatic rollback. Record action
probabilities for explored decisions so off-policy evaluation remains valid.

## Immutable boundary

The following remain outside the model action space:

- atomic publication and recoverable rollback;
- schema and artifact validation;
- privacy and redaction rules;
- maximum permitted cost and agent-call caps;
- critical-recall promotion requirements;
- availability and compatibility masks;
- authorization and external side-effect boundaries;
- ownership and definitions of final human evaluation signals.

The model may recommend policy changes but cannot enact them. This prevents it
from improving measured reward by weakening its evaluator or constraints.

## Implementation phases

1. **Dataset and compiler:** add immutable feedback tables, output-head metadata,
   feature extraction, normalization, and the typed compiler. Keep search/MCTS
   as the acting policy while collecting data.
2. **Baselines and outcome model:** train a dense MLP baseline, then a compact
   transformer outcome model. Predict human, verifier, benchmark, cost, and
   latency outcomes and rank search candidates; deploy only in shadow.
3. **Learned transformer policy:** train typed MLP action heads over the shared
   transformer state, calibrate uncertainty, and add unknown detection; canary
   only compiler-valid candidates.
4. **Constrained online learning:** add contextual-bandit updates for
   safety-equivalent choices and periodically retrain from the event store.

## Success criteria

The learned policy is production-ready only when it outperforms fixed profiles
on time-separated traces, stays calibrated across operating points, meets all
safety constraints, improves human preference without verifier reward hacking,
detects unknowns, reproduces every decision from its stored checkpoint and
features, and rolls back cleanly to an earlier policy.
