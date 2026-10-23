"""Validated, atomic phase lifecycle envelopes."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


STATUSES = {"completed", "failed", "skipped", "timed_out"}


class EnvelopeError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def artifact_ref(path: Path, *, relative_to: Path | None = None) -> dict[str, str]:
    shown = path.resolve()
    if relative_to is not None:
        try:
            shown = shown.relative_to(relative_to.resolve())
        except ValueError:
            pass
    return {"path": str(shown), "sha256": sha256_file(path)}


def build_envelope(
    *,
    run_id: str,
    phase: str,
    item_id: str,
    implementation: dict[str, Any],
    status: str,
    started_at: str,
    finished_at: str | None = None,
    input_refs: list[dict[str, str]] | None = None,
    output_ref: dict[str, str] | None = None,
    decision: dict[str, Any] | None = None,
    measurements: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = {
        "schema_version": 1,
        "run_id": run_id,
        "phase": phase,
        "item_id": item_id,
        "implementation": implementation,
        "status": status,
        "input_refs": input_refs or [],
        "output_ref": output_ref,
        "decision": decision or {"disposition": status, "reason_codes": []},
        "measurements": measurements or {},
        "started_at": started_at,
        "finished_at": finished_at or datetime.now(UTC).isoformat(),
        "error": error,
    }
    validate_envelope(value)
    return value


def validate_envelope(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise EnvelopeError("phase envelope schema_version must be 1")
    for field in ("run_id", "phase", "item_id", "started_at", "finished_at"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise EnvelopeError(f"phase envelope {field} must be a non-empty string")
    if value.get("status") not in STATUSES:
        raise EnvelopeError(f"invalid phase envelope status {value.get('status')!r}")
    implementation = value.get("implementation")
    if not isinstance(implementation, dict):
        raise EnvelopeError("phase envelope implementation must be an object")
    for field in ("kind", "name", "version", "config_digest"):
        if not isinstance(implementation.get(field), str) or not implementation[field]:
            raise EnvelopeError(f"implementation {field} must be a non-empty string")
    if not isinstance(value.get("input_refs"), list):
        raise EnvelopeError("phase envelope input_refs must be an array")
    if not isinstance(value.get("measurements"), dict):
        raise EnvelopeError("phase envelope measurements must be an object")
    if value["status"] == "failed" and not isinstance(value.get("error"), dict):
        raise EnvelopeError("failed phase envelope requires an error object")
    return value


def write_envelope(path: Path, value: dict[str, Any]) -> None:
    validate_envelope(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)

