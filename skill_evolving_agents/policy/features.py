"""Extract bounded policy features and transformer-ready typed tokens."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import stable_digest, validate_feature_record


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def extract_policy_features(
    workspace: Path,
    *,
    run_id: str,
    profile: dict[str, Any],
    execution_config: dict[str, Any],
) -> dict[str, Any]:
    findings = []
    for path in sorted((workspace / "traces/derived/findings").glob("*/finding.json")):
        row = _read(path)
        if row:
            findings.append(row)
    detectors = Counter(str(row.get("detector") or "unknown") for row in findings)
    severities = Counter(str(row.get("severity") or "unknown") for row in findings)
    confidence = [
        float(row["confidence"])
        for row in findings
        if isinstance(row.get("confidence"), (int, float))
        and not isinstance(row.get("confidence"), bool)
    ]
    evidence = [len(row.get("evidence") or []) for row in findings]
    tokens = []
    for row in findings[:128]:
        tokens.append(
            {
                "type": "FINDING",
                "id": row.get("signal_id"),
                "detector": row.get("detector"),
                "severity": row.get("severity"),
                "confidence": row.get("confidence"),
                "score": row.get("score"),
                "evidence_count": len(row.get("evidence") or []),
            }
        )
    for phase, selection in sorted((profile.get("phases") or {}).items()):
        tokens.append(
            {
                "type": "ALGORITHM",
                "phase": phase,
                "algorithm": selection.get("algorithm"),
                "mode": selection.get("mode"),
                "kind": selection.get("kind"),
            }
        )
    record = {
        "schema_version": 1,
        "run_id": run_id,
        "feature_schema": "policy-features/v1",
        "created_at": datetime.now(UTC).isoformat(),
        "dense": {
            "finding_count": len(findings),
            "mean_confidence": sum(confidence) / len(confidence) if confidence else None,
            "mean_evidence_count": sum(evidence) / len(evidence) if evidence else None,
            "agent_call_cap": (execution_config.get("budgets") or {}).get("hard_agent_call_cap"),
            "max_cost_tier": execution_config.get("max_cost_tier"),
        },
        "presence": {
            "findings": bool(findings),
            "confidence": bool(confidence),
            "evidence": bool(evidence),
        },
        "distributions": {
            "detectors": dict(detectors),
            "severities": dict(severities),
        },
        "tokens": tokens,
        "profile_digest": profile.get("config_digest"),
        "execution_config_digest": execution_config.get("config_digest"),
    }
    record["feature_digest"] = stable_digest(record)
    return validate_feature_record(record)
