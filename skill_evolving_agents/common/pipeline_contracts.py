#!/usr/bin/env python3
"""Validate the JSON artifacts passed between skill-evolver stages."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


PLACEHOLDER = re.compile(r"<[^<>]+>")
INLINE_CODE = re.compile(r"`[^`]*`")
KNOWN_OPS = {"create", "update", "delete", "merge", "split"}


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
                if not skill.get("sections") and not skill.get("dirs"):
                    fail(skill_path, "must name at least one section or directory change")
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
    scale = scoring.get("scale")
    if not isinstance(scale, dict):
        fail("$.scoring.scale", "must be an object")
    if scale.get("min") != 0 or scale.get("max") != 1:
        fail("$.scoring.scale", "must use the normalized 0 to 1 scale")
    threshold = scoring.get("pass_threshold")
    if (
        not isinstance(threshold, (int, float))
        or isinstance(threshold, bool)
        or not 0 < float(threshold) <= 1
    ):
        fail("$.scoring.pass_threshold", "must be a number above 0 and at most 1")
    weights = scoring.get("step_weights")
    expected_steps = {f"step{index}" for index in range(1, 6)}
    if not isinstance(weights, dict) or set(weights) != expected_steps:
        fail("$.scoring.step_weights", "must contain exactly step1 through step5")
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
    for index, skill in enumerate(skills):
        item_path = f"$.skills[{index}]"
        if not isinstance(skill, dict):
            fail(item_path, "must be an object")
        required_string(skill, "skill", item_path)
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
    checks = data.get("checks")
    if not isinstance(checks, dict):
        fail("$.checks", "must be an object")
    expected = expected_steps
    if set(checks) != expected:
        fail("$.checks", "must contain exactly step1 through step5")
    for step_id, check in checks.items():
        check_path = f"$.checks.{step_id}"
        if not isinstance(check, dict):
            fail(check_path, "must be an object")
        required_string(check, "check", check_path)
        assertions = required_list(check, "assertions", check_path)
        if not assertions or not all(
            isinstance(value, str) and value.strip() for value in assertions
        ):
            fail(f"{check_path}.assertions", "must contain non-empty strings")
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
    step_weights = scoring.get("step_weights") or {
        f"step{index}": 0.2 for index in range(1, 6)
    }
    step_groups = required_list(data, "verification_steps", "$")
    step_skills: set[str] = set()
    skill_scores: dict[str, float] = {}
    for group_index, group in enumerate(step_groups):
        group_path = f"$.verification_steps[{group_index}]"
        if not isinstance(group, dict):
            fail(group_path, "must be an object")
        group_skill = required_string(group, "skill", group_path)
        step_skills.add(group_skill)
        steps = required_list(group, "steps", group_path)
        step_ids: set[str] = set()
        weighted_score = 0.0
        for step_index, step in enumerate(steps):
            step_path = f"{group_path}.steps[{step_index}]"
            if not isinstance(step, dict):
                fail(step_path, "must be an object")
            step_id = required_string(step, "id", step_path)
            step_ids.add(step_id)
            if step.get("input_ref") != f"#/checks/{step_id}":
                fail(
                    f"{step_path}.input_ref",
                    f"must equal #/checks/{step_id}",
                )
            status = step.get("status")
            if status not in {"pass", "fail"}:
                fail(f"{step_path}.status", "must be pass or fail")
            score = step.get("score")
            if (
                not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not 0 <= float(score) <= 1
            ):
                fail(f"{step_path}.score", "must be a number from 0 to 1")
            if (float(score) >= pass_threshold) != (status == "pass"):
                fail(
                    step_path,
                    "status must pass exactly when score meets the input threshold",
                )
            required_string(step, "reasoning", step_path)
            evidence = required_list(step, "evidence", step_path)
            if not evidence or not all(
                isinstance(value, str) and value.strip() for value in evidence
            ):
                fail(f"{step_path}.evidence", "must contain non-empty strings")
            weighted_score += float(score) * float(step_weights[step_id])
        if step_ids != {f"step{index}" for index in range(1, 6)}:
            fail(f"{group_path}.steps", "must contain exactly step1 through step5")
        skill_scores[group_skill] = weighted_score
    if expected_skills is not None and step_skills != expected_skills:
        fail("$.verification_steps", "does not match the active op's skills")
    changelog = required_list(data, "changelog", "$")
    changed_names: set[str] = set()
    for index, change in enumerate(changelog):
        changed_names.add(
            _validate_changelog_entry(change, f"$.changelog[{index}]")
        )
    if expected_skills is not None and changed_names != expected_skills:
        fail("$.changelog", "does not match the active op's skills")
    feedback = data.get("feedback")
    if not isinstance(feedback, dict):
        fail("$.feedback", "must be an object")
    if feedback.get("overall_status") not in {"pass", "fail"}:
        fail("$.feedback.overall_status", "must be pass or fail")
    overall_score = feedback.get("overall_score")
    if (
        not isinstance(overall_score, (int, float))
        or isinstance(overall_score, bool)
        or not 0 <= float(overall_score) <= 1
    ):
        fail("$.feedback.overall_score", "must be a number from 0 to 1")
    expected_overall = sum(skill_scores.values()) / len(skill_scores)
    if abs(float(overall_score) - expected_overall) > 1e-6:
        fail(
            "$.feedback.overall_score",
            "must equal the mean weighted per-skill step score",
        )
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
        if (float(score) >= pass_threshold) != (row.get("status") == "pass"):
            fail(
                item_path,
                "status must pass exactly when score meets the input threshold",
            )
        retries = row.get("retries_used")
        if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
            fail(f"{item_path}.retries_used", "must be a non-negative integer")
    if expected_skills is not None and names != expected_skills:
        fail("$.feedback.per_skill", "does not match the active op's skills")
    action = feedback.get("action")
    if not judged:
        if action is not None:
            fail("$.feedback.action", "must be null before Judge")
        return data
    if not isinstance(action, dict) or action.get("op") not in {"pass", "back", "fail"}:
        fail("$.feedback.action.op", "must be pass, back, or fail")
    if action["op"] == "pass":
        if feedback["overall_status"] != "pass":
            fail("$.feedback.action.op", "cannot pass a failed overall status")
        failed = [row["skill"] for row in rows if row.get("status") != "pass"]
        if failed:
            fail("$.feedback.action.op", f"cannot pass failed skills: {', '.join(failed)}")
    return data
