"""Vendor trace adapters that emit the normalizer's internal turn shape."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


Parser = Callable[[Path], tuple[dict[str, Any], Counter[str]]]
Detector = Callable[[dict[str, Any]], bool]


def _turn(turn_id: str, timestamp: str, ordinal: int | None) -> dict[str, Any]:
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


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            candidate = (
                item.get("text")
                or item.get("content")
                or item.get("output_text")
                or item.get("input_text")
            )
            if isinstance(candidate, str):
                parts.append(candidate)
    return "\n".join(parts)


def _identifier(path: Path, line: int, value: Any = None) -> str:
    if isinstance(value, str) and value:
        return value
    digest = hashlib.sha256(f"{path.name}:{line}".encode()).hexdigest()[:20]
    return f"turn-{digest}"


def _epoch(value: str) -> float | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _record_timing(
    turn: dict[str, Any], timestamp: str, first_output: bool = False
) -> None:
    completed = _epoch(timestamp)
    started = turn["timing"]["started_at_epoch"]
    if completed is None:
        return
    turn["timing"]["completed_at_epoch"] = completed
    if isinstance(started, (int, float)) and completed >= started:
        elapsed = round((completed - started) * 1000)
        turn["timing"]["duration_ms"] = elapsed
        if first_output and turn["timing"]["time_to_first_token_ms"] is None:
            turn["timing"]["time_to_first_token_ms"] = elapsed


def _tool(
    turn: dict[str, Any],
    call_id: str,
    sequence: int,
    name: str,
    arguments: Any,
    result: Any = "",
    failed: bool = False,
) -> None:
    event = {
        "call_id": call_id,
        "sequence": sequence,
        "tool": name or "unknown",
        "arguments": arguments if arguments is not None else {},
        "result": result if result is not None else "",
        "status": "failed" if failed else "completed",
    }
    turn["tools"].append(event)
    turn["calls"][call_id] = event


def detects_claude(record: dict[str, Any]) -> bool:
    return (
        record.get("type") in {"user", "assistant"}
        and isinstance(record.get("message"), dict)
        and ("sessionId" in record or "uuid" in record)
    )


def parse_claude(path: Path) -> tuple[dict[str, Any], Counter[str]]:
    counters: Counter[str] = Counter()
    session: dict[str, Any] = {
        "session_id": path.stem,
        "parent_session_id": None,
        "raw_bytes": path.stat().st_size,
        "turns": {},
    }
    current: dict[str, Any] | None = None
    pending_tools: dict[str, tuple[str, Any, int]] = {}
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
            session_id = record.get("sessionId")
            if isinstance(session_id, str) and session_id:
                session["session_id"] = session_id
            if record.get("isSidechain"):
                session["parent_session_id"] = str(
                    record.get("parentUuid") or "sidechain"
                )
            role = record.get("type")
            message = record.get("message")
            if role not in {"user", "assistant"} or not isinstance(message, dict):
                counters[f"dropped_{role}"] += 1
                continue
            content = message.get("content")
            timestamp = str(record.get("timestamp") or "")
            if role == "user" and isinstance(content, str):
                turn_id = _identifier(path, line_number, record.get("uuid"))
                current = _turn(turn_id, timestamp, line_number)
                current["root_turn_id"] = turn_id
                current["timing"]["started_at_epoch"] = _epoch(timestamp)
                current["user"].append(
                    {"text": content, "user_input_order": line_number}
                )
                session["turns"][turn_id] = current
                continue
            if current is None:
                counters["orphan_response_items"] += 1
                continue
            if role == "assistant":
                text = _text(content)
                if text.strip():
                    current["assistant"].append(text)
                    current["assistant_observations"].append(
                        {
                            "text": text,
                            "after_tool_count": len(current["tools"]),
                            "source_ordinal": line_number,
                        }
                    )
                    current["assistant_final"].append(text)
                    _record_timing(current, timestamp, first_output=True)
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_use":
                            continue
                        sequence += 1
                        call_id = str(block.get("id") or f"tool-{sequence}")
                        pending_tools[call_id] = (
                            str(block.get("name") or "unknown"),
                            block.get("input") or {},
                            sequence,
                        )
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    call_id = str(block.get("tool_use_id") or f"tool-{sequence}")
                    name, arguments, call_sequence = pending_tools.pop(
                        call_id, ("unknown", {}, sequence)
                    )
                    _tool(
                        current,
                        call_id,
                        call_sequence,
                        name,
                        arguments,
                        block.get("content"),
                        bool(block.get("is_error")),
                    )
            current["status"] = "completed"
            _record_timing(current, timestamp)
            current["ordinals"][1] = line_number
    counters["session_meta"] += 1
    return session, counters


def detects_cursor(record: dict[str, Any]) -> bool:
    role = record.get("role")
    message = record.get("message")
    return role in {"user", "assistant", "tool"} or (
        isinstance(message, dict)
        and message.get("role") in {"user", "assistant", "tool"}
    )


def parse_cursor(path: Path) -> tuple[dict[str, Any], Counter[str]]:
    counters: Counter[str] = Counter()
    session: dict[str, Any] = {
        "session_id": path.stem,
        "parent_session_id": None,
        "raw_bytes": path.stat().st_size,
        "turns": {},
    }
    current: dict[str, Any] | None = None
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
            message = record.get("message")
            envelope = message if isinstance(message, dict) else record
            role = envelope.get("role")
            content = envelope.get("content") or envelope.get("text")
            timestamp = str(record.get("timestamp") or envelope.get("timestamp") or "")
            if role == "user":
                turn_id = _identifier(
                    path,
                    line_number,
                    envelope.get("turn_id") or record.get("turn_id") or record.get("id"),
                )
                current = _turn(turn_id, timestamp, line_number)
                current["root_turn_id"] = turn_id
                current["timing"]["started_at_epoch"] = _epoch(timestamp)
                current["user"].append(
                    {"text": _text(content), "user_input_order": line_number}
                )
                session["turns"][turn_id] = current
            elif current is None:
                counters["orphan_response_items"] += 1
            elif role == "assistant":
                text = _text(content)
                if text.strip():
                    current["assistant"].append(text)
                    current["assistant_observations"].append(
                        {
                            "text": text,
                            "after_tool_count": len(current["tools"]),
                            "source_ordinal": line_number,
                        }
                    )
                    current["assistant_final"].append(text)
                    _record_timing(current, timestamp, first_output=True)
                current["status"] = "completed"
                _record_timing(current, timestamp)
                current["ordinals"][1] = line_number
            elif role == "tool":
                sequence += 1
                call_id = str(
                    envelope.get("tool_call_id")
                    or envelope.get("call_id")
                    or f"tool-{sequence}"
                )
                _tool(
                    current,
                    call_id,
                    sequence,
                    str(envelope.get("name") or envelope.get("tool") or "unknown"),
                    envelope.get("arguments") or {},
                    content,
                    bool(envelope.get("error")),
                )
                current["ordinals"][1] = line_number
            else:
                counters[f"dropped_{role}"] += 1
    counters["session_meta"] += 1
    return session, counters


@dataclass(frozen=True)
class SourceAdapter:
    name: str
    detect: Detector
    parse: Parser


class SourceAdapterRegistry:
    def __init__(self) -> None:
        self._items: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        if adapter.name in self._items:
            raise ValueError(f"duplicate source adapter: {adapter.name}")
        self._items[adapter.name] = adapter

    def select(self, path: Path, requested: str) -> SourceAdapter:
        if requested not in {"auto", "multi_source"}:
            try:
                return self._items[requested]
            except KeyError as error:
                raise ValueError(f"unknown source adapter: {requested}") from error
        first: dict[str, Any] | None = None
        with path.open(errors="replace") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    first = value
                    break
        if first is None:
            raise ValueError(f"no valid JSON records in {path}")
        for adapter in self._items.values():
            if adapter.detect(first):
                return adapter
        raise ValueError(f"no source adapter recognized {path}")
