"""Deterministic, replayable interaction-friction detectors."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


CORRECTION = re.compile(
    r"^(no(?:pe)?|wrong|wait|stop|actually|instead|that'?s not|not what i|"
    r"i (?:said|meant|asked|wanted)|don'?t do that|why did you|why (?:did you )?stop)\b",
    re.IGNORECASE,
)
KEEP_GOING = re.compile(
    r"^(keep going|continue|keep at it|more|finish|go on|don'?t stop|"
    r"you'?re not done|not done|keep iterating|why (?:did you )?stop)\b",
    re.IGNORECASE,
)
TOKEN = re.compile(r"[A-Za-z0-9_]+")
_CONTRACTS = None
IMAGE_BLOCK = re.compile(r"<image\b[^>]*>.*?</image>", re.IGNORECASE | re.DOTALL)
AMBIENT_BLOCK = re.compile(
    r"<(?:external_codex_apps_open_page|in-app-browser-context)\b[^>]*>.*?"
    r"</(?:external_codex_apps_open_page|in-app-browser-context)>",
    re.IGNORECASE | re.DOTALL,
)
NEGATIVE = {
    "bad",
    "broken",
    "fail",
    "failed",
    "incorrect",
    "no",
    "revert",
    "stop",
    "undo",
    "wrong",
}
POSITIVE = {"correct", "done", "fixed", "good", "great", "thanks", "working"}
SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
CUT_CANDIDATE_QUALITY: dict[str, tuple[str, float]] = {
    "consecutive_repetition": ("high", 0.82),
    "long_turn_then_correction": ("high", 0.85),
    "correction_burst": ("high", 0.82),
    "rapid_correction": ("high", 0.8),
    "tool_failure_streak": ("high", 0.84),
    "keep_going_streak": ("high", 0.8),
    "unresolved_repeat": ("high", 0.8),
    "abandonment": ("high", 0.82),
    "repeated_assistant": ("medium", 0.72),
    "oscillation": ("high", 0.82),
}


def _cut_algorithms():
    try:
        from . import cut_algorithms as module
    except ImportError:
        path = Path(__file__).with_name("cut_algorithms.py")
        spec = importlib.util.spec_from_file_location("trace_cut_algorithms", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load cut algorithms: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def _methodology_miner():
    try:
        from . import methodology as module
    except ImportError:
        path = Path(__file__).with_name("methodology.py")
        spec = importlib.util.spec_from_file_location(
            "trace_methodology_miner", path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load methodology miner: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def _resource_opportunity_miner():
    try:
        from . import resource_opportunities as module
    except ImportError:
        path = Path(__file__).with_name("resource_opportunities.py")
        spec = importlib.util.spec_from_file_location(
            "trace_resource_opportunities", path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load resource opportunity miner: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def _words(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN.findall(text)}


def detector_text(text: str) -> str:
    """Remove attachment/ambient wrappers before lexical comparison."""
    text = IMAGE_BLOCK.sub(" ", text)
    text = AMBIENT_BLOCK.sub(" ", text)
    return " ".join(text.split())


def _pipeline_contracts():
    global _CONTRACTS
    if _CONTRACTS is None:
        path = (
            Path(__file__).resolve().parents[2] / "common/pipeline_contracts.py"
        )
        spec = importlib.util.spec_from_file_location(
            "skill_evolver_pipeline_contracts", path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load pipeline contracts from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _CONTRACTS = module
    return _CONTRACTS


def _infrastructure_failure(turn: dict[str, Any], config: dict[str, Any]) -> bool:
    patterns = config.get("infrastructure_error_patterns") or []
    return _pipeline_contracts().infrastructure_error(turn, patterns)


def _jaccard(left: str, right: str) -> float:
    a, b = _words(left), _words(right)
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _turn_text(turn: dict[str, Any]) -> str:
    return detector_text(
        f"{(turn.get('user') or {}).get('text') or ''} "
        f"{(turn.get('assistant') or {}).get('text') or ''}"
    )


def _representative_indexes(indexes: list[int], limit: int) -> list[int]:
    """Sample an ordered pattern across its lifecycle instead of only its tail."""
    values = sorted(set(indexes))
    if len(values) <= limit:
        return values
    if limit <= 1:
        return [values[-1]]
    positions = {
        round(position * (len(values) - 1) / (limit - 1))
        for position in range(limit)
    }
    return [values[position] for position in sorted(positions)]


def _sentiment(text: str) -> float:
    words = _words(text)
    matched = len(words & POSITIVE) + len(words & NEGATIVE)
    return (
        (len(words & POSITIVE) - len(words & NEGATIVE)) / matched
        if matched
        else 0.0
    )


def _finding(
    detector: str,
    session_id: str,
    turns: list[dict[str, Any]],
    severity: str,
    confidence: float,
    score: float,
    features: dict[str, Any],
    *,
    routing: str = "skill_evolution",
    evidence_field: str = "user.text",
) -> dict[str, Any]:
    trace_ids = [turn["trace_id"] for turn in turns]
    identity = json.dumps(
        [detector, session_id, trace_ids, features],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    signal_id = "sig-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
    return {
        "schema_version": 1,
        "signal_id": signal_id,
        "detector": detector,
        "detector_version": "1",
        "scope": "session",
        "session_id": session_id,
        "trace_ids": trace_ids,
        "first_seen": min(
            (turn.get("timestamp") or "" for turn in turns), default=""
        ),
        "last_seen": max(
            (turn.get("timestamp") or "" for turn in turns), default=""
        ),
        "severity": severity,
        "confidence": round(max(0.0, min(1.0, confidence)), 6),
        "score": round(score, 6),
        "routing": routing,
        "features": features,
        "evidence": [
            {
                "trace_id": turn["trace_id"],
                "turn_path": turn["_path"],
                "field": evidence_field,
                "quote_sha256": hashlib.sha256(
                    (
                        str((turn.get("outcome") or {}).get("error") or "")
                        if evidence_field == "outcome.error"
                        else turn["user"]["text"]
                    ).encode()
                ).hexdigest(),
            }
            for turn in turns
        ],
    }


def _session_findings(
    session_id: str,
    turns: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    signals_config = (
        config["signals"]
        if isinstance(config.get("signals"), dict)
        else config
    )
    cutter = _cut_algorithms()
    windows = cutter.select_windows(turns, config)
    findings: list[dict[str, Any]] = []
    texts = [detector_text(turn["user"]["text"]) for turn in turns]

    def emit(
        detector: str,
        indexes: list[int],
        severity: str,
        confidence: float,
        score: float,
        features: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        chosen, algorithm = cutter.choose_window(
            indexes, windows, turns, config
        )
        finding = _finding(
            detector,
            session_id,
            [turns[index] for index in chosen],
            severity,
            confidence,
            score,
            {
                **features,
                "cut_algorithm": algorithm,
                "cut_turns": len(chosen),
            },
            **kwargs,
        )
        finding["slice"] = cutter.bounded_slice(
            [turns[index] for index in chosen], config
        )
        findings.append(finding)

    correction_indexes = [
        index for index, text in enumerate(texts) if CORRECTION.search(text)
    ]
    correction_rate = len(correction_indexes) / len(texts) if texts else 0
    if (
        len(correction_indexes) >= signals_config["min_corrections"]
        and correction_rate >= signals_config["correction_rate"]
    ):
        emit(
            "correction-heavy",
            correction_indexes,
            "critical" if correction_rate >= 0.4 else "high",
            min(0.95, 0.6 + correction_rate / 2),
            -3 * len(correction_indexes),
            {
                "correction_count": len(correction_indexes),
                "turn_count": len(turns),
                "correction_rate": round(correction_rate, 6),
            },
        )
    keep_indexes = [
        index for index, text in enumerate(texts) if KEEP_GOING.search(text)
    ]
    if len(keep_indexes) >= signals_config["min_keep_going"]:
        emit(
            "keep-going-loop",
            keep_indexes,
            # Reaching the configured loop threshold is already a strong
            # unresolved-work signal. Labeling two or three occurrences as
            # medium made the default high-severity selector silently negate
            # min_keep_going=2.
            "critical" if len(keep_indexes) >= 4 else "high",
            min(0.95, 0.55 + len(keep_indexes) * 0.08),
            -2 * len(keep_indexes),
            {"count": len(keep_indexes)},
        )
    repeats: list[tuple[int, int, float]] = []
    lookahead = int(signals_config["repetition_lookahead"])
    threshold = float(signals_config["repetition_similarity"])
    for left in range(len(turns)):
        for right in range(left + 1, min(len(turns), left + lookahead + 1)):
            similarity = _jaccard(texts[left], texts[right])
            if similarity >= threshold:
                repeats.append((left, right, similarity))
    if len(repeats) >= signals_config["min_repetitions"]:
        indexes = sorted({index for pair in repeats for index in pair[:2]})
        emit(
            "repeated-instructions",
            indexes,
            "critical" if len(repeats) >= 4 else "high",
            max(similarity for _, _, similarity in repeats),
            -3 * len(repeats),
            {
                "method": "jaccard",
                "pair_count": len(repeats),
                "max_similarity": round(
                    max(similarity for _, _, similarity in repeats), 6
                ),
                "lookahead": lookahead,
            },
        )
    if len(turns) >= 4:
        middle = len(turns) // 2
        early = sum(_sentiment(text) for text in texts[:middle]) / middle
        late_size = len(texts) - middle
        late = sum(_sentiment(text) for text in texts[middle:]) / late_size
        drop = early - late
        if drop >= signals_config["sentiment_drop"] and late <= 0:
            worst = min(
                range(middle, len(turns)),
                key=lambda index: _sentiment(texts[index]),
            )
            emit(
                "negative-drift",
                [worst],
                "high" if drop >= 1.0 else "medium",
                min(0.9, 0.5 + drop / 3),
                -round(drop * 10),
                {
                    "method": "keyword_lexicon",
                    "early_average": round(early, 6),
                    "late_average": round(late, 6),
                    "drop": round(drop, 6),
                },
            )
    missing = [
        index
        for index, turn in enumerate(turns)
        if not turn["assistant"]["text"].strip()
    ]
    if missing:
        missing_turns = [turns[index] for index in missing]
        infrastructure = all(
            _infrastructure_failure(turn, signals_config) for turn in missing_turns
        )
        emit(
            "missing-final-response",
            missing,
            "high",
            0.95,
            -4 * len(missing),
            {
                "count": len(missing),
                "infrastructure_failure": infrastructure,
            },
            routing="infrastructure" if infrastructure else "skill_evolution",
            evidence_field="outcome.error" if infrastructure else "user.text",
        )
    failed = [
        index
        for index, turn in enumerate(turns)
        if turn["outcome"]["status"] in {"failed", "aborted"}
        or turn["tool_summary"]["error_count"] > 0
    ]
    if len(failed) >= signals_config["min_failed_turns"]:
        failed_turns = [turns[index] for index in failed]
        infrastructure = all(
            _infrastructure_failure(turn, signals_config) for turn in failed_turns
        )
        emit(
            "tool-error-loop",
            failed,
            "critical" if len(failed) >= 5 else "high",
            min(0.98, 0.65 + len(failed) * 0.06),
            -len(failed),
            {
                "failed_turns": len(failed),
                "infrastructure_failure": infrastructure,
            },
            routing="infrastructure" if infrastructure else "skill_evolution",
            evidence_field="outcome.error" if infrastructure else "user.text",
        )
    rapid: list[int] = []
    for index, (previous, current) in enumerate(zip(turns, turns[1:]), start=1):
        previous_completed = (
            (previous.get("timing") or {}).get("completed_at_epoch")
        )
        current_started = (current.get("timing") or {}).get("started_at_epoch")
        if not isinstance(previous_completed, (int, float)) or not isinstance(
            current_started, (int, float)
        ):
            continue
        delay = current_started - previous_completed
        if 0 < delay <= signals_config["rapid_correction_seconds"] and CORRECTION.search(
            current["user"]["text"]
        ):
            rapid.append(index)
    if len(rapid) >= signals_config["min_rapid_corrections"]:
        emit(
            "rapid-corrections",
            rapid,
            "high",
            min(0.95, 0.6 + len(rapid) * 0.08),
            -2 * len(rapid),
            {
                "count": len(rapid),
                "seconds": signals_config["rapid_correction_seconds"],
            },
        )
    candidate_config = signals_config.get("selection") or {}
    if candidate_config.get("include_cut_candidates", False):
        for window in windows:
            quality = CUT_CANDIDATE_QUALITY.get(window.algorithm)
            if quality is None:
                continue
            severity, base_confidence = quality
            similarity = window.features.get("request_similarity")
            confidence = (
                max(base_confidence, float(similarity))
                if isinstance(similarity, (int, float))
                and not isinstance(similarity, bool)
                else base_confidence
            )
            chosen = list(window.indexes)
            chosen_turns = [turns[index] for index in chosen]
            anchor_turns = [
                turns[index] for index in window.anchor_indexes
            ]
            infrastructure = all(
                _infrastructure_failure(turn, signals_config)
                for turn in anchor_turns
            )
            finding = _finding(
                f"cut-{window.algorithm}",
                session_id,
                chosen_turns,
                severity,
                confidence,
                -len(window.anchor_indexes),
                {
                    **window.features,
                    "candidate_source": "cut_window",
                    "cut_algorithm": window.algorithm,
                    "cut_turns": len(chosen),
                    "occurrence_count": len(window.anchor_indexes),
                    "distinct_windows": 1,
                    "infrastructure_failure": infrastructure,
                    "infrastructure_anchor_count": sum(
                        _infrastructure_failure(turn, signals_config)
                        for turn in anchor_turns
                    ),
                },
                routing="infrastructure"
                if infrastructure
                else "skill_evolution",
                evidence_field="outcome.error"
                if infrastructure
                else "user.text",
            )
            finding["slice"] = cutter.bounded_slice(
                chosen_turns, config
            )
            findings.append(finding)

        long_windows = [
            window for window in windows if window.algorithm == "long_turn"
        ]
        anchor_indexes = sorted(
            {
                index
                for window in long_windows
                for index in window.anchor_indexes
            }
        )
        similarity_threshold = float(
            candidate_config.get("long_turn_similarity", 0.15)
        )
        minimum_related = int(
            candidate_config.get("min_related_long_turns", 3)
        )
        neighbors: dict[int, set[int]] = {
            index: set() for index in anchor_indexes
        }
        pair_similarities: dict[tuple[int, int], float] = {}
        for offset, left in enumerate(anchor_indexes):
            for right in anchor_indexes[offset + 1 :]:
                similarity = _jaccard(
                    _turn_text(turns[left]), _turn_text(turns[right])
                )
                if similarity < similarity_threshold:
                    continue
                neighbors[left].add(right)
                neighbors[right].add(left)
                pair_similarities[(left, right)] = similarity
        components: list[list[int]] = []
        unseen = set(anchor_indexes)
        while unseen:
            start = min(unseen)
            stack = [start]
            component: set[int] = set()
            while stack:
                current = stack.pop()
                if current in component:
                    continue
                component.add(current)
                stack.extend(neighbors[current] - component)
            unseen -= component
            if len(component) >= minimum_related:
                components.append(sorted(component))
        evidence_limit = int(
            candidate_config.get(
                "max_pattern_evidence_turns",
                (config.get("cut") or {}).get("max_user_turns", 5),
            )
        )
        for component in components:
            representatives = _representative_indexes(
                component, max(1, evidence_limit)
            )
            similarities = [
                value
                for (left, right), value in pair_similarities.items()
                if left in component and right in component
            ]
            confidence = min(0.95, 0.72 + 0.03 * len(component))
            finding = _finding(
                "recurring-long-workflow",
                session_id,
                [turns[index] for index in representatives],
                "high",
                confidence,
                -len(component),
                {
                    "candidate_source": "cut_pattern",
                    "cut_algorithm": "long_turn",
                    "cut_turns": len(representatives),
                    "occurrence_count": len(component),
                    "distinct_windows": len(component),
                    "similarity_method": "combined-turn-jaccard-components",
                    "similarity_threshold": similarity_threshold,
                    "max_pair_similarity": round(max(similarities), 6),
                },
            )
            finding["slice"] = cutter.bounded_slice(
                [turns[index] for index in representatives], config
            )
            findings.append(finding)
    return findings


def _rank_key(row: dict[str, Any]) -> tuple[Any, ...]:
    features = row.get("features") or {}
    quality = features.get("quality") or {}
    return (
        -int(features.get("candidate_source") == "resource_opportunity"),
        -SEVERITY_RANK[row["severity"]],
        -float(row["confidence"]),
        -float(quality.get("value") or 0),
        -int(features.get("distinct_sessions") or 1),
        -int(features.get("occurrence_count") or 1),
        row["signal_id"],
    )


def _select_findings(
    findings: list[dict[str, Any]], detector_config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    config = detector_config["selection"]
    minimum_rank = SEVERITY_RANK[config["min_severity"]]
    minimum_confidence = float(config["min_confidence"])
    candidate_confidence = float(
        config.get("cut_candidate_min_confidence", minimum_confidence)
    )
    methodology_config = detector_config.get("_methodology") or {}
    resource_config = detector_config.get("_resource_opportunities") or {}
    methodology_confidence = float(
        methodology_config.get("min_confidence", minimum_confidence)
    )
    decisions: dict[str, dict[str, Any]] = {}
    eligible: list[dict[str, Any]] = []
    for row in findings:
        signal_id = row["signal_id"]
        source = (row.get("features") or {}).get("candidate_source")
        is_methodology = source in {"methodology", "methodology_consolidated"}
        is_cut_candidate = source in {"cut_window", "cut_pattern"}
        is_resource_opportunity = source == "resource_opportunity"
        decision = {
            "schema_version": 1,
            "finding_id": signal_id,
            "detector": row["detector"],
            "severity": row["severity"],
            "confidence": row["confidence"],
            "candidate_source": source or "signal_detector",
        }
        if row["routing"] == "infrastructure" and not config.get(
            "include_infrastructure_failures", False
        ):
            decision.update(
                {"disposition": "rejected", "reason": "infrastructure-routing"}
            )
        elif is_cut_candidate and not config.get("include_cut_candidates", False):
            decision.update(
                {"disposition": "rejected", "reason": "cut-candidates-disabled"}
            )
        elif is_methodology and not methodology_config.get("enabled", False):
            decision.update(
                {"disposition": "rejected", "reason": "methodology-disabled"}
            )
        elif is_resource_opportunity and not resource_config.get("enabled", True):
            decision.update(
                {"disposition": "rejected", "reason": "resource-opportunities-disabled"}
            )
        elif not source and SEVERITY_RANK[row["severity"]] < minimum_rank:
            decision.update(
                {"disposition": "rejected", "reason": "below-min-severity"}
            )
        elif float(row["confidence"]) < (
            methodology_confidence
            if is_methodology
            else float(resource_config.get("min_confidence", minimum_confidence))
            if is_resource_opportunity
            else candidate_confidence
            if is_cut_candidate
            else minimum_confidence
        ):
            decision.update(
                {"disposition": "rejected", "reason": "below-min-confidence"}
            )
        else:
            decision.update({"disposition": "eligible", "reason": "qualified"})
            eligible.append(row)
        decisions[signal_id] = decision

    overlap_threshold = float(
        config.get("deduplicate_overlap_threshold", 0.8)
    )
    deduplicated: list[dict[str, Any]] = []
    for row in sorted(eligible, key=_rank_key):
        trace_ids = set(row["trace_ids"])
        row_features = row.get("features") or {}
        row_events = set(row_features.get("event_sequences") or [])
        duplicate = next(
            (
                kept
                for kept in deduplicated
                if row["session_id"] == kept["session_id"]
                and (
                    (
                        row_events
                        and set((kept.get("features") or {}).get("event_sequences") or [])
                        and len(
                            row_events
                            & set(
                                (kept.get("features") or {}).get(
                                    "event_sequences"
                                )
                                or []
                            )
                        )
                        / min(
                            len(row_events),
                            len(
                                set(
                                    (kept.get("features") or {}).get(
                                        "event_sequences"
                                    )
                                    or []
                                )
                            ),
                        )
                        >= float(
                            methodology_config.get(
                                "event_overlap_threshold", overlap_threshold
                            )
                        )
                    )
                    if row_features.get("candidate_source")
                    in {"methodology", "methodology_consolidated"}
                    else len(trace_ids & set(kept["trace_ids"]))
                    / min(len(trace_ids), len(kept["trace_ids"]))
                    >= overlap_threshold
                )
                and not (
                    row_features.get("candidate_source") == "resource_opportunity"
                    or (kept.get("features") or {}).get("candidate_source")
                    == "resource_opportunity"
                )
            ),
            None,
        )
        if duplicate is not None:
            decisions[row["signal_id"]].update(
                {
                    "disposition": "deduplicated",
                    "reason": "overlapping-evidence",
                    "selected_representative": duplicate["signal_id"],
                }
            )
            continue
        deduplicated.append(row)

    limit = max(1, int(config.get("max_candidate_findings_per_run", 12)))
    methodology_limit = max(
        1, int(methodology_config.get("max_findings_per_run", limit))
    )
    per_trace_limit = max(
        1, int(methodology_config.get("max_findings_per_trace", 2))
    )
    selected: list[dict[str, Any]] = []
    methodology_count = 0
    methodology_per_trace: Counter[str] = Counter()
    reserved_resources = max(0, int(resource_config.get("reserved_selection_slots", 1)))
    resource_rows = [
        row for row in deduplicated
        if (row.get("features") or {}).get("candidate_source") == "resource_opportunity"
    ][:reserved_resources]
    selected.extend(resource_rows)
    for row in deduplicated:
        if row in selected:
            continue
        if len(selected) >= limit:
            break
        source = (row.get("features") or {}).get("candidate_source")
        if source in {"methodology", "methodology_consolidated"}:
            trace_id = row["trace_ids"][0]
            if (
                methodology_count >= methodology_limit
                or methodology_per_trace[trace_id] >= per_trace_limit
            ):
                continue
            methodology_count += 1
            methodology_per_trace[trace_id] += 1
        selected.append(row)
    selected_ids = {row["signal_id"] for row in selected}
    for rank, row in enumerate(selected, start=1):
        decisions[row["signal_id"]].update(
            {"disposition": "selected", "reason": "ranked", "rank": rank}
        )
    for row in deduplicated:
        if row["signal_id"] not in selected_ids:
            decisions[row["signal_id"]].update(
                {
                    "disposition": "deferred",
                    "reason": "source-or-run-selection-cap",
                }
            )
    return selected, [
        decisions[row["signal_id"]]
        for row in sorted(findings, key=lambda item: item["signal_id"])
    ]


def _patterns(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        grouped[finding["detector"]].append(finding)
    patterns: list[dict[str, Any]] = []
    for detector, rows in sorted(grouped.items()):
        sessions = sorted({row["session_id"] for row in rows})
        severity = max(rows, key=lambda row: SEVERITY_RANK[row["severity"]])[
            "severity"
        ]
        confidence = sum(row["confidence"] for row in rows) / len(rows)
        strength = len(sessions) * SEVERITY_RANK[severity] * confidence
        fingerprint = hashlib.sha256(detector.encode()).hexdigest()[:24]
        patterns.append(
            {
                "schema_version": 1,
                "pattern_id": f"pattern-{fingerprint}",
                "fingerprint": f"fp1:{fingerprint}",
                "kind": detector,
                "occurrences": len(rows),
                "distinct_sessions": len(sessions),
                "severity": SEVERITY_RANK[severity],
                "confidence": round(confidence, 6),
                "strength": round(strength, 6),
                "first_seen": min(row["first_seen"] for row in rows),
                "last_seen": max(row["last_seen"] for row in rows),
                "status": "active",
                "evidence_signal_ids": [row["signal_id"] for row in rows],
            }
        )
    return patterns


def run(
    workspace: Path,
    output_root: Path,
    config: dict[str, Any],
    database: Path,
    run_key: str,
) -> dict[str, Any]:
    root = output_root / "signals"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted((output_root / "normalized/turns").glob("*.json")):
        turn = json.loads(path.read_text())
        turn["_path"] = path.relative_to(workspace).as_posix()
        sessions[turn["session_id"]].append(turn)
    for rows in sessions.values():
        rows.sort(
            key=lambda row: (
                row.get("timestamp") or "",
                row["trace_id"],
            )
        )
    detector_config = config["signals"]
    detector_config["_methodology"] = config.get("methodology") or {}
    detector_config["_resource_opportunities"] = config.get("resource_opportunities") or {}
    findings = [
        finding
        for session_id, rows in sorted(sessions.items())
        for finding in _session_findings(session_id, rows, config)
    ]
    findings.extend(_methodology_miner().run(workspace, output_root, config))
    resource_findings, resource_decisions = _resource_opportunity_miner().analyze(
        workspace, output_root, config
    )
    findings.extend(resource_findings)
    findings.sort(key=lambda row: (row["detector"], row["signal_id"]))
    patterns = _patterns(findings)
    selected, selection_decisions = _select_findings(
        findings, detector_config
    )
    (root / "findings.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in findings)
    )
    (root / "patterns.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in patterns)
    )
    (root / "selected-manifest.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "schema_version": 1,
                    "finding_id": row["signal_id"],
                    "trace_id": row["trace_ids"][-1],
                    "turn_path": row["evidence"][-1]["turn_path"],
                    "severity": row["severity"],
                    "confidence": row["confidence"],
                    "detector": row["detector"],
                },
                sort_keys=True,
            )
            + "\n"
            for row in selected
        )
    )
    (root / "selection-decisions.jsonl").write_text(
        "".join(
            json.dumps(row, sort_keys=True) + "\n"
            for row in selection_decisions
        )
    )
    (root / "resource-opportunity-decisions.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in resource_decisions)
    )
    finding_root = output_root / "findings"
    if finding_root.exists():
        shutil.rmtree(finding_root)
    finding_root.mkdir(parents=True, exist_ok=True)
    for row in selected:
        finding_id = row["signal_id"]
        directory = finding_root / finding_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "finding.json").write_text(
            json.dumps(row, indent=2, sort_keys=True) + "\n"
        )
        (directory / "manifest.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        "schema_version": 1,
                        "cluster": finding_id,
                        "trace_id": evidence["trace_id"],
                        "turn_path": evidence["turn_path"],
                        "score": row["confidence"],
                        "finding_id": finding_id,
                    },
                    sort_keys=True,
                )
                + "\n"
                for evidence in row["evidence"]
            )
        )
    counts = Counter(row["detector"] for row in findings)
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_signal_runs (
                run_key TEXT PRIMARY KEY,
                finding_count INTEGER NOT NULL,
                selected_count INTEGER NOT NULL,
                pattern_count INTEGER NOT NULL,
                detector_counts_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT OR REPLACE INTO trace_signal_runs VALUES (?, ?, ?, ?, ?)",
            (
                run_key,
                len(findings),
                len(selected),
                len(patterns),
                json.dumps(dict(sorted(counts.items())), sort_keys=True),
            ),
        )
    return {
        "finding_count": len(findings),
        "selected_count": len(selected),
        "pattern_count": len(patterns),
        "eligible_count": sum(
            row["disposition"] in {"eligible", "selected"}
            for row in selection_decisions
        ),
        "deduplicated_count": sum(
            row["disposition"] == "deduplicated"
            for row in selection_decisions
        ),
        "deferred_count": sum(
            row["disposition"] == "deferred"
            for row in selection_decisions
        ),
        "detectors": dict(sorted(counts.items())),
    }
