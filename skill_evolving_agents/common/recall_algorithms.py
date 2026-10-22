"""Selectable, deterministic skill-recall scoring strategies."""

from __future__ import annotations

from typing import Any, Callable


def number(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    return float(value)


def path_similarity(left: str, right: str, ancestor_factor: float) -> float:
    if left == right:
        return 1.0
    if left.startswith(f"{right}/") or right.startswith(f"{left}/"):
        return ancestor_factor
    return 0.0


def exact_overlap(
    cluster_labels: list[dict[str, Any]],
    skill_labels: list[dict[str, Any]],
    params: dict[str, Any],
) -> dict[str, Any] | None:
    del params
    wanted = {item["type"] for item in cluster_labels}
    labels = [item for item in skill_labels if item["type"] in wanted]
    if not labels:
        return None
    matches = [
        {
            "cluster_type": item["type"],
            "skill_type": item["type"],
            "similarity": 1.0,
            "contribution": item["weight"],
        }
        for item in labels
    ]
    return {
        "score": round(sum(item["weight"] for item in labels), 6),
        "labels": labels,
        "matches": matches,
    }


def weighted_path_similarity(
    cluster_labels: list[dict[str, Any]],
    skill_labels: list[dict[str, Any]],
    params: dict[str, Any],
) -> dict[str, Any] | None:
    min_confidence = number(
        params.get("minimum_cluster_confidence", 0.0),
        "minimum_cluster_confidence",
    )
    min_weight = number(params.get("minimum_skill_weight", 0.0), "minimum_skill_weight")
    min_score = number(params.get("minimum_score", 0.0), "minimum_score")
    ancestor_factor = number(params.get("ancestor_match_factor", 0.7), "ancestor_match_factor")
    fallback_factor = number(params.get("fallback_path_factor", 1.0), "fallback_path_factor")
    for name, value in (
        ("minimum_cluster_confidence", min_confidence),
        ("minimum_skill_weight", min_weight),
        ("ancestor_match_factor", ancestor_factor),
        ("fallback_path_factor", fallback_factor),
    ):
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be from 0 to 1")
    if min_score < 0:
        raise ValueError("minimum_score must be non-negative")
    min_shared = params.get("minimum_shared_labels", 1)
    if not isinstance(min_shared, int) or isinstance(min_shared, bool) or min_shared < 1:
        raise ValueError("minimum_shared_labels must be a positive integer")
    fallback_segments = params.get(
        "fallback_segments", ["rest", "none", "unspecified", "unbound"]
    )
    if not isinstance(fallback_segments, list) or not all(
        isinstance(value, str) and value for value in fallback_segments
    ):
        raise ValueError("fallback_segments must be a list of strings")
    fallback = set(fallback_segments)

    eligible_skills = [
        item for item in skill_labels if item["weight"] >= min_weight
    ]
    matches: list[dict[str, Any]] = []
    selected: dict[str, dict[str, Any]] = {}
    for cluster in cluster_labels:
        if cluster["confidence"] < min_confidence:
            continue
        best: tuple[float, dict[str, Any], float] | None = None
        for skill in eligible_skills:
            similarity = path_similarity(
                cluster["type"], skill["type"], ancestor_factor
            )
            if similarity <= 0:
                continue
            if fallback.intersection(cluster["type"].split("/")) or fallback.intersection(
                skill["type"].split("/")
            ):
                similarity *= fallback_factor
            contribution = cluster["confidence"] * skill["weight"] * similarity
            if best is None or contribution > best[0]:
                best = (contribution, skill, similarity)
        if best is None:
            continue
        contribution, skill, similarity = best
        selected[skill["type"]] = skill
        matches.append(
            {
                "cluster_type": cluster["type"],
                "skill_type": skill["type"],
                "similarity": round(similarity, 6),
                "contribution": round(contribution, 6),
            }
        )
    score = sum(item["contribution"] for item in matches)
    if len(matches) < min_shared or score < min_score:
        return None
    return {
        "score": round(score, 6),
        "labels": list(selected.values()),
        "matches": matches,
    }


STRATEGIES: dict[
    str,
    Callable[
        [list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]],
        dict[str, Any] | None,
    ],
] = {
    "exact_overlap": exact_overlap,
    "weighted_path_similarity": weighted_path_similarity,
}


def score(
    strategy: str,
    cluster_labels: list[dict[str, Any]],
    skill_labels: list[dict[str, Any]],
    params: dict[str, Any],
) -> dict[str, Any] | None:
    scorer = STRATEGIES.get(strategy)
    if scorer is None:
        raise ValueError(
            f"unknown recall strategy {strategy!r}; choose from {sorted(STRATEGIES)}"
        )
    return scorer(cluster_labels, skill_labels, params)
