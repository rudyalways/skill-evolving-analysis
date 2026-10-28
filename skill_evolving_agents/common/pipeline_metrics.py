"""Pipeline timing spans with JSONL, SQLite, and Chrome Trace outputs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

try:
    from common import skill_resources
except ImportError:
    import skill_resources  # type: ignore[no-redef]


_LOCK = threading.RLock()
_INT31 = 0x7FFFFFFF


def trace_pid(run_id: str) -> int:
    """Process id that fits in a signed 32-bit Chrome trace field."""
    return int(hashlib.sha256(run_id.encode()).hexdigest()[:8], 16) & _INT31


def trace_tid(phase: str, item: str) -> int:
    """One track per phase and item.

    OS thread ids are pointer-sized and collide once Perfetto keeps 32 bits, so
    parallel complete slices were drawn on one thread and spilled.
    """
    digest = hashlib.sha256(f"{phase}\n{item}".encode()).digest()
    return int.from_bytes(digest[:4], "big") & _INT31 or 1


def _initialize(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_spans (
            span_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            phase TEXT NOT NULL,
            item TEXT NOT NULL,
            category TEXT NOT NULL,
            started_at TEXT NOT NULL,
            started_at_us INTEGER NOT NULL,
            duration_us INTEGER NOT NULL,
            status TEXT NOT NULL,
            backend TEXT,
            model TEXT,
            thread_id INTEGER NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS pipeline_spans_run "
        "ON pipeline_spans(run_id, started_at_us)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS pipeline_spans_phase "
        "ON pipeline_spans(phase, category)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_recall_observations (
            run_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            skill TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            recalled INTEGER NOT NULL,
            rank INTEGER,
            score REAL,
            PRIMARY KEY (run_id, scope, skill)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS skill_recall_by_skill "
        "ON skill_recall_observations(skill, observed_at)"
    )


def _databases(workspace: Path) -> list[Path]:
    local = workspace / "logs/metrics.sqlite"
    shared = workspace.parents[1] / "metrics.sqlite"
    return [local] if local == shared else [local, shared]


def clear_shared_run(workspace: Path) -> None:
    """Remove stale cross-run rows when a run id is intentionally recreated."""
    shared = workspace.resolve().parents[1] / "metrics.sqlite"
    if not shared.is_file():
        return
    with _LOCK, sqlite3.connect(shared, timeout=30) as connection:
        _initialize(connection)
        connection.execute(
            "DELETE FROM pipeline_spans WHERE run_id = ?",
            (workspace.name,),
        )
        connection.execute(
            "DELETE FROM skill_recall_observations WHERE run_id = ?",
            (workspace.name,),
        )


def replace_shared_run(workspace: Path) -> None:
    """Replace one shared run with its authoritative local timing rows."""
    workspace = workspace.resolve()
    local = workspace / "logs/metrics.sqlite"
    shared = workspace.parents[1] / "metrics.sqlite"
    if not local.is_file():
        clear_shared_run(workspace)
        return
    with _LOCK:
        with sqlite3.connect(local, timeout=30) as source:
            try:
                rows = source.execute(
                    "SELECT * FROM pipeline_spans WHERE run_id = ? "
                    "ORDER BY started_at_us",
                    (workspace.name,),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            try:
                recall_rows = source.execute(
                    "SELECT * FROM skill_recall_observations WHERE run_id = ?",
                    (workspace.name,),
                ).fetchall()
            except sqlite3.OperationalError:
                recall_rows = []
        with sqlite3.connect(shared, timeout=30) as destination:
            _initialize(destination)
            destination.execute(
                "DELETE FROM pipeline_spans WHERE run_id = ?",
                (workspace.name,),
            )
            destination.execute(
                "DELETE FROM skill_recall_observations WHERE run_id = ?",
                (workspace.name,),
            )
            if rows:
                destination.executemany(
                    "INSERT INTO pipeline_spans VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
            if recall_rows:
                destination.executemany(
                    "INSERT INTO skill_recall_observations VALUES "
                    "(?, ?, ?, ?, ?, ?, ?)",
                    recall_rows,
                )


def record_skill_recall_observations(
    workspace: Path,
    scope: str,
    inventory_skills: list[str],
    recalled: list[dict[str, Any]],
) -> None:
    """Persist one exposure/retrieval observation for every inventory skill."""
    workspace = workspace.resolve()
    run_id = workspace.name
    observed_at = datetime.now(UTC).isoformat()
    ranked = {
        str(row.get("skill")): (index, float(row.get("score") or 0))
        for index, row in enumerate(recalled, start=1)
        if isinstance(row, dict) and row.get("skill")
    }
    rows = [
        (
            run_id,
            scope,
            skill,
            observed_at,
            1 if skill in ranked else 0,
            ranked.get(skill, (None, None))[0],
            ranked.get(skill, (None, None))[1],
        )
        for skill in sorted(set(inventory_skills))
    ]
    with _LOCK:
        for database in _databases(workspace):
            database.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(database, timeout=30) as connection:
                _initialize(connection)
                connection.executemany(
                    "INSERT OR REPLACE INTO skill_recall_observations VALUES "
                    "(?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )


def _thread_name(pid: int, tid: int, item: str) -> dict[str, Any]:
    return {
        "name": "thread_name",
        "ph": "M",
        "pid": pid,
        "tid": tid,
        "args": {"name": item},
    }


def _process_name(pid: int, run_id: str) -> dict[str, Any]:
    return {
        "name": "process_name",
        "ph": "M",
        "pid": pid,
        "args": {"name": run_id},
    }


def _write_chrome_trace(
    workspace: Path, event: dict[str, Any], item: str
) -> None:
    path = workspace / "logs/pipeline-trace.json"
    events: list[dict[str, Any]] = []
    if path.is_file():
        try:
            value = json.loads(path.read_text())
            if isinstance(value, dict) and isinstance(value.get("traceEvents"), list):
                events = value["traceEvents"]
        except json.JSONDecodeError:
            events = []
    named = any(
        row.get("ph") == "M"
        and row.get("name") == "thread_name"
        and row.get("pid") == event["pid"]
        and row.get("tid") == event["tid"]
        for row in events
    )
    process_named = any(
        row.get("ph") == "M"
        and row.get("name") == "process_name"
        and row.get("pid") == event["pid"]
        for row in events
    )
    if not process_named:
        events.append(
            _process_name(event["pid"], str(event.get("args", {}).get("run_id", "")))
        )
    if not named:
        events.append(_thread_name(event["pid"], event["tid"], item))
    events.append(event)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"traceEvents": events}, indent=2, ensure_ascii=False) + "\n"
    )
    temporary.replace(path)


def record_span(
    workspace: Path,
    *,
    phase: str,
    item: str,
    category: str,
    started_at: datetime,
    started_at_us: int,
    duration_us: int,
    status: str,
    backend: str | None = None,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
    instant: bool = False,
) -> None:
    """Persist one timing span, or an instant audit mark, to all sinks."""
    workspace = workspace.resolve()
    span_id = uuid.uuid4().hex
    thread_id = threading.get_ident()
    run_id = workspace.name
    metadata = metadata or {}
    if not instant and duration_us <= 0:
        duration_us = 1
    row = (
        span_id,
        run_id,
        phase,
        item,
        category,
        started_at.isoformat(),
        started_at_us,
        max(0, duration_us),
        status,
        backend,
        model,
        thread_id,
        json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    )
    log_record = {
        "span_id": span_id,
        "run_id": run_id,
        "phase": phase,
        "item": item,
        "category": category,
        "started_at": started_at.isoformat(),
        "duration_ms": round(max(0, duration_us) / 1000, 3),
        "status": status,
        "backend": backend,
        "model": model,
        "thread_id": thread_id,
        "metadata": metadata,
        "instant": instant,
    }
    trace_event: dict[str, Any] = {
        "name": phase,
        "cat": category,
        "ph": "i" if instant else "X",
        "ts": started_at_us,
        "pid": trace_pid(run_id),
        "tid": trace_tid(phase, item),
        "args": {
            "run_id": run_id,
            "item": item,
            "status": status,
            "backend": backend,
            "model": model,
            **metadata,
        },
    }
    if instant:
        trace_event["s"] = "t"
    else:
        trace_event["dur"] = max(0, duration_us)
    with _LOCK:
        log = workspace / "logs/pipeline-timings.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as stream:
            stream.write(json.dumps(log_record, ensure_ascii=False) + "\n")
        if instant or category == "audit":
            audit = workspace / "logs/audit.jsonl"
            with audit.open("a") as stream:
                stream.write(json.dumps(log_record, ensure_ascii=False) + "\n")
        _write_chrome_trace(workspace, trace_event, item)
        for database in _databases(workspace):
            database.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(database, timeout=30) as connection:
                _initialize(connection)
                connection.execute(
                    "INSERT INTO pipeline_spans VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    row,
                )


@contextmanager
def span(
    workspace: Path,
    phase: str,
    item: str,
    category: str,
    *,
    backend: str | None = None,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[None]:
    """Measure a phase and persist it even when the phase fails."""
    started_at = datetime.now(UTC)
    started_at_us = time.time_ns() // 1000
    status = "ok"
    try:
        yield
    except BaseException:
        status = "error"
        raise
    finally:
        duration_us = time.time_ns() // 1000 - started_at_us
        record_span(
            workspace,
            phase=phase,
            item=item,
            category=category,
            started_at=started_at,
            started_at_us=started_at_us,
            duration_us=duration_us,
            status=status,
            backend=backend,
            model=model,
            metadata=metadata,
        )


def record_instant(
    workspace: Path,
    phase: str,
    item: str,
    metadata: dict[str, Any] | None = None,
    *,
    status: str = "ok",
) -> None:
    """Mark a decision on the Chrome trace without a duration."""
    record_span(
        workspace,
        phase=phase,
        item=item,
        category="audit",
        started_at=datetime.now(UTC),
        started_at_us=time.time_ns() // 1000,
        duration_us=0,
        status=status,
        metadata=metadata,
        instant=True,
    )


def peak_concurrency(rows: list[dict[str, Any]]) -> int:
    """How many spans of this set were running at the same instant."""
    events: list[tuple[int, int]] = []
    for row in rows:
        start = int(row["started_at_us"])
        end = start + max(0, int(row["duration_us"]))
        events.append((start, 1))
        events.append((end, -1))
    events.sort(key=lambda item: (item[0], item[1]))
    current = 0
    peak = 0
    for _timestamp, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    raw = row.get("metadata_json")
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def summarize_spans(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Wall time, overlap, and the fields needed to check a timing claim."""
    if not rows:
        return {
            "wall_seconds": 0.0,
            "started_at": None,
            "ended_at": None,
            "phases": [],
            "spans": [],
        }
    start = min(int(row["started_at_us"]) for row in rows)
    end = max(
        int(row["started_at_us"]) + max(0, int(row["duration_us"])) for row in rows
    )
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["phase"]), str(row["category"]))].append(row)
    phases: list[dict[str, Any]] = []
    for (phase, category), group in sorted(grouped.items()):
        durations = [max(0, int(row["duration_us"])) / 1_000_000 for row in group]
        group_start = min(int(row["started_at_us"]) for row in group)
        group_end = max(
            int(row["started_at_us"]) + max(0, int(row["duration_us"]))
            for row in group
        )
        ordered = sorted(durations)
        phases.append(
            {
                "phase": phase,
                "category": category,
                "count": len(group),
                "sum_seconds": round(sum(durations), 3),
                "wall_seconds": round((group_end - group_start) / 1_000_000, 3),
                "p50_seconds": round(ordered[len(ordered) // 2], 3),
                "max_seconds": round(max(durations), 3),
                "peak_concurrency": peak_concurrency(group),
            }
        )
    spans: list[dict[str, Any]] = []
    for row in rows:
        metadata = _metadata(row)
        spans.append(
            {
                "phase": row["phase"],
                "item": row["item"],
                "category": row["category"],
                "started_at": row["started_at"],
                "duration_ms": round(max(0, int(row["duration_us"])) / 1000, 3),
                "status": row["status"],
                "backend": row.get("backend"),
                "model": row.get("model"),
                "queue_wait_ms": metadata.get("queue_wait_ms"),
                "workers": metadata.get("workers"),
                "pool_items": metadata.get("pool_items"),
                "batch_index": metadata.get("batch_index"),
                "batch_count": metadata.get("batch_count"),
                "conflicts": metadata.get("conflicts"),
                "operation": metadata.get("operation"),
                "attempt": metadata.get("attempt"),
                "bundle_size": metadata.get("bundle_size"),
                "super_score": metadata.get("super_score"),
                "slice_present": metadata.get("slice_present"),
                "slice_count": metadata.get("slice_count"),
                "slice_user_turns": metadata.get("slice_user_turns"),
                "slice_tokens": metadata.get("slice_tokens"),
                "slice_max_tokens": metadata.get("slice_max_tokens"),
                "slice_truncated": metadata.get("slice_truncated"),
                "tool_events": metadata.get("tool_events"),
                "session_lines": metadata.get("session_lines"),
                "session_log": metadata.get("session_log"),
                "session_cwd": metadata.get("session_cwd"),
                "decision": metadata.get("decision"),
                "reason": metadata.get("reason"),
                "severity": metadata.get("severity"),
                "confidence": metadata.get("confidence"),
                "score": metadata.get("score"),
                "match_score": metadata.get("match_score"),
                "min_super_score": metadata.get("min_super_score"),
                "judge_action": metadata.get("judge_action"),
                "judge_to": metadata.get("judge_to"),
                "retries_used": metadata.get("retries_used"),
                "retry_budget": metadata.get("retry_budget"),
                "will_retry": metadata.get("will_retry"),
                "overall_status": metadata.get("overall_status"),
                "failed_skills": metadata.get("failed_skills"),
                "disposition": metadata.get("disposition"),
                "op_count": metadata.get("op_count"),
                "detail": metadata,
            }
        )
    return {
        "wall_seconds": round(max(end - start, 0) / 1_000_000, 3),
        "started_at": min(str(row["started_at"]) for row in rows),
        "ended_at": datetime.fromtimestamp(end / 1_000_000, UTC).isoformat(),
        "phases": phases,
        "spans": spans,
    }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def collect_phase_metrics(
    workspace: Path, spans: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Build an honest per-phase funnel from deterministic run artifacts.

    Coverage and outcomes are measured. Precision/correctness remain null unless
    human relevance labels or held-out behavioral replay are present.
    """
    workspace = workspace.resolve()
    spans = spans or []
    signal_root = workspace / "traces/derived/signals"
    findings = _read_jsonl(signal_root / "findings.jsonl")
    decisions = _read_jsonl(signal_root / "selection-decisions.jsonl")
    selected = sum(row.get("disposition") == "selected" for row in decisions)
    dispositions: dict[str, int] = defaultdict(int)
    for row in decisions:
        dispositions[str(row.get("disposition") or "unknown")] += 1
    manifest = _read_json(
        workspace / "traces/derived/normalized/manifest.json"
    )
    turn_count = (
        int(manifest.get("turn_count") or 0)
        if isinstance(manifest, dict)
        else 0
    )

    diagnoses = [
        value
        for path in (workspace / "run").glob("*/diagnosis.json")
        if isinstance(value := _read_json(path), dict)
    ]
    diagnosis_gaps = [
        gap
        for value in diagnoses
        for gap in (
            (value.get("skill_capabilities_missing") or [])
            + (value.get("newly_detected_skill_capabilites_missing") or [])
        )
    ]
    diagnosis_confidences = [
        float(gap["confidence"])
        for gap in diagnosis_gaps
        if isinstance(gap, dict)
        and isinstance(gap.get("confidence"), (int, float))
        and not isinstance(gap.get("confidence"), bool)
    ]
    newly_detected_gaps = sum(
        len(value.get("newly_detected_skill_capabilites_missing") or [])
        for value in diagnoses
    )
    diagnosis_spans = [
        row for row in spans if row.get("phase") == "label-traces-cluster"
    ]
    evolution_gate = _read_json(
        workspace / "traces/derived/evolution-gate.json"
    )
    gate_decisions = (
        evolution_gate.get("decisions") or []
        if isinstance(evolution_gate, dict)
        else []
    )
    admitted_scopes = (
        sum(
            isinstance(row, dict) and row.get("disposition") == "selected"
            for row in gate_decisions
        )
        if gate_decisions
        else selected
    )
    truncated_slices = sum(
        bool(_metadata(row).get("slice_truncated"))
        for row in diagnosis_spans
    )

    matching_files = list((workspace / "run").glob("*/label-matching.json"))
    matched_scopes = 0
    top_scores: list[float] = []
    for path in matching_files:
        document = _read_json(path)
        clusters = document.get("clusters") if isinstance(document, dict) else []
        scope_has_match = False
        for cluster in clusters or []:
            if not isinstance(cluster, dict):
                continue
            skills = cluster.get("skills") or []
            if skills:
                scope_has_match = True
            numeric = [
                float(skill["score"])
                for skill in skills
                if isinstance(skill, dict)
                and isinstance(skill.get("score"), (int, float))
                and not isinstance(skill.get("score"), bool)
            ]
            if numeric:
                top_scores.append(max(numeric))
        matched_scopes += scope_has_match

    pipeline_summary = _read_json(workspace / "run/pipeline-summary.json")
    scopes = (
        pipeline_summary.get("scopes") or []
        if isinstance(pipeline_summary, dict)
        else []
    )
    operations = (
        pipeline_summary.get("operations") or []
        if isinstance(pipeline_summary, dict)
        else []
    )
    changed_scopes = sum(
        isinstance(scope, dict) and scope.get("disposition") != "no_change"
        for scope in scopes
    )
    no_change_scopes = sum(
        isinstance(scope, dict) and scope.get("disposition") == "no_change"
        for scope in scopes
    )
    idempotent_scopes = sum(
        isinstance(scope, dict)
        and "exact finding was already applied" in str(scope.get("reason") or "").lower()
        for scope in scopes
    )
    accepted = sum(
        isinstance(operation, dict) and operation.get("accepted") is True
        for operation in operations
    )
    resource_decisions = _read_jsonl(
        signal_root / "resource-opportunity-decisions.jsonl"
    )
    converged_resource_opportunities = sum(
        isinstance(row, dict)
        and row.get("disposition") in {"suppressed", "rejected"}
        and bool(
            {"equivalent-resource-exists", "equivalent-existing-script"}
            & {
                str(code)
                for code in (row.get("reason_codes") or [])
                if isinstance(code, str)
            }
        )
        for row in resource_decisions
    )
    # A replay can converge before Goal: the detector suppresses a resource
    # whose authored equivalent already exists, so the finding never becomes a
    # scope. That is idempotency, not a failure to propose an action. Keep the
    # raw acceptance counts honest but mark consumer targets as converged.
    converged_replay = (
        changed_scopes == 0
        and accepted == 0
        and (idempotent_scopes + converged_resource_opportunities) > 0
    )
    novel_goal_scopes = max(len(scopes) - idempotent_scopes, 0)
    profile = _read_json(workspace / "run/config/pipeline-profile.json")
    funnel_targets = (
        profile.get("funnel_targets") or []
        if isinstance(profile, dict)
        else {}
    )
    if not isinstance(funnel_targets, dict):
        funnel_targets = {}
    action_count_distribution: dict[str, int] = defaultdict(int)
    for scope in scopes:
        if isinstance(scope, dict):
            action_count_distribution[str(int(scope.get("operation_count") or 0))] += 1
    operation_type_distribution: dict[str, int] = defaultdict(int)
    accepted_operation_type_distribution: dict[str, int] = defaultdict(int)
    for operation in operations:
        if isinstance(operation, dict):
            operation_type = str(
                operation.get("op")
                or operation.get("operation")
                or operation.get("action")
                or "unknown"
            )
            operation_type_distribution[operation_type] += 1
            if operation.get("accepted") is True:
                accepted_operation_type_distribution[operation_type] += 1

    funnel_rates = {
        "diagnosis_rate": _rate(len(diagnoses), selected),
        "goal_decision_rate": _rate(len(scopes), selected),
        "action_scope_rate": _rate(changed_scopes, selected),
        "action_given_goal_rate": _rate(changed_scopes, len(scopes)),
        "novel_action_scope_rate": _rate(changed_scopes, novel_goal_scopes),
        "proposal_rate": _rate(len(operations), selected),
        "proposal_given_goal_rate": _rate(len(operations), len(scopes)),
        "novel_proposal_rate": _rate(len(operations), novel_goal_scopes),
        "final_acceptance_rate": _rate(accepted, selected),
        "acceptance_given_goal_rate": _rate(accepted, len(scopes)),
        "novel_final_acceptance_rate": _rate(accepted, novel_goal_scopes),
        "proposal_acceptance_rate": _rate(accepted, len(operations)),
    }
    consumer_targets = {
        "action_scope_rate",
        "action_given_goal_rate",
        "novel_action_scope_rate",
        "proposal_rate",
        "proposal_given_goal_rate",
        "novel_proposal_rate",
        "final_acceptance_rate",
        "acceptance_given_goal_rate",
        "novel_final_acceptance_rate",
        "proposal_acceptance_rate",
    }
    target_evaluation = {}
    for name, target in funnel_targets.items():
        if name not in funnel_rates or not isinstance(target, (int, float)):
            continue
        actual = funnel_rates[name]
        if converged_replay and name in consumer_targets:
            target_evaluation[name] = {
                "target": float(target),
                "actual": actual,
                "delta": None,
                "status": "converged",
                "applicable": False,
            }
            continue
        target_evaluation[name] = {
            "target": float(target),
            "actual": actual,
            "delta": (
                round(float(actual) - float(target), 6)
                if actual is not None
                else None
            ),
            "status": (
                "met"
                if actual is not None and float(actual) >= float(target)
                else "missed" if actual is not None else "unavailable"
            ),
        }

    reduction = _read_json(workspace / "run/goal-reduction.json")
    reduction_decisions = (
        reduction.get("decisions") or []
        if isinstance(reduction, dict)
        else []
    )
    reduction_counts: dict[str, int] = defaultdict(int)
    for row in reduction_decisions:
        if isinstance(row, dict):
            reduction_counts[str(row.get("decision") or "unknown")] += 1

    verification_artifacts = [
        value
        for path in (workspace / "run").glob("*/ops/*/verification.json")
        if isinstance(value := _read_json(path), dict)
    ]
    verifications = [
        value
        for value in verification_artifacts
        if isinstance(value.get("feedback"), dict)
    ]
    skipped_verifications = sum(
        value.get("status") == "skipped"
        for value in verification_artifacts
    )
    failed_verifications = sum(
        value.get("status") == "failed"
        for value in verification_artifacts
    )
    verification_passes = 0
    replay_available = 0
    replay_passes = 0
    for verification in verifications:
        feedback = verification.get("feedback") or {}
        verification_passes += feedback.get("overall_status") == "pass"
        replay = feedback.get("replay") or {}
        replay_available += replay.get("available") is True
        replay_passes += (
            replay.get("available") is True and replay.get("status") == "pass"
        )

    judge_rows = [
        _metadata(row) for row in spans if row.get("phase") == "judge-decision"
    ]
    judge_actions: dict[str, int] = defaultdict(int)
    first_attempt_passes = 0
    first_attempts = 0
    for metadata in judge_rows:
        action = str(metadata.get("judge_action") or "unknown")
        judge_actions[action] += 1
        if metadata.get("attempt") == 1:
            first_attempts += 1
            first_attempt_passes += action == "pass"

    optimize_rows = [row for row in spans if row.get("phase") == "optimize"]
    optimize_first_attempts = sum(
        _metadata(row).get("attempt") == 1 for row in optimize_rows
    )
    optimize_attempt_twos = sum(
        _metadata(row).get("attempt") == 2 for row in optimize_rows
    )
    resource_documents = [
        value
        for path in (workspace / "run").glob("*/ops/*/resource-metrics.json")
        if isinstance(value := _read_json(path), dict)
    ]
    resource_summary = skill_resources.aggregate_resource_metrics(
        resource_documents
    )
    actual_agent_calls = sum(
        row.get("category") == "llm_agent" for row in spans
    )
    prefiltered_scopes = max(selected - admitted_scopes, 0)
    # Every scope admitted past the semantic/evidence filter would otherwise
    # require one Diagnosis and one Goal call. Later Optimize/Verify calls are
    # operation-dependent, so they are deliberately excluded from this
    # conservative counterfactual.
    estimated_calls_avoided = prefiltered_scopes * 2
    counterfactual_agent_calls = actual_agent_calls + estimated_calls_avoided

    warnings: list[str] = []
    if truncated_slices:
        warnings.append(
            f"{truncated_slices}/{len(diagnosis_spans)} diagnosis slices were truncated"
        )
    if verifications and replay_available == 0:
        warnings.append("all verification outcomes are structural; no replay was available")
    if isinstance(reduction, dict) and float(reduction.get("min_super_score") or 0) == 0:
        warnings.append("min_super_score is zero, so the edit quality gate is inactive")
    if matching_files and matched_scopes < len(matching_files):
        warnings.append(
            f"{len(matching_files) - matched_scopes}/{len(matching_files)} scopes had no recalled skill"
        )
    missed_targets = [
        name
        for name, result in target_evaluation.items()
        if result["status"] == "missed"
    ]
    if converged_replay:
        warnings.append(
            "converged replay: "
            f"{idempotent_scopes} exact finding scope(s) and "
            f"{converged_resource_opportunities} equivalent resource "
            "opportunit(ies) were already applied"
        )
    if missed_targets:
        warnings.append(
            "funnel targets missed: " + ", ".join(sorted(missed_targets))
        )

    return {
        "schema_version": 1,
        "run_id": workspace.name,
        "metric_semantics": {
            "measured": (
                "artifact coverage, deterministic validation, timing, replay "
                "availability, retry decisions, publication outcomes, and "
                "resource use or execution observed in session evidence"
            ),
            "proxy": (
                "match scores, structural verification, judge decisions, and "
                "publication acceptance; progressive-disclosure token share, "
                "unused resources, and duplicated content are static proxies"
            ),
            "unavailable": (
                "mining precision/recall, diagnosis correctness, recall precision, "
                "goal correctness, behavioral skill lift without labels or replay, "
                "and resource-use rates without matching runtime evidence"
            ),
        },
        "phases": {
            "mining": {
                "turns": turn_count,
                "findings": len(findings),
                "selected": selected,
                "selection_rate": _rate(selected, len(findings)),
                "dispositions": dict(sorted(dispositions.items())),
                "precision": None,
                "precision_reason": "no human finding labels",
                "resource_opportunities": sum(
                    (row.get("features") or {}).get("candidate_source")
                    == "resource_opportunity"
                    for row in findings
                ),
                "selected_resource_opportunities": sum(
                    decision.get("disposition") == "selected"
                    and decision.get("candidate_source") == "resource_opportunity"
                    for decision in decisions
                ),
            },
            "diagnosis": {
                "mined_selected_scopes": selected,
                "expected_scopes": admitted_scopes,
                "completed_scopes": len(diagnoses),
                "coverage": _rate(len(diagnoses), admitted_scopes),
                "capability_gaps": len(diagnosis_gaps),
                "newly_detected_gaps": newly_detected_gaps,
                "mean_gap_confidence": (
                    round(
                        sum(diagnosis_confidences)
                        / len(diagnosis_confidences),
                        6,
                    )
                    if diagnosis_confidences
                    else None
                ),
                "truncated_slices": truncated_slices,
                "correctness": None,
                "correctness_reason": "schema validity is not diagnosis ground truth",
            },
            "recall": {
                "scopes": len(matching_files),
                "scopes_with_candidates": matched_scopes,
                "candidate_coverage": _rate(matched_scopes, len(matching_files)),
                "mean_top_match_score": (
                    round(sum(top_scores) / len(top_scores), 6)
                    if top_scores
                    else None
                ),
                "precision": None,
                "precision_reason": "no relevance judgments for retrieved skills",
            },
            "goal": {
                "scopes": len(scopes),
                "changed_scopes": changed_scopes,
                "no_change_scopes": no_change_scopes,
                "idempotent_replay_scopes": idempotent_scopes,
                "idempotent_resource_opportunities": converged_resource_opportunities,
                "converged_replay": converged_replay,
                "run_disposition": (
                    "changed"
                    if changed_scopes
                    else "converged" if converged_replay else "no_change"
                ),
                "operations": len(operations),
                "reduction_decisions": dict(sorted(reduction_counts.items())),
                "min_super_score": (
                    float(reduction.get("min_super_score") or 0)
                    if isinstance(reduction, dict)
                    else None
                ),
                "score_gate_active": (
                    float(reduction.get("min_super_score") or 0) > 0
                    if isinstance(reduction, dict)
                    else None
                ),
                "correctness": None,
                "correctness_reason": "no labeled optimal operation or goal",
            },
            "optimize": {
                "attempts": len(optimize_rows),
                "operations_started": optimize_first_attempts,
                "second_attempts": optimize_attempt_twos,
                "retry_rate": _rate(
                    optimize_attempt_twos,
                    optimize_first_attempts,
                ),
                "quality": None,
                "quality_reason": "edit completion is not behavioral improvement",
            },
            "resources": resource_summary,
            "cost": {
                "agent_calls_actual": actual_agent_calls,
                "prefiltered_scopes": prefiltered_scopes,
                "estimated_agent_calls_avoided": estimated_calls_avoided,
                "counterfactual_agent_calls": counterfactual_agent_calls,
                "estimated_agent_call_savings_rate": _rate(
                    estimated_calls_avoided, counterfactual_agent_calls
                ),
                "estimation_basis": (
                    "two avoided calls per selected finding filtered before "
                    "Diagnosis and Goal; operation-dependent calls excluded"
                ),
            },
            "verify": {
                "operations": len(verifications),
                "artifact_records": len(verification_artifacts),
                "skipped": skipped_verifications,
                "failed_before_result": failed_verifications,
                "structural_passes": verification_passes,
                "structural_pass_rate": _rate(
                    verification_passes, len(verifications)
                ),
                "replay_available": replay_available,
                "replay_coverage": _rate(replay_available, len(verifications)),
                "replay_passes": replay_passes,
                "behavioral_pass_rate": (
                    _rate(replay_passes, replay_available)
                    if replay_available
                    else None
                ),
            },
            "judge": {
                "decisions": len(judge_rows),
                "actions": dict(sorted(judge_actions.items())),
                "first_attempt_passes": first_attempt_passes,
                "first_attempt_pass_rate": _rate(
                    first_attempt_passes, first_attempts
                ),
                "proposed_operations": len(operations),
                "accepted_proposals": accepted,
                "proposal_acceptance_rate": _rate(accepted, len(operations)),
                "note": (
                    "proposals include bundled operations; judge decisions and "
                    "verification operations count executable attempts only"
                ),
            },
        },
        "funnel": {
            "selected_findings": selected,
            "diagnosed_findings": len(diagnoses),
            "recalled_scopes": len(matching_files),
            "changed_scopes": changed_scopes,
            "proposed_operations": len(operations),
            "accepted_proposals": accepted,
            "idempotent_replay_scopes": idempotent_scopes,
            "idempotent_resource_opportunities": converged_resource_opportunities,
            "converged_replay": converged_replay,
            "run_disposition": (
                "changed"
                if changed_scopes
                else "converged" if converged_replay else "no_change"
            ),
            "novel_goal_scopes": novel_goal_scopes,
            "rates": funnel_rates,
            "action_count_distribution": dict(
                sorted(action_count_distribution.items(), key=lambda row: int(row[0]))
            ),
            "operation_type_distribution": dict(
                sorted(operation_type_distribution.items())
            ),
            "accepted_operation_type_distribution": dict(
                sorted(accepted_operation_type_distribution.items())
            ),
            "targets": target_evaluation,
        },
        "warnings": warnings,
    }


def write_phase_metrics(
    workspace: Path, spans: list[dict[str, Any]] | None = None
) -> Path:
    document = collect_phase_metrics(workspace, spans)
    path = workspace / "logs/phase-metrics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )
    temporary.replace(path)
    return path


def aggregate_phase_metrics(runs_root: Path) -> dict[str, Any]:
    reports = [
        value
        for path in sorted(runs_root.glob("*/logs/phase-metrics.json"))
        if isinstance(value := _read_json(path), dict)
    ]

    def total(phase: str, key: str) -> int:
        return sum(
            int(
                (((report.get("phases") or {}).get(phase) or {}).get(key))
                or 0
            )
            for report in reports
        )

    mining_findings = total("mining", "findings")
    mining_selected = total("mining", "selected")
    diagnosis_expected = total("diagnosis", "expected_scopes")
    diagnosis_completed = total("diagnosis", "completed_scopes")
    recall_scopes = total("recall", "scopes")
    recall_candidates = total("recall", "scopes_with_candidates")
    verify_operations = total("verify", "operations")
    replay_available = total("verify", "replay_available")
    proposed = total("judge", "proposed_operations")
    accepted = total("judge", "accepted_proposals")
    return {
        "schema_version": 1,
        "run_count": len(reports),
        "run_ids": [str(report.get("run_id") or "") for report in reports],
        "phases": {
            "mining": {
                "findings": mining_findings,
                "selected": mining_selected,
                "selection_rate": _rate(mining_selected, mining_findings),
                "precision": None,
            },
            "diagnosis": {
                "expected_scopes": diagnosis_expected,
                "completed_scopes": diagnosis_completed,
                "coverage": _rate(diagnosis_completed, diagnosis_expected),
                "capability_gaps": total("diagnosis", "capability_gaps"),
                "newly_detected_gaps": total(
                    "diagnosis", "newly_detected_gaps"
                ),
                "truncated_slices": total("diagnosis", "truncated_slices"),
                "correctness": None,
            },
            "recall": {
                "scopes": recall_scopes,
                "scopes_with_candidates": recall_candidates,
                "candidate_coverage": _rate(recall_candidates, recall_scopes),
                "precision": None,
            },
            "goal": {
                "changed_scopes": total("goal", "changed_scopes"),
                "no_change_scopes": total("goal", "no_change_scopes"),
                "operations": total("goal", "operations"),
                "idempotent_replay_scopes": total(
                    "goal", "idempotent_replay_scopes"
                ),
                "idempotent_resource_opportunities": total(
                    "goal", "idempotent_resource_opportunities"
                ),
                "converged_replay_runs": sum(
                    bool(
                        ((report.get("phases") or {}).get("goal") or {}).get(
                            "converged_replay"
                        )
                    )
                    for report in reports
                ),
                "runs_with_active_score_gate": sum(
                    (
                        ((report.get("phases") or {}).get("goal") or {}).get(
                            "score_gate_active"
                        )
                        is True
                    )
                    for report in reports
                ),
                "correctness": None,
            },
            "optimize": {
                "operations_started": total("optimize", "operations_started"),
                "second_attempts": total("optimize", "second_attempts"),
                "retry_rate": _rate(
                    total("optimize", "second_attempts"),
                    total("optimize", "operations_started"),
                ),
                "quality": None,
            },
            "cost": {
                "agent_calls_actual": total("cost", "agent_calls_actual"),
                "prefiltered_scopes": total("cost", "prefiltered_scopes"),
                "estimated_agent_calls_avoided": total(
                    "cost", "estimated_agent_calls_avoided"
                ),
                "counterfactual_agent_calls": total(
                    "cost", "counterfactual_agent_calls"
                ),
                "estimated_agent_call_savings_rate": _rate(
                    total("cost", "estimated_agent_calls_avoided"),
                    total("cost", "counterfactual_agent_calls"),
                ),
            },
            "verify": {
                "operations": verify_operations,
                "artifact_records": total("verify", "artifact_records"),
                "skipped": total("verify", "skipped"),
                "failed_before_result": total(
                    "verify", "failed_before_result"
                ),
                "structural_passes": total("verify", "structural_passes"),
                "structural_pass_rate": _rate(
                    total("verify", "structural_passes"), verify_operations
                ),
                "replay_available": replay_available,
                "replay_coverage": _rate(replay_available, verify_operations),
                "behavioral_pass_rate": (
                    _rate(total("verify", "replay_passes"), replay_available)
                    if replay_available
                    else None
                ),
            },
            "judge": {
                "proposed_operations": proposed,
                "accepted_proposals": accepted,
                "proposal_acceptance_rate": _rate(accepted, proposed),
                "first_attempt_passes": total(
                    "judge", "first_attempt_passes"
                ),
            },
        },
        "warnings": sorted(
            {
                warning
                for report in reports
                for warning in report.get("warnings") or []
                if isinstance(warning, str)
            }
        ),
        "quality_note": (
            "Null precision/correctness fields require labeled findings, recall "
            "relevance judgments, optimal-goal labels, or held-out replay."
        ),
    }


def write_phase_metrics_summary(
    runs_root: Path, output: Path | None = None
) -> Path:
    document = aggregate_phase_metrics(runs_root)
    path = output or runs_root.parent / "phase-metrics-summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )
    temporary.replace(path)
    return path


def collect_edits(workspace: Path) -> dict[str, Any]:
    """Join reduction, publication, and the final judge result for every edit."""
    reduction = _read_json(workspace / "run/goal-reduction.json")
    decisions = []
    summary: dict[str, Any] = {}
    if isinstance(reduction, dict):
        raw = reduction.get("decisions")
        if isinstance(raw, list):
            decisions = [row for row in raw if isinstance(row, dict)]
        for key in (
            "input_operation_count",
            "selected_operation_count",
            "max_ops_per_skill",
            "min_super_score",
            "retry_budget",
            "max_attempts",
        ):
            if key in reduction:
                summary[key] = reduction[key]
    edits: list[dict[str, Any]] = []
    for row in decisions:
        cluster = str(row.get("cluster") or "")
        op_index = row.get("op_index")
        selected_cluster = str(row.get("selected_cluster") or cluster)
        selected_index = row.get("selected_op_index", op_index)
        edit = dict(row)
        publication = _read_json(
            workspace / "run" / cluster / "ops" / str(op_index) / "publication.json"
        )
        if isinstance(publication, dict):
            edit["publication_accepted"] = publication.get("accepted")
            edit["publication_reason"] = publication.get("reason")
        verification = _read_json(
            workspace / "run" / selected_cluster / "ops" / str(selected_index) / "verification.json"
        )
        if isinstance(verification, dict):
            feedback = verification.get("feedback")
            if isinstance(feedback, dict):
                action = feedback.get("action")
                if isinstance(action, dict):
                    edit["judge_action"] = action.get("op")
                    edit["judge_to"] = action.get("to")
                edit["retry_budget"] = feedback.get("retry_budget")
                edit["overall_status"] = feedback.get("overall_status")
                used = [
                    item.get("retries_used")
                    for item in feedback.get("per_skill") or []
                    if isinstance(item, dict) and isinstance(item.get("retries_used"), int)
                ]
                edit["retries_used"] = max(used) if used else None
                edit["failed_skills"] = [
                    item.get("skill")
                    for item in feedback.get("per_skill") or []
                    if isinstance(item, dict) and item.get("status") == "fail"
                ]
        edits.append(edit)
    return {"summary": summary, "edits": edits}


def write_run_report(workspace: Path) -> Path | None:
    """Write logs/run-timing.json from this run's spans and cut budget."""
    try:
        workspace = workspace.resolve()
        database = workspace / "logs/metrics.sqlite"
        rows: list[dict[str, Any]] = []
        if database.is_file():
            with sqlite3.connect(database) as connection:
                connection.row_factory = sqlite3.Row
                try:
                    fetched = connection.execute(
                        "SELECT * FROM pipeline_spans ORDER BY started_at_us"
                    ).fetchall()
                except sqlite3.OperationalError:
                    fetched = []
                rows = [dict(row) for row in fetched]
        budget_path = workspace / "traces/derived/cut/budget.json"
        budget: Any = None
        if budget_path.is_file():
            try:
                budget = json.loads(budget_path.read_text())
            except json.JSONDecodeError:
                budget = None
        edits = collect_edits(workspace)
        phase_metrics = collect_phase_metrics(workspace, rows)
        document = {
            "schema_version": 1,
            "run_id": workspace.name,
            "policy": {
                "max_ops_per_skill": edits["summary"].get("max_ops_per_skill"),
                "min_super_score": edits["summary"].get("min_super_score"),
                "retry_budget": edits["summary"].get("retry_budget", 0),
                "max_attempts": edits["summary"].get("max_attempts", 1),
                "super_score": (
                    "severity_weight * confidence * (1 + abs(score)) + match_score"
                ),
                "severity_weights": {
                    "low": 1,
                    "medium": 2,
                    "high": 3,
                    "critical": 4,
                },
                "retry_policy": "disabled",
                "judge_actions": ["pass", "fail"],
            },
            **summarize_spans(rows),
            "edit_summary": edits["summary"],
            "edits": edits["edits"],
            "cut_budget": budget,
            "agent_call_savings": phase_metrics["phases"]["cost"],
            "phase_metrics": phase_metrics,
        }
        path = workspace / "logs/run-timing.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        )
        temporary.replace(path)
        write_phase_metrics(workspace, rows)
        print(f"timing report {path}", flush=True)
        return path
    except Exception as error:
        print(f"timing report failed: {error}", file=sys.stderr, flush=True)
        return None
