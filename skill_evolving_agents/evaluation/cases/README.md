# Stage benchmark cases

Cases are addressed by `stage`, not by their position in a workflow. A case can
be moved, reordered, or reused when the workflow composition changes.

Each case contains:

- `stage`: the contract boundary being tested.
- `split`: `calibration` or `heldout`.
- `review`: `pending`, `approved`, or `rejected`, with reviewer and notes.
- `sessions`: optional synthetic trace evidence, in the same turn form used by
  the funnel benchmark.
- `golden.diagnosis.gaps`: the intended capability gap and its evidence.
- `golden.action`: the targeted operation: create, update, merge, split,
  delete, or no_change.
- `expect`: behavioral expectations such as allowed operation types, gap types,
  resource decisions, detector findings, and admission.

The golden action is compiled into the real Goal contract and validated with
`common/pipeline_contracts.py`. The golden diagnosis is validated at the same
contract boundary. This catches malformed labels before they become review
evidence.

## Review

Every case starts as `"status": "pending"`. A reviewer should inspect the trace,
diagnosis, and targeted action, then edit the case:

```json
"review": {
  "status": "approved",
  "reviewer": "name",
  "notes": "Why this decision is correct."
}
```

Use `--require-reviewed` to make pending or rejected cases fail the run. The
normal run still executes pending cases so they can be inspected, but the
scorecard and dashboard report them separately.

## Run

```bash
python3 evaluation/benchmark_core.py \
  --cases evaluation/cases \
  --out /tmp/stage-benchmark.json \
  --dashboard /tmp/stage-benchmark.html
```

Filter by stage or split:

```bash
python3 evaluation/benchmark_core.py --stage goal --split calibration
python3 evaluation/benchmark_core.py --require-reviewed
```

The dashboard is a standalone HTML report: summary cards, per-stage results,
case table, review state, and expandable golden diagnosis/action details.
