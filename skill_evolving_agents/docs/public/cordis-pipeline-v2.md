# Cordis pipeline v2

## Decision

Build the next skill-evolution pipeline directly in TypeScript on real Cordis
concepts. Keep the existing Python pipeline running and unchanged as the
production baseline, comparison oracle, and temporary provider of mature
algorithms. Do not rewrite the current pipeline in place.

The v2 system is a TypeScript control plane. Existing Python trace mining,
embedding, mutation, and benchmark code remains available through versioned
JSON subprocess adapters until a TypeScript provider demonstrates equal or
better behavior.

## Why TypeScript and Cordis directly

DeepSeek Harness already supplies the architectural properties this project
needs:

- plugins contribute typed services, events, and reversible effects;
- registrations are owned by plugin lifecycle and unwind on disposal;
- profiles and bundles produce patchable runtime compositions;
- service definitions, providers, and consumers form explicit capability
  seams;
- durable events make model-visible decisions replayable and auditable;
- runtime inspection exposes live services, configuration, and plugin state;
- immutable package versions can be activated, replaced, stopped, or removed;
- configuration and policy can change without adding branches to one central
  orchestrator.

Recreating only the surface appearance of these properties in Python would
produce another framework to maintain and would still require a later DSH
integration. TypeScript also provides stronger compile-time contracts between
pipeline phases and is the native language of the target harness.

## Current benchmark position

There is no universal DeepSeek Harness SkillsBench baseline. Results depend on
the model, task cohort, timeout, harness revision, skill exposure mode, and
number of repetitions.

The current matched evidence is:

| Evaluation | No skill | Pipeline-selected skills |
|---|---:|---:|
| Full 16 tasks, first repetition | `5/16` = `31.25%` | `6/16` = `37.5%` |
| Full 16, two-repetition estimate | `31.25%` | `34.4%` raw |
| Full 16, strict budget outcome | `31.25%` | `31.25%` |
| Router-selected six tasks | `33.3%` | `41.7%` raw |
| Special seven-pair cohort | `14.3%` | `100%` |

The seven-pair result is concentrated on repeated Three.js trials and does not
represent general SkillsBench performance. The full held-out evidence does not
yet show a statistically significant general lift.

The target is at least `10/16` stable passes, equivalent to `62.5%` on the
current frozen cohort, followed by confirmation on a separate unseen promotion
cohort. The current best full run needs four additional stable passes; the
strict-budget result needs five.

## Non-goals

The first v2 milestone does not:

- port every Python module;
- launch paid benchmark trials;
- change the existing pipeline's outputs or database schema;
- install v2 as the default runtime;
- let an agent publish a mutation without replay and policy gates;
- treat the special Three.js cohort as evidence of general performance.

## Repository layout

Create the parallel implementation under `skill_evolving_agents/pipeline_v2/`:

```text
pipeline_v2/
├── package.json
├── tsconfig.json
├── src/
│   ├── contracts/
│   │   ├── ids.ts
│   │   ├── events.ts
│   │   ├── evidence.ts
│   │   ├── operations.ts
│   │   └── resources.ts
│   ├── core/
│   │   ├── context.ts
│   │   ├── event-log.ts
│   │   ├── lifecycle.ts
│   │   ├── projections.ts
│   │   └── run-controller.ts
│   ├── capabilities/
│   │   ├── trace-source.ts
│   │   ├── finding-detector.ts
│   │   ├── candidate-recall.ts
│   │   ├── goal-planner.ts
│   │   ├── skill-mutator.ts
│   │   ├── verifier.ts
│   │   ├── publisher.ts
│   │   └── feedback-learner.ts
│   ├── plugins/
│   │   ├── rules/
│   │   ├── embeddings/
│   │   ├── agents/
│   │   ├── replay/
│   │   └── skillsbench/
│   ├── adapters/
│   │   ├── python-worker.ts
│   │   └── legacy-pipeline.ts
│   └── profiles/
│       ├── low-cost.ts
│       ├── balanced.ts
│       └── research.ts
└── tests/
```

The exact split may evolve, but capability interfaces must remain independent
of their providers.

## Capability seams

Every phase is a service definition with one or more providers and at least one
consumer.

```text
TraceSource
  providers: JSONL, ACP, SkillsBench, session database

FindingDetector
  providers: deterministic rules, statistics, embedding anomaly, agent

CandidateRecall
  providers: lexical, Qwen embedding, learned router

GoalPlanner
  providers: deterministic template, small model, large agent

SkillMutator
  providers: legacy Python adapter, TypeScript mutator, delegated agent

Verifier
  providers: structural, fixture replay, behavioral benchmark, policy gate

Publisher
  providers: candidate workspace, Git branch, installed DSH bundle

FeedbackLearner
  providers: moving statistics, calibrated router, future learned policy
```

The pipeline controller consumes these interfaces. It does not select an
implementation through phase-specific conditionals. A profile mounts the
chosen providers.

## Durable event model

The event log is the source of truth for runs, metrics, replay, audit, and
learning. Initial events include:

```text
run/started
trace/ingested
finding/detected
candidate/recalled
candidate/selected
diagnosis/recorded
goal/proposed
operation/planned
resource/generated
verification/completed
operation/accepted
operation/rejected
publication/completed
benchmark/completed
feedback/recorded
run/completed
run/failed
```

Events are append-only, versioned, and reconstructable. Derived run state,
funnel metrics, resource-use metrics, and learned-policy examples are
projections. A model-visible decision must be represented by an event.

## Lifecycle and safety

All plugin registrations are effects with disposers. An experimental provider
can be mounted, measured, and removed without leaving registrations or global
state behind.

Mutation publication requires all applicable gates:

1. schema validation;
2. operation and resource contract validation;
3. fixture replay when a fixture exists;
4. behavioral verification when the claim is behavioral;
5. execution-budget validation;
6. no-regression policy;
7. immutable publication receipt.

Missing replay is not a structural pass when a fixture is available. A budget
failure is recorded as `efficiency_failure`, not as evidence that a skill is
good or bad.

## Cost-tiered composition

The default low-cost profile should mount:

```text
deterministic normalization
→ rule/statistical detection
→ Qwen3-Embedding-0.6B recall
→ deterministic intent and feedback gates
→ small-model decision only for unresolved candidates
→ large agent only for mutation or genuinely ambiguous judgment
→ deterministic replay and publication gates
```

Each escalation records the reason, estimated cost, uncertainty, selected
provider, and counterfactual lower-tier result.

## Python worker boundary

Python is an implementation provider, not the orchestrator. Each worker:

- receives one versioned JSON request on standard input or a local IPC channel;
- emits one versioned JSON result;
- writes no pipeline-global state directly;
- receives explicit input and output paths;
- has a wall-time and output-size limit;
- returns structured failure information;
- can be replaced independently by a TypeScript provider.

The bridge initially exposes existing trace mining, embedding, mutation, and
SkillsBench evaluation functions. Cross-runtime schemas live in the TypeScript
contracts package and have generated JSON Schema fixtures consumed by Python
tests.

## First vertical slice

The first end-to-end slice is deliberately narrow:

```text
one trace
→ deterministic finding detector
→ embedding recall adapter
→ deterministic goal decision
→ legacy Python mutation adapter
→ fixture replay verifier
→ provisional or accepted publication
→ feedback event
```

It runs beside the existing pipeline on the same trace. The comparison report
must include:

- emitted events and final projection;
- selected skill and operation;
- generated resource tree;
- replay result;
- agent calls, tokens, time, and cost availability;
- output equivalence or documented difference;
- cleanup/disposal confirmation.

No legacy phase is replaced until its v2 provider matches or exceeds behavior
on frozen offline cases.

## Path to 60 percent

Architecture alone will not produce the score target. The delivery plan is:

1. Freeze a representative development cohort and a separate unseen promotion
   cohort.
2. Convert current failed baseline traces into capability-family evidence.
3. Identify at least five failure families with reusable solutions rather than
   task-specific patches.
4. Build deterministic resources and replay fixtures before using an agent.
5. Require stable lifts across repetitions with no pass regressions.
6. Suppress quality-neutral cost regressions through feedback calibration.
7. Reach at least `10/16` under strict budgets on the development cohort.
8. Confirm the lift on the unseen cohort with confidence intervals and frozen
   configuration.

The promotion criterion is not a single `60%` observation. It is a repeatable
score at or above the target, within cost budgets, without task-specific
branches, and with no material regression in previously passing families.

## Milestones

### Milestone 0 — contracts and comparison harness

- scaffold the TypeScript package;
- define branded IDs, events, operations, resources, and failure types;
- implement an in-memory event log and projections;
- add lifecycle/disposal tests;
- add a legacy comparison-report schema;
- make no paid calls.

### Milestone 1 — low-cost vertical slice

- mount deterministic detection and the embedding recall adapter;
- call the legacy Python mutator through the worker boundary;
- run fixture replay;
- produce an immutable publication receipt;
- compare against one frozen legacy trace.

### Milestone 2 — controlled offline research

- add provider swapping through profiles;
- add wide/grid search over deterministic and embedding knobs;
- learn only from accepted, budget-valid feedback;
- require holdout improvement before promoting configuration.

### Milestone 3 — DSH integration

- package v2 as a DSH bundle/plugin;
- expose inspection, run, pause, and report operations;
- log all model-visible inputs and decisions;
- keep installation and persistent enablement under Plugin Manager ownership.

### Milestone 4 — benchmark promotion

- run the frozen development cohort;
- iterate only from admissible traces;
- reach the strict-budget score target;
- run the unseen promotion cohort;
- publish the reproducible report and frozen profile.

## Source references

The design follows these local DeepSeek Harness references:

- `/Users/maybewu/Documents/Projects/oss/deepseek-harness/docs/architecture.md`
- `/Users/maybewu/Documents/Projects/oss/deepseek-harness/docs/cordis-primer.md`
- `/Users/maybewu/Documents/Projects/oss/deepseek-harness/packages/boot/plugin-manager/README.md`
- `/Users/maybewu/Documents/Projects/oss/deepseek-harness/packages/extensions/cordis-host-runner/README.md`
- `/Users/maybewu/Documents/Projects/oss/deepseek-harness/docs/subsystems/extensions.md`
