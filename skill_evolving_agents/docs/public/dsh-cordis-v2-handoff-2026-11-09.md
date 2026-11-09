# DSH handoff — Cordis pipeline v2

## Goal

Create the first offline TypeScript/Cordis v2 scaffold while keeping the
existing Python pipeline unchanged. This handoff intentionally limits scope and
cost. Do not run hosted models, embeddings, Docker benchmarks, or SkillsBench.

## Required reading

1. `skill_evolving_agents/docs/public/cordis-pipeline-v2.md`
2. `skill_evolving_agents/docs/public/dsh-desktop-followup-2026-11-08.md`
3. `/Users/maybewu/Documents/Projects/oss/deepseek-harness/AGENTS.md`
4. `/Users/maybewu/Documents/Projects/oss/deepseek-harness/docs/architecture.md`
5. `/Users/maybewu/Documents/Projects/oss/deepseek-harness/docs/cordis-primer.md`

Read further Harness files only when directly needed for the scaffold. Do not
modify the DeepSeek Harness checkout.

## First assignment

Implement Milestone 0 only:

- create `skill_evolving_agents/pipeline_v2/` as a TypeScript package;
- use real Cordis interfaces and lifecycle patterns where they can be consumed
  without changing the existing Python application;
- define branded run, trace, finding, operation, skill, resource, and event IDs;
- define versioned event unions for the initial run lifecycle;
- implement an in-memory append-only event log;
- implement projections for run status, funnel counts, operations, resource
  use, and failures;
- implement plugin registration through reversible effects/disposers;
- define capability interfaces without implementing model-backed providers;
- define the versioned JSON request/result protocol for future Python workers;
- add focused tests for event validation, deterministic projection, provider
  replacement, disposal, duplicate registration, and structured failure;
- add a short README explaining how v2 coexists with the legacy pipeline.

Do not port the legacy pipeline, add a second database, change current pipeline
behavior, or make v2 the default. Do not run paid evaluation.

## Acceptance criteria

- the existing Python test suite remains unchanged and passing for touched
  integration surfaces;
- TypeScript type checking and focused tests pass locally;
- mounting and disposing a provider leaves no registration behind;
- the same event sequence always yields the same projection;
- invalid event versions and invalid state transitions fail with structured
  errors;
- no model, network, Docker, or benchmark command is executed;
- the final report lists files changed, commands run, unresolved design
  questions, and the next smallest vertical slice.

## Ready-to-paste cheap DSH prompt

```text
Work in /Users/maybewu/Documents/Projects/drafts/skill-evolving-analysis on
main. This is an offline implementation task: do not call hosted models, run
embeddings, start Docker, or run SkillsBench.

Read these files first:
- skill_evolving_agents/docs/public/cordis-pipeline-v2.md
- skill_evolving_agents/docs/public/dsh-desktop-followup-2026-11-08.md
- /Users/maybewu/Documents/Projects/oss/deepseek-harness/AGENTS.md
- /Users/maybewu/Documents/Projects/oss/deepseek-harness/docs/architecture.md
- /Users/maybewu/Documents/Projects/oss/deepseek-harness/docs/cordis-primer.md

Do not modify the deepseek-harness checkout. Implement only Milestone 0 under
skill_evolving_agents/pipeline_v2/: a TypeScript package using real Cordis
lifecycle patterns, branded IDs, versioned durable event unions, an in-memory
append-only event log, deterministic projections, reversible provider
registration, capability service definitions, and a versioned JSON protocol
for future Python workers. Keep the existing Python pipeline unchanged and do
not make v2 the default.

Add focused offline tests covering event validation, deterministic projection,
provider replacement, disposal, duplicate registration, invalid transitions,
and structured failures. Run only type checking and focused local tests. Do
not commit or push until you have reported the files changed, commands run,
test results, unresolved design decisions, and the proposed next vertical
slice. Keep the implementation small; do not port existing algorithms yet.
```
