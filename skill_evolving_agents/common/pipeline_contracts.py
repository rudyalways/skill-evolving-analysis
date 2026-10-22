#!/usr/bin/env python3
"""Validate the JSON artifacts passed between skill-evolver stages."""

from __future__ import annotations

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
        if not isinstance(row.get("features"), dict):
            fail(f"{item_path}.features", "must be an object")
        if not isinstance(row.get("evidence"), list):
            fail(f"{item_path}.evidence", "must be a list")
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


def validate_metadata(path: Path, skill_names: set[str] | None = None) -> dict[str, Any]:
    data = load_object(path)
    rows = required_list(data, "skills_metadata", "$")
    seen: set[str] = set()
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
    if skill_names is not None:
        missing = sorted(name for name in skill_names if name.casefold() not in seen)
        if missing:
            fail("$.skills_metadata", f"missing records for: {', '.join(missing)}")
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


def validate_verification(
    path: Path,
    *,
    judged: bool,
    expected_skills: set[str] | None = None,
) -> dict[str, Any]:
    data = load_object(path)
    feedback = data.get("feedback")
    if not isinstance(feedback, dict):
        fail("$.feedback", "must be an object")
    if feedback.get("overall_status") not in {"pass", "fail"}:
        fail("$.feedback.overall_status", "must be pass or fail")
    replay = feedback.get("replay")
    if not isinstance(replay, dict):
        fail("$.feedback.replay", "must be an object")
    available = replay.get("available")
    if not isinstance(available, bool):
        fail("$.feedback.replay.available", "must be boolean")
    replay_status = required_string(replay, "status", "$.feedback.replay")
    if available:
        if replay_status not in {"pass", "fail"}:
            fail("$.feedback.replay.status", "must be pass or fail when available")
        if not isinstance(replay.get("before"), dict):
            fail("$.feedback.replay.before", "must be an object when available")
        if not isinstance(replay.get("after"), dict):
            fail("$.feedback.replay.after", "must be an object when available")
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
