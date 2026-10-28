from __future__ import annotations

import json
from pathlib import Path


def build_report(store, target_id: str, output: str | Path) -> Path:
    counts = store.counts()
    statuses = {row[0]: row[1] for row in store.db.execute("SELECT status,count(*) FROM runs GROUP BY status")}
    error_kinds = {row[0] or "none": row[1] for row in store.db.execute("SELECT error_kind,count(*) FROM runs GROUP BY error_kind")}
    labels = list(store.db.execute("SELECT value_json,count(*) FROM labels WHERE name='task_success' GROUP BY value_json"))
    successes = sum(n for value, n in labels if json.loads(value) is True)
    total = sum(n for _, n in labels)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    text = f"""# Sampling report: {target_id}

## Summary

- Samples: {counts['samples']}
- Runs: {counts['runs']} ({statuses})
- Success rate: {successes / total if total else 0:.3f} ({successes}/{total})
- Adapter/infrastructure errors: {sum(v for k,v in error_kinds.items() if k != 'none')}
- Canonical events: {counts['events']}
- Trace feature records: {counts['trace_features']}

Raw immutable events and independent labels remain in SQLite. Reports contain aggregate values only; sensitive fields are redacted before persistence.
"""
    output.write_text(text)
    return output

