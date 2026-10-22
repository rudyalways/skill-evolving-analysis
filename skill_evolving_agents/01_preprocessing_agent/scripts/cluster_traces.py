#!/usr/bin/env python3
"""Build compact trace features and pointer-only cluster manifests."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import shutil
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
STOP = {
    "and",
    "are",
    "but",
    "can",
    "for",
    "from",
    "have",
    "into",
    "not",
    "that",
    "the",
    "this",
    "with",
    "you",
    "your",
}


def load_config(path: Path | dict[str, Any]) -> dict[str, Any]:
    value = path if isinstance(path, dict) else json.loads(path.read_text())
    if value.get("schema_version") != 1:
        raise SystemExit(f"unsupported preprocessing config: {path}")
    return value


def tokenize(text: str) -> list[str]:
    return [
        token.casefold()
        for token in TOKEN.findall(text)
        if token.casefold() not in STOP
    ]


def content_hash(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def minhash_signature(text: str, width: int) -> tuple[int, ...]:
    tokens = tokenize(text)
    shingles = {
        f"{left}\0{right}" for left, right in zip(tokens, tokens[1:])
    } or set(tokens)
    if not shingles:
        return tuple(0 for _ in range(width))
    return tuple(
        min(
            int.from_bytes(
                hashlib.sha256(f"{seed}:{shingle}".encode()).digest()[:8],
                "big",
            )
            for shingle in shingles
        )
        for seed in range(width)
    )


def deduplicate_rows(
    rows: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, dict[str, Any]]]:
    settings = config.get("deduplication", {})
    enabled = settings.get("enabled", True)
    near = settings.get("near_duplicate_enabled", True)
    width = int(settings.get("minhash_size", 64))
    threshold = float(settings.get("near_duplicate_threshold", 0.9))
    if width <= 0:
        raise SystemExit("deduplication.minhash_size must be positive")
    if not 0 <= threshold <= 1:
        raise SystemExit(
            "deduplication.near_duplicate_threshold must be from 0 to 1"
        )
    representatives: list[dict[str, Any]] = []
    aliases: dict[str, str] = {}
    details: dict[str, dict[str, Any]] = {}
    by_hash: dict[str, str] = {}
    signatures: dict[str, tuple[int, ...]] = {}
    for row in rows:
        trace_id = row["trace_id"]
        digest = content_hash(row["text"])
        if not enabled:
            representatives.append(row)
            aliases[trace_id] = trace_id
            details[trace_id] = {
                "method": "unique",
                "relation": "representative",
                "similarity": 1.0,
                "content_hash": digest,
                "content_sha256": digest,
            }
            continue
        exact = by_hash.get(digest)
        if exact:
            aliases[trace_id] = exact
            details[trace_id] = {
                "method": "exact",
                "relation": "exact_duplicate",
                "similarity": 1.0,
                "content_hash": digest,
                "content_sha256": digest,
            }
            continue
        signature = minhash_signature(row["text"], width)
        match: str | None = None
        match_similarity = 0.0
        if near:
            for candidate in representatives:
                candidate_id = candidate["trace_id"]
                other = signatures[candidate_id]
                similarity = sum(
                    left == right for left, right in zip(signature, other)
                ) / width
                if similarity >= threshold:
                    match = candidate_id
                    match_similarity = similarity
                    break
        if match:
            aliases[trace_id] = match
            details[trace_id] = {
                "method": "near",
                "relation": "near_duplicate",
                "similarity": round(match_similarity, 6),
                "content_hash": digest,
                "content_sha256": digest,
            }
            by_hash[digest] = match
            continue
        representatives.append(row)
        aliases[trace_id] = trace_id
        details[trace_id] = {
            "method": "unique",
            "relation": "representative",
            "similarity": 1.0,
            "content_hash": digest,
            "content_sha256": digest,
        }
        by_hash[digest] = trace_id
        signatures[trace_id] = signature
    return representatives, aliases, details


def sparse_cosine(left: dict[str, float], right: dict[str, float]) -> float:
    return sum(value * right.get(term, 0.0) for term, value in left.items())


def dense_cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise SystemExit("embedding vectors have inconsistent dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def average_sparse(rows: list[dict[str, float]]) -> dict[str, float]:
    values: Counter[str] = Counter()
    for row in rows:
        values.update(row)
    scale = 1 / len(rows)
    centroid = {key: value * scale for key, value in values.items()}
    norm = math.sqrt(sum(value * value for value in centroid.values()))
    return (
        {key: value / norm for key, value in centroid.items()}
        if norm
        else centroid
    )


def average_dense(rows: list[list[float]]) -> list[float]:
    width = len(rows[0])
    return [sum(row[index] for row in rows) / len(rows) for index in range(width)]


def safe_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return value[:64] or "unassigned"


def read_turns(
    workspace: Path, output_root: Path | None = None
) -> list[dict[str, Any]]:
    derived = output_root or workspace / "traces/derived"
    turns_root = derived / "normalized/turns"
    rows: list[dict[str, Any]] = []
    for path in sorted(turns_root.glob("*.json")):
        turn = json.loads(path.read_text())
        text = "\n".join(
            (
                str((turn.get("user") or {}).get("text") or ""),
                str((turn.get("assistant") or {}).get("text") or ""),
                str((turn.get("outcome") or {}).get("error") or ""),
            )
        )
        rows.append(
            {
                "trace_id": turn["trace_id"],
                "turn_path": path.relative_to(workspace).as_posix(),
                "text": text,
                "timestamp": turn.get("timestamp") or "",
            }
        )
    if not rows:
        raise SystemExit(f"no canonical turns found under {turns_root}")
    return rows


def tfidf_vectors(
    rows: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[dict[str, dict[str, float]], dict[str, Counter[str]]]:
    counts = {row["trace_id"]: Counter(tokenize(row["text"])) for row in rows}
    document_frequency: Counter[str] = Counter()
    for values in counts.values():
        document_frequency.update(values)
    minimum = int(config["features"].get("min_document_frequency", 1))
    maximum = int(config["features"].get("max_terms", 4096))
    vocabulary = {
        term
        for term, _frequency in document_frequency.most_common(maximum)
        if document_frequency[term] >= minimum
    }
    vectors: dict[str, dict[str, float]] = {}
    size = len(rows)
    for trace_id, values in counts.items():
        weighted = {
            term: count * (math.log((1 + size) / (1 + document_frequency[term])) + 1)
            for term, count in values.items()
            if term in vocabulary
        }
        norm = math.sqrt(sum(value * value for value in weighted.values()))
        vectors[trace_id] = (
            {term: value / norm for term, value in weighted.items()}
            if norm
            else {}
        )
    return vectors, counts


def load_embeddings(
    workspace: Path, config: dict[str, Any], trace_ids: set[str]
) -> dict[str, list[float]]:
    relative = config["clustering"]["embedding_vectors_path"]
    path = workspace / relative
    if not path.is_file():
        raise SystemExit(
            f"embedding strategy requires vectors at {path}; "
            "use tfidf or generate the configured JSONL first"
        )
    vectors: dict[str, list[float]] = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if row.get("trace_id") in trace_ids and isinstance(row.get("vector"), list):
            vector = row["vector"]
            if not all(isinstance(value, (int, float)) for value in vector):
                raise SystemExit(f"non-numeric embedding in {path}")
            vectors[row["trace_id"]] = [float(value) for value in vector]
    missing = sorted(trace_ids - vectors.keys())
    if missing:
        raise SystemExit(f"embeddings missing trace IDs: {', '.join(missing[:5])}")
    return vectors


def cluster_rows(
    rows: list[dict[str, Any]],
    vectors: dict[str, Any],
    strategy: str,
    threshold: float,
    max_clusters: int,
) -> tuple[list[list[dict[str, Any]]], dict[str, float]]:
    clusters: list[list[dict[str, Any]]] = []
    scores: dict[str, float] = {}
    for row in sorted(rows, key=lambda item: (item["timestamp"], item["trace_id"])):
        vector = vectors[row["trace_id"]]
        similarities: list[float] = []
        for cluster in clusters:
            members = [vectors[item["trace_id"]] for item in cluster]
            centroid = (
                average_dense(members)
                if strategy == "embedding"
                else average_sparse(members)
            )
            similarity = (
                dense_cosine(vector, centroid)
                if strategy == "embedding"
                else sparse_cosine(vector, centroid)
            )
            similarities.append(similarity)
        best = max(range(len(similarities)), key=similarities.__getitem__) if similarities else None
        if (
            best is None
            or (similarities[best] < threshold and len(clusters) < max_clusters)
        ):
            clusters.append([row])
            scores[row["trace_id"]] = 1.0
        else:
            clusters[best].append(row)
            scores[row["trace_id"]] = max(0.0, min(1.0, similarities[best]))
    return clusters, scores


def cluster_names(
    clusters: list[list[dict[str, Any]]],
    term_counts: dict[str, Counter[str]],
    top_terms: int,
) -> list[str]:
    names: list[str] = []
    used: Counter[str] = Counter()
    for cluster in clusters:
        terms: Counter[str] = Counter()
        for row in cluster:
            terms.update(term_counts[row["trace_id"]])
        base = safe_name("-".join(term for term, _ in terms.most_common(top_terms)))
        used[base] += 1
        names.append(base if used[base] == 1 else f"{base}-{used[base]}")
    return names


def manifest_record(
    cluster: str, row: dict[str, Any], score: float
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "cluster": cluster,
        "trace_id": row["trace_id"],
        "turn_path": row["turn_path"],
        "score": round(score, 6),
    }


def _cut_algorithms():
    path = (
        Path(__file__).resolve().parents[1] / "trace_mining" / "cut_algorithms.py"
    )
    spec = importlib.util.spec_from_file_location("trace_cut_algorithms", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load cut algorithms: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        )
    )


def build(
    workspace: Path,
    config_path: Path | dict[str, Any],
    clustered: bool,
    strategy_override: str | None = None,
    output_root: Path | None = None,
    database: Path | None = None,
    run_key: str | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    derived = output_root or workspace / "traces/derived"
    rows = read_turns(workspace, derived)
    unique_rows, aliases, dedup_details = deduplicate_rows(rows, config)
    features_root = derived / "features"
    cluster_root = derived / "cluster"
    cut_root = derived / "cut"
    strategy = strategy_override or config["clustering"]["active_strategy"]
    embedding_vectors = (
        load_embeddings(
            workspace, config, {row["trace_id"] for row in unique_rows}
        )
        if clustered and strategy == "embedding"
        else None
    )
    for path in (features_root, cluster_root, cut_root):
        if path.exists():
            shutil.rmtree(path)
    features_root.mkdir(parents=True)
    cut_root.mkdir(parents=True)
    tfidf, term_counts = tfidf_vectors(unique_rows, config)
    feature_rows: list[dict[str, Any]] = []
    for row in rows:
        representative = aliases[row["trace_id"]]
        feature_rows.append(
            {
                "schema_version": 1,
                "trace_id": row["trace_id"],
                "turn_path": row["turn_path"],
                "token_count": len(tokenize(row["text"])),
                "content_hash": dedup_details[row["trace_id"]]["content_hash"],
                "dedup_method": dedup_details[row["trace_id"]]["method"],
                "representative_trace_id": representative,
                "top_terms": [
                    term for term, _ in term_counts[representative].most_common(12)
                ],
            }
        )
    write_jsonl(features_root / "trace-features.jsonl", feature_rows)
    write_jsonl(
        features_root / "dedup-manifest.jsonl",
        [
            {
                "schema_version": 1,
                "trace_id": row["trace_id"],
                "representative_trace_id": aliases[row["trace_id"]],
                **dedup_details[row["trace_id"]],
            }
            for row in rows
        ],
    )
    write_jsonl(
        cut_root / "manifest.jsonl",
        [manifest_record("cut", row, 1.0) for row in rows],
    )
    names: list[str] = []
    cluster_members: dict[str, set[str]] = {}
    if clustered:
        if strategy not in {"tfidf", "embedding"}:
            raise SystemExit(f"unknown clustering strategy: {strategy}")
        vectors: dict[str, Any] = embedding_vectors or tfidf
        clusters, scores = cluster_rows(
            unique_rows,
            vectors,
            strategy,
            float(config["clustering"]["similarity_threshold"]),
            int(config["clustering"]["max_clusters"]),
        )
        names = cluster_names(
            clusters,
            term_counts,
            int(config["clustering"]["top_terms_per_cluster"]),
        )
        for name, cluster in zip(names, clusters):
            member_ids = {row["trace_id"] for row in cluster}
            expanded = [
                row
                for row in rows
                if aliases[row["trace_id"]] in member_ids
            ]
            cluster_members[name] = {row["trace_id"] for row in expanded}
            write_jsonl(
                cluster_root / name / "manifest.jsonl",
                [
                    manifest_record(
                        name, row, scores[aliases[row["trace_id"]]]
                    )
                    for row in expanded
                ],
            )
            representative = max(
                cluster, key=lambda row: scores[row["trace_id"]]
            )
            outlier_limit = int(
                config["clustering"].get("outliers_per_cluster", 1)
            )
            outliers = [
                row
                for row in sorted(
                    cluster, key=lambda item: scores[item["trace_id"]]
                )
                if row["trace_id"] != representative["trace_id"]
            ][:outlier_limit]
            write_jsonl(
                cluster_root / name / "representatives.jsonl",
                [
                    {
                        **manifest_record(
                            name,
                            representative,
                            scores[representative["trace_id"]],
                        ),
                        "role": "representative",
                    },
                    *[
                        {
                            **manifest_record(
                                name, row, scores[row["trace_id"]]
                            ),
                            "role": "outlier",
                        }
                        for row in outliers
                    ],
                ],
            )
    _cut_algorithms().write_cut_artifacts(
        workspace,
        derived,
        config,
        cluster_members or None,
    )
    metrics = {
        "schema_version": 1,
        "strategy": strategy,
        "trace_count": len(rows),
        "unique_trace_count": len(unique_rows),
        "deduplicated_trace_count": len(rows) - len(unique_rows),
        "cluster_count": len(names),
        "clusters": names,
    }
    (features_root / "cluster-metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n"
    )
    database_path = database or workspace / "logs/metrics.sqlite"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_cluster_runs (
                run_id TEXT PRIMARY KEY,
                strategy TEXT NOT NULL,
                trace_count INTEGER NOT NULL,
                cluster_count INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_dedup_runs (
                run_id TEXT PRIMARY KEY,
                trace_count INTEGER NOT NULL,
                unique_trace_count INTEGER NOT NULL,
                exact_duplicate_count INTEGER NOT NULL,
                near_duplicate_count INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT OR REPLACE INTO trace_cluster_runs VALUES (?, ?, ?, ?)",
            (run_key or workspace.name, strategy, len(rows), len(names)),
        )
        connection.execute(
            "INSERT OR REPLACE INTO trace_dedup_runs VALUES (?, ?, ?, ?, ?)",
            (
                run_key or workspace.name,
                len(rows),
                len(unique_rows),
                sum(
                    value["method"] == "exact"
                    for value in dedup_details.values()
                ),
                sum(
                    value["method"] == "near"
                    for value in dedup_details.values()
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "common/preprocessing-config.json",
    )
    parser.add_argument("--cluster", action="store_true")
    parser.add_argument("--strategy", choices=("tfidf", "embedding"))
    args = parser.parse_args()
    metrics = build(
        args.workspace.resolve(), args.config, args.cluster, args.strategy
    )
    print(json.dumps(metrics, sort_keys=True))


if __name__ == "__main__":
    main()
