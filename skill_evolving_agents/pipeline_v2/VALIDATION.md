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
- Files: `SKILL.md`, `scripts/validate_sheet.py`,
  `references/spreadsheet-formula-validation.md`,
  `evals/fixtures/spreadsheet-formula-validation.json`
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
| xlsx-recover-data | yes | with-skill | 0 | 0 | 45/83 | 150.0/209.9 | **invalid: skill not activated** |

The xlsx treatment was genuinely run with `with-skill`, but the trajectory
audit observed no `SKILL.md` read and no mounted-skill injection. It is excluded
from every scored view. It is not treated as an abstention.

## Metrics

- Validation cells submitted: 4
- Admitted: 3 (all abstentions)
- Invalid exposure: 1 (`treatment-skill-not-activated`)
- Activated cells: 0
- Selective policy: 1/3 = 33.3%; baseline: 1/3 = 33.3%; lift 0
- Activated effect: unmeasured (0 cells)
- Regressions: 0
- Efficiency failures: 0 admitted; xlsx treatment 0
- Calls: admitted 95/95; xlsx 45 -> 83
- Latency: admitted 329.9 s / 329.9 s; xlsx 150.0 s -> 209.9 s
- Cost: `null` / unmeasured for every cell; no `$0` claim

## Gate

- Positive absolute lift: **no**
- Activated-skill evidence: **none**
- Skill actually used: **no** for the one selected cell
- Second validation cohort warranted: **not yet**; first fix activation and
  produce a selected cell with observable skill use.
- Fresh sealed 16-task/8-domain holdout ready: **no**
- 60% milestone: **not claimed**
