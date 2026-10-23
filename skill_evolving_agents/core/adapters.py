"""Mode-aware phase adapter execution."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Callable

from .phase_envelope import build_envelope


def band_decision(score: float, reject_below: float, accept_at: float) -> str:
    if reject_below >= accept_at:
        raise ValueError("reject_below must be lower than accept_at")
    if score < reject_below:
        return "rejected"
    if score >= accept_at:
        return "selected"
    return "escalate"


def execute_adapter(
    *,
    run_id: str,
    phase: str,
    item_id: str,
    config: dict[str, Any],
    implementation: dict[str, str],
    operation: Callable[[], dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    mode = config["mode"]
    started = datetime.now(UTC)
    clock = time.perf_counter_ns()
    if mode in {"disabled", "passthrough"}:
        result = None
        disposition = mode
        status = "skipped" if mode == "disabled" else "completed"
    else:
        result = operation()
        disposition = str(result.get("disposition", "completed"))
        status = "completed"
        if mode == "observe":
            disposition = "observed_" + disposition
    envelope = build_envelope(
        run_id=run_id,
        phase=phase,
        item_id=item_id,
        implementation=implementation,
        status=status,
        started_at=started.isoformat(),
        decision={"disposition": disposition, "mode": mode, "reason_codes": []},
        measurements={"wall_ms": round((time.perf_counter_ns() - clock) / 1e6, 3)},
    )
    return result if mode == "enabled" else None, envelope

