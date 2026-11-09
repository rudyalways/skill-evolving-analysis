# DSH Desktop follow-up — 2026-11-08

Continuation of `dsh-desktop-handoff-2026-11-08.md`. The offline implementation
below was completed first; a separately approved 3-trial held-out screen was
then run. Private ignored artifacts and `.env` credentials were not printed or
committed.

## Confirmed regression addressed

`pptx-reference-formatting` passed without a skill in `30` tool calls and
failed with the router-selected `batch-doc-variant-publishing` skill in `46`
calls. Router policy `v4` now abstains on this pair through two independent
checks:

1. **Task-intent compatibility.** The task is a single presentation
   transformation (`pptx`, slides, font/layout edits). The skill is scoped to
   publishing multiple localized or copied XML document variants and says it
   must not be used for non-XML formats. The offline gate reads the full
   `SKILL.md`, detects the disjoint object family and the unrequested
   multi-variant action, and emits
   `intent-mismatch:object-format-excluded`.
2. **Feedback calibration.** The confirmed baseline/treatment pair was ingested
   with the existing benchmark feedback tooling
   (`evaluation/benchmark_resource_feedback.py`) into
   `workspace/optimization.sqlite`. The task-scoped event has reward delta
   `-1.0`, a regression rate of `1.0`, and a `-0.653333` score adjustment.
   Task-scoped negative evidence now abstains explicitly as
   `feedback-regression` instead of relying only on the threshold.

Preserved behavior:

- `threejs-to-obj` still selects `threejs-source-mesh-export`.
- `ada-bathroom-plan-repair` still selects `ada-plan-view-accessibility`.

## Other offline changes

- **Executable leverage.** `evaluation/executable_leverage.py` records
  discovered -> opened -> executed -> succeeded -> reduced tool calls. Claims
  distinguish discovery-only, opened-only, executed-not-succeeded,
  succeeded-no-reduction, and executable leverage. Paired benchmark feedback
  now stores the claim and aggregate stage rates.
- **Replay-required acceptance.** `common/acceptance_gates.py` rejects a
  resource-changing operation when an available replay failed or when a replay
  fixture exists without an executed replay. Publications record
  `outcome: replay_required`; no fixture/no replay stays explicitly
  provisional.
- **Strict budgets.** `common/execution_budget.py` and
  `evaluation/trial-budgets.json` enforce wall-time, tool-call, and cost limits
  with strict `>` semantics and an explicit `efficiency_failure` outcome. The
  paired report and resource feedback count these separately, and budget-failed
  pairs do not become skill-quality feedback. Pipeline runs record the same
  policy and mark budget exhaustion in `run/efficiency-failure.json` and the
  operation publication.
- **Safe resumability.** `common/run_identity.py` validates plain and
  timestamp-stamped run IDs, rejects path escape and impossible timestamps, and
  resolves workspaces inside `workspace/runs`. A stamped run without `--from`
  now auto-resumes from the earliest saved unaccepted operation and reports
  when there is nothing to continue instead of recreating the run.

## Evidence

Focused local tests (no hosted agents, no embeddings service):

```text
404 passed
```

New focused suites:

- `tests/test_task_intent_compatibility.py`
- `tests/test_executable_leverage.py`
- `tests/test_acceptance_gates.py`
- `tests/test_execution_budget.py`
- `tests/test_run_identity.py`

The recorded PPTX feedback artifact is
`workspace/skillbench/fresh-v46-pptx-feedback.json` (ignored local output). It
contains one paired task, one feedback event, `opened-only` leverage, and a
`-16` tool-call reduction (that is, 16 additional calls).

## First held-out screen (approved 3-trial batch)

The v4/v5 router was evaluated with the real local Qwen embedding model plus the
calibrated feedback database. It abstained on `pptx-reference-formatting`
(`below-minimum-score`, `feedback-regression`) and selected the domain skill for
ADA and Three.js.

Three treatment trials were run with `deepseek/deepseek-chat`, Docker, the
strict-time task copies, and the approved per-trial budgets:

| Task | Treatment | Baseline | Result |
|---|---|---|---|
| `ada-bathroom-plan-repair` | reward `0`, `62` calls, `150s` | reward `0`, `198` calls, `690s` | still failing; methodology leverage, no executable resource |
| `threejs-structure-parser` | reward `0`, `60` calls, `180s` | reward `0`, `14` calls, `60s` | still failing; skill applied an unrequested Blender Z-up rotation |
| `pptx-reference-formatting` | no-skill abstention, reward `0`, `44` calls | reward `1`, `30` calls | baseline drift/flaky; no skill was activated |

Total usage was about `4.5M` provider-reported tokens; provider cost telemetry
was unavailable (`price_source: null`), so the `$6` cap could not be verified
from cost data. The old v46 baseline is not a valid comparison for ADA because it
exceeded the strict `120`-call budget, and PPTX no-skill regressed without any
skill, so the first screen is a gap-finding round, not a promotion result.

The iteration controller (`evaluation/heldout_iteration.py`) classified six
gaps: `baseline_drift`, `baseline_efficiency_failure`, `still_failing` (ADA and
Three.js), `no_lift_no_efficiency` (Three.js), and `no_executable_leverage`
(Three.js). It correctly blocked the next paid round until matched baselines
were run; the matched round then reclassified ADA as
`task_budget_infeasible`.

## Round 2 matched screen

Round 2 reran matched baselines under the same strict task copies and budgets,
then reran the two changed skills:

| Task | Baseline | Treatment | Read |
|---|---|---|---|
| `threejs-structure-parser` | reward `0`, `26` calls, `60s` | reward `1`, `11` calls, `30s` | clear lift; native-frame fix worked |
| `ada-bathroom-plan-repair` | reward `0`, `140` calls, `600s` | reward `0`, `166` calls, `510s` | both over the `120`-call budget; no quality lift, more calls |
| `pptx-reference-formatting` | reward `1`, `38` calls | round-1 no-skill `0`, `44` calls | no-skill condition remains flaky; router still abstains |

The Three.js run executed
`node /skills/threejs-source-mesh-export/scripts/export_part_meshes.mjs
--module /root/data/object.js --out /root/output` once, kept native
coordinates, and passed `check_part_meshes.mjs` with `coordinate_error: 0` across
all 158 OBJ files. The ADA pair is blocked: the baseline is already over the
strict call budget, so the treatment delta is not admissible as skill-quality
evidence. No reward feedback event is recorded for that pair; a budget-failed
comparison is not treated as a skill regression.

Round 2 total usage was about `19.2M` provider-reported tokens. Provider cost
telemetry was still unavailable (`price_source: null`), so the `$10` cap remains
token-verified but not dollar-verified.

The matched iteration report is
`workspace/reports/heldout-v4-round2-iter2.json`. It reports one instrumentation
gap (`execution_evidence_reported`) because ACP dropped the tool-call command
input; the audit now records the agent-reported producer command as weaker
`reported-executable-leverage` rather than falsely claiming no execution. The
next adapter fix is to retain tool-call inputs.

## Round 3 score lift (6 matched Three.js repetitions + new domain)

The frozen router selected a skill for only `4/16` full held-out tasks; the
other `12` abstained. Round 3 therefore measured a pre-registered two-domain
skill cohort instead of spending the budget on abstentions:

| Task | Baseline | Treatment | Result |
|---|---|---|---|
| `threejs-structure-parser` | `0/6`, mean `21.2` calls, `60s` | `6/6`, mean `11.0` calls, `30s` | **+100 pp, −48% calls, −50% time** |
| `pdf-excel-diff` | `1/1`, `33` calls, `90s` | `1/1`, `115` calls, `360s` | quality preserved, efficiency regression |

Aggregate matched result over `7` pairs:

- baseline pass rate: `1/7` (`14.3%`)
- treatment pass rate: `7/7` (`100%`)
- absolute lift: **`+85.7` percentage points**
- exact two-sided sign test: **`p = 0.03125`**
- Wilson 95%: baseline `[0.026, 0.513]`, treatment `[0.646, 1.0]`
- `6` lifts, `0` regressions, `1` unchanged

Round 3 used about `8.6M` provider-reported tokens. The PDF pair preserved its pass but added `82` calls. The feedback formula
recorded a `−0.4` task-scoped adjustment (`0.6216 → 0.2216`, below the `0.35`
threshold), so the frozen router now abstains for that pair on the next round.
This is the general rule: quality-neutral cost regressions are suppressed by
calibrated evidence, not by a task-specific branch.

The remaining instrumentation gaps are `execution_evidence_reported` /
`execution_evidence_missing`: ACP drops tool-call command inputs, so some
successful producer runs are self-reported rather than observed. They are
recorded as weak evidence, not as skill-design failures.

## Full 16-task held-out score

The full held-out domain set was run with matched no-skill baselines and frozen
router-selected treatment. Sixteen tasks, one trial per cell, 900s agent caps,
`max_parallel=6`:

| Metric | Baseline | Treatment | Delta |
|---|---:|---:|---:|
| Passes | `5/16` (`31.25%`) | `6/16` (`37.5%`) | **+6.25 pp** |
| Tool calls | `1221` | `1375` | `+154` |
| Agent time | `5130s` | `5700s` | `+570s` |
| Efficiency failures | `4` | `5` | `+1` |

Exact discordant test: `p = 1.0` (one lift, zero regressions). Wilson 95%:
baseline `[0.142, 0.556]`, treatment `[0.185, 0.614]`.

On the six tasks where the router selected a skill:

| Metric | Baseline | Treatment | Delta |
|---|---:|---:|---:|
| Passes | `2/6` | `3/6` | **+16.7 pp** |
| Tool calls | `287` | `441` | `+154` |
| Agent time | `1110s` | `1680s` | `+570s` |

Only `protein-expression-analysis` changed from fail to pass (`97 → 77` calls,
`360 → 270s`). `invoice-fraud-detection` preserved its pass at `13 → 56` calls;
`weighted-gdp-calc` stayed failing but grew `82 → 241` calls. The other selected
tasks were quality-neutral or efficiency-only changes, and ten tasks abstained.

The one-trial full-benchmark lift is therefore **+6.25 pp, not statistically
significant**. The earlier `+85.7 pp` was a 7-pair cohort result and does not
transfer to the full held-out roster.

A second treatment repetition on the six router-selected tasks changed the
picture:

| View | Baseline | Treatment | Lift |
|---|---:|---:|---:|
| Selected 6, raw reward, 2 reps | `2/6` = `33.3%` | `2.5/6` = `41.7%` | **+8.3 pp** |
| Selected 6, strict budget outcome | `2/6` = `33.3%` | `2/6` = `33.3%` | **0 pp** |
| Full 16, raw reward, 2 reps | `5/16` = `31.25%` | `5.5/16` = `34.4%` | **+3.1 pp** |
| Full 16, strict budget outcome | `5/16` = `31.25%` | `5/16` = `31.25%` | **0 pp** |

`protein-expression-analysis` passed both repetitions (`0 → 1`), but the second
run used `252` calls and hit the 900s cap, so it is an `efficiency_failure`
under the strict budget. `invoice-fraud-detection` passed once and failed once.
`weighted-gdp-calc` stayed failing at `82 → 241` and `82 → 126` calls. The only
strict-budget conclusion is that the pipeline has **no statistically
significant full held-out score lift yet**; it has one repeatable quality win
whose cost is not stable.

A task-scoped feedback leak was also fixed: before the fix, one PDF
cost-regression event suppressed `verify-artifact-against-ground-truth` on
unrelated tasks, leaving only `1/16` selections. Task-scoped events now affect
only their own task, restoring `6/16` selected tasks. This is a general
calibration fix, not a task-specific branch.

## Controllable time and cost profiles

`evaluation/benchmark_controller.py` now turns a requested budget into a frozen
cohort plan. Profiles are `smoke-15m`, `quick-1h`, `standard-3h`, and `deep-1d`;
cost tiers are `low`, `standard`, and `high`. The planner selects tasks,
conditions, repetitions, parallelism, per-trial budgets, and a worst-case cost
cap, then writes a cohort spec.

A 15-minute smoke was executed end to end:

- planned `4` trials / `2` selected tasks / `2` workers
- completed in `457.7s` (`7.6 min`), inside the `900s` cap
- `powerlifting-coef-calc`: `1/1` baseline and `1/1` treatment
- `sec-financial-report`: `0/0`; one baseline trial hit the `300s` per-trial
  cap and was recorded as `timed_out`, not as a model failure
- no work was started after the wall-clock deadline

The parallel runner now enforces a process-group kill at the deadline, supports
`resume` (skips valid existing trials), and reports `timed_out` and
`stopped_by_wall_clock` separately.

## Round-1 fixes

- **Three.js frame handling.** The skill no longer requires the Blender Z-up
  rotation. `scripts/export_part_meshes.mjs` is the part/link producer and keeps
  native coordinates; `scripts/export-scene.mjs` and
  `scripts/check-export.mjs` accept `--frame native|blender-z-up` with native as
  the producer default. The Blender transfer is applied only when the task
  explicitly requests it. This addresses the observed unrequested rotation.
- **ADA environment preflight.** The skill now treats the DXF/rules JSON as
  authoritative, treats a missing screenshot as optional, and forbids
  matplotlib/image-render detours or repeated environment repair. It also asks
  for incremental JSON/DXF outputs so a failed run preserves partial evidence.
- **Methodology leverage.** A prose-only skill that reduces calls without
  executable resources is reported as `methodology-leverage`, not as a missed
  script execution. `executable_available` distinguishes the two.
- **Baseline gates.** The iteration controller blocks on `baseline_drift` and
  `baseline_efficiency_failure` before it attributes a treatment delta to a
  skill.

## Expected metric effect

- False-positive router selections for single-artifact formatting tasks should
  fall without reducing recall for the Three.js and ADA pairs.
- Resource claims require execution and success, so
  `executable_leverage_rate` should be lower than a discovery/read-only count
  and more predictive of real tool-call reduction.
- Structural-only acceptance of resource changes drops to zero whenever a
  replay fixture is present; replay coverage becomes a visible blocker rather
  than an unreported gap.
- Budget-exceeding trials move out of pass/fail attribution into
  `efficiency_failure`, preventing expensive regressions from being scored as
  either clean passes or skill-quality failures.
- Interrupted stamped runs can continue without duplicating the run directory.

## Remaining risks

- The task-intent gate is lexical and conservative. Novel phrasings that name
  no recognized artifact family remain eligible; that is intentional but means
  recall, not the gate, still decides those cases.
- Task-scoped feedback with a single observation is intentionally actionable
  for this confirmed regression. More repetitions are still needed before
  promotion decisions; one event is not a population estimate.
- Replay fixture discovery currently covers held-out/replay fixture paths. A
  skill that ships only development `evals/evals.json` and no held-out fixture
  still accepts provisionally.
- Cost data is often unavailable in the harness. Unknown cost does not fail a
  budget, but the report records `cost_available: false`; strict cost
  enforcement depends on the trial exposing cost.
- No paid benchmark was run, so the gate's held-out precision/recall and the
  budget thresholds remain unvalidated on fresh tasks.
