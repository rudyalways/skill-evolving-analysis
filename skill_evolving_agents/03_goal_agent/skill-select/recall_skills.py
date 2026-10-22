#!/usr/bin/env python3
"""Recall existing skills with a selectable, configurable scoring strategy.

Reads the cluster labels in diagnosis.json and the skill labels in
metadata.json. Does not choose an action.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
AGENT = ROOT.parents[1]
DEFAULT_DIAGNOSIS = AGENT / "workspace" / "run" / "diagnosis.json"
DEFAULT_METADATA = (
    AGENT / "workspace" / "target" / "to_be_improved_skills_metadata" / "metadata.json"
)
DEFAULT_SKILLS = AGENT / "workspace" / "target" / "to_be_improved_skills"
DEFAULT_CLUSTERS = AGENT / "workspace" / "traces" / "derived" / "cluster"
DEFAULT_OUT = AGENT / "workspace" / "run" / "label-matching.json"
DEFAULT_CONFIG = AGENT / "common" / "recall-config.json"
_TYPE_CHECKER = AGENT / "common" / "skill_type_checker.py"
_spec = importlib.util.spec_from_file_location("skill_type_checker", _TYPE_CHECKER)
skill_type_checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skill_type_checker)
_ALGORITHMS = AGENT / "common" / "recall_algorithms.py"
_algorithm_spec = importlib.util.spec_from_file_location(
    "recall_algorithms", _ALGORITHMS
)
recall_algorithms = importlib.util.module_from_spec(_algorithm_spec)
_algorithm_spec.loader.exec_module(recall_algorithms)

MISSING = "skill_capabilities_missing"


def bare(value: str) -> str:
    return skill_type_checker.bare(value)


def weight_of(item: dict) -> float:
    weight = item.get("weight")
    if isinstance(weight, (int, float)) and not isinstance(weight, bool):
        return float(weight)
    return 0.0


def confidence_of(item: dict) -> float:
    confidence = item.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        return float(confidence)
    return 0.0


def leaf_type(item: object, leaves: set[str]) -> str | None:
    path = skill_type_checker.type_path(item)
    if not isinstance(path, str) or not bare(path):
        return None
    key = bare(path)
    if leaves and key not in leaves:
        return None
    return key


def cluster_name(record: dict) -> str:
    value = record.get("cluster")
    if isinstance(value, str) and bare(value):
        return bare(value)
    return ""


def skill_dirs(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def named_skills(metadata: dict, dirs: list[str]) -> list[tuple[str, dict]]:
    records = metadata.get("skills_metadata") or []
    if not isinstance(records, list):
        raise SystemExit("skills_metadata must be a list")
    found: list[tuple[str, dict]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise SystemExit(f"skills_metadata[{index}] must be an object")
        value = record.get("skill")
        if not isinstance(value, str) or not bare(value):
            raise SystemExit(f"skills_metadata[{index}].skill must name its directory")
        name = bare(value)
        if name not in dirs:
            raise SystemExit(f"metadata names a missing skill directory: {name}")
        found.append((name, record))
    return found


def load_config(path: Path, strategy_override: str | None = None) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid recall config {path}: {error}")
    if not isinstance(document, dict):
        raise SystemExit("recall config must be an object")
    version = document.get("schema_version")
    strategy = strategy_override or document.get("active_strategy")
    strategies = document.get("strategies")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise SystemExit("recall config schema_version must be a positive integer")
    if not isinstance(strategy, str) or not strategy:
        raise SystemExit("recall config active_strategy must be a string")
    if not isinstance(strategies, dict) or strategy not in strategies:
        raise SystemExit(f"recall config has no parameters for strategy {strategy!r}")
    params = strategies[strategy]
    if not isinstance(params, dict):
        raise SystemExit(f"recall strategy {strategy!r} parameters must be an object")
    if strategy not in recall_algorithms.STRATEGIES:
        raise SystemExit(
            f"unknown recall strategy {strategy!r}; "
            f"choose from {sorted(recall_algorithms.STRATEGIES)}"
        )
    top_k = params.get("top_k", 0)
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 0:
        raise SystemExit("recall strategy top_k must be a non-negative integer")
    try:
        recall_algorithms.score(strategy, [], [], params)
    except ValueError as error:
        raise SystemExit(f"invalid recall strategy config: {error}")
    effective = {
        "schema_version": version,
        "strategy": strategy,
        "params": params,
    }
    return {
        "schema_version": version,
        "strategy": strategy,
        "params": params,
        "sha256": hashlib.sha256(
            json.dumps(effective, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def recall(
    diagnosis: dict,
    metadata: dict,
    dirs: list[str],
    cluster_dirs: list[str],
    leaves: set[str],
    config: dict[str, Any],
) -> dict:
    groups: dict[str, dict[str, float]] = {}
    missing = diagnosis.get(MISSING) or []
    if not isinstance(missing, list):
        raise SystemExit(f"{MISSING} must be a list")
    for record in missing:
        if not isinstance(record, dict):
            continue
        key = leaf_type(record, leaves)
        if key is None:
            continue
        name = cluster_name(record)
        bucket = groups.setdefault(name, {})
        bucket[key] = max(bucket.get(key, 0.0), confidence_of(record))
    for name in cluster_dirs:
        groups.setdefault(name, {})

    skills = []
    for name, record in named_skills(metadata, dirs):
        labels = []
        seen: set[str] = set()
        for item in record.get(skill_type_checker.TYPES) or []:
            key = leaf_type(item, leaves)
            if key is None or key in seen:
                continue
            seen.add(key)
            labels.append(
                {
                    "type": key,
                    "weight": weight_of(item) if isinstance(item, dict) else 0.0,
                }
            )
        skills.append((name, labels))

    clusters = []
    for name in sorted(groups):
        cluster_labels = [
            {"type": key, "confidence": confidence}
            for key, confidence in groups[name].items()
        ]
        matched = []
        for skill, labels in skills:
            try:
                result = recall_algorithms.score(
                    config["strategy"],
                    cluster_labels,
                    labels,
                    config["params"],
                )
            except ValueError as error:
                raise SystemExit(f"invalid recall strategy config: {error}")
            if result is None:
                continue
            matched.append((result["score"], skill, result))
        matched.sort(key=lambda item: (-item[0], item[1].casefold()))
        top_k = config["params"].get("top_k", 0)
        if top_k:
            matched = matched[:top_k]
        entry: dict = {
            "labels": [item["type"] for item in cluster_labels],
            "skills": [
                {
                    "skill": skill,
                    "score": result["score"],
                    "labels": result["labels"],
                    "matches": result["matches"],
                }
                for _score, skill, result in matched
            ],
        }
        if name:
            entry = {"cluster": name, **entry}
        clusters.append(entry)
    return {
        "matching": {
            "strategy": config["strategy"],
            "config_version": config["schema_version"],
            "config_sha256": config["sha256"],
        },
        "clusters": clusters,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnosis", type=Path, default=DEFAULT_DIAGNOSIS)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--skills", type=Path, default=DEFAULT_SKILLS)
    parser.add_argument("--clusters", type=Path, default=DEFAULT_CLUSTERS)
    parser.add_argument("--tree", type=Path, default=skill_type_checker.DEFAULT_TREE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--strategy",
        choices=sorted(recall_algorithms.STRATEGIES),
        help="override active_strategy from the recall config",
    )
    parser.add_argument("--cluster", help="this session's cluster directory name")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    custom_inputs = (
        args.diagnosis != DEFAULT_DIAGNOSIS
        or args.metadata != DEFAULT_METADATA
        or args.skills != DEFAULT_SKILLS
        or args.clusters != DEFAULT_CLUSTERS
        or args.config != DEFAULT_CONFIG
        or args.strategy is not None
    )
    if custom_inputs and args.out is None:
        raise SystemExit("--out is required when any input path is overridden")
    diagnosis = json.loads(args.diagnosis.read_text())
    metadata = json.loads(args.metadata.read_text())
    dirs = skill_dirs(args.skills)
    cluster_dirs = skill_dirs(args.clusters)
    leaves = skill_type_checker.leaf_paths(args.tree)
    config = load_config(args.config, args.strategy)
    out = recall(diagnosis, metadata, dirs, cluster_dirs, leaves, config)
    if args.cluster:
        name = bare(args.cluster)
        kept = [
            item
            for item in out["clusters"]
            if item.get("cluster") == name or (name == "cut" and "cluster" not in item)
        ]
        if not kept:
            kept = [{"cluster": name, "labels": [], "skills": []}]
        out = {"matching": out["matching"], "clusters": kept}
    out_path = args.out
    if out_path is None:
        out_path = (
            AGENT / "workspace" / "run" / bare(args.cluster) / "label-matching.json"
            if args.cluster
            else DEFAULT_OUT
        )
    text = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    args.out = out_path
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(f"wrote {len(out['clusters'])} clusters to {args.out}")


if __name__ == "__main__":
    main()
