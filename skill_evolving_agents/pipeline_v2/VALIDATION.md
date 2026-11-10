# v2 validation record — 2026-11-09

This is an offline/validation record, not a holdout claim. It records the first
real v2 trace-to-publication run and the four-task validation cohort.

## Train-to-publication run

- Run ID: `v2-train-officeval-spreadsheet-001`
- Trace: `train-officeval-spreadsheet-5c596cbd` from
  `workspace/runs/schema-live-officeval-20261106@2026-11-06T10:08`
- Router decision: create (`spreadsheet-formula-validation`)
- Preflight: `accept`
- Verification: `ReplayVerifier` pass
- Published skill: `v2-train-officeval-spreadsheet-001:generated-skill`
- Release/tree hash:
  `66d61aec1a400de52e790d678afa9f55bbf6014f63b43d9b5debe13b045c4bc1`
- Receipt:
  `.../inventory/skills/v2-train-officeval-spreadsheet-001-generated-ski-4bd56df905fc0b88/receipts/5a1ddfcca3897426775b08e398933e95de29821c5249af212fbc84e4c7ae3572.json`
- Receipt file SHA-256:
  `8d72f24ecfaa8bd194b06c16d5f3d6bbf1257df98e6c59c0d6ee5b17ee0d7095`
- Files: `SKILL.md` (`df797db61064…`), `scripts/validate_sheet.py` (`5d6f4f0826a4…`),
  `references/spreadsheet-formula-validation.md` (`eba28fbb8844…`),
  `evals/fixtures/spreadsheet-formula-validation.json` (`86f8f2767229…`)
- Source trace recorded in receipt: `train-officeval-spreadsheet-5c596cbd`
- Policy/config: `cli-policy-v1` / `cli-config-v1`
- No assets; no fabricated asset was added.

## Validation cohort

- Cohort ID: `v2-validation-20261109`
- Seed: `20261109`
- Train membership hash:
  `19edd26ea2aa2c30e1d036ec93b07e81bb4e823c99ab9250c780d00accbcf5fb`
- Validation membership hash:
  `669b548a7ccb1664acbac4a531073b949a15f18f5bf955e2d24bbe8ce9914c68`
- Validation tasks: `offer-letter-generator`, `software-dependency-audit`,
  `threejs-structure-parser`, `xlsx-recover-data`
- Domains: document-generation, security, threejs-graphics, finance-economics
- Task/group overlap with train: none
- `ada-bathroom-plan-repair` baseline timed out at 900 s and was replaced by
  `threejs-structure-parser` before analysis.

## Cells

| Task | Selected | Mode | Baseline | Treatment | Calls B/T | Seconds B/T | Admission |
|---|---|---:|---:|---:|---:|---:|---|
| offer-letter-generator | no | no-skill | 1 | inherited 1 | 35/35 | 89.9/89.9 | abstention, baseline inherited |
| software-dependency-audit | no | no-skill | 0 | inherited 0 | 37/37 | 180.0/180.0 | abstention, baseline inherited |
| threejs-structure-parser | no | no-skill | 0 | inherited 0 | 23/23 | 60.0/60.0 | abstention, baseline inherited |
| xlsx-recover-data | yes | with-skill | 0 | **1** | 45/12 | 150.0/30.0 | activated by SKILL.md read; pass; within budget |

The publisher initially created release directories with mode `700`, so the
non-root sandbox user could not read `/skills`. The publisher now normalizes
directories to `755` and files to `644`. The corrected standard `--skills-dir`
treatment was genuinely activated (`SKILL.md` read), passed the verifier, and
stayed within budget.

## Metrics

- Validation cells submitted: 4
- Admitted: 4
- Invalid exposure: 0
- Activated cells: 1 (xlsx, SKILL.md read)
- Selective policy: 2/4 = 50.0%; baseline: 1/4 = 25.0%; lift +25.0pp
- Activated effect: 1/1 = 100%; lift +100pp
- Regressions: 0
- Efficiency failures: 0
- Calls: 140/107; xlsx 45 -> 12
- Latency: 479.9 s / 359.9 s; xlsx 150.0 s -> 30.0 s
- Cost: `null` / unmeasured for every cell; no `$0` claim

## Bounded repair: deterministic recovery script

A general financial-workbook recovery script was added to the generated skill:

- `scripts/recover_financial_table.py`
- `evals/fixtures/recover-financial-table.json`

It solves rows from totals, infers missing totals from year-over-year evidence,
derives shares, YoY, CAGR, five-year change, and the five-year-window average,
and writes numeric values. Against the validation workbook it produces a
workbook that passes the task verifier **19/19 locally**.

This is a local executable-verifier result, not a benchmark result. The
benchmark treatment that exposed the script in the prompt did not complete
within the 600s wall budget and was stopped unscored. It is not counted as a
lift.

## Second validation cohort — partial, not a valid policy cohort

Disjoint baseline tasks from the catalog:

| Task | Domain | Baseline | Calls | Seconds |
|---|---|---:|---:|---:|
| exceltable-in-ppt | office-white-collar | 1 | 13 | 30 |
| pptx-reference-formatting | office-white-collar | 1 | 51 | 120 |
| data-to-d3 | software-engineering | 0 | 8 | 60 |
| dialogue-parser | software-engineering | 0.667 partial | 30 | 90 |
| dapt-intrusion-detection | cybersecurity | 0 | 30 | 210 |

Baseline complete passes: **2/4 = 50%**.

Selected treatments:

| Task | Exposure | Baseline | Treatment | Calls B/T | Seconds B/T |
|---|---|---|---:|---:|---:|---:|
| exceltable-in-ppt | `SKILL.md` read | 1 | 1 | 13/15 | 30/60 |
| dialogue-parser | `SKILL.md` read | 0.667 | 1.0 | 30/27 | 90/60 |

**Integrity exclusion:** the dialogue skill was generated from the dialogue train
run, and the benchmark task is the same dialogue-parser task. The 1.0 result is
a train replay, not a disjoint validation lift, and must not be used as policy
evidence.

The energy-domain task timed out and the first cybersecurity attempt failed its
sandbox CPU constraint. `dapt-intrusion-detection` completed as the third
domain.

Excluding the train-overlap dialogue cell, the valid second cohort is:

| Task | Domain | Baseline | Treatment |
|---|---|---:|---:|
| exceltable-in-ppt | office-white-collar | 1 | 1 |
| pptx-reference-formatting | office-white-collar | 1 | baseline inherited |
| data-to-d3 | software-engineering | 0 | baseline inherited |
| dapt-intrusion-detection | cybersecurity | 0 | baseline inherited |

- Valid cohort: 4 tasks / 3 domains
- Baseline: 2/4 = 50%
- Selective policy: 2/4 = 50%
- Lift: 0
- No training-independent second-cohort lift.

## Dialogue parser capability

A general dialogue-graph parser family was added to the planner. It parses
bracketed scenes, speaker lines, numbered choices, reachability, and DOT output.

- Local task verifier: **35/35 passed**
- Train-replay benchmark: **1.0**, `SKILL.md` read, 27 calls
- It is not counted as a validation lift because of the train/validation task
  overlap.


## Network-forensics development loop (not validation)

Added a generic Scapy-based PCAP metric extractor and network-forensics family.

- Local DAPT verifier: **37/37 passed**
- Baseline: 0.0, 30 calls, 210s
- First skill treatment: 0.0, 36 calls; 35/37 checks; agent overrode two
  task-defined analysis flags
- Updated skill instruction: use script flags verbatim
- Rerun: **1.0**, 16 calls, 60s, verified `SKILL.md` read, no efficiency failure

This is a **train replay** because the skill was generated from the DAPT baseline
trace. It demonstrates the intended run → trace → update → rerun loop, but it is
not a disjoint validation or holdout result.


## Data-visualization development loop (incomplete)

Added a `data-visualization` family with a D3 output-layout validator and an
implementation checklist.

- Skill generation: succeeded
- Benchmark rerun: **not scored**; the sandbox timed out during deepagents
  installation at the 600s wall cap, and a retry with a 1,200s execution budget
  timed out during agent execution. No verifier result was produced.
- No reward, exposure, or lift is claimed for this cell

The next retry must first confirm the data-to-d3 agent environment installs
within budget; otherwise it is an infrastructure exclusion.


## Fresh 16-task/8-domain holdout attempt — invalid

A pre-registered 16-task, 8-domain fresh catalog cohort was attempted on
2026-11-10. It did **not** complete:

- completed baselines: 6
- completed passes: 1 (`financial-modeling-qa`)
- completed failures: 5
- environment failures: 8 Docker build/agent-install failures
- remaining: 2 tasks not completed before the run was stopped
- sequential retries initially failed under four-way concurrency
- root cause: the Docker VM disk was 100% full; after removing stale
  containers/build cache, all eight previously failed task images built
  successfully
- retries produced: `pddl-tpp-planning` pass, `3d-scan-calc` pass,
  `threejs-to-obj` pass, `organize-messy-files` fail; `seismic-phase-picking`
  still errored
- validated cells so far: 10, passes 4 (financial-modeling-qa, pddl-tpp-planning,
  3d-scan-calc, threejs-to-obj), failures 6
- still unresolved: 6 cells; holdout remains incomplete and unscored

The incomplete cohort is **not** a valid holdout and is not scored. No 60%
claim can be derived from it.

## Gate

- Positive absolute lift: **yes on validation** (+25pp selective, +100pp activated)
- Activated-skill evidence: **one cell, complete pass**
- Skill actually used: **yes** (`SKILL.md` read)
- Second validation cohort warranted: **yes**, on a disjoint set; this is still
  validation, not a holdout result.
- Fresh sealed 16-task/8-domain holdout ready: **no**
- 60% milestone: **not claimed**
