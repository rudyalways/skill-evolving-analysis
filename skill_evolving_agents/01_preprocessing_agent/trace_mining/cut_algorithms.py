"""Heuristic windows that cut a session down to the turns worth diagnosing.

The coverage manifest still lists every canonical turn. These algorithms choose
the short slice a diagnosis agent should read. Each enabled name in
``preprocessing-config.json`` under ``cut.algorithms`` is one entry in
``ALGORITHM_LIST``.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable


TOKEN = re.compile(r"[A-Za-z0-9_]+")
IMAGE_BLOCK = re.compile(r"<image\b[^>]*>.*?</image>", re.IGNORECASE | re.DOTALL)
AMBIENT_BLOCK = re.compile(
    r"<(?:external_codex_apps_open_page|in-app-browser-context)\b[^>]*>.*?"
    r"</(?:external_codex_apps_open_page|in-app-browser-context)>",
    re.IGNORECASE | re.DOTALL,
)
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

DEFAULTS: dict[str, Any] = {
    "algorithms": None,
    "repetition_similarity": 0.6,
    "min_consecutive": 3,
    "context_before": 1,
    "context_after": 1,
    "max_window": 5,
    "max_user_turns": 5,
    "max_tokens": 2000,
    "long_turn_ms": 300_000,
    "rapid_correction_seconds": 10,
    "assistant_repeat_similarity": 0.75,
    "unresolved_similarity": 0.2,
    "keep_tool_events": 12,
    "tool_preview_chars": 400,
}


class CutWindow:
    def __init__(
        self,
        algorithm: str,
        version: str,
        indexes: tuple[int, ...],
        anchor_indexes: tuple[int, ...],
        features: dict[str, Any],
    ) -> None:
        self.algorithm = algorithm
        self.version = version
        self.indexes = indexes
        self.anchor_indexes = anchor_indexes
        self.features = features

    def record(
        self, turns: list[dict[str, Any]], config: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "algorithm": self.algorithm,
            "algorithm_version": self.version,
            "session_id": turns[0]["session_id"],
            "trace_ids": [turns[index]["trace_id"] for index in self.indexes],
            "anchor_trace_ids": [
                turns[index]["trace_id"] for index in self.anchor_indexes
            ],
            "turn_paths": [turns[index]["_path"] for index in self.indexes],
            "features": self.features,
            "slice": bounded_slice(
                [turns[index] for index in self.indexes], config
            ),
        }


Detect = Callable[
    [list[dict[str, Any]], list[str], dict[str, Any]],
    list[CutWindow],
]


class CutAlgorithm:
    def __init__(
        self,
        name: str,
        version: str,
        summary: str,
        detect: Detect,
    ) -> None:
        self.name = name
        self.version = version
        self.summary = summary
        self.detect = detect


def cut_config(config: dict[str, Any]) -> dict[str, Any]:
    section = dict(DEFAULTS)
    raw = config.get("cut")
    if isinstance(raw, dict):
        section.update(raw)
    if section["algorithms"] is None:
        section["algorithms"] = [algorithm.name for algorithm in ALGORITHM_LIST]
    return section


def plain_text(text: str) -> str:
    text = IMAGE_BLOCK.sub(" ", text or "")
    text = AMBIENT_BLOCK.sub(" ", text)
    return " ".join(text.split())


def jaccard(left: str, right: str) -> float:
    a = {token.casefold() for token in TOKEN.findall(left)}
    b = {token.casefold() for token in TOKEN.findall(right)}
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def duration_ms(turn: dict[str, Any]) -> float | None:
    timing = turn.get("timing") or {}
    duration = timing.get("duration_ms")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool):
        return float(duration)
    started = timing.get("started_at_epoch")
    completed = timing.get("completed_at_epoch")
    if (
        isinstance(started, (int, float))
        and isinstance(completed, (int, float))
        and completed >= started
    ):
        return (completed - started) * 1000
    return None


def window_around(
    core: list[int],
    turn_count: int,
    config: dict[str, Any],
) -> list[int]:
    """Keep the core, one neighbor on each side, and cap the slice."""
    if not core:
        return []
    before = max(0, int(config["context_before"]))
    after = max(0, int(config["context_after"]))
    limit = max(1, int(config["max_window"]))
    user_turns = config.get("max_user_turns")
    if isinstance(user_turns, int) and user_turns > 0:
        limit = min(limit, user_turns)
    start, end = min(core), max(core)
    budget = limit - before - after
    if budget < 1:
        before = after = 0
        budget = limit
    if end - start + 1 > budget:
        start = end - budget + 1
    low = max(0, start - before)
    high = min(turn_count - 1, end + after)
    indexes = list(range(low, high + 1))
    while len(indexes) > limit and indexes[0] < start:
        indexes.pop(0)
    while len(indexes) > limit and indexes[-1] > end:
        indexes.pop()
    while len(indexes) > limit:
        indexes.pop(0)
    return indexes


def _make(
    name: str,
    version: str,
    core: list[int],
    turns: list[dict[str, Any]],
    config: dict[str, Any],
    features: dict[str, Any],
) -> CutWindow:
    anchors = tuple(sorted(set(core)))
    indexes = limit_indexes(
        window_around(core, len(turns), config),
        anchors,
        turns,
        config,
    )
    return CutWindow(name, version, tuple(indexes), anchors, features)


def _consecutive_runs(texts: list[str], threshold: float, minimum: int) -> list[list[int]]:
    runs: list[list[int]] = []
    start = 0
    while start < len(texts):
        end = start
        while end + 1 < len(texts) and jaccard(texts[end], texts[end + 1]) >= threshold:
            end += 1
        if end > start and end - start + 1 >= minimum:
            runs.append(list(range(start, end + 1)))
            start = end + 1
        else:
            start += 1
    return runs


def _failed(turn: dict[str, Any]) -> bool:
    status = str((turn.get("outcome") or {}).get("status") or "")
    errors = int((turn.get("tool_summary") or {}).get("error_count") or 0)
    return status in {"failed", "aborted"} or errors > 0


def _detect_consecutive_repetition(
    turns: list[dict[str, Any]], texts: list[str], config: dict[str, Any]
) -> list[CutWindow]:
    threshold = float(config["repetition_similarity"])
    minimum = int(config["min_consecutive"])
    windows: list[CutWindow] = []
    for run in _consecutive_runs(texts, threshold, minimum):
        score = min(
            jaccard(texts[left], texts[right])
            for left, right in zip(run, run[1:])
        )
        windows.append(
            _make(
                "consecutive_repetition",
                "1",
                run,
                turns,
                config,
                {
                    "run_length": len(run),
                    "min_similarity": round(score, 6),
                },
            )
        )
    return windows


def _detect_long_turn(
    turns: list[dict[str, Any]], texts: list[str], config: dict[str, Any]
) -> list[CutWindow]:
    del texts
    limit = float(config["long_turn_ms"])
    windows: list[CutWindow] = []
    for index, turn in enumerate(turns):
        duration = duration_ms(turn)
        if duration is None or duration < limit:
            continue
        windows.append(
            _make(
                "long_turn",
                "1",
                [index],
                turns,
                config,
                {"duration_ms": round(duration, 3)},
            )
        )
    return windows


def _detect_long_turn_then_correction(
    turns: list[dict[str, Any]], texts: list[str], config: dict[str, Any]
) -> list[CutWindow]:
    limit = float(config["long_turn_ms"])
    windows: list[CutWindow] = []
    for index, turn in enumerate(turns[:-1]):
        duration = duration_ms(turn)
        if duration is None or duration < limit:
            continue
        if not CORRECTION.search(texts[index + 1]):
            continue
        windows.append(
            _make(
                "long_turn_then_correction",
                "1",
                [index, index + 1],
                turns,
                config,
                {"duration_ms": round(duration, 3)},
            )
        )
    return windows


def _detect_correction_burst(
    turns: list[dict[str, Any]], texts: list[str], config: dict[str, Any]
) -> list[CutWindow]:
    windows: list[CutWindow] = []
    start = 0
    while start < len(texts):
        if not CORRECTION.search(texts[start]):
            start += 1
            continue
        end = start
        while end + 1 < len(texts) and CORRECTION.search(texts[end + 1]):
            end += 1
        if end > start:
            windows.append(
                _make(
                    "correction_burst",
                    "1",
                    list(range(start, end + 1)),
                    turns,
                    config,
                    {"correction_count": end - start + 1},
                )
            )
            start = end + 1
        else:
            start += 1
    return windows


def _detect_rapid_correction(
    turns: list[dict[str, Any]], texts: list[str], config: dict[str, Any]
) -> list[CutWindow]:
    limit = float(config["rapid_correction_seconds"])
    windows: list[CutWindow] = []
    for index in range(1, len(turns)):
        if not CORRECTION.search(texts[index]):
            continue
        previous = (turns[index - 1].get("timing") or {}).get("completed_at_epoch")
        started = (turns[index].get("timing") or {}).get("started_at_epoch")
        if not isinstance(previous, (int, float)) or not isinstance(started, (int, float)):
            continue
        delay = started - previous
        if 0 < delay <= limit:
            windows.append(
                _make(
                    "rapid_correction",
                    "1",
                    [index - 1, index],
                    turns,
                    config,
                    {"delay_seconds": round(delay, 3)},
                )
            )
    return windows


def _detect_tool_failure_streak(
    turns: list[dict[str, Any]], texts: list[str], config: dict[str, Any]
) -> list[CutWindow]:
    del texts
    windows: list[CutWindow] = []
    start = 0
    while start < len(turns):
        if not _failed(turns[start]):
            start += 1
            continue
        end = start
        while end + 1 < len(turns) and _failed(turns[end + 1]):
            end += 1
        if end > start:
            windows.append(
                _make(
                    "tool_failure_streak",
                    "1",
                    list(range(start, end + 1)),
                    turns,
                    config,
                    {"failed_turns": end - start + 1},
                )
            )
            start = end + 1
        else:
            start += 1
    return windows


def _detect_keep_going_streak(
    turns: list[dict[str, Any]], texts: list[str], config: dict[str, Any]
) -> list[CutWindow]:
    windows: list[CutWindow] = []
    start = 0
    while start < len(texts):
        if not KEEP_GOING.search(texts[start]):
            start += 1
            continue
        end = start
        while end + 1 < len(texts) and KEEP_GOING.search(texts[end + 1]):
            end += 1
        if end > start:
            windows.append(
                _make(
                    "keep_going_streak",
                    "1",
                    list(range(start, end + 1)),
                    turns,
                    config,
                    {"count": end - start + 1},
                )
            )
            start = end + 1
        else:
            start += 1
    return windows


def _detect_unresolved_repeat(
    turns: list[dict[str, Any]], texts: list[str], config: dict[str, Any]
) -> list[CutWindow]:
    threshold = float(config["repetition_similarity"])
    unresolved = float(config["unresolved_similarity"])
    windows: list[CutWindow] = []
    for index in range(len(turns) - 1):
        if jaccard(texts[index], texts[index + 1]) < threshold:
            continue
        assistant = plain_text(str((turns[index].get("assistant") or {}).get("text") or ""))
        if assistant and jaccard(texts[index], assistant) >= unresolved:
            continue
        windows.append(
            _make(
                "unresolved_repeat",
                "1",
                [index, index + 1],
                turns,
                config,
                {
                    "request_similarity": round(
                        jaccard(texts[index], texts[index + 1]), 6
                    )
                },
            )
        )
    return windows


def _detect_abandonment(
    turns: list[dict[str, Any]], texts: list[str], config: dict[str, Any]
) -> list[CutWindow]:
    del texts
    windows: list[CutWindow] = []
    for index, turn in enumerate(turns):
        if str((turn.get("assistant") or {}).get("text") or "").strip():
            continue
        windows.append(
            _make(
                "abandonment",
                "1",
                [index],
                turns,
                config,
                {},
            )
        )
    return windows


def _detect_repeated_assistant(
    turns: list[dict[str, Any]], texts: list[str], config: dict[str, Any]
) -> list[CutWindow]:
    del texts
    replies = [
        plain_text(str((turn.get("assistant") or {}).get("text") or ""))
        for turn in turns
    ]
    threshold = float(config["assistant_repeat_similarity"])
    windows: list[CutWindow] = []
    for run in _consecutive_runs(replies, threshold, int(config["min_consecutive"])):
        windows.append(
            _make(
                "repeated_assistant",
                "1",
                run,
                turns,
                config,
                {"run_length": len(run)},
            )
        )
    return windows


def _detect_oscillation(
    turns: list[dict[str, Any]], texts: list[str], config: dict[str, Any]
) -> list[CutWindow]:
    threshold = float(config["repetition_similarity"])
    windows: list[CutWindow] = []
    start = 0
    while start + 4 < len(texts):
        if not (
            jaccard(texts[start], texts[start + 2]) >= threshold
            and jaccard(texts[start + 2], texts[start + 4]) >= threshold
            and jaccard(texts[start], texts[start + 1]) < threshold
        ):
            start += 1
            continue
        end = start + 4
        while end + 2 < len(texts) and jaccard(texts[end], texts[end + 2]) >= threshold:
            end += 2
        windows.append(
            _make(
                "oscillation",
                "1",
                list(range(start, end + 1, 2)),
                turns,
                config,
                {"period": 2, "repeats": (end - start) // 2 + 1},
            )
        )
        start = end + 1
    return windows


ALGORITHM_LIST: tuple[CutAlgorithm, ...] = (
    CutAlgorithm(
        "consecutive_repetition",
        "1",
        "Three or more similar user requests in a row. Keep that run plus the "
        "request before it and the request after it, at most five turns.",
        _detect_consecutive_repetition,
    ),
    CutAlgorithm(
        "long_turn",
        "1",
        "One user request whose agent run exceeds five minutes. Keep that turn "
        "plus the request before it and the request after it.",
        _detect_long_turn,
    ),
    CutAlgorithm(
        "long_turn_then_correction",
        "1",
        "A long agent run whose next user message is an immediate correction.",
        _detect_long_turn_then_correction,
    ),
    CutAlgorithm(
        "correction_burst",
        "1",
        "Two or more correction requests in a row, plus the turn they correct.",
        _detect_correction_burst,
    ),
    CutAlgorithm(
        "rapid_correction",
        "1",
        "A correction that arrives within seconds of the previous turn finishing.",
        _detect_rapid_correction,
    ),
    CutAlgorithm(
        "tool_failure_streak",
        "1",
        "Two or more consecutive turns that fail or record a tool error.",
        _detect_tool_failure_streak,
    ),
    CutAlgorithm(
        "keep_going_streak",
        "1",
        "Two or more consecutive keep-going requests, plus the unfinished turn.",
        _detect_keep_going_streak,
    ),
    CutAlgorithm(
        "unresolved_repeat",
        "1",
        "The next request repeats the previous one and the reply does not answer it.",
        _detect_unresolved_repeat,
    ),
    CutAlgorithm(
        "abandonment",
        "1",
        "A turn with no final assistant response, plus the preceding request.",
        _detect_abandonment,
    ),
    CutAlgorithm(
        "repeated_assistant",
        "1",
        "Three or more consecutive assistant replies that say nearly the same thing.",
        _detect_repeated_assistant,
    ),
    CutAlgorithm(
        "oscillation",
        "1",
        "User requests that alternate and then return to the same ask at least three times.",
        _detect_oscillation,
    ),
)


def enabled_algorithms(config: dict[str, Any]) -> list[CutAlgorithm]:
    section = cut_config(config)
    names = section["algorithms"]
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError("cut.algorithms must be a list of algorithm names")
    by_name = {algorithm.name: algorithm for algorithm in ALGORITHM_LIST}
    unknown = [name for name in names if name not in by_name]
    if unknown:
        raise ValueError(
            "unknown cut algorithms: " + ", ".join(unknown)
        )
    return [by_name[name] for name in names]


def select_windows(
    turns: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[CutWindow]:
    section = cut_config(config)
    texts = [
        plain_text(str((turn.get("user") or {}).get("text") or ""))
        for turn in turns
    ]
    windows: list[CutWindow] = []
    for algorithm in enabled_algorithms(config):
        windows.extend(algorithm.detect(turns, texts, section))
    suppressed = {
        index
        for window in windows
        if window.algorithm == "long_turn_then_correction"
        for index in window.anchor_indexes
    }
    kept: list[CutWindow] = []
    seen: set[tuple[str, tuple[int, ...]]] = set()
    for window in windows:
        if window.algorithm == "long_turn" and set(window.anchor_indexes) <= suppressed:
            continue
        key = (window.algorithm, window.indexes)
        if key in seen:
            continue
        seen.add(key)
        kept.append(window)
    return kept


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _turn_tokens(turn: dict[str, Any]) -> int:
    user = str((turn.get("user") or {}).get("text") or "")
    assistant = str((turn.get("assistant") or {}).get("text") or "")
    error = str((turn.get("outcome") or {}).get("error") or "")
    return _estimate_tokens(user) + _estimate_tokens(assistant) + _estimate_tokens(error)


def _clip_text(text: str, tokens: int) -> tuple[str, bool]:
    limit = max(0, tokens) * 4
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def limit_indexes(
    indexes: list[int],
    anchors: list[int] | tuple[int, ...],
    turns: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[int]:
    """Keep at most max_user_turns, preferring anchors, inside the token budget."""
    section = cut_config(config) if "max_tokens" not in config else {
        **DEFAULTS,
        **config,
    }
    chosen = sorted(set(indexes))
    anchor_set = {index for index in anchors if index in chosen}
    if not anchor_set and chosen:
        anchor_set = {chosen[-1]}
    max_turns = max(
        1,
        int(section.get("max_user_turns") or section["max_window"]),
    )
    max_tokens = max(1, int(section["max_tokens"]))
    center = sorted(anchor_set)[len(anchor_set) // 2] if anchor_set else 0

    def farthest_context() -> int | None:
        context = [index for index in chosen if index not in anchor_set]
        if not context:
            return None
        return max(context, key=lambda index: (abs(index - center), -index))

    while len(chosen) > max_turns:
        drop = farthest_context()
        if drop is None:
            extras = [index for index in chosen if index != max(anchor_set)]
            if not extras:
                break
            drop = min(extras)
        chosen.remove(drop)
        anchor_set.discard(drop)
    while (
        sum(_turn_tokens(turns[index]) for index in chosen) > max_tokens
    ):
        drop = farthest_context()
        if drop is None:
            break
        chosen.remove(drop)
    return chosen


def bounded_slice(
    turns: list[dict[str, Any]], config: dict[str, Any]
) -> dict[str, Any]:
    """Clip user, assistant, and error text so the slice stays inside max_tokens."""
    section = cut_config(config) if "max_tokens" not in config else {
        **DEFAULTS,
        **config,
    }
    budget = max(1, int(section["max_tokens"]))
    share = max(1, budget // max(1, len(turns)))
    user_tokens = max(1, int(share * 0.4))
    assistant_tokens = max(1, int(share * 0.5))
    error_tokens = max(1, share - user_tokens - assistant_tokens)
    rows: list[dict[str, Any]] = []
    used = 0
    for turn in turns:
        user, user_cut = _clip_text(
            str((turn.get("user") or {}).get("text") or ""), user_tokens
        )
        assistant, assistant_cut = _clip_text(
            str((turn.get("assistant") or {}).get("text") or ""),
            assistant_tokens,
        )
        error, error_cut = _clip_text(
            str((turn.get("outcome") or {}).get("error") or ""), error_tokens
        )
        tokens = (
            _estimate_tokens(user)
            + _estimate_tokens(assistant)
            + _estimate_tokens(error)
        )
        used += tokens
        rows.append(
            {
                "trace_id": turn.get("trace_id"),
                "user": user,
                "assistant": assistant,
                "outcome_status": (turn.get("outcome") or {}).get("status"),
                "error": error,
                "token_estimate": tokens,
                "truncated": user_cut or assistant_cut or error_cut,
            }
        )
    return {
        "user_turns": len(rows),
        "token_estimate": used,
        "max_tokens": budget,
        "max_user_turns": int(section.get("max_user_turns") or section["max_window"]),
        "turns": rows,
    }


def choose_window(
    core: list[int],
    windows: list[CutWindow],
    turns: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[list[int], str]:
    """Prefer a detected slice. Otherwise keep a bounded neighborhood."""
    section = cut_config(config)
    core_set = set(core)
    overlapping = [
        window for window in windows if core_set & set(window.indexes)
    ]
    if overlapping:
        best = max(
            overlapping,
            key=lambda window: (
                len(core_set & set(window.indexes)),
                -len(window.indexes),
                window.algorithm,
            ),
        )
        indexes, algorithm = list(best.indexes), best.algorithm
    else:
        indexes = window_around(core, len(turns), section)
        algorithm = "bounded_neighborhood"
    return limit_indexes(indexes, core, turns, section), algorithm


def algorithm_catalog() -> list[dict[str, str]]:
    return [
        {
            "name": algorithm.name,
            "version": algorithm.version,
            "summary": algorithm.summary,
        }
        for algorithm in ALGORITHM_LIST
    ]


def load_sessions(derived: Path, workspace: Path) -> list[list[dict[str, Any]]]:
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    turns = derived / "normalized/turns"
    if not turns.is_dir():
        return []
    for path in sorted(turns.glob("*.json")):
        turn = json.loads(path.read_text())
        turn["_path"] = path.relative_to(workspace).as_posix()
        sessions[str(turn["session_id"])].append(turn)
    ordered: list[list[dict[str, Any]]] = []
    for rows in sessions.values():
        rows.sort(key=lambda row: (row.get("timestamp") or "", row["trace_id"]))
        ordered.append(rows)
    ordered.sort(key=lambda rows: rows[0]["trace_id"])
    return ordered


def _excerpt_event(event: dict[str, Any], preview_chars: int) -> dict[str, Any]:
    excerpt = dict(event)
    preview = excerpt.get("result_preview")
    if isinstance(preview, str) and len(preview) > preview_chars:
        excerpt["result_preview"] = preview[:preview_chars]
        excerpt["result_preview_truncated"] = True
    arguments = excerpt.get("arguments")
    if isinstance(arguments, str) and len(arguments) > preview_chars:
        excerpt["arguments"] = arguments[:preview_chars]
        excerpt["arguments_truncated"] = True
    return excerpt


def write_tool_excerpts(
    workspace: Path,
    derived: Path,
    windows: list[dict[str, Any]],
    turns_by_id: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> None:
    section = cut_config(config)
    limit = int(section["keep_tool_events"])
    preview_chars = int(section["tool_preview_chars"])
    root = derived / "cut/tool_evidence"
    for window in windows:
        if window["algorithm"] not in {"long_turn", "long_turn_then_correction"}:
            continue
        excerpts: list[str] = []
        for trace_id in window["anchor_trace_ids"]:
            turn = turns_by_id.get(trace_id)
            if turn is None:
                continue
            relative = (turn.get("tool_summary") or {}).get("evidence_path")
            if not isinstance(relative, str) or not relative:
                continue
            source = workspace / relative
            if not source.is_file():
                continue
            events = [
                json.loads(line)
                for line in source.read_text().splitlines()
                if line.strip()
            ]
            if len(events) <= limit and all(
                len(str(event.get("result_preview") or "")) <= preview_chars
                and len(str(event.get("arguments") or "")) <= preview_chars
                for event in events
            ):
                continue
            failed = [
                index
                for index, event in enumerate(events)
                if event.get("status") == "failed"
            ]
            head = list(range(min(2, len(events))))
            tail = list(range(max(0, len(events) - 8), len(events)))
            chosen = sorted(set(failed + head + tail))[:limit]
            destination = root / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                "".join(
                    json.dumps(
                        _excerpt_event(events[index], preview_chars),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                    for index in chosen
                )
            )
            excerpts.append(destination.relative_to(workspace).as_posix())
        if excerpts:
            window["tool_evidence_excerpts"] = excerpts


def budget_summary(
    records: list[dict[str, Any]], config: dict[str, Any]
) -> dict[str, Any]:
    """User-turn and token totals actually emitted for diagnosis."""
    section = cut_config(config)
    windows: list[dict[str, Any]] = []
    for record in records:
        raw_slice = record.get("slice")
        window_slice = raw_slice if isinstance(raw_slice, dict) else {}
        turns = window_slice.get("turns") or []
        windows.append(
            {
                "algorithm": record.get("algorithm"),
                "session_id": record.get("session_id"),
                "trace_ids": record.get("trace_ids") or [],
                "user_turns": int(
                    window_slice.get("user_turns")
                    or len(record.get("trace_ids") or [])
                ),
                "token_estimate": int(window_slice.get("token_estimate") or 0),
                "truncated": any(
                    bool(turn.get("truncated"))
                    for turn in turns
                    if isinstance(turn, dict)
                ),
            }
        )
    return {
        "schema_version": 1,
        "max_user_turns": int(section["max_user_turns"]),
        "max_tokens": int(section["max_tokens"]),
        "window_count": len(windows),
        "max_user_turns_seen": max(
            (window["user_turns"] for window in windows), default=0
        ),
        "max_tokens_seen": max(
            (window["token_estimate"] for window in windows), default=0
        ),
        "truncated_windows": sum(1 for window in windows if window["truncated"]),
        "windows": windows,
    }


def write_cut_artifacts(
    workspace: Path,
    derived: Path,
    config: dict[str, Any],
    cluster_members: dict[str, set[str]] | None = None,
) -> list[dict[str, Any]]:
    sessions = load_sessions(derived, workspace)
    records: list[dict[str, Any]] = []
    turns_by_id: dict[str, dict[str, Any]] = {}
    for session in sessions:
        for turn in session:
            turns_by_id[turn["trace_id"]] = turn
        for window in select_windows(session, config):
            records.append(window.record(session, config))
    write_tool_excerpts(workspace, derived, records, turns_by_id, config)
    cut_root = derived / "cut"
    cut_root.mkdir(parents=True, exist_ok=True)
    (cut_root / "algorithms.json").write_text(
        json.dumps(
            {"schema_version": 1, "algorithms": algorithm_catalog()},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    (cut_root / "windows.jsonl").write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        )
    )
    (cut_root / "budget.json").write_text(
        json.dumps(budget_summary(records, config), indent=2, ensure_ascii=False)
        + "\n"
    )
    if cluster_members:
        for name, members in cluster_members.items():
            matched = [
                record
                for record in records
                if set(record["anchor_trace_ids"]) & members
            ]
            if not matched:
                continue
            path = derived / "cluster" / name / "cut.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "".join(
                    json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                    for record in matched
                )
            )
    return records
