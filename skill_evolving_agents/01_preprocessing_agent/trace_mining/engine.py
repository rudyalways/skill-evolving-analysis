"""Execute active and isolated experiment trace-mining profiles."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import time
from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import MiningConfigError, MiningResult
from .registry import Registry, load_profile
from . import signals as signal_miner


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise MiningConfigError(f"cannot load trace-mining module: {path}")
    spec.loader.exec_module(module)
    return module


normalizer = _load_script(
    "trace_mining_normalizer", ROOT / "scripts/normalize_codex.py"
)
cluster_builder = _load_script(
    "trace_mining_cluster_builder", ROOT / "scripts/cluster_traces.py"
)


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text())
    if config.get("schema_version") != 1:
        raise MiningConfigError(f"unsupported preprocessing config: {path}")
    return config


def _stable_hash(value: Any) -> str:
    rendered = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(rendered.encode()).hexdigest()


def _source_hash(workspace: Path) -> str:
    digest = hashlib.sha256()
    roots = (
        workspace / "traces/raw/codex",
        workspace / "traces/raw/claude",
        workspace / "traces/raw/cursor",
        workspace / "traces/raw/target_agent",
    )
    paths = sorted(
        {path.resolve() for root in roots if root.is_dir() for path in root.glob("*.jsonl")}
    )
    for path in paths:
        digest.update(path.name.encode())
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def _effective_config(
    config: dict[str, Any], profile_name: str
) -> tuple[dict[str, Any], list[str], Any]:
    profile = load_profile(config, profile_name)
    run, selected = Registry().configure(profile)
    effective = deepcopy(config)
    effective["source"]["adapter"] = run.source_adapter
    effective["tool_evidence"]["policy"] = run.evidence_policy
    effective["clustering"]["active_strategy"] = run.vector_strategy
    sections = {
        "adapter": "source",
        "selector": "source",
        "evidence": "tool_evidence",
        "projector": "features",
        "feature": "features",
        "clusterer": "clustering",
        "namer": "clustering",
    }
    for stage, options in profile.options.items():
        effective[sections[stage]].update(options)
    identities = [strategy.identity for strategy in selected]
    return effective, identities, run


def _annotate_manifests(
    output_root: Path, provenance: dict[str, Any]
) -> None:
    for path in (
        output_root / "normalized/manifest.json",
        output_root / "features/cluster-metrics.json",
    ):
        if path.is_file():
            value = json.loads(path.read_text())
            value["mining_profile"] = provenance
            path.write_text(
                json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
                + "\n"
            )
    for path in sorted(output_root.glob("**/manifest.jsonl")):
        records = []
        for line in path.read_text().splitlines():
            record = json.loads(line)
            record["mining_profile"] = provenance
            records.append(record)
        path.write_text(
            "".join(
                json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                for record in records
            )
        )


def _record_profile(
    database: Path,
    run_key: str,
    profile: str,
    kind: str,
    fingerprint: str,
    config_hash: str,
    source_hash: str,
    strategies: list[str],
    duration_ms: int,
    metrics: dict[str, Any],
) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_mining_profile_runs (
                run_key TEXT PRIMARY KEY,
                profile TEXT NOT NULL,
                run_kind TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                strategies_json TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                metrics_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT OR REPLACE INTO trace_mining_profile_runs VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_key,
                profile,
                kind,
                fingerprint,
                config_hash,
                source_hash,
                json.dumps(strategies, sort_keys=True),
                duration_ms,
                json.dumps(metrics, sort_keys=True),
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def run_profile(
    workspace: Path,
    config: dict[str, Any],
    profile_name: str,
    *,
    clustered: bool,
    experiment: bool,
    source_hash: str,
    span_factory=None,
) -> MiningResult:
    effective, strategies, choices = _effective_config(config, profile_name)
    should_cluster = clustered and choices.clustered
    output_root = (
        workspace / "traces/derived/experiments" / profile_name
        if experiment
        else workspace / "traces/derived"
    )
    kind = "experiment" if experiment else "active"
    run_key = (
        f"{workspace.name}:experiment:{profile_name}"
        if experiment
        else workspace.name
    )
    config_hash = _stable_hash(
        {"profile": config["profiles"][profile_name], "effective": effective}
    )
    fingerprint = _stable_hash(
        {
            "config_hash": config_hash,
            "source_hash": source_hash,
            "strategies": strategies,
        }
    )
    database = workspace / "logs/metrics.sqlite"
    started = time.monotonic()
    normalize_span = (
        span_factory(
            workspace,
            "normalize-traces",
            run_key,
            "deterministic",
            metadata={"profile": profile_name, "kind": kind},
        )
        if span_factory
        else nullcontext()
    )
    with normalize_span:
        normalization = normalizer.normalize(
            workspace,
            effective,
            database=database,
            output_root=output_root,
            run_key=run_key,
        )
    signal_span = (
        span_factory(
            workspace,
            "detect-signals",
            run_key,
            "deterministic",
            metadata={"profile": profile_name, "kind": kind},
        )
        if span_factory
        else nullcontext()
    )
    with signal_span:
        signal_metrics = (
            signal_miner.run(
                workspace,
                output_root,
                effective,
                database,
                run_key,
            )
            if effective.get("signals", {}).get("enabled", True)
            else {
                "finding_count": 0,
                "selected_count": 0,
                "pattern_count": 0,
                "detectors": {},
            }
        )
    cluster_span = (
        span_factory(
            workspace,
            "deduplicate-and-cluster",
            run_key,
            "deterministic",
            metadata={"profile": profile_name, "kind": kind},
        )
        if span_factory
        else nullcontext()
    )
    with cluster_span:
        clustering = cluster_builder.build(
            workspace,
            effective,
            should_cluster,
            strategy_override=choices.vector_strategy,
            output_root=output_root,
            database=database,
            run_key=run_key,
        )
    provenance = {
        "profile": profile_name,
        "kind": kind,
        "config_hash": config_hash,
        "source_hash": source_hash,
        "fingerprint": fingerprint,
        "strategies": strategies,
    }
    _annotate_manifests(output_root, provenance)
    duration_ms = round((time.monotonic() - started) * 1000)
    _record_profile(
        database,
        run_key,
        profile_name,
        kind,
        fingerprint,
        config_hash,
        source_hash,
        strategies,
        duration_ms,
        {
            "normalization": normalization,
            "signals": signal_metrics,
            "clustering": clustering,
        },
    )
    return MiningResult(
        profile_name,
        output_root.relative_to(workspace).as_posix(),
        fingerprint,
        normalization,
        signal_metrics,
        clustering,
    )


def run(
    workspace: Path,
    config_path: Path,
    *,
    clustered: bool,
    profile_name: str | None = None,
    experiment_profiles: list[str] | None = None,
    span_factory=None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    config = load_config(config_path)
    active_name = profile_name or config.get("active_profile")
    active = load_profile(config, active_name).name
    requested_experiments = experiment_profiles or []
    if len(requested_experiments) != len(set(requested_experiments)):
        raise MiningConfigError("experiment profiles must be unique")
    experiments = list(requested_experiments)
    if active in experiments:
        raise MiningConfigError(
            f"active profile cannot also be an experiment: {active}"
        )
    for name in experiments:
        load_profile(config, name)
    source_hash = _source_hash(workspace)
    active_result = run_profile(
        workspace,
        config,
        active,
        clustered=clustered,
        experiment=False,
        source_hash=source_hash,
        span_factory=span_factory,
    )
    experiment_results = [
        run_profile(
            workspace,
            config,
            name,
            clustered=clustered,
            experiment=True,
            source_hash=source_hash,
            span_factory=span_factory,
        )
        for name in experiments
    ]
    return {
        "active": active_result.__dict__,
        "experiments": [result.__dict__ for result in experiment_results],
    }
