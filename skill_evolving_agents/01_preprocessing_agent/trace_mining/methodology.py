"""Mine reusable methodology from a single task's observable action trajectory."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
QUOTED = re.compile(r"(['\"]).*?\1")
SPACE = re.compile(r"\s+")
GENERIC_VERIFY = re.compile(r"^(test|build|lint|check|verify|validate)$", re.I)
TOKEN = re.compile(r"[A-Za-z0-9_]+")
SEARCH_ACTION = re.compile(
    r"\b(search|websearch|grep|ripgrep|rg|find|glob|query|lookup|list)\b",
    re.IGNORECASE,
)
RETRYABLE_ERROR = re.compile(
    r"\b(timeout|timed out|temporar(?:y|ily)|connection reset|"
    r"connection refused|rate.?limit|too many requests|429|"
    r"50[0234]|service unavailable|try again)\b",
    re.IGNORECASE,
)
REFLECTION_PATTERNS = {
    "reconsider": re.compile(
        r"\b(wait|hold on|actually|let me reconsider|rethink|think again|"
        r"reconsider|try again)\b",
        re.IGNORECASE,
    ),
    "error_awareness": re.compile(
        r"\b(i was wrong|that won'?t work|made a mistake|missed something|"
        r"the previous approach failed)\b",
        re.IGNORECASE,
    ),
    "uncertainty": re.compile(
        r"\b(not sure|uncertain|maybe|perhaps|i suspect|could be)\b",
        re.IGNORECASE,
    ),
    "pivot": re.compile(
        r"\b(instead|different approach|alternative|rather than|start over)\b",
        re.IGNORECASE,
    ),
    "diagnosis": re.compile(
        r"\b(root cause|the issue is|this failed because)\b",
        re.IGNORECASE,
    ),
    "verification": re.compile(
        r"\b(double[- ]check|recheck|check again|confirm|validate|verify)\b",
        re.IGNORECASE,
    ),
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalized_action(event: dict[str, Any]) -> str:
    arguments = str(event.get("arguments_preview") or "").casefold()
    arguments = QUOTED.sub("<value>", arguments)
    arguments = NUMBER.sub("<n>", arguments)
    arguments = SPACE.sub(" ", arguments).strip()
    targets = ",".join(
        sorted(
            {
                Path(target).suffix.casefold() or "<path>"
                for target in event.get("targets") or []
            }
        )
    )
    return f"{event.get('phase')}|{event.get('tool')}|{arguments[:160]}|{targets}"


def _retry_signature(event: dict[str, Any]) -> str:
    """Preserve query, pagination, and parameter changes when comparing retries."""
    arguments = SPACE.sub(
        " ", str(event.get("arguments_preview") or "").casefold()
    ).strip()
    targets = ",".join(sorted(set(event.get("targets") or [])))
    return f"{event.get('phase')}|{event.get('tool')}|{arguments[:500]}|{targets}"


def _words(value: Any) -> set[str]:
    return {token.casefold() for token in TOKEN.findall(str(value or ""))}


def _text_similarity(left: Any, right: Any) -> float:
    a, b = _words(left), _words(right)
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def _is_search(event: dict[str, Any]) -> bool:
    text = f"{event.get('tool') or ''} {event.get('arguments_preview') or ''}"
    return bool(SEARCH_ACTION.search(text))


def _related_targets(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a = set(left.get("targets") or [])
    b = set(right.get("targets") or [])
    return not a or not b or bool(a & b)


def _intervening_state_change(
    events: list[dict[str, Any]],
    left_index: int,
    right_index: int,
    reference: dict[str, Any],
) -> bool:
    return any(
        event.get("phase") == "modify"
        and _related_targets(reference, event)
        for event in events[left_index + 1 : right_index]
    )


def _analyze_retries(
    events: list[dict[str, Any]], config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Classify repeated tools without treating exploration as wasted retry."""
    result_threshold = float(config.get("retry_result_similarity", 0.9))
    novelty_threshold = float(config.get("search_result_novelty", 0.2))
    max_transient = int(config.get("max_transient_retries", 1))
    signatures = [_retry_signature(event) for event in events]
    previous_by_signature: dict[str, int] = {}
    previous_by_tool: dict[str, int] = {}
    transient_attempts: defaultdict[str, int] = defaultdict(int)
    records: list[dict[str, Any]] = []

    for index, event in enumerate(events):
        signature = signatures[index]
        tool = str(event.get("tool") or "").casefold()
        # Deliberate waits are pacing, not retry oscillation. Monitoring a
        # deployment with repeated sleep calls must not be treated as an
        # unchanged action retry.
        if tool in {"sleep", "wait"}:
            previous_by_signature[signature] = index
            previous_by_tool[tool] = index
            continue
        previous_index = previous_by_signature.get(signature)
        same_action = previous_index is not None
        if previous_index is None and _is_search(event):
            previous_index = previous_by_tool.get(tool)
        if previous_index is None:
            previous_by_signature[signature] = index
            previous_by_tool[tool] = index
            continue

        previous = events[previous_index]
        action_similarity = 1.0 if same_action else _text_similarity(
            previous.get("arguments_preview"),
            event.get("arguments_preview"),
        )
        result_similarity = _text_similarity(
            previous.get("result_preview"), event.get("result_preview")
        )
        result_novelty = 1.0 - result_similarity
        state_changed = _intervening_state_change(
            events, previous_index, index, event
        )
        retryable = (
            previous.get("status") == "failed"
            and bool(RETRYABLE_ERROR.search(str(previous.get("result_preview") or "")))
        )
        necessary = False
        reason = "unchanged-action-state-and-result"

        if _is_search(event) and not same_action:
            necessary = True
            reason = "search-query-or-scope-refinement"
        elif _is_search(event) and result_novelty >= novelty_threshold:
            necessary = True
            reason = "search-returned-new-information"
        elif state_changed:
            necessary = True
            reason = "revalidation-after-relevant-state-change"
        elif retryable and transient_attempts[signature] < max_transient:
            necessary = True
            reason = "bounded-transient-retry"
            transient_attempts[signature] += 1
        elif result_similarity < result_threshold:
            necessary = True
            reason = "retry-produced-materially-different-result"

        waste_score = _clamp(
            0.3 * action_similarity
            + 0.2 * float(not state_changed)
            + 0.2 * result_similarity
            + 0.2 * float(result_novelty < novelty_threshold)
            + 0.1 * float(not retryable)
            - 0.3 * float(state_changed)
            - 0.2 * float(necessary)
        )
        records.append(
            {
                "first_sequence": previous["sequence"],
                "retry_sequence": event["sequence"],
                "necessary": necessary,
                "reason": reason,
                "same_action": same_action,
                "state_changed": state_changed,
                "retryable_error": retryable,
                "action_similarity": round(action_similarity, 6),
                "result_similarity": round(result_similarity, 6),
                "result_novelty": round(result_novelty, 6),
                "waste_score": round(waste_score, 6),
            }
        )
        previous_by_signature[signature] = index
        previous_by_tool[tool] = index

    # A→B→A is wasteful only when B did not mutate relevant state or change A's result.
    for index in range(len(events) - 2):
        if signatures[index] != signatures[index + 2]:
            continue
        if signatures[index] == signatures[index + 1]:
            continue
        if _intervening_state_change(events, index, index + 2, events[index]):
            continue
        similarity = _text_similarity(
            events[index].get("result_preview"),
            events[index + 2].get("result_preview"),
        )
        if similarity < result_threshold:
            continue
        records.append(
            {
                "first_sequence": events[index]["sequence"],
                "retry_sequence": events[index + 2]["sequence"],
                "necessary": False,
                "reason": "oscillation-without-new-state-or-result",
                "same_action": True,
                "state_changed": False,
                "retryable_error": False,
                "action_similarity": 1.0,
                "result_similarity": round(similarity, 6),
                "result_novelty": round(1.0 - similarity, 6),
                "waste_score": 1.0,
            }
        )
    return records


def _method_fingerprint(kind: str, events: list[dict[str, Any]]) -> str:
    shape = [
        (
            event.get("phase"),
            str(event.get("tool") or "").casefold(),
            tuple(
                sorted(
                    Path(target).suffix.casefold()
                    for target in event.get("targets") or []
                    if Path(target).suffix
                )
            ),
            event.get("status"),
        )
        for event in events
    ]
    payload = json.dumps([kind, shape], sort_keys=True, separators=(",", ":"))
    return "method-v1:" + hashlib.sha256(payload.encode()).hexdigest()[:24]


def _task_specificity(events: list[dict[str, Any]]) -> float:
    arguments = " ".join(
        str(event.get("arguments_preview") or "") for event in events
    )
    path_count = sum(len(event.get("targets") or []) for event in events)
    long_literals = len(re.findall(r"\b[A-Fa-f0-9]{12,}\b", arguments))
    return _clamp(path_count / max(12, len(events) * 5) + long_literals * 0.2)


def _quality(
    events: list[dict[str, Any]],
    *,
    success_dependency: float,
    surprise: float,
    reusability: float,
    evidence_quality: float,
    redundancy: float = 0.0,
) -> dict[str, float]:
    phases = {event.get("phase") for event in events}
    failures = sum(event.get("status") == "failed" for event in events)
    obviousness = _clamp(
        (0.35 if len(events) <= 3 else 0.0)
        + (0.25 if not failures and phases <= {"inspect", "modify", "verify"} else 0.0)
    )
    specificity = _task_specificity(events)
    product = (
        _clamp(success_dependency)
        * _clamp(surprise)
        * _clamp(reusability)
        * _clamp(evidence_quality)
    )
    value = product - obviousness * 0.35 - specificity * 0.25 - redundancy * 0.25
    return {
        "success_dependency": round(_clamp(success_dependency), 6),
        "surprise": round(_clamp(surprise), 6),
        "reusability": round(_clamp(reusability), 6),
        "evidence_quality": round(_clamp(evidence_quality), 6),
        "obviousness": round(obviousness, 6),
        "task_specificity": round(specificity, 6),
        "redundancy": round(_clamp(redundancy), 6),
        "value": round(value, 6),
    }


def _event_excerpt(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: event.get(key)
        for key in (
            "sequence",
            "tool",
            "phase",
            "status",
            "arguments_preview",
            "result_preview",
            "targets",
        )
    }


def _observation_excerpt(observation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: observation.get(key)
        for key in ("text", "text_sha256", "after_tool_count", "source_ordinal")
    }


def _finding(
    detector: str,
    trajectory: dict[str, Any],
    turn_path: str,
    events: list[dict[str, Any]],
    confidence: float,
    quality: dict[str, float],
    lesson: dict[str, Any],
    *,
    observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    trace_id = trajectory["trace_id"]
    event_sequences = sorted({int(event["sequence"]) for event in events})
    fingerprint = _method_fingerprint(detector, events)
    identity = json.dumps(
        [detector, trace_id, event_sequences, fingerprint],
        sort_keys=True,
        separators=(",", ":"),
    )
    signal_id = "sig-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
    observation_rows = [
        _observation_excerpt(observation)
        for observation in (observations or [])
    ]
    quote = json.dumps(
        {
            "events": [_event_excerpt(event) for event in events],
            "assistant_observations": observation_rows,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    severity = "critical" if quality["value"] >= 0.5 else "high"
    return {
        "schema_version": 1,
        "signal_id": signal_id,
        "detector": detector,
        "detector_version": "1",
        "scope": "task_trajectory",
        "session_id": trajectory["session_id"],
        "trace_ids": [trace_id],
        "first_seen": "",
        "last_seen": "",
        "severity": severity,
        "confidence": round(_clamp(confidence), 6),
        "score": round(quality["value"] * 10, 6),
        "routing": "skill_evolution",
        "features": {
            "candidate_source": "methodology",
            "method_fingerprint": fingerprint,
            "event_sequences": event_sequences,
            "event_count": len(events),
            "quality": quality,
            "lesson": lesson,
            "distinct_windows": 1,
            "occurrence_count": 1,
        },
        "evidence": [
            {
                "trace_id": trace_id,
                "turn_path": turn_path,
                "field": "task_trajectory.events",
                "quote": quote,
                "quote_sha256": hashlib.sha256(quote.encode()).hexdigest(),
                "event_sequences": event_sequences,
            }
        ],
        "slice": {
            "kind": "task_trajectory",
            "task": trajectory["task"],
            "outcome": trajectory["outcome"],
            "phases": trajectory["phases"],
            "events": [_event_excerpt(event) for event in events],
            "assistant_observations": observation_rows,
        },
    }


def _phase_workflow(
    trajectory: dict[str, Any], turn_path: str
) -> list[dict[str, Any]]:
    events = trajectory["events"]
    phases = [row["phase"] for row in trajectory["phases"]]
    if len(phases) < 4 or "modify" not in phases or "verify" not in phases:
        return []
    quality = _quality(
        events,
        success_dependency=0.8 if trajectory["outcome"]["status"] == "completed" else 0.4,
        surprise=min(0.9, 0.35 + len(phases) * 0.08),
        reusability=0.75,
        evidence_quality=0.85,
    )
    return [
        _finding(
            "method-phase-workflow",
            trajectory,
            turn_path,
            events,
            0.74 + min(0.16, len(phases) * 0.02),
            quality,
            {
                "kind": "ordered_workflow",
                "phase_order": phases,
                "rule": "Preserve the observed phase ordering and verify after modification.",
            },
        )
    ]


def _failure_recovery(
    trajectory: dict[str, Any], turn_path: str
) -> list[dict[str, Any]]:
    events = trajectory["events"]
    for index, failed in enumerate(events):
        if failed["status"] != "failed":
            continue
        failed_action = _normalized_action(failed)
        recovered = next(
            (
                event
                for event in events[index + 1 :]
                if event["status"] == "completed"
                and _normalized_action(event) != failed_action
            ),
            None,
        )
        if recovered is None:
            continue
        evidence = [failed, recovered]
        quality = _quality(
            evidence,
            success_dependency=0.95,
            surprise=0.9,
            reusability=0.85,
            evidence_quality=0.95,
        )
        return [
            _finding(
                "method-failure-recovery",
                trajectory,
                turn_path,
                evidence,
                0.9,
                quality,
                {
                    "kind": "failure_recovery",
                    "failed_action": failed_action,
                    "recovery_action": _normalized_action(recovered),
                    "rule": "After this failure signature, change the action rather than retrying unchanged.",
                },
            )
        ]
    return []


def _retry_oscillation(
    trajectory: dict[str, Any], turn_path: str, config: dict[str, Any]
) -> list[dict[str, Any]]:
    events = trajectory["events"]
    classifications = _analyze_retries(events, config)
    unnecessary = [
        row for row in classifications
        if not row["necessary"]
        and row["waste_score"] >= float(config.get("retry_waste_threshold", 0.7))
    ]
    if not unnecessary:
        return []
    sequences = {
        sequence
        for row in unnecessary
        for sequence in (row["first_sequence"], row["retry_sequence"])
    }
    selected = [event for event in events if event["sequence"] in sequences]
    necessary_count = sum(row["necessary"] for row in classifications)
    max_waste = max(row["waste_score"] for row in unnecessary)
    quality = _quality(
        selected,
        success_dependency=min(0.92, 0.68 + len(unnecessary) * 0.08),
        surprise=min(0.9, 0.62 + max_waste * 0.2),
        reusability=0.8,
        evidence_quality=0.9,
    )
    return [
        _finding(
            "method-retry-oscillation",
            trajectory,
            turn_path,
            selected,
            min(0.94, 0.72 + max_waste * 0.18),
            quality,
            {
                "kind": "retry_guard",
                "unnecessary_retry_count": len(unnecessary),
                "necessary_retry_count": necessary_count,
                "retry_classifications": classifications,
                "rule": (
                    "Retry only after a relevant state change, meaningful search "
                    "refinement or information gain, or a bounded transient failure; "
                    "otherwise change the action or acquire new evidence."
                ),
            },
        )
    ]


def _reflection_decision(
    trajectory: dict[str, Any], turn_path: str
) -> list[dict[str, Any]]:
    """Keep reflection text only when observable behavior changes afterward."""
    events = trajectory["events"]
    candidates: list[tuple[float, dict[str, Any], list[dict[str, Any]], dict[str, Any]]] = []
    for observation in trajectory.get("assistant_observations") or []:
        text = str(observation.get("text") or "")
        markers = [
            name for name, pattern in REFLECTION_PATTERNS.items()
            if pattern.search(text)
        ]
        if not markers:
            continue
        after_count = int(observation.get("after_tool_count") or 0)
        if after_count <= 0 or after_count >= len(events):
            continue
        previous = events[after_count - 1]
        following = events[after_count]
        action_changed = _retry_signature(previous) != _retry_signature(following)
        if not action_changed:
            continue
        preceding_failure = previous.get("status") == "failed"
        acquired_evidence = following.get("phase") == "inspect"
        later = events[after_count:]
        later_success = any(event.get("status") == "completed" for event in later)
        if not later_success:
            continue
        terminal_verify = next(
            (
                event for event in reversed(later)
                if event.get("phase") == "verify"
                and event.get("status") == "completed"
            ),
            None,
        )
        selected = [previous, following]
        if terminal_verify is not None and terminal_verify not in selected:
            selected.append(terminal_verify)
        functional_score = _clamp(
            0.2
            + 0.25 * float(action_changed)
            + 0.2 * float(preceding_failure)
            + 0.15 * float(acquired_evidence)
            + 0.2 * float(terminal_verify is not None)
        )
        candidates.append(
            (
                functional_score,
                observation,
                selected,
                {
                    "kind": "functional_reflection",
                    "marker_categories": markers,
                    "preceding_failure": preceding_failure,
                    "acquired_evidence": acquired_evidence,
                    "action_before": _normalized_action(previous),
                    "action_after": _normalized_action(following),
                    "functional_score": round(functional_score, 6),
                    "rule": (
                        "Treat reflection as useful only when it changes the "
                        "observable action and the revised path reaches a "
                        "successful check; reflective wording alone is not evidence."
                    ),
                },
            )
        )
    if not candidates:
        return []
    score, observation, selected, lesson = max(
        candidates, key=lambda item: item[0]
    )
    quality = _quality(
        selected,
        success_dependency=score,
        surprise=0.78,
        reusability=0.76,
        evidence_quality=0.9,
    )
    return [
        _finding(
            "method-functional-reflection",
            trajectory,
            turn_path,
            selected,
            min(0.92, 0.66 + score * 0.28),
            quality,
            lesson,
            observations=[observation],
        )
    ]


def _knowledge_acquisition(
    trajectory: dict[str, Any], turn_path: str, config: dict[str, Any]
) -> list[dict[str, Any]]:
    events = trajectory["events"]
    first_change = next(
        (
            index
            for index, event in enumerate(events)
            if event["phase"] in {"modify", "execute", "verify"}
        ),
        len(events),
    )
    exploration = [
        event for event in events[:first_change] if event["phase"] == "inspect"
    ]
    minimum = int(config.get("deep_exploration_events", 4))
    if len(exploration) < minimum or first_change >= len(events):
        return []
    enabling = events[first_change]
    selected = exploration[-minimum:] + [enabling]
    quality = _quality(
        selected,
        success_dependency=0.72,
        surprise=min(0.95, 0.55 + len(exploration) * 0.06),
        reusability=0.7,
        evidence_quality=0.72,
    )
    return [
        _finding(
            "method-knowledge-acquisition",
            trajectory,
            turn_path,
            selected,
            min(0.9, 0.68 + len(exploration) * 0.03),
            quality,
            {
                "kind": "knowledge_acquisition",
                "exploration_depth": len(exploration),
                "enabling_action": _normalized_action(enabling),
                "rule": "Inspect the relevant structure and constraints before choosing the mutating action.",
            },
        )
    ]


def _critical_path(
    trajectory: dict[str, Any], turn_path: str, config: dict[str, Any]
) -> list[dict[str, Any]]:
    events = trajectory["events"]
    terminal = next(
        (
            index
            for index in range(len(events) - 1, -1, -1)
            if events[index]["phase"] == "verify"
            and events[index]["status"] == "completed"
        ),
        None,
    )
    if terminal is None:
        return []
    needed: list[dict[str, Any]] = [events[terminal]]
    known_targets = set(events[terminal].get("targets") or [])
    for event in reversed(events[:terminal]):
        targets = set(event.get("targets") or [])
        if (
            event["phase"] == "modify"
            or targets & known_targets
            or (len(needed) == 1 and event["phase"] == "execute")
        ):
            needed.append(event)
            known_targets.update(targets)
    needed.reverse()
    minimum = int(config.get("critical_path_min_events", 3))
    detours = len(events) - len(needed)
    if len(needed) < minimum or detours < 1:
        return []
    quality = _quality(
        needed,
        success_dependency=0.92,
        surprise=min(0.9, 0.5 + detours * 0.08),
        reusability=0.78,
        evidence_quality=0.88,
    )
    return [
        _finding(
            "method-critical-path",
            trajectory,
            turn_path,
            needed,
            min(0.92, 0.76 + detours * 0.03),
            quality,
            {
                "kind": "critical_path",
                "detour_count": detours,
                "critical_sequences": [event["sequence"] for event in needed],
                "rule": "Use the dependency-preserving successful path and omit unrelated detours.",
            },
        )
    ]


def _direction_pivot(
    trajectory: dict[str, Any], turn_path: str
) -> list[dict[str, Any]]:
    events = trajectory["events"]
    for index, failed in enumerate(events[:-1]):
        if failed["status"] != "failed":
            continue
        later = events[index + 1 :]
        pivot = next(
            (
                event
                for event in later
                if event["status"] == "completed"
                and (
                    event["tool"] != failed["tool"]
                    or event["phase"] != failed["phase"]
                    or set(event.get("targets") or [])
                    != set(failed.get("targets") or [])
                )
            ),
            None,
        )
        if pivot is None:
            continue
        selected = [failed, pivot]
        quality = _quality(
            selected,
            success_dependency=0.88,
            surprise=0.82,
            reusability=0.76,
            evidence_quality=0.86,
        )
        return [
            _finding(
                "method-direction-pivot",
                trajectory,
                turn_path,
                selected,
                0.82,
                quality,
                {
                    "kind": "direction_pivot",
                    "from": _normalized_action(failed),
                    "to": _normalized_action(pivot),
                    "rule": "Use the failure evidence to switch target, tool, or phase.",
                },
            )
        ]
    return []


def _completion_contract(
    trajectory: dict[str, Any], turn_path: str
) -> list[dict[str, Any]]:
    events = trajectory["events"]
    verifies = [
        event
        for event in events
        if event["phase"] == "verify" and event["status"] == "completed"
    ]
    all_verifies = [
        event for event in events if event["phase"] == "verify"
    ]
    modifies = [event for event in events if event["phase"] == "modify"]
    if not verifies or not modifies:
        return []
    selected = modifies[-2:] + all_verifies
    argument_text = " ".join(
        str(event.get("arguments_preview") or "") for event in verifies
    ).strip()
    if len(verifies) == 1 and GENERIC_VERIFY.match(argument_text):
        return []
    quality = _quality(
        selected,
        success_dependency=0.96,
        surprise=0.68 if len(verifies) > 1 else 0.52,
        reusability=0.82,
        evidence_quality=0.92,
    )
    return [
        _finding(
            "method-completion-contract",
            trajectory,
            turn_path,
            selected,
            min(0.92, 0.78 + len(verifies) * 0.03),
            quality,
            {
                "kind": "completion_contract",
                "verification_actions": [
                    _normalized_action(event) for event in verifies
                ],
                "rule": "Do not stop after editing; satisfy the observed verification contract.",
            },
        )
    ]


def mine_trajectory(
    trajectory: dict[str, Any], turn_path: str, config: dict[str, Any]
) -> list[dict[str, Any]]:
    events = trajectory.get("events") or []
    if len(events) < int(config.get("min_events", 3)):
        return []
    configured = config.get("enabled_detectors")
    enabled = (
        {str(name) for name in configured}
        if isinstance(configured, list)
        else None
    )

    def use(name: str) -> bool:
        return enabled is None or name in enabled

    findings: list[dict[str, Any]] = []
    if use("method-phase-workflow"):
        findings.extend(_phase_workflow(trajectory, turn_path))
    if use("method-failure-recovery"):
        findings.extend(_failure_recovery(trajectory, turn_path))
    if use("method-retry-oscillation"):
        findings.extend(_retry_oscillation(trajectory, turn_path, config))
    if use("method-functional-reflection"):
        findings.extend(_reflection_decision(trajectory, turn_path))
    if use("method-knowledge-acquisition"):
        findings.extend(_knowledge_acquisition(trajectory, turn_path, config))
    if use("method-critical-path"):
        findings.extend(_critical_path(trajectory, turn_path, config))
    if use("method-direction-pivot"):
        findings.extend(_direction_pivot(trajectory, turn_path))
    if use("method-completion-contract"):
        findings.extend(_completion_contract(trajectory, turn_path))
    minimum = float(config.get("min_value_score", 0.08))
    maximum_obviousness = float(config.get("max_obviousness", 0.55))
    maximum_specificity = float(config.get("max_task_specificity", 0.65))
    return [
        finding
        for finding in findings
        if (
            float(finding["features"]["quality"]["value"]) >= minimum
            and float(finding["features"]["quality"]["obviousness"])
            <= maximum_obviousness
            and float(finding["features"]["quality"]["task_specificity"])
            <= maximum_specificity
        )
    ]


def consolidate_cross_task(
    findings: list[dict[str, Any]], config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Promote compatible recipes supported by distinct single-task sessions."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        if (finding.get("features") or {}).get("candidate_source") != "methodology":
            continue
        groups[finding["features"]["method_fingerprint"]].append(finding)
    minimum = int(config.get("cross_task_min_sessions", 2))
    consolidated: list[dict[str, Any]] = []
    for fingerprint, rows in groups.items():
        sessions = {row["session_id"] for row in rows}
        tasks = {
            str((row.get("slice") or {}).get("task", {}).get("text") or "").casefold()
            for row in rows
        }
        if len(sessions) < minimum or len(tasks) < minimum:
            continue
        representative = max(rows, key=lambda row: row["confidence"])
        row = json.loads(json.dumps(representative))
        identity = json.dumps(
            ["cross-task-methodology", fingerprint, sorted(sessions)],
            separators=(",", ":"),
        )
        row["signal_id"] = "sig-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        row["detector"] = "method-cross-task-consolidation"
        row["confidence"] = round(
            min(0.98, sum(item["confidence"] for item in rows) / len(rows) + 0.08),
            6,
        )
        row["features"]["candidate_source"] = "methodology_consolidated"
        row["features"]["distinct_sessions"] = len(sessions)
        row["features"]["distinct_tasks"] = len(tasks)
        row["features"]["supporting_signal_ids"] = [
            item["signal_id"] for item in rows
        ]
        consolidated.append(row)
    return consolidated


def run(
    workspace: Path, output_root: Path, config: dict[str, Any]
) -> list[dict[str, Any]]:
    methodology_config = config.get("methodology") or {}
    if not methodology_config.get("enabled", False):
        return []
    turns: dict[str, tuple[str, dict[str, Any]]] = {}
    for path in sorted((output_root / "normalized/turns").glob("*.json")):
        turn = json.loads(path.read_text())
        turns[turn["trace_id"]] = (
            path.relative_to(workspace).as_posix(),
            turn,
        )
    findings: list[dict[str, Any]] = []
    trajectories = output_root / "normalized/task_trajectories"
    for path in sorted(trajectories.glob("*.json")):
        trajectory = json.loads(path.read_text())
        turn = turns.get(trajectory["trace_id"])
        if turn is None:
            continue
        findings.extend(
            mine_trajectory(trajectory, turn[0], methodology_config)
        )
    configured = methodology_config.get("enabled_detectors")
    if (
        not isinstance(configured, list)
        or "method-cross-task-consolidation" in configured
    ):
        findings.extend(consolidate_cross_task(findings, methodology_config))
    return findings
