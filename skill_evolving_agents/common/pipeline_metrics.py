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
        with sqlite3.connect(shared, timeout=30) as destination:
            _initialize(destination)
            destination.execute(
                "DELETE FROM pipeline_spans WHERE run_id = ?",
                (workspace.name,),
            )
            if rows:
                destination.executemany(
                    "INSERT INTO pipeline_spans VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        document = {
            "schema_version": 1,
            "run_id": workspace.name,
            "policy": {
                "max_ops_per_skill": edits["summary"].get("max_ops_per_skill"),
                "min_super_score": edits["summary"].get("min_super_score"),
                "retry_budget": edits["summary"].get("retry_budget", 1),
                "max_attempts": edits["summary"].get("max_attempts", 2),
                "super_score": (
                    "severity_weight * confidence * (1 + abs(score)) + match_score"
                ),
                "severity_weights": {
                    "low": 1,
                    "medium": 2,
                    "high": 3,
                    "critical": 4,
                },
                "judge_back_restarts": ["optimize", "verifiter", "judge"],
                "judge_back_does_not_reopen": [
                    "preprocessing",
                    "label-skills",
                    "label-traces-cluster",
                    "goal",
                ],
            },
            **summarize_spans(rows),
            "edit_summary": edits["summary"],
            "edits": edits["edits"],
            "cut_budget": budget,
        }
        path = workspace / "logs/run-timing.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        )
        temporary.replace(path)
        print(f"timing report {path}", flush=True)
        return path
    except Exception as error:
        print(f"timing report failed: {error}", file=sys.stderr, flush=True)
        return None
