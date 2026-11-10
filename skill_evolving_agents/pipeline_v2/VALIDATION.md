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

## Gate

- Positive absolute lift: **yes on validation** (+25pp selective, +100pp activated)
- Activated-skill evidence: **one cell, complete pass**
- Skill actually used: **yes** (`SKILL.md` read)
- Second validation cohort warranted: **yes**, on a disjoint set; this is still
  validation, not a holdout result.
- Fresh sealed 16-task/8-domain holdout ready: **no**
- 60% milestone: **not claimed**
