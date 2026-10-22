#!/usr/bin/env python3
"""Convert Codex rollout JSONL into bounded, canonical turn records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PREPROCESSING_ROOT = Path(__file__).resolve().parents[1]
if str(PREPROCESSING_ROOT) not in sys.path:
    sys.path.insert(0, str(PREPROCESSING_ROOT))
from trace_mining.source_adapters import (
    SourceAdapter,
    SourceAdapterRegistry,
    detects_claude,
    detects_cursor,
    parse_claude,
    parse_cursor,
)


DROP_USER_PREFIXES = (
    "# agents.md instructions",
    "<app-context",
    "<codex_apps_client_time_context",
    "<external",
    "<in-app-browser-context",
    "<skills_instructions",
    "<system",
    "<tools>",
)
BASE64_DATA = re.compile(
    r"data:[a-z0-9.+/-]+;base64,[A-Za-z0-9+/=\\s]+", re.IGNORECASE
)
PATH_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:\.{0,2}/)?[A-Za-z0-9_.-]+"
    r"(?:/[A-Za-z0-9_.-]+)+|[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,8}"
)
VERIFY_TERMS = re.compile(
    r"\b(test|tests|pytest|unittest|build|lint|check|verify|validate|"
    r"typecheck|tsc|cargo test|go test|npm test)\b",
    re.IGNORECASE,
)


def load_config(path: Path | dict[str, Any]) -> dict[str, Any]:
    value = path if isinstance(path, dict) else json.loads(path.read_text())
    if value.get("schema_version") != 1:
        raise SystemExit(f"unsupported preprocessing config: {path}")
    return value


def content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def clean_text(value: Any) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    value = BASE64_DATA.sub("[base64 content removed]", value)
    value = value.replace("\x00", "")
    return value.strip()


def bounded(value: Any, maximum: int) -> str:
    text = clean_text(value)
    if len(text) <= maximum:
        return text
    marker = f"\n...[{len(text) - maximum} chars omitted]...\n"
    head = max(0, (maximum - len(marker)) * 2 // 3)
    tail = max(0, maximum - len(marker) - head)
    return text[:head] + marker + (text[-tail:] if tail else "")


def canonical_timing(value: Any) -> dict[str, int | float | None]:
    source = value if isinstance(value, dict) else {}

    def number(key: str) -> int | float | None:
        item = source.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            return item if item >= 0 else None
        if isinstance(item, str) and key.endswith("_epoch"):
            try:
                return datetime.fromisoformat(
                    item.replace("Z", "+00:00")
                ).timestamp()
            except ValueError:
                return None
        return None

    timing = {
        key: number(key)
        for key in (
            "started_at_epoch",
            "completed_at_epoch",
            "duration_ms",
            "time_to_first_token_ms",
        )
    }
    if (
        timing["duration_ms"] is None
        and timing["started_at_epoch"] is not None
        and timing["completed_at_epoch"] is not None
        and timing["completed_at_epoch"] >= timing["started_at_epoch"]
    ):
        timing["duration_ms"] = round(
            (timing["completed_at_epoch"] - timing["started_at_epoch"]) * 1000
        )
    return timing


def substantive_user_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    folded = stripped.casefold()
    return not any(folded.startswith(prefix) for prefix in DROP_USER_PREFIXES)


def message_metadata(
    record: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    for value in (
        payload.get("internal_chat_message_metadata_passthrough"),
        record.get("internal_chat_message_metadata_passthrough"),
    ):
        if isinstance(value, dict):
            return value
    return {}


def extract_user_text(
    record: dict[str, Any], payload: dict[str, Any]
) -> tuple[str, int | None] | None:
    metadata = message_metadata(record, payload)
    kinds = metadata.get("content_item_kinds")
    if isinstance(kinds, list) and not any(
        kind in {"user.text", "user.image"} for kind in kinds
    ):
        return None
    text = content_text(payload.get("content"))
    marker = re.search(r"(?im)^## My request:\s*", text)
    if marker:
        text = text[marker.end() :]
    if not substantive_user_text(text):
        return None
    order = (record.get("metadata") or {}).get("user_input_order")
    return text, order if isinstance(order, int) else None


def turn_id_from(record: dict[str, Any], payload: dict[str, Any]) -> str | None:
    for candidate in (
        payload.get("turn_id"),
        message_metadata(record, payload).get("turn_id"),
        (record.get("metadata") or {}).get("turn_id"),
    ):
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def new_turn(turn_id: str, timestamp: str, ordinal: int | None) -> dict[str, Any]:
    return {
        "turn_id": turn_id,
        "root_turn_id": None,
        "timestamp": timestamp,
        "user": [],
        "assistant": [],
        "assistant_observations": [],
        "assistant_final": [],
        "last_agent_message": "",
        "status": "unknown",
        "error": None,
        "tools": [],
        "calls": {},
        "ordinals": [ordinal, ordinal],
        "timing": {
            "started_at_epoch": None,
            "completed_at_epoch": None,
            "duration_ms": None,
            "time_to_first_token_ms": None,
        },
    }


def update_ordinals(turn: dict[str, Any], ordinal: Any) -> None:
    if not isinstance(ordinal, int):
        return
    start, end = turn["ordinals"]
    turn["ordinals"] = [
        ordinal if start is None else min(start, ordinal),
        ordinal if end is None else max(end, ordinal),
    ]


def tool_call(payload: dict[str, Any], sequence: int) -> dict[str, Any]:
    call_id = payload.get("call_id") or payload.get("id") or f"tool-{sequence}"
    name = payload.get("name") or payload.get("tool") or payload.get("server")
    arguments = payload.get("arguments")
    if arguments is None:
        arguments = payload.get("input")
    if arguments is None:
        arguments = payload.get("args")
    return {
        "call_id": str(call_id),
        "sequence": sequence,
        "tool": str(name or payload.get("type") or "unknown"),
        "arguments": arguments if arguments is not None else {},
        "result": "",
        "status": "unknown",
    }


def attach_tool_output(
    turn: dict[str, Any], payload: dict[str, Any], sequence: int
) -> None:
    call_id = str(payload.get("call_id") or payload.get("id") or "")
    event = turn["calls"].get(call_id)
    if event is None:
        event = tool_call(payload, sequence)
        event["call_id"] = call_id or event["call_id"]
        turn["tools"].append(event)
        turn["calls"][event["call_id"]] = event
    result = payload.get("output")
    if result is None:
        result = payload.get("result")
    if result is None:
        result = payload.get("content")
    event["result"] = result if result is not None else ""
    status = payload.get("status")
    result_text = clean_text(event["result"]).casefold()
    if status in {"failed", "error"} or re.search(
        r"(^|\\W)(error|failed|failure|traceback)(\\W|$)", result_text
    ):
        event["status"] = "failed"
    else:
        event["status"] = "completed"


def parse_source(path: Path) -> tuple[dict[str, Any], Counter[str]]:
    session: dict[str, Any] = {
        "session_id": path.stem,
        "parent_session_id": None,
        "raw_bytes": path.stat().st_size,
        "turns": {},
    }
    counters: Counter[str] = Counter()
    current_turn: str | None = None
    sequence = 0
    with path.open(errors="replace") as stream:
        for line_number, line in enumerate(stream, start=1):
            counters["raw_records"] += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                counters["invalid_records"] += 1
                continue
            if not isinstance(record, dict):
                counters["dropped_records"] += 1
                continue
            kind = record.get("type")
            payload = record.get("payload")
            if not isinstance(payload, dict):
                counters[f"dropped_{kind}"] += 1
                continue
            timestamp = str(record.get("timestamp") or "")
            ordinal = record.get("ordinal")
            if kind == "session_meta":
                session["session_id"] = str(
                    payload.get("session_id") or payload.get("id") or path.stem
                )
                parent = payload.get("parent_thread_id") or payload.get(
                    "parent_session_id"
                )
                session["parent_session_id"] = (
                    str(parent) if isinstance(parent, str) and parent else None
                )
                counters["session_meta"] += 1
                continue
            subtype = payload.get("type")
            if kind == "event_msg" and subtype == "task_started":
                current_turn = str(
                    payload.get("turn_id")
                    or payload.get("root_turn_id")
                    or f"line-{line_number}"
                )
                turn = session["turns"].setdefault(
                    current_turn, new_turn(current_turn, timestamp, ordinal)
                )
                turn["root_turn_id"] = payload.get("root_turn_id")
                turn["timing"]["started_at_epoch"] = payload.get("started_at")
                update_ordinals(turn, ordinal)
                continue
            turn_id = turn_id_from(record, payload) or current_turn
            if kind == "event_msg" and subtype in {"task_complete", "turn_aborted"}:
                if not turn_id:
                    counters["orphan_completion"] += 1
                    continue
                turn = session["turns"].setdefault(
                    turn_id, new_turn(turn_id, timestamp, ordinal)
                )
                update_ordinals(turn, ordinal)
                error = payload.get("error")
                if subtype == "turn_aborted":
                    turn["status"] = "aborted"
                elif error:
                    turn["status"] = "failed"
                    turn["error"] = error
                else:
                    turn["status"] = "completed"
                last = payload.get("last_agent_message")
                if isinstance(last, str):
                    turn["last_agent_message"] = last
                turn["timing"]["started_at_epoch"] = (
                    payload.get("started_at")
                    or turn["timing"]["started_at_epoch"]
                )
                turn["timing"]["completed_at_epoch"] = payload.get("completed_at")
                turn["timing"]["duration_ms"] = payload.get("duration_ms")
                turn["timing"]["time_to_first_token_ms"] = payload.get(
                    "time_to_first_token_ms"
                )
                continue
            if kind != "response_item":
                counters[f"dropped_{kind}"] += 1
                continue
            if not turn_id:
                counters["orphan_response_items"] += 1
                continue
            turn = session["turns"].setdefault(
                turn_id, new_turn(turn_id, timestamp, ordinal)
            )
            update_ordinals(turn, ordinal)
            if subtype == "message":
                role = payload.get("role")
                text = content_text(payload.get("content"))
                if role == "user":
                    extracted = extract_user_text(record, payload)
                    if extracted:
                        user_text, user_input_order = extracted
                        turn["user"].append(
                            {
                                "text": user_text,
                                "user_input_order": user_input_order,
                            }
                        )
                    else:
                        counters["dropped_message_user"] += 1
                elif role == "assistant" and text.strip():
                    turn["assistant"].append(text)
                    turn["assistant_observations"].append(
                        {
                            "text": text,
                            "after_tool_count": len(turn["tools"]),
                            "source_ordinal": ordinal,
                        }
                    )
                    if payload.get("phase") == "final_answer":
                        turn["assistant_final"].append(text)
                else:
                    counters[f"dropped_message_{role}"] += 1
            elif subtype in {"custom_tool_call", "function_call"}:
                sequence += 1
                event = tool_call(payload, sequence)
                turn["tools"].append(event)
                turn["calls"][event["call_id"]] = event
            elif subtype in {"custom_tool_call_output", "function_call_output"}:
                sequence += 1
                attach_tool_output(turn, payload, sequence)
            else:
                counters[f"dropped_response_{subtype}"] += 1
    return session, counters


def source_registry() -> SourceAdapterRegistry:
    registry = SourceAdapterRegistry()
    registry.register(
        SourceAdapter(
            "codex",
            lambda record: record.get("type")
            in {
                "session_meta",
                "response_item",
                "event_msg",
                "token_usage_record",
            },
            parse_source,
        )
    )
    registry.register(SourceAdapter("claude", detects_claude, parse_claude))
    registry.register(SourceAdapter("cursor", detects_cursor, parse_cursor))
    return registry


def evidence_required(
    turn: dict[str, Any], user: str, config: dict[str, Any]
) -> bool:
    if (config.get("methodology") or {}).get("enabled", False):
        return bool(turn["tools"])
    policy = config["tool_evidence"].get("policy", "on_signal")
    if policy == "always":
        return bool(turn["tools"])
    if policy == "never":
        return False
    if any(event["status"] == "failed" for event in turn["tools"]):
        return True
    if turn["status"] in {"failed", "aborted"} or not turn["assistant"]:
        return bool(turn["tools"])
    folded = user.casefold()
    return any(
        str(term).casefold() in folded
        for term in config["tool_evidence"].get("user_signal_terms", [])
    )


def write_tool_evidence(
    turn: dict[str, Any],
    trace_id: str,
    target: Path,
    config: dict[str, Any],
) -> tuple[int, int]:
    limits = config["limits"]
    events = turn["tools"][: limits["max_tool_events_per_turn"]]
    target.parent.mkdir(parents=True, exist_ok=True)
    error_count = 0
    with target.open("w") as output:
        for event in events:
            result = clean_text(event["result"])
            if event["status"] == "failed":
                error_count += 1
            row = {
                "schema_version": 1,
                "trace_id": trace_id,
                "sequence": event["sequence"],
                "tool": event["tool"],
                "status": event["status"],
                "arguments": bounded(
                    event["arguments"], limits["tool_argument_chars"]
                ),
                "result_preview": bounded(
                    result, limits["tool_result_preview_chars"]
                ),
                "result_bytes": len(result.encode()),
                "result_sha256": hashlib.sha256(result.encode()).hexdigest(),
            }
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return len(events), error_count


def event_phase(tool: str, arguments: str) -> str:
    """Classify observable actions without retaining model reasoning."""
    folded = f"{tool} {arguments}".casefold()
    if VERIFY_TERMS.search(folded):
        return "verify"
    if any(term in folded for term in (
        "apply_patch", "edit", "write", "create_file", "delete", "move", "rename",
    )):
        return "modify"
    if any(term in folded for term in (
        "read", "search", "grep", "glob", "find", "list", "fetch", "inspect",
        "snapshot",
    )):
        return "inspect"
    return "execute"


def task_event_rows(
    turn: dict[str, Any], trace_id: str, config: dict[str, Any]
) -> list[dict[str, Any]]:
    limits = config["limits"]
    methodology = config.get("methodology") or {}
    preview_chars = int(methodology.get("event_preview_chars", 400))
    events: list[dict[str, Any]] = []
    for event in turn["tools"][: limits["max_tool_events_per_turn"]]:
        arguments = bounded(event["arguments"], preview_chars)
        result = clean_text(event["result"])
        targets = sorted(set(PATH_TOKEN.findall(arguments)))[:8]
        events.append(
            {
                "sequence": event["sequence"],
                "tool": event["tool"],
                "phase": event_phase(event["tool"], arguments),
                "status": event["status"],
                "arguments_preview": arguments,
                "argument_sha256": hashlib.sha256(
                    clean_text(event["arguments"]).encode()
                ).hexdigest(),
                "result_preview": bounded(result, preview_chars),
                "result_sha256": hashlib.sha256(result.encode()).hexdigest(),
                "targets": targets,
            }
        )
    return events


def phase_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    phases: list[dict[str, Any]] = []
    for event in events:
        phase = event["phase"]
        if phases and phases[-1]["phase"] == phase:
            phases[-1]["end_sequence"] = event["sequence"]
            phases[-1]["event_count"] += 1
            phases[-1]["failed_count"] += event["status"] == "failed"
            continue
        phases.append(
            {
                "phase": phase,
                "start_sequence": event["sequence"],
                "end_sequence": event["sequence"],
                "event_count": 1,
                "failed_count": int(event["status"] == "failed"),
            }
        )
    return phases


def assistant_observation_rows(
    turn: dict[str, Any],
    config: dict[str, Any],
    max_after_tool_count: int | None = None,
) -> list[dict[str, Any]]:
    methodology = config.get("methodology") or {}
    preview_chars = int(methodology.get("reflection_preview_chars", 600))
    maximum = int(methodology.get("max_assistant_observations", 32))
    rows: list[dict[str, Any]] = []
    retained_tool_count = (
        len(turn["tools"])
        if max_after_tool_count is None
        else min(len(turn["tools"]), max(max_after_tool_count, 0))
    )
    for observation in (turn.get("assistant_observations") or [])[:maximum]:
        text = bounded(observation.get("text") or "", preview_chars)
        if not text:
            continue
        rows.append(
            {
                "text": text,
                "text_sha256": hashlib.sha256(
                    clean_text(observation.get("text") or "").encode()
                ).hexdigest(),
                "after_tool_count": min(
                    max(int(observation.get("after_tool_count") or 0), 0),
                    retained_tool_count,
                ),
                "source_ordinal": observation.get("source_ordinal"),
            }
        )
    return rows


def relative_to_workspace(path: Path, workspace: Path) -> str:
    return path.relative_to(workspace).as_posix()


def normalize(
    workspace: Path,
    config_path: Path | dict[str, Any],
    database: Path | None = None,
    output_root: Path | None = None,
    run_key: str | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    config = load_config(config_path)
    raw_root = workspace / "traces/raw"
    source_roots = [
        path
        for path in (
            raw_root / "codex",
            raw_root / "claude",
            raw_root / "cursor",
            raw_root / "target_agent",
        )
        if path.is_dir()
    ]
    sources = sorted(
        {path.resolve() for root in source_roots for path in root.glob("*.jsonl")}
    )
    if not sources:
        raise SystemExit(f"no Codex jsonl files found under {raw_root}")
    derived = output_root or workspace / "traces/derived"
    normalized = derived / "normalized"
    if normalized.exists():
        shutil.rmtree(normalized)
    turns_root = normalized / "turns"
    evidence_root = normalized / "tool_evidence"
    trajectories_root = normalized / "task_trajectories"
    turns_root.mkdir(parents=True)
    evidence_root.mkdir(parents=True)
    trajectories_root.mkdir(parents=True)
    limits = config["limits"]
    counters: Counter[str] = Counter()
    candidates: dict[str, tuple[dict[str, Any], Path, dict[str, Any]]] = {}
    raw_bytes = 0
    adapters_used: set[str] = set()
    registry = source_registry()
    requested_adapter = str(config["source"].get("adapter") or "auto")
    for source in sources:
        try:
            adapter = registry.select(source, requested_adapter)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        session, source_counts = adapter.parse(source)
        adapters_used.add(adapter.name)
        source_counts[f"adapter_{adapter.name}_files"] += 1
        counters.update(source_counts)
        raw_bytes += source.stat().st_size
        child = bool(session["parent_session_id"])
        for turn in session["turns"].values():
            users = turn["user"]
            if config["source"].get("exclude_child_sessions") and child:
                counters["excluded_child_turns"] += 1
                continue
            if not users:
                counters["excluded_non_substantive_turns"] += 1
                continue
            ordered_users = [
                item for item in users if item["user_input_order"] is not None
            ]
            selected_user = (ordered_users or users)[-1]["text"]
            user = bounded(selected_user, limits["user_chars"])
            assistant_source = (
                turn["assistant_final"][-1]
                if turn["assistant_final"]
                else turn["last_agent_message"]
                if turn["last_agent_message"]
                else turn["assistant"][-1]
                if turn["assistant"]
                else ""
            )
            assistant = bounded(assistant_source, limits["assistant_chars"])
            error = (
                bounded(turn["error"], limits["error_chars"])
                if turn["error"] is not None
                else None
            )
            trace_id = (
                f"{adapter.name}:{session['session_id']}:{turn['turn_id']}"
            )
            candidate = {
                "trace_id": trace_id,
                "source_adapter": adapter.name,
                "session_id": session["session_id"],
                "parent_session_id": session["parent_session_id"],
                "turn": turn,
                "user": user,
                "assistant": assistant,
                "error": error,
            }
            score = len(user) + len(assistant) + len(turn["tools"]) * 100
            previous = candidates.get(trace_id)
            if previous is None or score > previous[2]["score"]:
                candidates[trace_id] = (
                    candidate,
                    source,
                    {"score": score, "raw_bytes": session["raw_bytes"]},
                )
    trace_ids: list[str] = []
    normalized_bytes = 0
    trace_metrics: list[tuple[Any, ...]] = []
    for trace_id in sorted(candidates):
        candidate, source, metadata = candidates[trace_id]
        turn = candidate["turn"]
        digest = hashlib.sha256(trace_id.encode()).hexdigest()[:24]
        filename = f"{candidate['source_adapter']}-{digest}.json"
        evidence_relative: str | None = None
        evidence_count = 0
        error_count = sum(
            event["status"] == "failed" for event in turn["tools"]
        )
        if evidence_required(turn, candidate["user"], config):
            evidence = evidence_root / (
                f"{candidate['source_adapter']}-{digest}.jsonl"
            )
            evidence_count, error_count = write_tool_evidence(
                turn, trace_id, evidence, config
            )
            evidence_relative = relative_to_workspace(evidence, workspace)
        document = {
            "schema_version": 1,
            "trace_id": trace_id,
            "source": candidate["source_adapter"],
            "session_id": candidate["session_id"],
            "turn_id": turn["turn_id"],
            "root_turn_id": turn["root_turn_id"],
            "parent_session_id": candidate["parent_session_id"],
            "timestamp": turn["timestamp"],
            "timing": canonical_timing(turn["timing"]),
            "user": {"text": candidate["user"]},
            "assistant": {"text": candidate["assistant"]},
            "outcome": {
                "status": turn["status"],
                "error": candidate["error"],
            },
            "tool_summary": {
                "count": len(turn["tools"]),
                "names": sorted({event["tool"] for event in turn["tools"]}),
                "error_count": error_count,
                "evidence_path": evidence_relative,
            },
            "provenance": {
                "raw_file": relative_to_workspace(source, workspace),
                "raw_bytes": metadata["raw_bytes"],
                "ordinals": turn["ordinals"],
            },
        }
        trajectory_events = task_event_rows(turn, trace_id, config)
        trajectory = {
            "schema_version": 1,
            "trace_id": trace_id,
            "session_id": candidate["session_id"],
            "task": {"text": candidate["user"]},
            "outcome": document["outcome"],
            "events": trajectory_events,
            "phases": phase_rows(trajectory_events),
            "assistant_observations": assistant_observation_rows(
                turn,
                config,
                max_after_tool_count=len(trajectory_events),
            ),
            "final_response_sha256": hashlib.sha256(
                candidate["assistant"].encode()
            ).hexdigest(),
            "provenance": {
                "turn_path": relative_to_workspace(
                    turns_root / filename, workspace
                ),
                "tool_evidence_path": evidence_relative,
            },
        }
        trajectory_target = trajectories_root / filename
        trajectory_target.write_text(
            json.dumps(trajectory, indent=2, ensure_ascii=False, sort_keys=True)
            + "\n"
        )
        document["task_trajectory_path"] = relative_to_workspace(
            trajectory_target, workspace
        )
        target = turns_root / filename
        target.write_text(
            json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True)
            + "\n"
        )
        size = target.stat().st_size
        normalized_bytes += size
        trace_ids.append(trace_id)
        trace_metrics.append(
            (
                run_key or workspace.name,
                trace_id,
                document["provenance"]["raw_file"],
                size,
                len(candidate["user"]) + len(candidate["assistant"]),
                len(turn["tools"]),
                evidence_count,
                turn["status"],
            )
        )
    manifest = {
        "schema_version": 1,
        "source": "mixed" if len(adapters_used) > 1 else next(iter(adapters_used)),
        "source_adapters": sorted(adapters_used),
        "source_files": [
            relative_to_workspace(path, workspace) for path in sources
        ],
        "eligible_trace_ids": trace_ids,
        "turn_count": len(trace_ids),
        "excluded_turn_count": (
            counters["excluded_child_turns"]
            + counters["excluded_non_substantive_turns"]
        ),
    }
    (normalized / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    metrics = {
        "schema_version": 1,
        "run_id": run_key or workspace.name,
        "generated_at": datetime.now(UTC).isoformat(),
        "raw_files": len(sources),
        "raw_bytes": raw_bytes,
        "raw_estimated_tokens": raw_bytes // 4,
        "normalized_turns": len(trace_ids),
        "normalized_bytes": normalized_bytes,
        "normalized_estimated_tokens": normalized_bytes // 4,
        "reduction_ratio": (
            round(1 - normalized_bytes / raw_bytes, 6) if raw_bytes else 0
        ),
        "counters": dict(sorted(counters.items())),
    }
    (normalized / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n"
    )
    write_metrics_database(
        database or workspace / "logs/metrics.sqlite", metrics, trace_metrics
    )
    return metrics


def write_metrics_database(
    path: Path,
    metrics: dict[str, Any],
    traces: list[tuple[Any, ...]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS trace_preprocessing_runs (
                run_id TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                raw_files INTEGER NOT NULL,
                raw_bytes INTEGER NOT NULL,
                normalized_turns INTEGER NOT NULL,
                normalized_bytes INTEGER NOT NULL,
                reduction_ratio REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS normalized_traces (
                run_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                raw_file TEXT NOT NULL,
                normalized_bytes INTEGER NOT NULL,
                core_chars INTEGER NOT NULL,
                tool_count INTEGER NOT NULL,
                evidence_count INTEGER NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY (run_id, trace_id)
            );
            """
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO trace_preprocessing_runs
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metrics["run_id"],
                metrics["generated_at"],
                metrics["raw_files"],
                metrics["raw_bytes"],
                metrics["normalized_turns"],
                metrics["normalized_bytes"],
                metrics["reduction_ratio"],
            ),
        )
        connection.execute(
            "DELETE FROM normalized_traces WHERE run_id = ?",
            (metrics["run_id"],),
        )
        connection.executemany(
            "INSERT INTO normalized_traces VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            traces,
        )
        connection.commit()
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "common/preprocessing-config.json",
    )
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    metrics = normalize(args.workspace.resolve(), args.config, args.database)
    print(json.dumps(metrics, sort_keys=True))


if __name__ == "__main__":
    main()
