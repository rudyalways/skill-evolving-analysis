#!/usr/bin/env python3
"""Validate the JSON artifacts passed between skill-evolver stages."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any


PLACEHOLDER = re.compile(r"<[^<>]+>")
INLINE_CODE = re.compile(r"`[^`]*`")
KNOWN_OPS = {"create", "update", "delete", "merge", "split"}
VERIFICATION_STEP_COUNT = 8
VERIFICATION_ROLES = {
    "created",
    "updated",
    "deleted",
    "merge_source",
    "merge_target",
    "split_source",
    "split_target",
}
ASSERTION_SCORE_ANCHORS = {0.0, 0.25, 0.5, 0.75, 1.0}
OPERATION_PHASES = ("goal", "optimize", "verification", "judge")
PHASE_STATUSES = {"pending", "running", "completed", "skipped", "failed"}


def verification_status(score: float, threshold: float) -> str:
    return "pass" if score >= threshold else "fail"


def verification_step_score(scores: list[float]) -> float:
    if not scores:
        raise ContractError("cannot score a step without assertions")
    return sum(scores) / len(scores)


def verification_skill_score(
    weighted_scores: list[tuple[float, float]],
) -> float:
    weight = sum(item_weight for _, item_weight in weighted_scores)
    if weight <= 0:
        raise ContractError("cannot score a skill without applicable weight")
    return sum(score * item_weight for score, item_weight in weighted_scores) / weight


def verification_overall_score(skill_scores: list[float]) -> float:
    if not skill_scores:
        raise ContractError("cannot score verification without skills")
    return min(skill_scores)


class ContractError(ValueError):
    pass


def fail(path: str, message: str) -> None:
    raise ContractError(f"{path}: {message}")


def infrastructure_error(turn: dict[str, Any], patterns: list[Any]) -> bool:
    """True when the turn error matches a configured infrastructure pattern."""
    error = str(((turn.get("outcome") or {}).get("error") or ""))
    return any(
        isinstance(pattern, str) and re.search(pattern, error, re.IGNORECASE)
        for pattern in patterns
    )


def infrastructure_only_turn(turn: dict[str, Any], patterns: list[Any]) -> bool:
    """True when the turn has no assistant text and only an infrastructure error."""
    assistant = turn.get("assistant")
    if not isinstance(assistant, dict):
        assistant = {}
    text = str(assistant.get("text") or "").strip()
    return not text and infrastructure_error(turn, patterns)


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        fail(str(path), "file was not produced")
    except json.JSONDecodeError as error:
        fail(str(path), f"invalid JSON: {error}")
    if not isinstance(value, dict):
        fail(str(path), "top level must be an object")
    reject_placeholders(value, str(path))
    return value


def reject_placeholders(value: Any, path: str = "$") -> None:
    if (
        isinstance(value, str)
        and PLACEHOLDER.search(INLINE_CODE.sub("", value))
    ):
        fail(path, f"unresolved placeholder {value!r}")
    if isinstance(value, dict):
        for key, item in value.items():
            reject_placeholders(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_placeholders(item, f"{path}[{index}]")


def required_string(record: dict[str, Any], key: str, path: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(f"{path}.{key}", "must be a non-empty string")
    return value.strip()


def required_list(record: dict[str, Any], key: str, path: str) -> list[Any]:
    value = record.get(key)
    if not isinstance(value, list):
        fail(f"{path}.{key}", "must be a list")
    return value


def validate_weight(record: dict[str, Any], path: str) -> None:
    required_string(record, "type", path)
    weight = record.get("weight")
    if (
        not isinstance(weight, (int, float))
        or isinstance(weight, bool)
        or not 0 <= float(weight) <= 1
    ):
        fail(f"{path}.weight", "must be a number from 0 to 1")


def load_json_object(path: Path) -> dict[str, Any]:
    """Load generated data whose quoted source text may contain angle brackets."""
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        fail(str(path), "file was not produced")
    except json.JSONDecodeError as error:
        fail(str(path), f"invalid JSON: {error}")
    if not isinstance(value, dict):
        fail(str(path), "top level must be an object")
    return value


def validate_canonical_turn(
    path: Path, limits: dict[str, int] | None = None
) -> dict[str, Any]:
    data = load_json_object(path)
    if data.get("schema_version") != 1:
        fail("$.schema_version", "must equal 1")
    for key in ("trace_id", "source", "session_id", "turn_id", "timestamp"):
        required_string(data, key, "$")
    for key in ("user", "assistant", "outcome", "tool_summary", "provenance"):
        if not isinstance(data.get(key), dict):
            fail(f"$.{key}", "must be an object")
    user = required_string(data["user"], "text", "$.user")
    assistant = data["assistant"].get("text")
    if not isinstance(assistant, str):
        fail("$.assistant.text", "must be a string")
    status = required_string(data["outcome"], "status", "$.outcome")
    if status not in {"completed", "failed", "aborted", "unknown"}:
        fail("$.outcome.status", "must be completed, failed, aborted, or unknown")
    error = data["outcome"].get("error")
    if error is not None and not isinstance(error, str):
        fail("$.outcome.error", "must be a string or null")
    summary = data["tool_summary"]
    count = summary.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        fail("$.tool_summary.count", "must be a non-negative integer")
    names = required_list(summary, "names", "$.tool_summary")
    if not all(isinstance(value, str) and value for value in names):
        fail("$.tool_summary.names", "must contain non-empty strings")
    evidence = summary.get("evidence_path")
    if evidence is not None and not isinstance(evidence, str):
        fail("$.tool_summary.evidence_path", "must be a string or null")
    required_string(data["provenance"], "raw_file", "$.provenance")
    timing = data.get("timing")
    if timing is not None:
        if not isinstance(timing, dict):
            fail("$.timing", "must be an object")
        for key in (
            "started_at_epoch",
            "completed_at_epoch",
            "duration_ms",
            "time_to_first_token_ms",
        ):
            value = timing.get(key)
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or value < 0
            ):
                fail(f"$.timing.{key}", "must be a non-negative number or null")
    if limits:
        for value, key in (
            (user, "user_chars"),
            (assistant, "assistant_chars"),
            (error or "", "error_chars"),
        ):
            maximum = limits.get(key)
            if isinstance(maximum, int) and len(value) > maximum:
                fail(f"$.{key}", f"exceeds configured limit {maximum}")
    return data


def validate_task_trajectory(
    path: Path, expected_trace_id: str | None = None
) -> dict[str, Any]:
    data = load_json_object(path)
    if data.get("schema_version") != 1:
        fail("$.schema_version", "must equal 1")
    trace_id = required_string(data, "trace_id", "$")
    if expected_trace_id is not None and trace_id != expected_trace_id:
        fail("$.trace_id", f"must equal {expected_trace_id!r}")
    required_string(data, "session_id", "$")
    for key in ("task", "outcome", "provenance"):
        if not isinstance(data.get(key), dict):
            fail(f"$.{key}", "must be an object")
    required_string(data["task"], "text", "$.task")
    required_string(data["outcome"], "status", "$.outcome")
    required_string(data["provenance"], "turn_path", "$.provenance")
    events = required_list(data, "events", "$")
    previous_sequence = 0
    allowed_phases = {"inspect", "modify", "execute", "verify"}
    for index, event in enumerate(events):
        event_path = f"$.events[{index}]"
        if not isinstance(event, dict):
            fail(event_path, "must be an object")
        sequence = event.get("sequence")
        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or sequence <= previous_sequence
        ):
            fail(f"{event_path}.sequence", "must be a strictly increasing integer")
        previous_sequence = sequence
        required_string(event, "tool", event_path)
        phase = required_string(event, "phase", event_path)
        if phase not in allowed_phases:
            fail(f"{event_path}.phase", "has an unknown value")
        status = required_string(event, "status", event_path)
        if status not in {"completed", "failed", "unknown"}:
            fail(f"{event_path}.status", "has an unknown value")
        for key in (
            "arguments_preview",
            "argument_sha256",
            "result_preview",
            "result_sha256",
        ):
            if not isinstance(event.get(key), str):
                fail(f"{event_path}.{key}", "must be a string")
        targets = required_list(event, "targets", event_path)
        if not all(isinstance(target, str) for target in targets):
            fail(f"{event_path}.targets", "must contain strings")
    phases = required_list(data, "phases", "$")
    for index, phase in enumerate(phases):
        phase_path = f"$.phases[{index}]"
        if not isinstance(phase, dict):
            fail(phase_path, "must be an object")
        name = required_string(phase, "phase", phase_path)
        if name not in allowed_phases:
            fail(f"{phase_path}.phase", "has an unknown value")
        for key in ("start_sequence", "end_sequence", "event_count", "failed_count"):
            value = phase.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                fail(f"{phase_path}.{key}", "must be a non-negative integer")
        if phase["event_count"] < 1:
            fail(f"{phase_path}.event_count", "must be positive")
        if phase["start_sequence"] > phase["end_sequence"]:
            fail(phase_path, "start_sequence must not exceed end_sequence")
    observations = required_list(data, "assistant_observations", "$")
    for index, observation in enumerate(observations):
        observation_path = f"$.assistant_observations[{index}]"
        if not isinstance(observation, dict):
            fail(observation_path, "must be an object")
        required_string(observation, "text", observation_path)
        digest = required_string(
            observation, "text_sha256", observation_path
        )
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            fail(f"{observation_path}.text_sha256", "must be a SHA-256 digest")
        count = observation.get("after_tool_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            fail(
                f"{observation_path}.after_tool_count",
                "must be a non-negative integer",
            )
        if count > len(events):
            fail(
                f"{observation_path}.after_tool_count",
                "cannot exceed event count",
            )
        ordinal = observation.get("source_ordinal")
        if ordinal is not None and (
            not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0
        ):
            fail(
                f"{observation_path}.source_ordinal",
                "must be a non-negative integer or null",
            )
    return data


def validate_cluster_manifest(
    path: Path,
    cluster: str,
    turns_root: Path,
) -> set[str]:
    trace_ids: set[str] = set()
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        fail(str(path), "file was not produced")
    if not lines:
        fail(str(path), "must contain at least one record")
    for index, line in enumerate(lines, start=1):
        item_path = f"{path}:{index}"
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            fail(item_path, f"invalid JSON: {error}")
        if not isinstance(row, dict):
            fail(item_path, "must be an object")
        if row.get("schema_version") != 1:
            fail(f"{item_path}.schema_version", "must equal 1")
        if row.get("cluster") != cluster:
            fail(f"{item_path}.cluster", f"must equal {cluster!r}")
        trace_id = required_string(row, "trace_id", item_path)
        if trace_id in trace_ids:
            fail(f"{item_path}.trace_id", "duplicates this manifest")
        trace_ids.add(trace_id)
        relative = required_string(row, "turn_path", item_path)
        turn_path = turns_root.parents[3] / relative
        turn = validate_canonical_turn(turn_path)
        if turn["trace_id"] != trace_id:
            fail(f"{item_path}.turn_path", "does not resolve to this trace_id")
        score = row.get("score")
        if (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not 0 <= float(score) <= 1
        ):
            fail(f"{item_path}.score", "must be a number from 0 to 1")
    return trace_ids


def validate_signal_findings(
    path: Path, eligible_trace_ids: set[str]
) -> set[str]:
    signal_ids: set[str] = set()
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        fail(str(path), "file was not produced")
    for index, line in enumerate(lines, start=1):
        item_path = f"{path}:{index}"
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            fail(item_path, f"invalid JSON: {error}")
        if not isinstance(row, dict):
            fail(item_path, "must be an object")
        if row.get("schema_version") != 1:
            fail(f"{item_path}.schema_version", "must equal 1")
        signal_id = required_string(row, "signal_id", item_path)
        if signal_id in signal_ids:
            fail(f"{item_path}.signal_id", "must be unique")
        signal_ids.add(signal_id)
        required_string(row, "detector", item_path)
        required_string(row, "detector_version", item_path)
        severity = required_string(row, "severity", item_path)
        if severity not in {"low", "medium", "high", "critical"}:
            fail(f"{item_path}.severity", "has an unknown value")
        routing = required_string(row, "routing", item_path)
        if routing not in {"skill_evolution", "infrastructure"}:
            fail(f"{item_path}.routing", "has an unknown value")
        confidence = row.get("confidence")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= float(confidence) <= 1
        ):
            fail(f"{item_path}.confidence", "must be a number from 0 to 1")
        trace_ids = required_list(row, "trace_ids", item_path)
        if not trace_ids or not all(
            isinstance(value, str) and value in eligible_trace_ids
            for value in trace_ids
        ):
            fail(f"{item_path}.trace_ids", "must reference eligible traces")
        features = row.get("features")
        if not isinstance(features, dict):
            fail(f"{item_path}.features", "must be an object")
        evidence = row.get("evidence")
        if not isinstance(evidence, list):
            fail(f"{item_path}.evidence", "must be a list")
        methodology = features.get("candidate_source") in {
            "methodology",
            "methodology_consolidated",
        }
        for evidence_index, record in enumerate(evidence):
            evidence_path = f"{item_path}.evidence[{evidence_index}]"
            if not isinstance(record, dict):
                fail(evidence_path, "must be an object")
            evidence_trace = required_string(record, "trace_id", evidence_path)
            if evidence_trace not in eligible_trace_ids:
                fail(f"{evidence_path}.trace_id", "must reference an eligible trace")
            required_string(record, "turn_path", evidence_path)
            digest = required_string(record, "quote_sha256", evidence_path)
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                fail(f"{evidence_path}.quote_sha256", "must be a SHA-256 digest")
            quote = record.get("quote")
            if methodology and (not isinstance(quote, str) or not quote):
                fail(f"{evidence_path}.quote", "is required for methodology evidence")
            if isinstance(quote, str) and hashlib.sha256(quote.encode()).hexdigest() != digest:
                fail(f"{evidence_path}.quote_sha256", "does not match quote")
    return signal_ids


def validate_signal_patterns(path: Path, signal_ids: set[str]) -> set[str]:
    pattern_ids: set[str] = set()
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        fail(str(path), "file was not produced")
    for index, line in enumerate(lines, start=1):
        item_path = f"{path}:{index}"
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            fail(item_path, f"invalid JSON: {error}")
        if not isinstance(row, dict):
            fail(item_path, "must be an object")
        pattern_id = required_string(row, "pattern_id", item_path)
        if pattern_id in pattern_ids:
            fail(f"{item_path}.pattern_id", "must be unique")
        pattern_ids.add(pattern_id)
        required_string(row, "fingerprint", item_path)
        required_string(row, "kind", item_path)
        evidence = required_list(row, "evidence_signal_ids", item_path)
        if not evidence or not all(value in signal_ids for value in evidence):
            fail(
                f"{item_path}.evidence_signal_ids",
                "must reference known findings",
            )
    return pattern_ids


def validate_selected_findings(
    path: Path, signal_ids: set[str], eligible_trace_ids: set[str]
) -> set[str]:
    selected: set[str] = set()
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        fail(str(path), "file was not produced")
    for index, line in enumerate(lines, start=1):
        item_path = f"{path}:{index}"
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            fail(item_path, f"invalid JSON: {error}")
        if not isinstance(row, dict):
            fail(item_path, "must be an object")
        finding_id = required_string(row, "finding_id", item_path)
        if finding_id not in signal_ids or finding_id in selected:
            fail(f"{item_path}.finding_id", "must reference one unique finding")
        selected.add(finding_id)
        if required_string(row, "trace_id", item_path) not in eligible_trace_ids:
            fail(f"{item_path}.trace_id", "must reference an eligible trace")
        required_string(row, "turn_path", item_path)
    return selected


def validate_selection_decisions(
    path: Path, signal_ids: set[str], selected_ids: set[str]
) -> None:
    decisions: dict[str, str] = {}
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        fail(str(path), "file was not produced")
    for index, line in enumerate(lines, start=1):
        item_path = f"{path}:{index}"
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            fail(item_path, f"invalid JSON: {error}")
        if not isinstance(row, dict):
            fail(item_path, "must be an object")
        finding_id = required_string(row, "finding_id", item_path)
        if finding_id not in signal_ids or finding_id in decisions:
            fail(f"{item_path}.finding_id", "must reference one unique finding")
        disposition = required_string(row, "disposition", item_path)
        if disposition not in {
            "rejected",
            "deduplicated",
            "selected",
            "deferred",
        }:
            fail(f"{item_path}.disposition", "has an unknown value")
        required_string(row, "reason", item_path)
        decisions[finding_id] = disposition
    if set(decisions) != signal_ids:
        fail(str(path), "must contain exactly one decision per finding")
    decided_selected = {
        finding_id
        for finding_id, disposition in decisions.items()
        if disposition == "selected"
    }
    if decided_selected != selected_ids:
        fail(str(path), "selected decisions must match selected manifest")


def validate_dedup_manifest(
    path: Path, eligible_trace_ids: set[str]
) -> dict[str, str]:
    aliases: dict[str, str] = {}
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        fail(str(path), "file was not produced")
    for index, line in enumerate(lines, start=1):
        item_path = f"{path}:{index}"
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            fail(item_path, f"invalid JSON: {error}")
        if not isinstance(row, dict):
            fail(item_path, "must be an object")
        trace_id = required_string(row, "trace_id", item_path)
        representative = required_string(
            row, "representative_trace_id", item_path
        )
        if trace_id in aliases:
            fail(f"{item_path}.trace_id", "must be unique")
        if (
            trace_id not in eligible_trace_ids
            or representative not in eligible_trace_ids
        ):
            fail(item_path, "must reference eligible traces")
        relation = required_string(row, "relation", item_path)
        if relation not in {
            "representative",
            "exact_duplicate",
            "near_duplicate",
        }:
            fail(f"{item_path}.relation", "has an unknown value")
        similarity = row.get("similarity")
        if (
            not isinstance(similarity, (int, float))
            or isinstance(similarity, bool)
            or not 0 <= float(similarity) <= 1
        ):
            fail(f"{item_path}.similarity", "must be a number from 0 to 1")
        required_string(row, "content_sha256", item_path)
        aliases[trace_id] = representative
    if set(aliases) != eligible_trace_ids:
        fail(str(path), "must cover every eligible trace exactly once")
    for trace_id, representative in aliases.items():
        if aliases.get(representative) != representative:
            fail(
                f"{path}:{trace_id}",
                "representative must point to itself",
            )
    return aliases


def _validate_changelog_entry(record: Any, path: str) -> str:
    if not isinstance(record, dict):
        fail(path, "must be an object")
    required_string(record, "id", path)
    skill = required_string(record, "skill", path)
    operation = required_string(record, "operation", path)
    if operation not in KNOWN_OPS:
        fail(f"{path}.operation", "must be create, update, delete, merge, or split")
    required_string(record, "run_id", path)
    required_string(record, "finding_id", path)
    changed_on = required_string(record, "date", path)
    try:
        parsed_date = date.fromisoformat(changed_on)
    except ValueError:
        fail(f"{path}.date", "must be a valid ISO date")
    if parsed_date.isoformat() != changed_on:
        fail(f"{path}.date", "must use YYYY-MM-DD")
    op_index = record.get("op_index")
    if not isinstance(op_index, int) or isinstance(op_index, bool) or op_index < 1:
        fail(f"{path}.op_index", "must be a positive integer")
    for key in ("sections", "directories"):
        values = required_list(record, key, path)
        if not all(isinstance(value, str) and value.strip() for value in values):
            fail(f"{path}.{key}", "must contain non-empty strings")
    for key in ("before_sha256", "after_sha256"):
        digest = record.get(key)
        if digest is not None and (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            fail(f"{path}.{key}", "must be null or a SHA-256 digest")
    if record.get("status") not in {"pending", "accepted"}:
        fail(f"{path}.status", "must be pending or accepted")
    return skill


def validate_changelog(
    path: Path,
    expected_skills: set[str] | None = None,
) -> dict[str, Any]:
    data = load_json_object(path)
    if data.get("schema_version") != 1:
        fail("$.schema_version", "must equal 1")
    changes = required_list(data, "changes", "$")
    if not changes:
        fail("$.changes", "must not be empty")
    ids: set[str] = set()
    skills: set[str] = set()
    dates: set[str] = set()
    operation_identity: tuple[object, ...] | None = None
    for index, change in enumerate(changes):
        change_path = f"$.changes[{index}]"
        skill = _validate_changelog_entry(change, change_path)
        change_id = str(change["id"])
        if change_id in ids:
            fail(f"{change_path}.id", "duplicates another changelog entry")
        ids.add(change_id)
        skills.add(skill)
        dates.add(str(change["date"]))
        identity = (
            change.get("run_id"),
            change.get("finding_id"),
            change.get("op_index"),
            change.get("operation"),
        )
        if operation_identity is None:
            operation_identity = identity
        elif identity != operation_identity:
            fail(
                change_path,
                "must use the same run, finding, op index, and operation",
            )
    if len(dates) != 1:
        fail("$.changes", "all entries for one operation must use the same date")
    if expected_skills is not None and skills != expected_skills:
        fail("$.changes", "does not match the expected skill set")
    markers = required_list(data, "phase_markers", "$")
    marker_names: set[str] = set()
    for index, marker in enumerate(markers):
        marker_path = f"$.phase_markers[{index}]"
        if not isinstance(marker, dict):
            fail(marker_path, "must be an object")
        phase = required_string(marker, "phase", marker_path)
        if phase not in OPERATION_PHASES:
            fail(f"{marker_path}.phase", "has an unknown operation phase")
        if phase in marker_names:
            fail(f"{marker_path}.phase", "duplicates another phase marker")
        marker_names.add(phase)
        status = required_string(marker, "status", marker_path)
        if status not in PHASE_STATUSES:
            fail(f"{marker_path}.status", "has an unknown phase status")
        marker_date = required_string(marker, "date", marker_path)
        try:
            parsed_marker_date = date.fromisoformat(marker_date)
        except ValueError:
            fail(f"{marker_path}.date", "must be a valid ISO date")
        if parsed_marker_date.isoformat() != marker_date:
            fail(f"{marker_path}.date", "must use YYYY-MM-DD")
        marked_at = required_string(marker, "at", marker_path)
        try:
            datetime.fromisoformat(marked_at)
        except ValueError:
            fail(f"{marker_path}.at", "must be an ISO timestamp")
        if status in {"skipped", "failed"}:
            required_string(marker, "reason", marker_path)
    if marker_names != set(OPERATION_PHASES):
        fail(
            "$.phase_markers",
            "must contain goal, optimize, verification, and judge exactly once",
        )
    goal_marker = next(
        marker
        for marker in markers
        if isinstance(marker, dict) and marker.get("phase") == "goal"
    )
    if goal_marker.get("status") != "completed":
        fail("$.phase_markers", "goal phase must be completed")
    events = required_list(data, "phase_events", "$")
    if not events:
        fail("$.phase_events", "must not be empty")
    event_state: dict[str, str] = {}
    last_event: dict[str, dict[str, Any]] = {}
    previous_at: datetime | None = None
    allowed_transitions = {
        None: {"pending", "completed"},
        "pending": {"running", "skipped", "failed"},
        "running": {"completed", "failed"},
        "completed": {"running"},
        "skipped": set(),
        "failed": set(),
    }
    for index, event in enumerate(events):
        event_path = f"$.phase_events[{index}]"
        if not isinstance(event, dict):
            fail(event_path, "must be an object")
        phase = required_string(event, "phase", event_path)
        status = required_string(event, "status", event_path)
        if phase not in OPERATION_PHASES:
            fail(f"{event_path}.phase", "has an unknown operation phase")
        if status not in PHASE_STATUSES:
            fail(f"{event_path}.status", "has an unknown phase status")
        event_date = required_string(event, "date", event_path)
        try:
            parsed_event_date = date.fromisoformat(event_date)
        except ValueError:
            fail(f"{event_path}.date", "must be a valid ISO date")
        if parsed_event_date.isoformat() != event_date:
            fail(f"{event_path}.date", "must use YYYY-MM-DD")
        marked_at = required_string(event, "at", event_path)
        try:
            parsed_at = datetime.fromisoformat(marked_at)
        except ValueError:
            fail(f"{event_path}.at", "must be an ISO timestamp")
        if previous_at is not None and parsed_at < previous_at:
            fail(f"{event_path}.at", "must not precede the prior phase event")
        previous_at = parsed_at
        if status in {"skipped", "failed"}:
            required_string(event, "reason", event_path)
        previous_status = event_state.get(phase)
        if status not in allowed_transitions[previous_status]:
            fail(
                f"{event_path}.status",
                f"cannot follow {previous_status or 'no prior status'}",
            )
        event_state[phase] = status
        last_event[phase] = event
    for marker in markers:
        phase = str(marker["phase"])
        latest = last_event.get(phase)
        if latest is None:
            fail("$.phase_events", f"has no event for phase {phase!r}")
        for key in ("status", "date", "at", "reason"):
            if marker.get(key) != latest.get(key):
                fail(
                    "$.phase_markers",
                    f"{phase!r} marker does not match its latest event",
                )
    return data


def validate_metadata(path: Path, skill_names: set[str] | None = None) -> dict[str, Any]:
    data = load_object(path)
    rows = required_list(data, "skills_metadata", "$")
    seen: set[str] = set()
    dependencies_by_skill: dict[str, list[str]] = {}
    for index, row in enumerate(rows):
        item_path = f"$.skills_metadata[{index}]"
        if not isinstance(row, dict):
            fail(item_path, "must be an object")
        name = required_string(row, "skill", item_path)
        folded = name.casefold()
        if folded in seen:
            fail(f"{item_path}.skill", "duplicates another skill")
        seen.add(folded)
        labels = required_list(row, "skill_types", item_path)
        for label_index, label in enumerate(labels):
            if not isinstance(label, dict):
                fail(f"{item_path}.skill_types[{label_index}]", "must be an object")
            validate_weight(label, f"{item_path}.skill_types[{label_index}]")
        unmatched = row.get("unmatched_skill_types", [])
        if not isinstance(unmatched, list):
            fail(f"{item_path}.unmatched_skill_types", "must be a list")
        for label_index, label in enumerate(unmatched):
            if not isinstance(label, dict):
                fail(
                    f"{item_path}.unmatched_skill_types[{label_index}]",
                    "must be an object",
                )
            validate_weight(label, f"{item_path}.unmatched_skill_types[{label_index}]")
        dependencies = row.get("dependencies", [])
        if not isinstance(dependencies, list) or any(
            not isinstance(value, str) or not value
            for value in dependencies
        ):
            fail(f"{item_path}.dependencies", "must be a list of skill names")
        if len(set(dependencies)) != len(dependencies):
            fail(f"{item_path}.dependencies", "must not contain duplicates")
        if name in dependencies:
            fail(f"{item_path}.dependencies", "must not contain the skill itself")
        dependencies_by_skill[name] = dependencies
        changelog = row.get("changelog", [])
        if not isinstance(changelog, list):
            fail(f"{item_path}.changelog", "must be a list")
        change_ids: set[str] = set()
        for change_index, change in enumerate(changelog):
            change_path = f"{item_path}.changelog[{change_index}]"
            changed_skill = _validate_changelog_entry(change, change_path)
            if changed_skill != name:
                fail(f"{change_path}.skill", f"must equal {name!r}")
            change_id = str(change["id"])
            if change_id in change_ids:
                fail(f"{change_path}.id", "duplicates another changelog entry")
            change_ids.add(change_id)
        sources = row.get("sources", [])
        if not isinstance(sources, list):
            fail(f"{item_path}.sources", "must be a list")
        for source_index, source in enumerate(sources):
            source_path = f"{item_path}.sources[{source_index}]"
            if not isinstance(source, dict):
                fail(source_path, "must be an object")
            url = required_string(source, "url", source_path)
            if not url.startswith(("https://", "http://")):
                fail(f"{source_path}.url", "must be an HTTP(S) URL")
            revision = required_string(source, "revision", source_path)
            if revision.casefold() in {"main", "master", "head", "latest"}:
                fail(f"{source_path}.revision", "must be pinned, not a moving ref")
            retrieved_at = required_string(
                source, "retrieved_at", source_path
            )
            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
                retrieved_at,
            ):
                fail(
                    f"{source_path}.retrieved_at",
                    "must be an ISO-8601 timestamp with timezone",
                )
            digest = required_string(source, "sha256", source_path)
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                fail(f"{source_path}.sha256", "must be 64 lowercase hex characters")
        lifecycle = row.get("lifecycle")
        if lifecycle is not None:
            lifecycle_path = f"{item_path}.lifecycle"
            if not isinstance(lifecycle, dict):
                fail(lifecycle_path, "must be an object")
            status = required_string(lifecycle, "status", lifecycle_path)
            if status not in {
                "provisional",
                "stable",
                "evaluated",
                "promoted",
            }:
                fail(f"{lifecycle_path}.status", "has an unknown value")
            required_string(lifecycle, "origin_run_id", lifecycle_path)
            required_string(lifecycle, "origin_finding_id", lifecycle_path)
            sessions = required_list(
                lifecycle, "origin_session_ids", lifecycle_path
            )
            if not sessions or not all(
                isinstance(value, str) and value for value in sessions
            ):
                fail(
                    f"{lifecycle_path}.origin_session_ids",
                    "must contain non-empty strings",
                )
            confidence = lifecycle.get("confidence")
            if (
                not isinstance(confidence, (int, float))
                or isinstance(confidence, bool)
                or not 0 <= float(confidence) <= 1
            ):
                fail(
                    f"{lifecycle_path}.confidence",
                    "must be a number from 0 to 1",
                )
            for field in ("evidence_records", "distinct_windows"):
                value = lifecycle.get(field)
                if (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or value < 0
                ):
                    fail(
                        f"{lifecycle_path}.{field}",
                        "must be a non-negative integer",
                    )
            if "seeded_from" in lifecycle:
                required_string(lifecycle, "seeded_from", lifecycle_path)
            for field in ("evaluated_at", "promoted_at", "evaluation_kind"):
                if field in lifecycle:
                    required_string(lifecycle, field, lifecycle_path)
            if "content_sha256" in lifecycle:
                digest = required_string(
                    lifecycle, "content_sha256", lifecycle_path
                )
                if not re.fullmatch(r"[0-9a-f]{64}", digest):
                    fail(
                        f"{lifecycle_path}.content_sha256",
                        "must be 64 lowercase hex characters",
                    )
    if skill_names is not None:
        missing = sorted(name for name in skill_names if name.casefold() not in seen)
        if missing:
            fail("$.skills_metadata", f"missing records for: {', '.join(missing)}")
        known = {name.casefold() for name in skill_names}
        for name, dependencies in dependencies_by_skill.items():
            unknown = sorted(
                value for value in dependencies if value.casefold() not in known
            )
            if unknown:
                fail(
                    f"$.skills_metadata[{name}].dependencies",
                    f"references unknown skills: {', '.join(unknown)}",
                )
    return data


def validate_diagnosis(
    path: Path, allowed_clusters: set[str] | None = None
) -> dict[str, Any]:
    data = load_object(path)
    for key in (
        "skill_capabilities_missing",
        "newly_detected_skill_capabilites_missing",
    ):
        rows = required_list(data, key, "$")
        for index, row in enumerate(rows):
            item_path = f"$.{key}[{index}]"
            if not isinstance(row, dict):
                fail(item_path, "must be an object")
            required_string(row, "type", item_path)
            required_string(row, "description", item_path)
            confidence = row.get("confidence")
            if (
                not isinstance(confidence, (int, float))
                or isinstance(confidence, bool)
                or not 0 <= float(confidence) <= 1
            ):
                fail(f"{item_path}.confidence", "must be a number from 0 to 1")
            required_string(row, "reasoning", item_path)
            evidence = required_list(row, "evidence_list", item_path)
            if not all(isinstance(value, str) and value.strip() for value in evidence):
                fail(f"{item_path}.evidence_list", "must contain non-empty strings")
            if allowed_clusters is not None:
                if row.get("cluster") not in allowed_clusters:
                    fail(
                        f"{item_path}.cluster",
                        "must name a discovered cluster directory",
                    )
            elif "cluster" in row:
                fail(f"{item_path}.cluster", "must be omitted in cut-only mode")
    return data


def validate_label_matching(path: Path, cluster: str) -> dict[str, Any]:
    data = load_object(path)
    matching = data.get("matching")
    if not isinstance(matching, dict):
        fail("$.matching", "must be an object")
    required_string(matching, "strategy", "$.matching")
    version = matching.get("config_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        fail("$.matching.config_version", "must be a positive integer")
    config_hash = required_string(matching, "config_sha256", "$.matching")
    if not re.fullmatch(r"[0-9a-f]{64}", config_hash):
        fail("$.matching.config_sha256", "must be a SHA-256 hex digest")
    rows = required_list(data, "clusters", "$")
    if len(rows) != 1 or not isinstance(rows[0], dict):
        fail("$.clusters", "must contain exactly this session's cluster")
    row = rows[0]
    if cluster == "cut":
        if row.get("cluster") not in (None, "cut"):
            fail("$.clusters[0].cluster", "must be omitted or equal 'cut'")
    elif row.get("cluster") != cluster:
        fail("$.clusters[0].cluster", f"must equal {cluster!r}")
    labels = required_list(row, "labels", "$.clusters[0]")
    if not all(isinstance(value, str) and value.strip() for value in labels):
        fail("$.clusters[0].labels", "must contain non-empty strings")
    skills = required_list(row, "skills", "$.clusters[0]")
    for index, skill in enumerate(skills):
        item_path = f"$.clusters[0].skills[{index}]"
        if not isinstance(skill, dict):
            fail(item_path, "must be an object")
        required_string(skill, "skill", item_path)
        score = skill.get("score")
        if (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or float(score) < 0
        ):
            fail(f"{item_path}.score", "must be a non-negative number")
        matches = required_list(skill, "labels", item_path)
        for label_index, label in enumerate(matches):
            if not isinstance(label, dict):
                fail(f"{item_path}.labels[{label_index}]", "must be an object")
            validate_weight(label, f"{item_path}.labels[{label_index}]")
        reasons = required_list(skill, "matches", item_path)
        if not reasons:
            fail(f"{item_path}.matches", "must not be empty")
        for reason_index, reason in enumerate(reasons):
            reason_path = f"{item_path}.matches[{reason_index}]"
            if not isinstance(reason, dict):
                fail(reason_path, "must be an object")
            required_string(reason, "cluster_type", reason_path)
            required_string(reason, "skill_type", reason_path)
            similarity = reason.get("similarity")
            if (
                not isinstance(similarity, (int, float))
                or isinstance(similarity, bool)
                or not 0 <= float(similarity) <= 1
            ):
                fail(f"{reason_path}.similarity", "must be a number from 0 to 1")
            contribution = reason.get("contribution")
            if (
                not isinstance(contribution, (int, float))
                or isinstance(contribution, bool)
                or float(contribution) < 0
            ):
                fail(
                    f"{reason_path}.contribution",
                    "must be a non-negative number",
                )
    return data


def _validate_skill_objects(rows: Any, path: str) -> None:
    if not isinstance(rows, list) or not rows:
        fail(path, "must be a non-empty list")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            fail(f"{path}[{index}]", "must be an object")
        required_string(row, "skill", f"{path}[{index}]")


def _validate_change_lists(record: dict[str, Any], path: str) -> None:
    for key in ("sections", "dirs"):
        values = record.get(key, [])
        if not isinstance(values, list):
            fail(f"{path}.{key}", "must be a list")
        for index, value in enumerate(values):
            item_path = f"{path}.{key}[{index}]"
            if isinstance(value, str):
                if not value.strip():
                    fail(item_path, "must not be empty")
                continue
            if not isinstance(value, dict):
                fail(item_path, "must be a string or object")
            field = "section" if key == "sections" else "dir"
            required_string(value, field, item_path)
            required_string(value, "goal", item_path)
    removals = record.get("remove", [])
    if not isinstance(removals, list) or any(
        not isinstance(value, str) or not value.strip() for value in removals
    ):
        fail(f"{path}.remove", "must be a list of non-empty strings")


def validate_goal(path: Path, *, exactly_one_op: bool = False) -> dict[str, Any]:
    data = load_object(path)
    goal = data.get("goal")
    if not isinstance(goal, dict):
        fail("$.goal", "must be an object")
    if not isinstance(goal.get("improve_skills"), list):
        fail("$.goal.improve_skills", "must be a list")
    required_string(data, "reasoning", "$")
    required_string(data, "plan", "$")
    required_string(data, "feedback_to", "$")
    action = data.get("action")
    if not isinstance(action, dict):
        fail("$.action", "must be an object")
    ops = required_list(action, "ops", "$.action")
    if not ops:
        if exactly_one_op:
            fail("$.action.ops", "must contain exactly one active op")
        if action.get("disposition") != "no_change":
            fail(
                "$.action.disposition",
                "must equal no_change when action.ops is empty",
            )
        required_string(action, "reason", "$.action")
        if goal.get("improve_skills"):
            fail(
                "$.goal.improve_skills",
                "must be empty for a no-change disposition",
            )
        return data
    if exactly_one_op and len(ops) != 1:
        fail("$.action.ops", "must contain exactly one active op")
    for index, op in enumerate(ops):
        op_path = f"$.action.ops[{index}]"
        if not isinstance(op, dict):
            fail(op_path, "must be an object")
        name = required_string(op, "op", op_path)
        if name in {"create", "update", "delete"}:
            _validate_skill_objects(op.get("skills"), f"{op_path}.skills")
        elif name == "merge":
            sources = op.get("skills")
            if (
                not isinstance(sources, list)
                or len(sources) < 2
                or not all(isinstance(value, str) and value.strip() for value in sources)
            ):
                fail(f"{op_path}.skills", "must name at least two source skills")
            into = op.get("into")
            if not isinstance(into, dict):
                fail(f"{op_path}.into", "must be an object")
            required_string(into, "skill", f"{op_path}.into")
        elif name == "split":
            required_string(op, "skill", op_path)
            _validate_skill_objects(op.get("into"), f"{op_path}.into")
        elif name not in KNOWN_OPS:
            required_string(op, "description", op_path)
        if name == "create":
            for skill_index, skill in enumerate(op["skills"]):
                skill_path = f"{op_path}.skills[{skill_index}]"
                required_string(skill, "description", skill_path)
                _validate_change_lists(skill, skill_path)
                if not skill.get("sections"):
                    fail(f"{skill_path}.sections", "must not be empty")
                labels = skill.get("labels")
                if not isinstance(labels, list) or len(labels) < 3:
                    fail(
                        f"{op_path}.skills[{skill_index}].labels",
                        "must contain at least three labels",
                    )
                for label_index, label in enumerate(labels):
                    if not isinstance(label, dict):
                        fail(
                            f"{op_path}.skills[{skill_index}].labels[{label_index}]",
                            "must be an object",
                        )
                    validate_weight(
                        label,
                        f"{op_path}.skills[{skill_index}].labels[{label_index}]",
                    )
                dependencies = skill.get("dependencies", [])
                if not isinstance(dependencies, list) or any(
                    not isinstance(value, str) or not value
                    for value in dependencies
                ):
                    fail(
                        f"{skill_path}.dependencies",
                        "must be a list of skill names",
                    )
                if skill["skill"] in dependencies:
                    fail(
                        f"{skill_path}.dependencies",
                        "must not contain the skill itself",
                    )
        elif name == "update":
            for skill_index, skill in enumerate(op["skills"]):
                skill_path = f"{op_path}.skills[{skill_index}]"
                required_string(skill, "goal", skill_path)
                required_string(skill, "facet", skill_path)
                _validate_change_lists(skill, skill_path)
                if (
                    not skill.get("sections")
                    and not skill.get("dirs")
                    and not skill.get("remove")
                ):
                    fail(
                        skill_path,
                        "must name at least one section, directory, or removal change",
                    )
        elif name == "delete":
            for skill_index, skill in enumerate(op["skills"]):
                required_string(
                    skill, "reason", f"{op_path}.skills[{skill_index}]"
                )
        elif name == "merge":
            into = op["into"]
            required_string(into, "description", f"{op_path}.into")
            _validate_change_lists(into, f"{op_path}.into")
        elif name == "split":
            for part_index, part in enumerate(op["into"]):
                part_path = f"{op_path}.into[{part_index}]"
                required_string(part, "description", part_path)
                _validate_change_lists(part, part_path)
    return data


def validate_verification_input(path: Path) -> dict[str, Any]:
    data = load_object(path)
    if data.get("schema_version") != 1:
        fail("$.schema_version", "must equal 1")
    required_string(data, "run_id", "$")
    required_string(data, "finding_id", "$")
    operation = required_string(data, "operation", "$")
    if operation not in KNOWN_OPS:
        fail("$.operation", "must be create, update, delete, merge, or split")
    op_index = data.get("op_index")
    if not isinstance(op_index, int) or isinstance(op_index, bool) or op_index < 1:
        fail("$.op_index", "must be a positive integer")
    scoring = data.get("scoring")
    if not isinstance(scoring, dict):
        fail("$.scoring", "must be an object")
    if scoring.get("strategy_version") != 1:
        fail("$.scoring.strategy_version", "must equal 1")
    scale = scoring.get("scale")
    if not isinstance(scale, dict):
        fail("$.scoring.scale", "must be an object")
    if scale.get("min") != 0 or scale.get("max") != 1:
        fail("$.scoring.scale", "must use the normalized 0 to 1 scale")
    anchors = scoring.get("assertion_score_anchors")
    try:
        anchor_values = (
            {float(value) for value in anchors}
            if isinstance(anchors, dict)
            else set()
        )
    except (TypeError, ValueError):
        anchor_values = set()
    if anchor_values != ASSERTION_SCORE_ANCHORS:
        fail(
            "$.scoring.assertion_score_anchors",
            "must define 0, 0.25, 0.5, 0.75, and 1 anchors",
        )
    if not all(isinstance(value, str) and value.strip() for value in anchors.values()):
        fail(
            "$.scoring.assertion_score_anchors",
            "anchor descriptions must be non-empty strings",
        )
    threshold = scoring.get("pass_threshold")
    if (
        not isinstance(threshold, (int, float))
        or isinstance(threshold, bool)
        or not 0 < float(threshold) <= 1
    ):
        fail("$.scoring.pass_threshold", "must be a number above 0 and at most 1")
    expected_strategy = {
        "step_aggregation": "arithmetic_mean",
        "skill_aggregation": "weighted_mean_applicable",
        "overall_aggregation": "minimum",
        "required_assertion_policy": "all_must_pass",
        "required_step_policy": "all_applicable_must_pass",
        "replay_policy": "hard_gate",
    }
    for field, expected_value in expected_strategy.items():
        if scoring.get(field) != expected_value:
            fail(f"$.scoring.{field}", f"must equal {expected_value!r}")
    round_digits = scoring.get("round_digits")
    if (
        not isinstance(round_digits, int)
        or isinstance(round_digits, bool)
        or not 0 <= round_digits <= 12
    ):
        fail("$.scoring.round_digits", "must be an integer from 0 to 12")
    expected_formulas = {
        "step_score": "sum(assertion_scores) / count(assertion_scores)",
        "skill_score": (
            "sum(applicable_step_weight * step_score) / "
            "sum(applicable_step_weight)"
        ),
        "overall_score": "min(skill_scores)",
        "step_status": (
            "pass iff step_score >= pass_threshold and every assertion passes"
        ),
        "skill_status": (
            "pass iff skill_score >= pass_threshold and every applicable step passes"
        ),
        "overall_status": (
            "pass iff every skill passes and replay is not fail"
        ),
    }
    if scoring.get("formulas") != expected_formulas:
        fail("$.scoring.formulas", "does not match scoring strategy version 1")
    weights = scoring.get("step_weights")
    expected_steps = {
        f"step{index}" for index in range(1, VERIFICATION_STEP_COUNT + 1)
    }
    expected_step_order = [
        f"step{index}" for index in range(1, VERIFICATION_STEP_COUNT + 1)
    ]
    if not isinstance(weights, dict) or set(weights) != expected_steps:
        fail("$.scoring.step_weights", "must contain exactly step1 through step8")
    if any(
        not isinstance(weight, (int, float))
        or isinstance(weight, bool)
        or float(weight) < 0
        for weight in weights.values()
    ):
        fail("$.scoring.step_weights", "must contain non-negative numbers")
    if abs(sum(float(weight) for weight in weights.values()) - 1.0) > 1e-9:
        fail("$.scoring.step_weights", "must sum to 1")
    skills = required_list(data, "skills", "$")
    if not skills:
        fail("$.skills", "must not be empty")
    skill_names_seen: set[str] = set()
    for index, skill in enumerate(skills):
        item_path = f"$.skills[{index}]"
        if not isinstance(skill, dict):
            fail(item_path, "must be an object")
        skill_name = required_string(skill, "skill", item_path)
        if skill_name in skill_names_seen:
            fail(f"{item_path}.skill", "duplicates another input skill")
        skill_names_seen.add(skill_name)
        role = required_string(skill, "role", item_path)
        if role not in VERIFICATION_ROLES:
            fail(f"{item_path}.role", "has an unknown verification role")
        for field in ("baseline_expected", "candidate_expected"):
            if not isinstance(skill.get(field), bool):
                fail(f"{item_path}.{field}", "must be boolean")
        requirements = skill.get("requirements")
        if not isinstance(requirements, dict):
            fail(f"{item_path}.requirements", "must be an object")
        for key, name_key in (
            ("sections", "section"),
            ("directories", "directory"),
        ):
            rows = required_list(requirements, key, f"{item_path}.requirements")
            for row_index, row in enumerate(rows):
                row_path = f"{item_path}.requirements.{key}[{row_index}]"
                if not isinstance(row, dict):
                    fail(row_path, "must be an object")
                required_string(row, name_key, row_path)
                required_string(row, "expectation", row_path)
        avoid = required_list(requirements, "avoid", f"{item_path}.requirements")
        if not all(isinstance(value, str) and value.strip() for value in avoid):
            fail(f"{item_path}.requirements.avoid", "must contain non-empty strings")
        removals = required_list(
            requirements, "removals", f"{item_path}.requirements"
        )
        if not all(
            isinstance(value, str) and value.strip() for value in removals
        ):
            fail(
                f"{item_path}.requirements.removals",
                "must contain non-empty strings",
            )
        required_list(skill, "checks", item_path)
    checks = data.get("checks")
    if not isinstance(checks, dict):
        fail("$.checks", "must be an object")
    expected = expected_steps
    if set(checks) != expected:
        fail("$.checks", "must contain exactly step1 through step8")
    if list(checks) != expected_step_order:
        fail("$.checks", "must be ordered from step1 through step8")
    for step_id, check in checks.items():
        check_path = f"$.checks.{step_id}"
        if not isinstance(check, dict):
            fail(check_path, "must be an object")
        required_string(check, "check", check_path)
        applies_to = required_list(check, "applies_to", check_path)
        if not applies_to or not all(
            isinstance(role, str) and role in VERIFICATION_ROLES
            for role in applies_to
        ):
            fail(
                f"{check_path}.applies_to",
                "must contain known verification roles",
            )
        if len(set(applies_to)) != len(applies_to):
            fail(f"{check_path}.applies_to", "must not contain duplicates")
        assertions = required_list(check, "assertions", check_path)
        if not assertions:
            fail(f"{check_path}.assertions", "must not be empty")
        assertion_ids: set[str] = set()
        for assertion_index, assertion in enumerate(assertions):
            assertion_path = (
                f"{check_path}.assertions[{assertion_index}]"
            )
            if not isinstance(assertion, dict):
                fail(assertion_path, "must be an object")
            assertion_id = required_string(
                assertion, "id", assertion_path
            )
            if assertion_id in assertion_ids:
                fail(f"{assertion_path}.id", "duplicates another assertion")
            assertion_ids.add(assertion_id)
            required_string(assertion, "text", assertion_path)
    evidence = checks["step3"].get("evidence")
    if not isinstance(evidence, dict):
        fail("$.checks.step3.evidence", "must be an object")
    findings = required_list(evidence, "findings", "$.checks.step3.evidence")
    if not findings:
        fail("$.checks.step3.evidence.findings", "must not be empty")
    finding_ids: set[str] = set()
    for finding_index, finding in enumerate(findings):
        finding_path = f"$.checks.step3.evidence.findings[{finding_index}]"
        if not isinstance(finding, dict):
            fail(finding_path, "must be an object")
        finding_id = required_string(finding, "finding_id", finding_path)
        if finding_id in finding_ids:
            fail(f"{finding_path}.finding_id", "duplicates another finding")
        finding_ids.add(finding_id)
        source_path = finding.get("path")
        if source_path is not None and (
            not isinstance(source_path, str) or not source_path.strip()
        ):
            fail(f"{finding_path}.path", "must be a non-empty string or null")
        confidence = finding.get("confidence")
        if confidence is not None and (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= float(confidence) <= 1
        ):
            fail(f"{finding_path}.confidence", "must be from 0 to 1 or null")
        records = finding.get("evidence_records")
        if (
            not isinstance(records, int)
            or isinstance(records, bool)
            or records < 0
        ):
            fail(f"{finding_path}.evidence_records", "must be non-negative")
        windows = finding.get("distinct_windows")
        if windows is not None and (
            not isinstance(windows, int)
            or isinstance(windows, bool)
            or windows < 0
        ):
            fail(
                f"{finding_path}.distinct_windows",
                "must be a non-negative integer or null",
            )
        for field in ("candidate_source", "lesson"):
            value = finding.get(field)
            if value is not None and not isinstance(value, str):
                fail(f"{finding_path}.{field}", "must be a string or null")
    if data["finding_id"] not in finding_ids:
        fail(
            "$.checks.step3.evidence.findings",
            "must include the operation finding_id",
        )
    goal_path = path.parent / "evolve-goal.json"
    if goal_path.is_file():
        goal = load_object(goal_path)
        bundle = goal.get("bundle")
        if isinstance(bundle, dict):
            selected_ids = {
                row.get("cluster")
                for row in bundle.get("selected") or []
                if isinstance(row, dict) and isinstance(row.get("cluster"), str)
            }
            expected_finding_ids = {data["finding_id"], *selected_ids}
            if finding_ids != expected_finding_ids:
                fail(
                    "$.checks.step3.evidence.findings",
                    "must match every finding selected by the operation bundle",
                )
    for skill_index, skill in enumerate(skills):
        item_path = f"$.skills[{skill_index}]"
        role = skill["role"]
        materialized_checks = skill["checks"]
        if len(materialized_checks) != len(expected_steps):
            fail(
                f"{item_path}.checks",
                "must contain exactly one item per shared check",
            )
        seen_checks: set[str] = set()
        for check_index, materialized in enumerate(materialized_checks):
            check_path = f"{item_path}.checks[{check_index}]"
            if not isinstance(materialized, dict):
                fail(check_path, "must be an object")
            step_id = required_string(materialized, "id", check_path)
            if step_id not in checks or step_id in seen_checks:
                fail(f"{check_path}.id", "must reference one unique shared check")
            if step_id != expected_step_order[check_index]:
                fail(
                    f"{check_path}.id",
                    f"must equal {expected_step_order[check_index]} at this position",
                )
            seen_checks.add(step_id)
            if materialized.get("definition_ref") != f"#/checks/{step_id}":
                fail(
                    f"{check_path}.definition_ref",
                    f"must equal #/checks/{step_id}",
                )
            expected_applicable = role in checks[step_id]["applies_to"]
            if materialized.get("applicable") is not expected_applicable:
                fail(
                    f"{check_path}.applicable",
                    "does not match the skill role",
                )
            assertions = required_list(
                materialized, "assertions", check_path
            )
            assertion_ids: set[str] = set()
            for assertion_index, assertion in enumerate(assertions):
                assertion_path = (
                    f"{check_path}.assertions[{assertion_index}]"
                )
                if not isinstance(assertion, dict):
                    fail(assertion_path, "must be an object")
                assertion_id = required_string(
                    assertion, "id", assertion_path
                )
                if assertion_id in assertion_ids:
                    fail(
                        f"{assertion_path}.id",
                        "duplicates another per-skill assertion",
                    )
                assertion_ids.add(assertion_id)
                required_string(assertion, "text", assertion_path)
                source_ref = required_string(
                    assertion, "source_ref", assertion_path
                )
                if not source_ref.startswith(
                    f"#/skills/{skill_index}/requirements/"
                ):
                    fail(
                        f"{assertion_path}.source_ref",
                        "must point into this skill's requirements",
                    )
    return data


def validate_verification(
    path: Path,
    *,
    judged: bool,
    expected_skills: set[str] | None = None,
) -> dict[str, Any]:
    data = load_object(path)
    input_ref = data.get("verification_input")
    if not isinstance(input_ref, dict):
        fail("$.verification_input", "must be an object")
    if input_ref.get("path") != "verification-input.json":
        fail(
            "$.verification_input.path",
            "must equal verification-input.json",
        )
    input_digest = required_string(
        input_ref, "sha256", "$.verification_input"
    )
    if re.fullmatch(r"[0-9a-f]{64}", input_digest) is None:
        fail("$.verification_input.sha256", "must be a SHA-256 digest")
    input_path = path.parent / "verification-input.json"
    input_data: dict[str, Any] | None = None
    if input_path.is_file():
        input_data = validate_verification_input(input_path)
        actual_digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
        if actual_digest != input_digest:
            fail(
                "$.verification_input.sha256",
                "does not match run/verification-input.json",
            )
    scoring = (input_data or {}).get("scoring") or {}
    pass_threshold = float(scoring.get("pass_threshold", 0.7))
    round_digits = int(scoring.get("round_digits", 6))
    step_weights = scoring.get("step_weights") or {
        f"step{index}": 1 / VERIFICATION_STEP_COUNT
        for index in range(1, VERIFICATION_STEP_COUNT + 1)
    }
    step_groups = required_list(data, "verification_steps", "$")
    if not step_groups:
        fail("$.verification_steps", "must not be empty")
    input_skills = {
        row["skill"]: row
        for row in (input_data or {}).get("skills") or []
        if isinstance(row, dict) and isinstance(row.get("skill"), str)
    }
    input_skill_positions = {
        row["skill"]: index
        for index, row in enumerate((input_data or {}).get("skills") or [])
        if isinstance(row, dict) and isinstance(row.get("skill"), str)
    }
    input_checks = (input_data or {}).get("checks") or {}
    step_skills: set[str] = set()
    skill_scores: dict[str, float] = {}
    skill_required_steps_pass: dict[str, bool] = {}
    skill_applicable_weights: dict[str, float] = {}
    skill_failed_steps: dict[str, list[str]] = {}
    for group_index, group in enumerate(step_groups):
        group_path = f"$.verification_steps[{group_index}]"
        if not isinstance(group, dict):
            fail(group_path, "must be an object")
        group_skill = required_string(group, "skill", group_path)
        if group_skill in step_skills:
            fail(f"{group_path}.skill", "duplicates another output skill")
        if input_data is not None:
            ordered_input_skills = [
                row.get("skill")
                for row in input_data.get("skills") or []
                if isinstance(row, dict)
            ]
            if (
                group_index >= len(ordered_input_skills)
                or group_skill != ordered_input_skills[group_index]
            ):
                fail(
                    f"{group_path}.skill",
                    "must follow verification input skill order",
                )
            expected_steps_from = (
                f"verification-input.json#/skills/{group_index}/checks"
            )
            if group.get("steps_from") != expected_steps_from:
                fail(
                    f"{group_path}.steps_from",
                    f"must equal {expected_steps_from}",
                )
        if group.get("used_by") != "verifier stage":
            fail(f"{group_path}.used_by", "must equal verifier stage")
        step_skills.add(group_skill)
        input_skill = input_skills.get(group_skill)
        if input_data is not None and input_skill is None:
            fail(f"{group_path}.skill", "is not present in verification input")
        role = input_skill.get("role") if input_skill else None
        materialized_checks = {
            check.get("id"): check
            for check in (input_skill or {}).get("checks") or []
            if isinstance(check, dict)
        }
        materialized_check_positions = {
            check.get("id"): index
            for index, check in enumerate((input_skill or {}).get("checks") or [])
            if isinstance(check, dict)
        }
        steps = required_list(group, "steps", group_path)
        step_ids: set[str] = set()
        weighted_scores: list[tuple[float, float]] = []
        all_applicable_steps_pass = True
        failed_steps: list[str] = []
        for step_index, step in enumerate(steps):
            step_path = f"{group_path}.steps[{step_index}]"
            if not isinstance(step, dict):
                fail(step_path, "must be an object")
            step_id = required_string(step, "id", step_path)
            if step_id in step_ids:
                fail(f"{step_path}.id", "duplicates another step")
            if step_id != f"step{step_index + 1}":
                fail(
                    f"{step_path}.id",
                    f"must equal step{step_index + 1} at this position",
                )
            step_ids.add(step_id)
            input_check = input_checks.get(step_id)
            if input_data is not None and not isinstance(input_check, dict):
                fail(f"{step_path}.id", "is not present in verification input")
            if input_check is not None and step.get("check") != input_check.get("check"):
                fail(f"{step_path}.check", "does not match verification input")
            expected_input_ref = (
                f"#/skills/{input_skill_positions[group_skill]}/checks/"
                f"{materialized_check_positions[step_id]}"
                if input_data is not None
                and group_skill in input_skill_positions
                and step_id in materialized_check_positions
                else f"#/checks/{step_id}"
            )
            if step.get("input_ref") != expected_input_ref:
                fail(
                    f"{step_path}.input_ref",
                    f"must equal {expected_input_ref}",
                )
            materialized_check = materialized_checks.get(step_id)
            expected_applicable = (
                materialized_check.get("applicable")
                if materialized_check is not None
                else role in (input_check.get("applies_to") or [])
                if input_check is not None
                else True
            )
            if step.get("applicable") is not expected_applicable:
                fail(
                    f"{step_path}.applicable",
                    "does not match the input role applicability",
                )
            status = step.get("status")
            score = step.get("score")
            required_string(step, "reasoning", step_path)
            evidence = required_list(step, "evidence", step_path)
            assertion_results = required_list(
                step, "assertion_results", step_path
            )
            if not expected_applicable:
                if status != "not_applicable":
                    fail(
                        f"{step_path}.status",
                        "must be not_applicable when the step does not apply",
                    )
                if score is not None:
                    fail(
                        f"{step_path}.score",
                        "must be null when the step does not apply",
                    )
                if evidence or assertion_results:
                    fail(
                        step_path,
                        "non-applicable steps must have empty evidence and assertion_results",
                    )
                continue
            if status not in {"pass", "fail"}:
                fail(f"{step_path}.status", "must be pass or fail")
            if (
                not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not 0 <= float(score) <= 1
            ):
                fail(f"{step_path}.score", "must be a number from 0 to 1")
            if not evidence or not all(
                isinstance(value, str) and value.strip() for value in evidence
            ):
                fail(f"{step_path}.evidence", "must contain non-empty strings")
            expected_assertions = {
                assertion["id"]: assertion
                for assertion in [
                    *((input_check or {}).get("assertions") or []),
                    *((materialized_check or {}).get("assertions") or []),
                ]
                if isinstance(assertion, dict)
            }
            result_ids: set[str] = set()
            assertion_scores: list[float] = []
            all_assertions_pass = True
            for result_index, result in enumerate(assertion_results):
                result_path = (
                    f"{step_path}.assertion_results[{result_index}]"
                )
                if not isinstance(result, dict):
                    fail(result_path, "must be an object")
                assertion_id = required_string(
                    result, "assertion_id", result_path
                )
                if assertion_id in result_ids:
                    fail(
                        f"{result_path}.assertion_id",
                        "duplicates another assertion result",
                    )
                result_ids.add(assertion_id)
                assertion_status = result.get("status")
                assertion_score = result.get("score")
                if assertion_status not in {"pass", "fail"}:
                    fail(f"{result_path}.status", "must be pass or fail")
                if (
                    not isinstance(assertion_score, (int, float))
                    or isinstance(assertion_score, bool)
                    or not 0 <= float(assertion_score) <= 1
                ):
                    fail(
                        f"{result_path}.score",
                        "must be a number from 0 to 1",
                    )
                if float(assertion_score) not in ASSERTION_SCORE_ANCHORS:
                    fail(
                        f"{result_path}.score",
                        "must use a configured assertion score anchor",
                    )
                if (
                    verification_status(
                        float(assertion_score), pass_threshold
                    )
                    != assertion_status
                ):
                    fail(
                        result_path,
                        "status must match the input pass threshold",
                    )
                required_string(result, "reasoning", result_path)
                result_evidence = required_list(
                    result, "evidence", result_path
                )
                if not result_evidence or not all(
                    isinstance(value, str) and value.strip()
                    for value in result_evidence
                ):
                    fail(
                        f"{result_path}.evidence",
                        "must contain non-empty strings",
                    )
                assertion_scores.append(float(assertion_score))
                all_assertions_pass = (
                    all_assertions_pass and assertion_status == "pass"
                )
            if input_check is not None and result_ids != set(expected_assertions):
                fail(
                    f"{step_path}.assertion_results",
                    "must cover every input assertion exactly once",
                )
            if not assertion_scores:
                fail(
                    f"{step_path}.assertion_results",
                    "must not be empty for an applicable step",
                )
            assertion_mean = round(
                verification_step_score(assertion_scores), round_digits
            )
            if abs(float(score) - assertion_mean) > 1e-6:
                fail(
                    f"{step_path}.score",
                    "must equal the mean assertion score",
                )
            expected_step_status = (
                "pass"
                if verification_status(float(score), pass_threshold) == "pass"
                and all_assertions_pass
                else "fail"
            )
            if status != expected_step_status:
                fail(
                    step_path,
                    "status must reflect score threshold and all assertion gates",
                )
            weight = float(step_weights[step_id])
            weighted_scores.append((float(score), weight))
            all_applicable_steps_pass = (
                all_applicable_steps_pass and status == "pass"
            )
            if status == "fail":
                failed_steps.append(step_id)
        if step_ids != {
            f"step{index}"
            for index in range(1, VERIFICATION_STEP_COUNT + 1)
        }:
            fail(f"{group_path}.steps", "must contain exactly step1 through step8")
        try:
            skill_scores[group_skill] = round(
                verification_skill_score(weighted_scores), round_digits
            )
        except ContractError as error:
            fail(group_path, str(error))
        skill_required_steps_pass[group_skill] = all_applicable_steps_pass
        skill_applicable_weights[group_skill] = sum(
            weight for _, weight in weighted_scores
        )
        skill_failed_steps[group_skill] = sorted(failed_steps)
    if input_data is not None and step_skills != set(input_skills):
        fail("$.verification_steps", "does not match verification input skills")
    if expected_skills is not None and step_skills != expected_skills:
        fail("$.verification_steps", "does not match the active op's skills")
    contract_skills = (
        expected_skills
        if expected_skills is not None
        else set(input_skills)
        if input_data is not None
        else None
    )
    changelog = required_list(data, "changelog", "$")
    changed_names: set[str] = set()
    for index, change in enumerate(changelog):
        changed_names.add(
            _validate_changelog_entry(change, f"$.changelog[{index}]")
        )
    if contract_skills is not None and changed_names != contract_skills:
        fail("$.changelog", "does not match the verification skill set")
    feedback = data.get("feedback")
    if not isinstance(feedback, dict):
        fail("$.feedback", "must be an object")
    if feedback.get("scoring_strategy_version") != 1:
        fail("$.feedback.scoring_strategy_version", "must equal 1")
    if feedback.get("overall_status") not in {"pass", "fail"}:
        fail("$.feedback.overall_status", "must be pass or fail")
    overall_score = feedback.get("overall_score")
    if (
        not isinstance(overall_score, (int, float))
        or isinstance(overall_score, bool)
        or not 0 <= float(overall_score) <= 1
    ):
        fail("$.feedback.overall_score", "must be a number from 0 to 1")
    expected_overall = verification_overall_score(
        list(skill_scores.values())
    )
    if abs(float(overall_score) - expected_overall) > 1e-6:
        fail(
            "$.feedback.overall_score",
            "must equal the minimum per-skill score",
        )
    bottlenecks = required_list(feedback, "bottleneck_skills", "$.feedback")
    if not all(isinstance(value, str) and value for value in bottlenecks):
        fail(
            "$.feedback.bottleneck_skills",
            "must contain non-empty skill names",
        )
    expected_bottlenecks = sorted(
        name
        for name, score in skill_scores.items()
        if abs(score - expected_overall) <= 1e-6
    )
    if sorted(bottlenecks) != expected_bottlenecks:
        fail(
            "$.feedback.bottleneck_skills",
            "must name every skill at the minimum score",
        )
    required_string(feedback, "overall_feedback", "$.feedback")
    replay = feedback.get("replay")
    if not isinstance(replay, dict):
        fail("$.feedback.replay", "must be an object")
    available = replay.get("available")
    if not isinstance(available, bool):
        fail("$.feedback.replay.available", "must be boolean")
    replay_status = required_string(replay, "status", "$.feedback.replay")
    replay_kind = replay.get("kind", "targeted_detector")
    if replay_kind not in {"targeted_detector", "paired_skill_eval"}:
        fail("$.feedback.replay.kind", "has an unknown value")
    if available:
        if replay_status not in {"pass", "fail"}:
            fail("$.feedback.replay.status", "must be pass or fail when available")
        if not isinstance(replay.get("before"), dict):
            fail("$.feedback.replay.before", "must be an object when available")
        if not isinstance(replay.get("after"), dict):
            fail("$.feedback.replay.after", "must be an object when available")
        if (
            replay_status == "fail"
            and feedback.get("overall_status") != "fail"
        ):
            fail(
                "$.feedback.overall_status",
                "must be fail when behavioral replay fails",
            )
        if replay_kind == "paired_skill_eval":
            after = replay.get("after") or {}
            held_out_cases = after.get("held_out_cases")
            if (
                not isinstance(held_out_cases, int)
                or isinstance(held_out_cases, bool)
                or held_out_cases < 0
            ):
                fail(
                    "$.feedback.replay.after.held_out_cases",
                    "must be a non-negative integer",
                )
            for field in (
                "held_out_pass_rate",
                "activation_false_positive_rate",
            ):
                value = after.get(field)
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not 0 <= float(value) <= 1
                ):
                    fail(
                        f"$.feedback.replay.after.{field}",
                        "must be a number from 0 to 1",
                    )
    else:
        if replay_status != "not_run":
            fail("$.feedback.replay.status", "must be not_run when unavailable")
        required_string(replay, "reason", "$.feedback.replay")
        if replay.get("before") is not None or replay.get("after") is not None:
            fail(
                "$.feedback.replay",
                "before and after must be null when replay is unavailable",
            )
    budget = feedback.get("retry_budget")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        fail("$.feedback.retry_budget", "must be a non-negative integer")
    if budget != 0:
        fail("$.feedback.retry_budget", "must be 0 while retries are disabled")
    rows = required_list(feedback, "per_skill", "$.feedback")
    names: set[str] = set()
    for index, row in enumerate(rows):
        item_path = f"$.feedback.per_skill[{index}]"
        if not isinstance(row, dict):
            fail(item_path, "must be an object")
        name = required_string(row, "skill", item_path)
        names.add(name)
        if row.get("status") not in {"pass", "fail"}:
            fail(f"{item_path}.status", "must be pass or fail")
        score = row.get("score")
        if (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not 0 <= float(score) <= 1
        ):
            fail(f"{item_path}.score", "must be a number from 0 to 1")
        expected_score = skill_scores.get(name)
        if expected_score is None or abs(float(score) - expected_score) > 1e-6:
            fail(
                f"{item_path}.score",
                "must equal this skill's weighted step score",
            )
        applicable_weight = row.get("applicable_weight")
        if (
            not isinstance(applicable_weight, (int, float))
            or isinstance(applicable_weight, bool)
            or abs(
                float(applicable_weight)
                - skill_applicable_weights.get(name, -1)
            )
            > 1e-6
        ):
            fail(
                f"{item_path}.applicable_weight",
                "must equal the sum of applicable step weights",
            )
        failed_required_steps = required_list(
            row, "failed_required_steps", item_path
        )
        if not all(
            isinstance(value, str) and value for value in failed_required_steps
        ):
            fail(
                f"{item_path}.failed_required_steps",
                "must contain step IDs",
            )
        if sorted(failed_required_steps) != skill_failed_steps.get(name):
            fail(
                f"{item_path}.failed_required_steps",
                "must list every failed applicable step",
            )
        expected_status = (
            "pass"
            if verification_status(float(score), pass_threshold) == "pass"
            and skill_required_steps_pass.get(name) is True
            else "fail"
        )
        if row.get("status") != expected_status:
            fail(
                item_path,
                "status must reflect score threshold and all applicable step gates",
            )
        required_string(row, "feedback", item_path)
        if row.get("action") is not None:
            fail(f"{item_path}.action", "must remain null")
        retries = row.get("retries_used")
        if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
            fail(f"{item_path}.retries_used", "must be a non-negative integer")
        if retries != 0:
            fail(f"{item_path}.retries_used", "must be 0 while retries are disabled")
    if contract_skills is not None and names != contract_skills:
        fail("$.feedback.per_skill", "does not match the verification skill set")
    expected_overall_status = (
        "pass"
        if all(row.get("status") == "pass" for row in rows)
        and replay_status != "fail"
        else "fail"
    )
    if feedback.get("overall_status") != expected_overall_status:
        fail(
            "$.feedback.overall_status",
            "must reflect every per-skill gate and the replay hard gate",
        )
    ood = required_list(feedback, "ood", "$.feedback")
    for index, item in enumerate(ood):
        item_path = f"$.feedback.ood[{index}]"
        if not isinstance(item, dict):
            fail(item_path, "must be an object")
        skill = required_string(item, "skill", item_path)
        if contract_skills is not None and skill not in contract_skills:
            fail(f"{item_path}.skill", "must name a verified skill")
        if item.get("kind") not in {"section", "dir", "check"}:
            fail(f"{item_path}.kind", "must be section, dir, or check")
        required_string(item, "name", item_path)
        required_string(item, "description", item_path)
    action = feedback.get("action")
    if not judged:
        if action is not None:
            fail("$.feedback.action", "must be null before Judge")
        return data
    if not isinstance(action, dict) or action.get("op") not in {"pass", "fail"}:
        fail("$.feedback.action.op", "must be pass or fail while retries are disabled")
    if action.get("to") not in {None, ""}:
        fail("$.feedback.action.to", "must be empty while retries are disabled")
    if action["op"] == "pass":
        if feedback["overall_status"] != "pass":
            fail("$.feedback.action.op", "cannot pass a failed overall status")
        failed = [row["skill"] for row in rows if row.get("status") != "pass"]
        if failed:
            fail("$.feedback.action.op", f"cannot pass failed skills: {', '.join(failed)}")
    elif feedback["overall_status"] != "fail":
        fail("$.feedback.action.op", "cannot fail a passing overall status")
    return data


def _operation_skill_names(operation: dict[str, Any]) -> set[str]:
    name = operation.get("op")
    if name in {"create", "update", "delete"}:
        return {
            str(row["skill"])
            for row in operation.get("skills") or []
            if isinstance(row, dict) and row.get("skill")
        }
    if name == "merge":
        sources = {
            str(skill)
            for skill in operation.get("skills") or []
            if isinstance(skill, str) and skill
        }
        target = operation.get("into")
        if isinstance(target, dict) and target.get("skill"):
            sources.add(str(target["skill"]))
        return sources
    if name == "split":
        names = (
            {str(operation["skill"])}
            if isinstance(operation.get("skill"), str)
            else set()
        )
        names.update(
            str(row["skill"])
            for row in operation.get("into") or []
            if isinstance(row, dict) and row.get("skill")
        )
        return names
    return set()


def validate_operation_artifacts(directory: Path) -> dict[str, Any]:
    """Require one dated goal, verification, judge, and changelog bundle."""
    paths = {
        name: directory / filename
        for name, filename in {
            "goal": "evolve-goal.json",
            "verification_input": "verification-input.json",
            "verification": "verification.json",
            "judge": "judge.json",
            "changelog": "changelog.json",
        }.items()
    }
    for name, path in paths.items():
        if not path.is_file():
            fail(str(path), f"{name} artifact was not produced")

    goal = validate_goal(paths["goal"], exactly_one_op=True)
    verification_input = validate_verification_input(
        paths["verification_input"]
    )
    changelog = validate_changelog(paths["changelog"])
    unfinished = [
        str(marker.get("phase"))
        for marker in changelog["phase_markers"]
        if isinstance(marker, dict)
        and marker.get("status") in {"pending", "running"}
    ]
    if unfinished:
        fail(
            str(paths["changelog"]),
            "operation bundle has unfinished phases: "
            + ", ".join(unfinished),
        )
    skills = {
        str(change["skill"])
        for change in changelog["changes"]
        if isinstance(change, dict)
    }
    operation = goal["action"]["ops"][0]
    first_change = changelog["changes"][0]
    if _operation_skill_names(operation) != skills:
        fail(str(paths["goal"]), "skill set does not match changelog.json")
    if operation.get("op") != first_change.get("operation"):
        fail(str(paths["goal"]), "operation does not match changelog.json")
    for key in ("run_id", "finding_id", "op_index", "operation"):
        if verification_input.get(key) != first_change.get(key):
            fail(
                f"{paths['verification_input']}:{key}",
                "does not match changelog.json",
            )
    input_skills = {
        str(row["skill"])
        for row in verification_input.get("skills") or []
        if isinstance(row, dict) and row.get("skill")
    }
    if input_skills != skills:
        fail(
            str(paths["verification_input"]),
            "skill set does not match changelog.json",
        )

    raw_verification = load_json_object(paths["verification"])
    terminal_status = raw_verification.get("status")
    if terminal_status in {"skipped", "failed"}:
        verification = raw_verification
        if verification.get("phase") != "verification":
            fail("$.phase", "must equal verification")
        required_string(verification, "reason", "$")
        placeholder_skills = required_list(verification, "skills", "$")
        if set(placeholder_skills) != skills:
            fail("$.skills", "must match changelog.json")
        input_ref = verification.get("verification_input")
        if not isinstance(input_ref, dict):
            fail("$.verification_input", "must be an object")
        if input_ref.get("path") != "verification-input.json":
            fail(
                "$.verification_input.path",
                "must equal verification-input.json",
            )
        actual_input_digest = hashlib.sha256(
            paths["verification_input"].read_bytes()
        ).hexdigest()
        if input_ref.get("sha256") != actual_input_digest:
            fail(
                "$.verification_input.sha256",
                "does not match verification-input.json",
            )
    else:
        terminal_status = "completed"
        verification = validate_verification(
            paths["verification"],
            judged=True,
            expected_skills=skills,
        )

    embedded_changes = verification.get("changelog")
    if not isinstance(embedded_changes, list):
        fail(
            str(paths["verification"]),
            "embedded changelog must be a list",
        )
    embedded_by_id = {
        change.get("id"): change
        for change in embedded_changes
        if isinstance(change, dict)
    }
    standalone_by_id = {
        change.get("id"): change
        for change in changelog["changes"]
        if isinstance(change, dict)
    }
    if set(embedded_by_id) != set(standalone_by_id):
        fail(
            str(paths["verification"]),
            "embedded changelog IDs must equal changelog.json",
        )
    for change_id, standalone in standalone_by_id.items():
        embedded = embedded_by_id[change_id]
        for key in (
            "skill",
            "operation",
            "run_id",
            "finding_id",
            "op_index",
            "date",
            "sections",
            "directories",
            "before_sha256",
            "after_sha256",
            "status",
        ):
            if embedded.get(key) != standalone.get(key):
                fail(
                    str(paths["verification"]),
                    f"embedded changelog {change_id!r} field {key!r} "
                    "must equal changelog.json",
                )

    judge = load_json_object(paths["judge"])
    if judge.get("schema_version") != 1:
        fail("$.schema_version", "must equal 1")
    decided_on = required_string(judge, "date", "$")
    try:
        parsed_date = date.fromisoformat(decided_on)
    except ValueError:
        fail("$.date", "must be a valid ISO date")
    if parsed_date.isoformat() != decided_on:
        fail("$.date", "must use YYYY-MM-DD")
    required_string(judge, "run_id", "$")
    required_string(judge, "finding_id", "$")
    op_index = judge.get("op_index")
    if not isinstance(op_index, int) or isinstance(op_index, bool) or op_index < 1:
        fail("$.op_index", "must be a positive integer")
    judge_skills = required_list(judge, "skills", "$")
    if (
        not all(isinstance(skill, str) and skill for skill in judge_skills)
        or set(judge_skills) != skills
        or len(judge_skills) != len(skills)
    ):
        fail("$.skills", "must name every changelog skill exactly once")
    judge_status = required_string(judge, "status", "$")
    if judge_status != terminal_status:
        fail("$.status", "must match verification status")
    action = judge.get("action")
    if action != (verification.get("feedback") or {}).get("action"):
        fail("$.action", "must equal verification feedback.action")
    if terminal_status in {"skipped", "failed"}:
        required_string(judge, "reason", "$")
        if action is not None:
            fail("$.action", "must be null for skipped or failed operations")

    marker_statuses = {
        str(marker.get("phase")): marker.get("status")
        for marker in changelog["phase_markers"]
        if isinstance(marker, dict)
    }
    if terminal_status == "completed" and any(
        status != "completed" for status in marker_statuses.values()
    ):
        fail(
            str(paths["changelog"]),
            "completed bundle requires every phase to be completed",
        )
    if terminal_status == "skipped" and any(
        marker_statuses.get(phase) != "skipped"
        for phase in OPERATION_PHASES[1:]
    ):
        fail(
            str(paths["changelog"]),
            "skipped bundle requires every downstream phase to be skipped",
        )
    if terminal_status == "failed" and "failed" not in marker_statuses.values():
        fail(
            str(paths["changelog"]),
            "failed bundle requires a failed phase marker",
        )

    first_change = changelog["changes"][0]
    for key in ("run_id", "finding_id", "op_index", "date"):
        if judge.get(key) != first_change.get(key):
            fail(f"$.{key}", "must match changelog.json")

    artifacts = judge.get("artifacts")
    if not isinstance(artifacts, dict):
        fail("$.artifacts", "must be an object")
    expected_artifacts = {
        "goal": "evolve-goal.json",
        "verification_input": "verification-input.json",
        "verification": "verification.json",
        "changelog": "changelog.json",
    }
    for key, filename in expected_artifacts.items():
        reference = artifacts.get(key)
        reference_path = f"$.artifacts.{key}"
        if not isinstance(reference, dict):
            fail(reference_path, "must be an object")
        if reference.get("path") != filename:
            fail(f"{reference_path}.path", f"must equal {filename!r}")
        digest = required_string(reference, "sha256", reference_path)
        actual = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
        if digest != actual:
            fail(f"{reference_path}.sha256", f"does not match {filename}")
    return judge
