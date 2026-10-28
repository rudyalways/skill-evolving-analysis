from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from matrix_sampler.redaction import redact


def _messages(row: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(row.get("messages"), list):
        return row["messages"]
    if isinstance(row.get("turns"), list):
        return [{"role": x.get("role", "unknown"), "content": x.get("content", x.get("text", ""))} for x in row["turns"]]
    return [{"role": "user", "content": row.get("prompt", "")}, {"role": "assistant", "content": row.get("response", "")}]


def ingest(path: str | Path, store) -> dict[str, Any]:
    path = Path(path)
    counts, tools, failures, durations, records = Counter(), Counter(), Counter(), [], 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        messages = _messages(row)
        text = " ".join(str(x.get("content", "")) for x in messages)
        trace_id = "trc_" + hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:20]
        lower = text.lower()
        domain = "software" if any(k in lower for k in ("code", "file", "test", "python")) else "knowledge_work"
        scenario = "debug" if any(k in lower for k in ("error", "fail", "bug")) else "explain"
        counts[(domain, scenario)] += 1
        for event in row.get("tool_events", row.get("events", [])):
            tools[str(event.get("tool", event.get("name", "unknown")))] += 1
        outcome = row.get("outcome", row.get("status", "unknown"))
        if str(outcome).lower() in {"failed", "failure", "error"}:
            failures[scenario] += 1
        if row.get("duration_ms") is not None:
            durations.append(float(row["duration_ms"]))
        feature = {"schema_version": 1, "trace_id": trace_id, "domain": domain, "scenario": scenario, "outcome": outcome, "observed_at": row.get("timestamp"), "excerpt": redact(text[:240]), "source_sha256": hashlib.sha256(line.encode()).hexdigest()}
        store.put_json("trace_features", "trace_id", trace_id, "feature_json", feature)
        records += 1
    total = max(records, 1)
    proposals = []
    declared = {"debug", "test", "implement", "explain"}
    observed = {scenario for _, scenario in counts}
    for missing in sorted(declared - observed):
        proposals.append({"status": "ood_candidate", "axis": "task_scenario_shift", "label": missing, "reason_codes": ["absent_from_trace_sample", "declared_capability_unobserved"], "confidence": min(.9, .5 + records / 100)})
    summary = {"schema_version": 1, "source": str(path), "records": records, "id_frequency": [{"domain": d, "scenario": s, "count": n, "frequency": n / total} for (d, s), n in sorted(counts.items())], "tool_counts": dict(tools), "failure_counts": dict(failures), "duration_ms": {"min": min(durations) if durations else None, "max": max(durations) if durations else None}, "ood_proposals": proposals, "generated_at": datetime.now(timezone.utc).isoformat()}
    return summary

