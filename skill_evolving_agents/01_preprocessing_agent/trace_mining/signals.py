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
    r"i (?:said|meant|asked|wanted)|don'?t do that|why did you)\b",
    re.IGNORECASE,
)
KEEP_GOING = re.compile(
    r"^(keep going|continue|keep at it|more|finish|go on|don'?t stop|"
    r"you'?re not done|not done|keep iterating)\b",
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
            "high" if len(keep_indexes) >= 4 else "medium",
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
    return findings


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
    findings = [
        finding
        for session_id, rows in sorted(sessions.items())
        for finding in _session_findings(session_id, rows, config)
    ]
    findings.sort(key=lambda row: (row["detector"], row["signal_id"]))
    patterns = _patterns(findings)
    selected = [
        row
        for row in findings
        if SEVERITY_RANK[row["severity"]]
        >= SEVERITY_RANK[detector_config["selection"]["min_severity"]]
        and row["confidence"] >= detector_config["selection"]["min_confidence"]
        and (
            row["routing"] != "infrastructure"
            or detector_config["selection"].get(
                "include_infrastructure_failures", False
            )
        )
    ]
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
        "detectors": dict(sorted(counts.items())),
    }
