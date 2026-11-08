# DSH Desktop handoff — 2026-11-08

## Objective

Continue improving `skill_evolving_agents` so pipeline-generated skills create
measurable lifts on fresh held-out tasks without overfitting, regressions, or
unbounded agent cost. Prefer offline implementation and focused tests before
launching another paid benchmark.

## Repository and runtime

- Repository: `skill_evolving_agents/` inside `skill-evolving-analysis`
- Branch: `main`
- Agent backend for pipeline work: `dsh --model deepseek-chat`
- Credentials are local in `../.env`; never print or commit them.
- DeepSeek API base URL: `https://api.deepseek.com/v1`
- Embedding model: `Qwen/Qwen3-Embedding-0.6B`
- Docker context used by SkillsBench: `colima-deep-prep-ci`
- Raw benchmark artifacts under `workspace/skillbench/` are intentionally
  ignored because they are large local experiment outputs.

## What is implemented

- Cost-tiered, phase-configurable pipeline with rule, embedding, small-model,
  and large-model implementations.
- Local embedding service/library modes and embedding recall/filter phases.
- Dynamic state transitions, funnel metrics, runtime metrics database, router
  feedback calibration, held-out reporting, and trace adapters.
- Resource-aware skill planning and updates for `scripts`, `references`,
  `assets`, delegated `agents`, and `evals`, including bounded nested paths.
- ACP/SkillsBench trace import, mounted-skill activation audit, benchmark trial
  validity audit, paired reports, and objective-verifier feedback mining.
- Deterministic `agents/openai.yaml` generation and richer resource metrics.
- Goal contract repair loops and deterministic semantic contracts for native
  Three.js producers.

## Latest verified success

Pipeline run:

`workspace/runs/threejs-world-matrix-v46-20261108@2026-11-08T20:52`

It produced one accepted update to `threejs-source-mesh-export` with:

- `scripts/export-scene.mjs`
- `scripts/check-export.mjs`
- clean and wrongly framed native-module fixtures
- updated verification references
- focused evals

Independent local resource test:

- clean fixture: checker passed, rotated max delta `0`
- wrong-frame fixture: checker exited `1`, rotated max delta about `7.38`
- wrong-frame artifact matched the unrotated comparison, proving useful frame
  attribution rather than a self-consistent false pass

Fresh SkillsBench result for `threejs-to-obj`:

- historical no-skill baseline: reward `0`, `107` tool calls
- v40 passing skill: reward `1`, `105` tool calls, agent timeout boundary
- v43: reward `0`, `15` calls; checker had a stale-matrix false positive
- v46: reward `1`, `35` calls, `90s` agent time, no timeout
- activation audit: valid injected skill; resources were discovered, but the
  agent followed instructions instead of executing the new producer directly

The v46 pipeline itself recorded:

- one finding, one diagnosis, one goal, one update, one acceptance
- five agent calls
- structural verification pass
- replay coverage `0`, which is still a major weakness

## Fresh held-out evidence

Baseline cohort:

- `ada-bathroom-plan-repair`: reward `0`, `198` calls, pathological duration
- `pptx-reference-formatting`: reward `1`, `30` calls
- `threejs-structure-parser`: reward `0`, `14` calls

Router selections:

- ADA → `ada-plan-view-accessibility`, score `0.700222`
- PPTX → `batch-doc-variant-publishing`, score `0.476191`
- Three.js structure → `threejs-source-mesh-export`, score `0.643914`

Treatment observations:

- ADA treatment was manually stopped after exceeding the already pathological
  baseline duration. Treat it as an efficiency failure, not a scored result.
- PPTX treatment regressed: reward `0`, `46` calls versus baseline reward `1`,
  `30` calls. This is a confirmed false-positive router selection.
- Three.js structure treatment was started but stopped when the user requested
  that paid work end; do not interpret it as a benchmark result.

## Highest-value next work

Do these offline before spending on another benchmark:

1. Require behavioral replay for accepted script/reference/eval changes when a
   replay fixture is available. Structural-only acceptance is insufficient.
2. Add an executable-leverage metric and gate:
   resource discovered → opened → executed → succeeded → reduced tool calls.
3. Feed the PPTX regression into `workspace/optimization.sqlite` using the
   existing benchmark feedback tooling, then add a task-intent compatibility
   gate so generic document workflow skills do not route to presentation
   analysis solely on embedding similarity.
4. Add strict per-trial wall-time, tool-call, and cost budgets with automatic
   early stopping and explicit `efficiency_failure` status.
5. Improve router precision with required object/action compatibility features
   in addition to embeddings. For example, PPTX title detection should not
   match document publishing without presentation-inspection evidence.
6. Make generated skills put the exact producer/checker command near the top
   and measure direct script adoption. Scripts-present is not enough.
7. Fix resumability for timestamp-stamped run IDs containing `@`; interrupted
   runs currently need recreation instead of safe continuation.
8. Add a small fixed offline/cheap regression suite, then run paid held-outs
   only after unit, contract, router, and fixture tests pass.

## Suggested first session

1. Read this handoff and `evaluation/README.md`.
2. Inspect the PPTX baseline/treatment trajectories under the ignored local
   `workspace/skillbench/` tree if they are present.
3. Implement task-intent compatibility plus regression feedback ingestion.
4. Add focused unit tests demonstrating that:
   - `threejs-to-obj` still selects `threejs-source-mesh-export`;
   - ADA still selects its domain skill;
   - `pptx-reference-formatting` abstains from
     `batch-doc-variant-publishing`.
5. Run only focused tests. Report the diff and expected metric effect before
   requesting approval for any paid benchmark.

## Ready-to-paste continuation prompt

```text
Continue work in the skill-evolving-analysis repository on main. Read
skill_evolving_agents/docs/public/dsh-desktop-handoff-2026-11-08.md and
skill_evolving_agents/evaluation/README.md first. Do not launch paid model or
SkillsBench runs yet. Preserve private ignored docs and never print or commit
credentials from .env.

Start with the confirmed held-out router regression: pptx-reference-formatting
passed without a skill in 30 tool calls but failed with the router-selected
batch-doc-variant-publishing skill in 46 calls. Implement an offline,
generalizable task-intent compatibility gate plus feedback calibration so this
pair abstains, while threejs-to-obj still selects threejs-source-mesh-export and
ada-bathroom-plan-repair still selects ada-plan-view-accessibility. Add focused
tests. Then implement executable-leverage metrics and replay-required
acceptance for resource-changing operations when fixtures exist. Run focused
unit/fixture tests only, summarize evidence and remaining risks, and ask before
starting any paid benchmark.
```
