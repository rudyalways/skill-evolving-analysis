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

Every case starts as `"status": "pending"` and with
`"labeling.origin": "agent_synthetic"`. These are **draft hypotheses authored by
the coding agent**, not validated human-need ground truth. The runner assigns:

- `draft` — not approved, or approved by one reviewer;
- `silver` — one reviewer;
- `gold` — two independent reviewers covering the required roles
  (`domain_expert`, `user_advocate`);
- `rejected` — explicitly rejected.

To approve, inspect the trace, diagnosis, and targeted action, then add
reviewers:

```json
"review": {
  "status": "approved",
  "reviewer": "name",
  "reviewers": [
    {"name": "domain reviewer", "role": "domain_expert"},
    {"name": "user reviewer", "role": "user_advocate"}
  ],
  "required_roles": ["domain_expert", "user_advocate"],
  "notes": "Why this decision is correct."
}
```

Use `--require-reviewed` to require approval, or `--require-gold` to require
two independent reviewers with the required roles. A normal run still executes
draft cases for inspection, but the scorecard and dashboard mark them as draft
and warn that they are not ground truth.

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
