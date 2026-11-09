# v2 integration map

Status: the durable v2 integration slice is implemented and covered by offline
tests. This file is the dependency map for moving the TypeScript/Cordis
pipeline to the primary implementation. It must not be used to claim a
benchmark result.

## Verified starting point

`heldout-v8` (sealed cohort already consumed):

- baseline: `5/16 = 31.25%`
- selective policy: `6/16 = 37.5%`
- selected cells: 6
- abstentions: 10
- valid activated exposures: 6
- lifts: 1
- regressions: 0
- full-cohort tool calls: `1221 -> 1375`; agent seconds: `5130.4 -> 5700.5`
- treatment efficiency failures: 5 full-cohort, 1 selected

The selective score is valid only for cells with verified `with-skill`
exposure. Abstained cells inherit the baseline outcome and are not activated
treatments. A later audit found that 10 of the 16 v8 treatment directories are
byte-identical copies of baseline, so the full-16 treatment number is not a
genuine 16-pair treatment result; only the 6 selected exposure cells carry a
real treatment. No fresh holdout has been evaluated for v2, and 10/16 has not
been demonstrated.

## Target lifecycle

```text
trace
  -> evidence extraction
  -> diagnosis
  -> two-stage routing (lexical/embedding recall, bounded decision)
  -> resource/completeness planning
  -> create/update/merge/delete/no-change decision
  -> skill/resource generation
  -> executable preflight
  -> verification
  -> acceptance/rejection
  -> publication
  -> benchmark observation / feedback
  -> future search evidence (train/validation only)
```

## Current implementation

| Layer | Status | Files |
|---|---|---|
| Branded IDs, durable event unions, validation | implemented | `src/contracts/` |
| Append-only in-memory log, projections | implemented | `src/core/event-log.ts`, `src/core/projections.ts` |
| Cordis service/provider lifecycle | implemented | `src/core/capabilities.ts` |
| Low-cost deterministic providers | partial (fixture only) | `src/providers/low-cost.ts` |
| Deterministic single-trace controller | partial | `src/core/pipeline-controller.ts` |
| Two-stage router | implemented | `src/router/two-stage-router.ts` |
| Durable study store | implemented (JSONL+snapshot) | `src/store/study-store.ts` |
| Resource planner + renderer | implemented | `src/resources/planner.ts` |
| Executable preflight | implemented | `src/preflight/preflight.ts` |
| Benchmark admission/reporting | implemented | `src/benchmark/admission.ts`, `src/benchmark/report.ts` |
| Python worker client | implemented seam | `src/adapters/python-worker.ts` |
| Search portfolio / sealed evaluator | implemented | `src/search/` |
| Successive halving | implemented | `src/search/halving.ts` |
| Durable v2 pipeline slice | implemented | `src/core/v2-pipeline.ts` |
| Low-cost Cordis profile | implemented | `src/profiles/low-cost-v2.ts` |
| Real verifier/replay execution | implemented | `src/verification/replay-verifier.ts` |
| Content-addressed publication | implemented | `src/publication/publisher.ts` |
| Benchmark observation producer | implemented | `src/benchmark/job-directory.ts` |
| Production CLI | implemented | `src/cli/v2.ts` |
| Semantic embedding seam | implemented | `src/router/qwen-embedding.ts` |
| Validation cohort builder/audit | implemented | `src/validation/cohort.ts` |
| DSH bundle/profile packaging | missing | - |

## Dependency rules

1. `contracts/` depends on no core, provider, store, or benchmark module.
2. Capability providers depend on contracts and their own module; the
   controller depends on capability interfaces, not concrete providers.
3. The durable store depends on contracts and the event log/projection; the
   controller owns transaction boundaries.
4. Router and resource planning must not read benchmark answers or holdout
   outcomes.
5. Benchmark admission/reporting is a consumer of observations; it must not
   feed holdout results back into search.
6. Python remains a trace/worker/report adapter or comparison oracle. New
   orchestration, routing, resource planning, preflight, and generalization
   logic lives in v2.

## Sealing rules

- `train`, `validation`, and `holdout` task ids and group/family ids are
  disjoint. A repeated id across stages is a hard error.
- Holdout observations are never included in `validationReward` or search
  history.
- A selected treatment is scored only when `skill_mode == with-skill` and the
  exposure audit confirms activation.
- An abstention is scored with the baseline outcome and is not counted as an
  activated treatment.
- Invalid/contradictory exposure, contamination, duplicate observations, and
  infrastructure errors are excluded with structured reasons.
- A fresh sealed cohort is required before any 10/16 claim.

## Implemented vertical slice

`src/core/v2-pipeline.ts` now runs:

```text
fixture trace
-> keyword finding
-> lexical + in-memory embedding recall
-> bounded deterministic decision
-> justified resource plan and rendered bundle
-> executable preflight
-> verifier/publisher
-> durable store replay across restart
```

The router, resource planner, and preflight are mounted as Cordis capability
providers. The store rejects holdout feedback. The benchmark admission/report
modules consume paired observations and separate raw, activated, and selective
views.

## First validation result

The real v2 run published a generated spreadsheet skill, then ran a four-task
validation cohort. Three cells were abstentions. The selected xlsx cell ran with
the published skill prompt-mounted (the sandbox `/skills` mount was not
visible); activation was verified, but the treatment did not pass and used more
calls and time than baseline. There was no lift and no evidence for a fresh
holdout. See `VALIDATION.md`.

## Next vertical slice

Improve the generated spreadsheet skill so the one verified activated cell
produces a pass or partial-reward lift, then run a bounded repair round on a
second disjoint validation cohort. A fresh sealed holdout remains mandatory for
any 10/16 claim.
