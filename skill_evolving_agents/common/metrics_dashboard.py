#!/usr/bin/env python3
"""Render a dependency-free cross-run pipeline timing dashboard."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import sqlite3
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse


def _load_metrics():
    path = Path(__file__).with_name("pipeline_metrics.py")
    spec = importlib.util.spec_from_file_location(
        "pipeline_metrics_for_dashboard", path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


_METRICS = _load_metrics()
_SIG_RE = re.compile(r"(sig-[0-9a-f]+)")
_LIVE_STATUS_MAX_SECONDS = 12 * 60 * 60
_TRUNK = {
    "normalize-traces",
    "detect-signals",
    "deduplicate-and-cluster",
    "validate-preprocessing",
    "label-skills",
    "validate-skill-labels",
}
_PHASE_OUTPUT_JSON = {
    "finding.json",
    "diagnosis.json",
    "label-matching.json",
    "evolve-goal.json",
    "goal-reduction.json",
    "changelog.json",
    "verification-input.json",
    "verification-output.required.json",
    "verification.json",
    "judge.json",
    "publication.json",
    "pipeline-summary.json",
}
_PHASE_OUTPUT_ORDER = (
    "detect-signals",
    "label-traces-cluster",
    "label-skills",
    "goal",
    "optimize",
    "verification",
    "judge",
    "publication",
    "summary",
)


def skill_inventory_stats(database: Path) -> dict[str, Any]:
    """Aggregate domain, OOD, lifecycle, and per-skill inventory statistics."""
    path = database.parent / "candidate_skills_metadata/metadata.json"
    empty = {
        "source": str(path), "total_skills": 0, "domain_stats": [],
        "ood_stats": [], "lifecycle_stats": [], "top_skills": [], "per_skill": [],
    }
    try:
        document = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return empty
    rows = [row for row in document.get("skills_metadata", []) if isinstance(row, dict)]
    domains: dict[str, dict[str, float]] = defaultdict(lambda: {"skills": 0, "weight": 0.0})
    ood: dict[str, int] = defaultdict(int)
    lifecycle_counts: dict[str, int] = defaultdict(int)
    per_skill = []
    for row in rows:
        lifecycle = row.get("lifecycle") if isinstance(row.get("lifecycle"), dict) else {}
        status = str(lifecycle.get("status") or "unknown")
        evidence_records = int(lifecycle.get("evidence_records") or 0)
        evaluation_kind = str(lifecycle.get("evaluation_kind") or "unknown")
        legacy_default = (
            evaluation_kind == "legacy_inventory_backfill"
            or lifecycle.get("evaluation_baseline_reason") == "legacy_inventory_backfill"
        )
        confidence_state = "legacy_default" if legacy_default else "measured" if evidence_records else "no_evidence"
        lifecycle_counts[status] += 1
        skill_domains = []
        for value in row.get("skill_types") or []:
            if not isinstance(value, dict) or not str(value.get("type", "")).startswith("domain/"):
                continue
            name = str(value["type"]).removeprefix("domain/") or "unspecified"
            weight = float(value.get("weight") or 0)
            domains[name]["skills"] += 1
            domains[name]["weight"] += weight
            skill_domains.append({"domain": name, "weight": weight})
        unmatched = [str(value.get("type") if isinstance(value, dict) else value) for value in row.get("unmatched_skill_types") or []]
        for value in unmatched:
            ood[value or "unspecified"] += 1
        per_skill.append({
            "skill": str(row.get("skill") or "unnamed"),
            "description": str(row.get("description") or ""),
            "domains": sorted(skill_domains, key=lambda value: (-value["weight"], value["domain"])),
            "ood": unmatched,
            "status": status,
            "confidence": lifecycle.get("confidence"),
            "evidence_records": evidence_records,
            "distinct_sessions": int(lifecycle.get("distinct_sessions") or len(lifecycle.get("origin_session_ids") or [])),
            "evaluation_kind": evaluation_kind,
            "confidence_state": confidence_state,
            "is_uncalibrated": confidence_state != "measured",
        })
    domain_stats = [
        {
            "domain": name,
            "skills": int(values["skills"]),
            "weight": round(values["weight"], 3),
            "mean_weight": round(values["weight"] / values["skills"], 3),
        }
        for name, values in domains.items()
    ]
    domain_stats.sort(key=lambda row: (-row["skills"], -row["weight"], row["domain"]))
    per_skill.sort(key=lambda row: row["skill"])
    top_skills = sorted(
        per_skill,
        key=lambda row: (
            row["is_uncalibrated"],
            -(float(row["confidence"]) if isinstance(row["confidence"], (int, float)) else -1),
            -row["evidence_records"], -row["distinct_sessions"], row["skill"],
        ),
    )[:10]
    return {
        "source": str(path), "total_skills": len(per_skill),
        "domain_stats": domain_stats,
        "ood_stats": [{"type": name, "skills": count} for name, count in sorted(ood.items(), key=lambda item: (-item[1], item[0]))],
        "lifecycle_stats": [{"status": name, "skills": count} for name, count in sorted(lifecycle_counts.items(), key=lambda item: (-item[1], item[0]))],
        "top_skills": top_skills, "per_skill": per_skill,
    }


def _json_phase(relative: Path) -> str:
    """Map a run-owned JSON artifact to the phase that produced it."""
    parts = relative.parts
    name = relative.name
    if parts[:3] == ("traces", "derived", "normalized"):
        return "preprocessing"
    if parts[:3] == ("traces", "derived", "findings"):
        return "detect-signals"
    if name in {"cluster-metrics.json", "diagnosis.json"}:
        return "label-traces-cluster"
    if name == "label-matching.json":
        return "label-skills"
    if name in {"evolve-goal.json", "goal-reduction.json"}:
        return "goal"
    if name in {"optimization.json", "changelog.json"}:
        return "optimize"
    if name in {"verification.json", "verification-input.json", "verification-output.required.json"}:
        return "verification"
    if name == "judge.json":
        return "judge"
    if name == "publication.json":
        return "publication"
    if name == "pipeline-summary.json":
        return "summary"
    if len(parts) > 2 and parts[:2] == ("run", "status"):
        return parts[2]
    if parts and parts[0] == "logs":
        return "observability"
    if parts and parts[0] == "target":
        return "inventory"
    return "control-plane"


def _artifact_id(value: Any, path: Path) -> str:
    parts = path.parts
    if "ops" in parts:
        index = parts.index("ops")
        if index > 0 and index + 1 < len(parts):
            return f"{parts[index - 1]}:op-{parts[index + 1]}"
    if isinstance(value, dict):
        for key in ("id", "finding_id", "operation_id", "cluster_id", "skill", "run_id", "item"):
            raw = value.get(key)
            if isinstance(raw, (str, int)) and str(raw).strip():
                return str(raw)
    if path.parent.name.startswith("sig-"):
        return path.parent.name
    return path.stem


def _ood_values(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in {
                "ood", "out_of_distribution", "unmatched_skill_types",
                # Preserve the producer's historical misspelling.
                "newly_detected_skill_capabilites_missing",
                "newly_detected_skill_capabilities_missing",
            }:
                if child not in (None, [], {}, "", False):
                    if isinstance(child, list):
                        found.extend(
                            str(item.get("type") or item.get("id") or item)
                            if isinstance(item, dict) else str(item)
                            for item in child[:8]
                        )
                    elif isinstance(child, dict):
                        found.extend(str(item) for item in list(child)[:8])
                    else:
                        found.append(str(child))
            found.extend(_ood_values(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_ood_values(child))
    return list(dict.fromkeys(found))[:12]


def phase_json_audit(database: Path, run_id: str) -> dict[str, Any]:
    runs_root = (database.parent / "runs").resolve()
    root = (runs_root / run_id).resolve()
    if root.parent != runs_root or not root.is_dir():
        return {"run_id": run_id, "phases": [], "document_count": 0}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(root.rglob("*.json")):
        relative = path.relative_to(root)
        if path.name not in _PHASE_OUTPUT_JSON:
            continue
        try:
            value = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        ood = _ood_values(value)
        grouped[_json_phase(relative)].append({
            "path": relative.as_posix(),
            "name": path.name,
            "id": _artifact_id(value, path),
            "ood": ood,
            "has_ood": bool(ood),
            "keys": list(value)[:12] if isinstance(value, dict) else [],
            "bytes": path.stat().st_size,
            "url": f"/api/artifact?run={quote(run_id)}&path={quote(relative.as_posix())}",
        })
    order = {name: index for index, name in enumerate(_PHASE_OUTPUT_ORDER)}
    phases = [
        {"phase": phase, "documents": documents,
         "document_count": len(documents),
         "ood_count": sum(row["has_ood"] for row in documents)}
        for phase in _PHASE_OUTPUT_ORDER
        for documents in [grouped.get(phase, [])]
    ]
    phases.sort(key=lambda row: (order.get(row["phase"], 999), row["phase"]))
    return {"run_id": run_id, "phases": phases,
            "document_count": sum(row["document_count"] for row in phases)}


def goal_operation_stats(database: Path) -> dict[str, Any]:
    """Aggregate proposed goal operations across runs, without relying on execution."""
    kinds = ("create", "update", "delete", "merge", "split", "no_change")
    operation_counts = defaultdict(int)
    skills: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    categories: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    ood_types: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sections: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    directories: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    resource_decisions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    goal_documents = 0
    for run_root in sorted((database.parent / "runs").glob("*")):
        metadata_path = run_root / "target/to_be_improved_skills_metadata/metadata.json"
        metadata_by_skill: dict[str, dict[str, Any]] = {}
        try:
            metadata = json.loads(metadata_path.read_text())
            metadata_by_skill = {
                str(row.get("skill")): row
                for row in metadata.get("skills_metadata", [])
                if isinstance(row, dict) and row.get("skill")
            }
        except (OSError, json.JSONDecodeError):
            pass
        for path in sorted((run_root / "run").glob("*/evolve-goal.json")):
            try:
                goal = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            goal_documents += 1
            operations = ((goal.get("action") or {}).get("ops") or []) if isinstance(goal, dict) else []
            if not operations:
                operation_counts["no_change"] += 1
                continue
            for operation in operations:
                if not isinstance(operation, dict):
                    continue
                kind = str(operation.get("op") or "unknown")
                operation_counts[kind] += 1
                embedded: dict[str, dict[str, Any]] = {}
                raw_skills = operation.get("skills") or []
                for value in raw_skills:
                    if isinstance(value, dict) and value.get("skill"):
                        embedded[str(value["skill"])] = value
                    elif isinstance(value, str) and value:
                        embedded[value] = {}
                if isinstance(operation.get("into"), dict) and operation["into"].get("skill"):
                    embedded[str(operation["into"]["skill"])] = operation["into"]
                if isinstance(operation.get("skill"), str):
                    embedded.setdefault(str(operation["skill"]), {})
                into_values = operation.get("into") if isinstance(operation.get("into"), list) else []
                for value in into_values:
                    if isinstance(value, dict) and value.get("skill"):
                        embedded[str(value["skill"])] = value
                for name, definition in embedded.items():
                    metadata_row = metadata_by_skill.get(name, {})
                    labels = definition.get("labels") or metadata_row.get("skill_types") or []
                    label_names = sorted({
                        str(label.get("type"))
                        for label in labels if isinstance(label, dict) and label.get("type")
                    })
                    unmatched = definition.get("unmatched_skill_types") or metadata_row.get("unmatched_skill_types") or []
                    unmatched_names = sorted({
                        str(value.get("type") if isinstance(value, dict) else value)
                        for value in unmatched if value
                    })
                    section_names = sorted({
                        str(value.get("section")) for value in definition.get("sections") or []
                        if isinstance(value, dict) and value.get("section")
                    })
                    directory_names = sorted({
                        str(value.get("dir")).split("/", 1)[0] for value in definition.get("dirs") or []
                        if isinstance(value, dict) and value.get("dir")
                    })
                    plans = sorted({
                        f"{value.get('resource')}:{value.get('decision')}"
                        for value in definition.get("resource_plan") or []
                        if isinstance(value, dict) and value.get("resource") and value.get("decision")
                    })
                    for bucket in (kind, "all"):
                        row = skills[bucket].setdefault(name, {
                            "skill": name, "count": 0, "categories": set(), "ood": set(),
                            "sections": set(), "directories": set(), "resource_decisions": set(),
                        })
                        row["count"] += 1
                        row["categories"].update(label_names)
                        row["ood"].update(unmatched_names)
                        row["sections"].update(section_names)
                        row["directories"].update(directory_names)
                        row["resource_decisions"].update(plans)
                        for label in label_names:
                            categories[bucket][label] += 1
                        for value in unmatched_names:
                            ood_types[bucket][value] += 1
                        for value in section_names:
                            sections[bucket][value] += 1
                        for value in directory_names:
                            directories[bucket][value] += 1
                        for value in plans:
                            resource_decisions[bucket][value] += 1
    return {
        "goal_documents": goal_documents,
        "operations": [{"operation": kind, "count": operation_counts[kind]} for kind in kinds],
        "by_operation": {
            kind: {
                "skills": [
                    {**row, **{field: sorted(row[field]) for field in (
                        "categories", "ood", "sections", "directories", "resource_decisions"
                    )}}
                    for row in sorted(skills[kind].values(), key=lambda value: (-value["count"], value["skill"]))
                ],
                "categories": [
                    {"category": name, "count": count}
                    for name, count in sorted(categories[kind].items(), key=lambda item: (-item[1], item[0]))
                ],
                "ood": [
                    {"type": name, "count": count}
                    for name, count in sorted(ood_types[kind].items(), key=lambda item: (-item[1], item[0]))
                ],
                "sections": [{"name": name, "count": count} for name, count in sorted(sections[kind].items(), key=lambda item: (-item[1], item[0]))],
                "directories": [{"name": name, "count": count} for name, count in sorted(directories[kind].items(), key=lambda item: (-item[1], item[0]))],
                "resource_decisions": [{"name": name, "count": count} for name, count in sorted(resource_decisions[kind].items(), key=lambda item: (-item[1], item[0]))],
            }
            for kind in ("all", *kinds)
        },
    }


def optimize_distribution_stats(database: Path) -> dict[str, Any]:
    """Aggregate actual optimized skill changes from operation changelogs."""
    operation_kinds = ("create", "update", "delete", "merge", "split", "no_change")
    counters = {name: defaultdict(int) for name in ("operations", "skills", "sections", "directories")}
    by_operation: dict[str, dict[str, defaultdict[str, int]]] = defaultdict(
        lambda: {name: defaultdict(int) for name in ("skills", "sections", "directories")}
    )
    document_count = 0
    change_count = 0
    for path in sorted((database.parent / "runs").glob("*/run/*/ops/*/changelog.json")):
        try:
            document = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        document_count += 1
        for change in document.get("changes") or []:
            if not isinstance(change, dict):
                continue
            change_count += 1
            operation = str(change.get("operation") or "unknown")
            skill = str(change.get("skill") or "unknown")
            counters["operations"][operation] += 1
            counters["skills"][skill] += 1
            by_operation[operation]["skills"][skill] += 1
            for value in change.get("sections") or []:
                counters["sections"][str(value)] += 1
                by_operation[operation]["sections"][str(value)] += 1
            for value in change.get("directories") or []:
                directory = str(value).split("/", 1)[0]
                counters["directories"][directory] += 1
                by_operation[operation]["directories"][directory] += 1
    serialize = lambda values: [
        {"name": key, "count": count}
        for key, count in sorted(values.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "document_count": document_count,
        "change_count": change_count,
        **{
            name: serialize(values)
            for name, values in counters.items()
        },
        "operations": [
            {"name": operation, "count": counters["operations"][operation]}
            for operation in (*operation_kinds, *sorted(set(counters["operations"]) - set(operation_kinds)))
        ],
        "by_operation": {
            operation: {name: serialize(values) for name, values in groups.items()}
            for operation, groups in sorted(by_operation.items())
        },
    }


def diagnosis_distribution_stats(database: Path) -> dict[str, Any]:
    """Aggregate scoped diagnosis capability classifications across all runs."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    document_count = 0
    for path in sorted((database.parent / "runs").glob("*/run/*/diagnosis.json")):
        try:
            document = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        document_count += 1
        groups = (
            ("known", document.get("skill_capabilities_missing") or []),
            ("ood", document.get("newly_detected_skill_capabilites_missing") or document.get("newly_detected_skill_capabilities_missing") or []),
        )
        for classification, values in groups:
            for value in values:
                if not isinstance(value, dict):
                    continue
                capability = str(value.get("type") or value.get("skill_capability") or "unspecified")
                key = (classification, capability)
                row = rows.setdefault(key, {
                    "classification": classification,
                    "type": capability,
                    "category": capability.split("/", 1)[0] if "/" in capability else "uncategorized",
                    "count": 0,
                    "confidences": [],
                })
                row["count"] += 1
                confidence = value.get("confidence")
                if isinstance(confidence, (int, float)):
                    row["confidences"].append(float(confidence))
    distribution = []
    for row in rows.values():
        confidences = row.pop("confidences")
        distribution.append({
            **row,
            "mean_confidence": round(statistics.mean(confidences), 3) if confidences else None,
        })
    # Review in-distribution gaps before novel/OOD detections.
    distribution.sort(key=lambda row: (row["classification"] == "ood", -row["count"], row["type"]))
    categories: dict[tuple[str, str], int] = defaultdict(int)
    for row in distribution:
        categories[(row["classification"], row["category"])] += row["count"]
    return {
        "document_count": document_count,
        "known_count": sum(row["count"] for row in distribution if row["classification"] == "known"),
        "ood_count": sum(row["count"] for row in distribution if row["classification"] == "ood"),
        "distribution": distribution,
        "categories": [
            {"classification": classification, "category": category, "count": count}
            for (classification, category), count in sorted(categories.items(), key=lambda item: (item[0][0] == "ood", -item[1], item[0][1]))
        ],
    }


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def load_rows(database: Path) -> list[dict[str, Any]]:
    if not database.is_file():
        return []
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT * FROM pipeline_spans ORDER BY started_at_us"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(row) for row in rows]


def active_statuses(database: Path, run_id: str) -> list[dict[str, Any]]:
    """Return currently started items with a live elapsed duration."""
    root = database.parent / "runs" / run_id / "run/status"
    if not root.is_dir():
        return []
    now = datetime.now(UTC)
    active: list[dict[str, Any]] = []
    for path in root.glob("*/*.json"):
        try:
            row = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or row.get("state") != "started":
            continue
        raw_started = row.get("started_at") or row.get("at")
        try:
            started = datetime.fromisoformat(str(raw_started).replace("Z", "+00:00"))
        except ValueError:
            continue
        elapsed_seconds = max((now - started).total_seconds(), 0)
        if elapsed_seconds > _LIVE_STATUS_MAX_SECONDS:
            continue
        record = {
            "stage": row.get("stage"),
            "item": row.get("item"),
            "started_at": started.isoformat(),
            "elapsed_seconds": elapsed_seconds,
        }
        skills = row.get("skills")
        if isinstance(skills, list):
            names = [str(name) for name in skills if str(name).strip()]
            if names:
                record["skills"] = names
        active.append(record)
    return sorted(active, key=lambda row: row["started_at"])


def run_progress(
    database: Path, run_id: str, spans: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build a concise live checklist from runner-owned status records."""
    workspace = database.parent / "runs" / run_id
    status_root = workspace / "run/status"
    documents: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if status_root.is_dir():
        for path in status_root.glob("*/*.json"):
            try:
                row = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(row, dict) and isinstance(row.get("stage"), str):
                documents[row["stage"]].append(row)
    queue_phases = {
        "label-traces-cluster": "diagnosis-queue",
        "goal": "goal-queue",
        "optimize": "operation-queue",
    }
    display = [
        ("preprocessing", "Preprocessing"),
        ("label-skills", "LabelSkills"),
        ("label-traces-cluster", "Diagnosis"),
        ("goal", "Goal"),
        ("optimize", "Optimize"),
        ("verifiter", "Verifiter"),
        ("judge", "Judge"),
    ]
    goals = []
    for path in (workspace / "run").glob("*/evolve-goal.json"):
        try:
            value = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            goals.append(value)
    goal_done = bool(documents.get("goal")) and all(
        row.get("state") == "done" for row in documents["goal"]
    )
    operations_skipped = goal_done and bool(goals) and all(
        not ((value.get("action") or {}).get("ops") or []) for value in goals
    )
    now = datetime.now(UTC)
    stages: list[dict[str, Any]] = []
    for stage, label in display:
        rows = documents.get(stage, [])
        states = []
        for row in rows:
            value = row.get("state")
            if value == "started":
                raw = row.get("started_at") or row.get("at")
                try:
                    started = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                    if (now - started).total_seconds() > _LIVE_STATUS_MAX_SECONDS:
                        value = "stale"
                except ValueError:
                    value = "stale"
            states.append(value)
        if "failed" in states:
            state = "failed"
        elif "started" in states:
            state = "running"
        elif "stale" in states:
            state = "stale"
        elif rows and all(value == "done" for value in states):
            state = "done"
        elif operations_skipped and stage in {"optimize", "verifiter", "judge"}:
            state = "skipped"
        else:
            state = "pending"
        completed_ms = sum(
            float(row.get("duration_ms") or 0)
            for row in rows
            if row.get("state") == "done"
        )
        running_seconds = 0.0
        for row, effective_state in zip(rows, states):
            if effective_state != "started":
                continue
            raw = row.get("started_at") or row.get("at")
            try:
                started = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            running_seconds = max(running_seconds, (now - started).total_seconds())
        queue_phase = queue_phases.get(stage)
        queue_wait_ms = None
        if queue_phase:
            waits = []
            for span in spans:
                if span.get("phase") != queue_phase:
                    continue
                metadata = _METRICS._metadata(span)
                value = metadata.get("queue_wait_ms")
                if isinstance(value, (int, float)):
                    waits.append(float(value))
            if waits:
                queue_wait_ms = round(sum(waits), 3)
        stages.append(
            {
                "stage": stage,
                "label": label,
                "state": state,
                "duration_seconds": round(
                    running_seconds if state == "running" else completed_ms / 1000,
                    3,
                ),
                "items_done": sum(value == "done" for value in states),
                "items_total": len(rows),
                "queue_wait_ms": queue_wait_ms,
            }
        )
    findings = workspace / "traces/derived/findings"
    selected_findings = (
        sum(1 for path in findings.iterdir() if path.is_dir())
        if findings.is_dir()
        else 0
    )
    return {"selected_findings": selected_findings, "stages": stages}


def cluster_labels(
    database: Path, run_id: str, spans: list[dict[str, Any]]
) -> dict[str, str]:
    """Name each finding by its detector.

    Repeated detectors keep a short signature so those lanes stay distinct.
    """
    detectors: dict[str, str] = {}
    findings = database.parent / "runs" / run_id / "traces/derived/findings"
    if findings.is_dir():
        for path in sorted(findings.glob("*/finding.json")):
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            detector = data.get("detector")
            if isinstance(detector, str) and detector.strip():
                detectors[path.parent.name] = detector.strip()
    for span in spans:
        metadata = _METRICS._metadata(span)
        detector = metadata.get("detector")
        match = _SIG_RE.search(str(span.get("item") or ""))
        if (
            match
            and isinstance(detector, str)
            and detector.strip()
            and match.group(1) not in detectors
        ):
            detectors[match.group(1)] = detector.strip()
    counts: dict[str, int] = defaultdict(int)
    for detector in detectors.values():
        counts[detector] += 1
    labels: dict[str, str] = {}
    for sig, detector in detectors.items():
        short = sig[4:12]
        labels[sig] = detector if counts[detector] == 1 else f"{detector} · {short}"
    return labels


def operation_labels(
    database: Path, run_id: str, spans: list[dict[str, Any]]
) -> dict[str, Any]:
    """Name each operation by its skill and verb.

    Changelogs already written for this run supply create, update, and the
    other verbs. Span metadata fills an operation whose changelog is not on
    disk yet. A finding with no operation is labeled no change.
    """
    by_op: dict[str, str] = {}
    no_change: set[str] = set()
    for span in spans:
        item = str(span.get("item") or "")
        match = _SIG_RE.search(item)
        if not match:
            continue
        operation = span.get("operation")
        if not isinstance(operation, str) or not operation.strip():
            detail = span.get("detail")
            if isinstance(detail, dict):
                operation = detail.get("operation")
        conflicts = span.get("conflicts")
        if not isinstance(conflicts, list):
            detail = span.get("detail")
            conflicts = detail.get("conflicts") if isinstance(detail, dict) else None
        skills = [
            str(name)
            for name in conflicts or []
            if str(name).strip() and str(name) != "*"
        ]
        if not isinstance(operation, str) or not operation.strip() or not skills:
            continue
        op_match = re.search(r"-op-(\d+)", item)
        op_index = op_match.group(1) if op_match else "1"
        by_op.setdefault(
            f"{match.group(1)}:{op_index}",
            f"{', '.join(skills)} · {operation.strip()}",
        )
    root = database.parent / "runs" / run_id / "run"
    if root.is_dir():
        for path in sorted(root.glob("sig-*/ops/*/changelog.json")):
            label = _changelog_label(path)
            if not label:
                continue
            by_op[f"{path.parents[2].name}:{path.parent.name}"] = label
        for path in sorted(root.glob("sig-*/changelog.json")):
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and data.get("disposition") == "no_change":
                no_change.add(path.parent.name)
    grouped: dict[str, list[str]] = defaultdict(list)
    for key, label in by_op.items():
        sig, _sep, _op = key.rpartition(":")
        if label not in grouped[sig]:
            grouped[sig].append(label)
    by_sig = {sig: ", ".join(labels) for sig, labels in grouped.items()}
    for sig in no_change:
        by_sig.setdefault(sig, "no change")
    skills_by_op = {
        key: text
        for key, label in by_op.items()
        if (text := _skill_names_in_label(label))
    }
    skills_by_sig: dict[str, str] = {}
    for key, text in skills_by_op.items():
        sig = key.rpartition(":")[0]
        skills_by_sig[sig] = _join_skill_names(
            [*skills_by_sig.get(sig, "").split(", "), *text.split(", ")]
        )
    if root.is_dir():
        for path in sorted(root.glob("sig-*/evolve-goal.json")):
            names = _goal_file_skills(path)
            if names:
                skills_by_sig[path.parent.name] = ", ".join(names)
        for path in sorted(root.glob("sig-*/label-matching.json")):
            sig = path.parent.name
            if skills_by_sig.get(sig):
                continue
            names = _matching_file_skills(path)
            if names:
                skills_by_sig[sig] = ", ".join(names)
    return {
        "by_op": by_op,
        "by_sig": by_sig,
        "skills_by_op": skills_by_op,
        "skills_by_sig": skills_by_sig,
    }


def _join_skill_names(values: list[str]) -> str:
    names: list[str] = []
    for value in values:
        name = value.strip()
        if name and name not in names:
            names.append(name)
    return ", ".join(names)


def _skill_names_in_label(label: str) -> str:
    names: list[str] = []
    for part in label.split(","):
        name = part.split(" · ")[0].strip()
        if name and name != "no change" and name not in names:
            names.append(name)
    return ", ".join(names)


def _goal_file_skills(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    names: list[str] = []

    def add(value: object) -> None:
        if not isinstance(value, str):
            return
        name = value.strip()
        if name.startswith("<") and name.endswith(">") and len(name) > 2:
            name = name[1:-1].strip()
        if name and name not in names:
            names.append(name)

    goal = data.get("goal")
    if isinstance(goal, dict):
        improve = goal.get("improve_skills")
        if isinstance(improve, list):
            for item in improve:
                if isinstance(item, str):
                    add(item)
                elif isinstance(item, dict):
                    add(item.get("skill"))
    action = data.get("action")
    if isinstance(action, dict):
        for op in action.get("ops") or []:
            if not isinstance(op, dict):
                continue
            add(op.get("skill"))
            listed = op.get("skills")
            if isinstance(listed, list):
                for item in listed:
                    if isinstance(item, str):
                        add(item)
                    elif isinstance(item, dict):
                        add(item.get("skill"))
    return names


def _matching_file_skills(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    names: list[str] = []
    for cluster in data.get("clusters") or []:
        if not isinstance(cluster, dict):
            continue
        for row in cluster.get("skills") or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("skill") or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def _changelog_label(path: Path) -> str:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    parts: list[str] = []
    for change in data.get("changes") or []:
        if not isinstance(change, dict):
            continue
        skill = str(change.get("skill") or "").strip()
        operation = str(change.get("operation") or "").strip()
        if skill and operation:
            label = f"{skill} · {operation}"
        else:
            label = skill or operation
        if label and label not in parts:
            parts.append(label)
    return ", ".join(parts)


def assign_passes(
    spans: list[dict[str, Any]], active: list[dict[str, Any]]
) -> None:
    """Number each execution of the pipeline.

    A repeated trunk phase means the run was started again. Later spans,
    including a still-running goal, belong to that later pass.
    """
    events: list[tuple[str, dict[str, Any], str]] = []
    events.extend(
        (str(row.get("started_at") or ""), row, "phase") for row in spans
    )
    events.extend(
        (str(row.get("started_at") or ""), row, "stage") for row in active
    )
    events.sort(key=lambda item: item[0])
    number = 1
    seen: set[str] = set()
    for _started, row, key in events:
        phase = str(row.get(key) or "")
        if phase in _TRUNK:
            if phase in seen:
                number += 1
                seen.clear()
            seen.add(phase)
        row["pass"] = number


def execution_id(run_id: str, started_at: str) -> str:
    """Identity of one start, stable for the minute it began."""
    moment = datetime.fromisoformat(started_at.replace("Z", "+00:00")).astimezone()
    return f"{run_id}@{moment.strftime('%Y-%m-%dT%H:%M')}"


def failed_statuses(database: Path, run_id: str) -> dict[tuple[str, str], str]:
    """Map (stage, item) to the error that stopped that item."""
    root = database.parent / "runs" / run_id / "run/status"
    if not root.is_dir():
        return {}
    found: dict[tuple[str, str], str] = {}
    for path in root.glob("*/*.json"):
        try:
            row = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or row.get("state") != "failed":
            continue
        error = row.get("error")
        stage = row.get("stage")
        item = row.get("item")
        if isinstance(error, str) and error and isinstance(stage, str) and isinstance(item, str):
            found[(stage, item)] = error
    return found


def _short_error(error: str) -> str:
    text = " ".join(error.split())
    if "timed out after" in text:
        tail = text.rsplit("timed out after", 1)[-1].strip(" .")
        return f"timed out after {tail}" if tail else "timed out"
    if len(text) > 180:
        return text[:177] + "..."
    return text


def annotate_rejections(
    spans: list[dict[str, Any]], failures: dict[tuple[str, str], str]
) -> None:
    """Mark the latest span for an item whose status record failed.

    Earlier starts of the same item keep their own result. An optimize
    rejection means verification never started.
    """
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for span in spans:
        key = (str(span.get("phase")), str(span.get("item")))
        current = latest.get(key)
        if current is None or str(span.get("started_at") or "") >= str(
            current.get("started_at") or ""
        ):
            latest[key] = span
    for key, error in failures.items():
        span = latest.get(key)
        if span is None:
            continue
        span["status"] = "rejected"
        span["rejection"] = _short_error(error)
        if span.get("phase") == "optimize":
            span["rejection_label"] = "rejected before verification"


def _sig(item: str) -> str:
    marker = "sig-"
    start = item.find(marker)
    if start < 0:
        return ""
    token = []
    for char in item[start + len(marker) :]:
        if char not in "0123456789abcdef":
            break
        token.append(char)
    return marker + "".join(token) if token else ""


def _ending_headline(error: str, label: str = "") -> str:
    if label:
        return label
    text = error.lower()
    if "timed out" in text:
        return error if len(error) <= 48 else "timed out"
    if "parse" in text or "json" in text:
        return "parse error"
    if len(error) > 48:
        return error[:45] + "..."
    return error or "error"


def _stamp_ending(
    span: dict[str, Any], label: str, detail: str, *, bad: bool
) -> None:
    if span.get("ending_label"):
        return
    span["ending_label"] = label
    span["ending_detail"] = detail
    span["ending_bad"] = bad


def _chain_continues(
    span: dict[str, Any],
    spans: list[dict[str, Any]],
    active: list[dict[str, Any]],
) -> bool:
    """True when a later phase of this item is already running or recorded."""
    phase = str(span.get("phase") or "")
    sig = _sig(str(span.get("item") or ""))
    start = str(span.get("started_at") or "")

    def later(names: set[str]) -> bool:
        return any(
            row.get("phase") in names
            and _sig(str(row.get("item") or "")) == sig
            and str(row.get("started_at") or "") >= start
            for row in spans
        )

    def live(names: set[str]) -> bool:
        return any(
            str(row.get("stage") or "") in names
            and _sig(str(row.get("item") or "")) == sig
            for row in active
        )

    if phase == "label-traces-cluster":
        return later({"goal"}) or live({"goal"})
    if phase == "goal":
        return any(row.get("phase") == "reduce-goals" for row in spans)
    if phase == "optimize":
        return later({"verifiter"}) or live({"verifiter"})
    if phase == "verifiter":
        return later({"judge", "judge-decision"}) or live({"judge"})
    return False


def _inferred_timeout(duration_ms: float) -> str:
    """Name a session killed at the 180s or 360s verifier limit."""
    for limit in (180_000, 360_000):
        if limit - 1_000 <= duration_ms <= limit + 8_000:
            return f"timed out after {limit // 1000} seconds"
    return ""


def annotate_endings(
    spans: list[dict[str, Any]], active: list[dict[str, Any]]
) -> None:
    """Attach the reason a chain stopped, on the bar that actually ends it.

    A rejection, timeout, or parse failure is named on that span. A judge
    result is named on the last visible bar of the operation. A bar with no
    next phase, and nothing still running after it, is marked completed or
    stopped before verification.
    """
    for span in spans:
        rejection = str(span.get("rejection") or "")
        if not rejection and span.get("status") == "error":
            rejection = _inferred_timeout(float(span.get("duration_ms") or 0))
        if rejection or span.get("status") in {"rejected", "error"}:
            label = _ending_headline(
                rejection, str(span.get("rejection_label") or "")
            )
            if not label:
                label = "error" if span.get("status") == "error" else "rejected"
            _stamp_ending(span, label, rejection or label, bad=True)

    for span in spans:
        action = span.get("judge_action")
        if not action and span.get("phase") != "judge-decision":
            continue
        if not action:
            action = span.get("overall_status") or "ended"
        sig = _sig(str(span.get("item") or ""))
        skills = span.get("failed_skills") or []
        if isinstance(skills, str):
            skills = [skills]
        if not isinstance(skills, list):
            skills = []
        failed = [str(skill) for skill in skills if skill]
        if str(action) in {"fail", "failed"} and failed:
            label = "does not pass " + ", ".join(failed)
        elif str(action) in {"fail", "failed"}:
            label = "judge fail"
        else:
            label = f"judge {action}"
        detail = label
        if span.get("will_retry") is False:
            detail = f"{label} · will not retry"
        hosts = [
            row
            for row in spans
            if row.get("phase") in {"verifiter", "judge"}
            and _sig(str(row.get("item") or "")) == sig
        ]
        visible = [
            row for row in hosts if float(row.get("duration_ms") or 0) >= 800
        ]
        pool = visible or hosts or [span]
        host = max(pool, key=lambda row: str(row.get("started_at") or ""))
        bad = str(action) in {"fail", "failed"} or span.get("overall_status") in {
            "fail",
            "failed",
        }
        _stamp_ending(host, label, detail, bad=bad)

    for span in spans:
        phase = str(span.get("phase") or "")
        if phase not in {"label-traces-cluster", "goal", "optimize", "verifiter"}:
            continue
        if span.get("ending_label") or _chain_continues(span, spans, active):
            continue
        if phase == "optimize":
            _stamp_ending(
                span,
                "stopped before verification",
                "stopped before verification",
                bad=True,
            )
        else:
            _stamp_ending(
                span, "completed", str(span.get("status") or "completed"), bad=False
            )


def _phase_rows(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for span in spans:
        grouped[(str(span["phase"]), str(span["category"]))].append(span)
    rows: list[dict[str, Any]] = []
    for (phase, category), group in sorted(grouped.items()):
        durations = [float(span["duration_ms"]) / 1000 for span in group]
        ordered = sorted(durations)
        intervals = []
        for span in group:
            start = datetime.fromisoformat(str(span["started_at"]))
            intervals.append(
                (start.timestamp(), start.timestamp() + float(span["duration_ms"]) / 1000)
            )
        events: list[tuple[float, int]] = []
        for start, finish in intervals:
            events.append((start, 1))
            events.append((finish, -1))
        events.sort()
        current = peak = 0
        for _moment, delta in events:
            current += delta
            peak = max(peak, current)
        rows.append(
            {
                "phase": phase,
                "category": category,
                "count": len(group),
                "sum_seconds": round(sum(durations), 3),
                "wall_seconds": round(
                    max(max(finish for _, finish in intervals) - min(start for start, _ in intervals), 0),
                    3,
                ),
                "p50_seconds": round(ordered[len(ordered) // 2], 3),
                "max_seconds": round(max(durations), 3),
                "peak_concurrency": peak,
            }
        )
    return rows


def metrics_payload(database: Path) -> dict[str, Any]:
    rows = load_rows(database)
    runs_root = database.parent / "runs"
    active_by_run = {
        path.name: active
        for path in runs_root.iterdir()
        if path.is_dir() and (active := active_statuses(database, path.name))
    } if runs_root.is_dir() else {}
    excluded_run_ids = sorted(
        {
            str(row["run_id"])
            for row in rows
            if not (runs_root / str(row["run_id"])).is_dir()
        }
    )
    rows = [
        row
        for row in rows
        if (runs_root / str(row["run_id"])).is_dir()
    ]
    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    phases: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        runs[row["run_id"]].append(row)
        phases[(row["phase"], row["category"])].append(
            row["duration_us"] / 1_000_000
        )
    for run_id in active_by_run:
        runs.setdefault(run_id, [])

    def run_start(item: tuple[str, list[dict[str, Any]]]) -> float:
        run_id, spans = item
        if spans:
            return min(row["started_at_us"] for row in spans)
        return datetime.fromisoformat(
            active_by_run[run_id][0]["started_at"]
        ).timestamp() * 1_000_000

    run_summaries: list[dict[str, Any]] = []
    for run_id, spans in sorted(
        runs.items(),
        key=run_start,
        reverse=True,
    ):
        active = active_by_run.get(run_id, [])
        timing = _METRICS.summarize_spans(spans)
        assign_passes(timing["spans"], active)
        annotate_rejections(timing["spans"], failed_statuses(database, run_id))
        labels = cluster_labels(database, run_id, spans)
        operations = operation_labels(database, run_id, timing["spans"])
        progress = run_progress(database, run_id, spans)
        phase_metrics = _METRICS._read_json(
            runs_root / run_id / "logs/phase-metrics.json"
        )
        by_pass: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for span in timing["spans"]:
            by_pass[int(span["pass"])].append(span)
        active_by_pass: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in active:
            active_by_pass[int(row["pass"])].append(row)
        numbers = sorted(set(by_pass) | set(active_by_pass))
        if not numbers:
            continue
        latest = numbers[-1]
        single_start = len(numbers) == 1
        now_us = int(datetime.now(UTC).timestamp() * 1_000_000)
        for number in numbers:
            group = by_pass.get(number, [])
            group_active = active_by_pass.get(number, []) if number == latest else []
            annotate_endings(group, active_by_pass.get(number, []))
            if group:
                started_at = min(str(span["started_at"]) for span in group)
                start = min(
                    datetime.fromisoformat(str(span["started_at"])).timestamp()
                    for span in group
                )
                end = max(
                    datetime.fromisoformat(str(span["started_at"])).timestamp()
                    + float(span["duration_ms"]) / 1000
                    for span in group
                )
            else:
                started_at = group_active[0]["started_at"]
                start = datetime.fromisoformat(started_at).timestamp()
                end = start
            if group_active:
                end = max(end, now_us / 1_000_000)
            totals: dict[str, float] = defaultdict(float)
            for span in group:
                totals[str(span["category"])] += float(span["duration_ms"]) / 1000
            run_summaries.append(
                {
                    "run_id": run_id,
                    "execution_id": (
                        run_id if single_start else execution_id(run_id, started_at)
                    ),
                    "historical": number != latest,
                    "wall_seconds": max(end - start, 0),
                    "category_seconds": dict(sorted(totals.items())),
                    "span_count": len(group),
                    "error_count": sum(
                        span.get("status") not in {None, "ok"} for span in group
                    ),
                    "started_at": started_at,
                    "phases": _phase_rows(group),
                    "spans": group,
                    "active": group_active,
                    "cluster_labels": labels,
                    "operations": operations,
                    "progress": progress if number == latest else {
                        "selected_findings": progress["selected_findings"],
                        "stages": [],
                    },
                    "phase_metrics": phase_metrics,
                }
            )
    run_summaries.sort(key=lambda row: row["started_at"], reverse=True)
    phase_summaries = [
        {
            "phase": phase,
            "category": category,
            "count": len(values),
            "average_seconds": statistics.mean(values),
            "p50_seconds": percentile(values, 0.5),
            "p95_seconds": percentile(values, 0.95),
            "maximum_seconds": max(values),
        }
        for (phase, category), values in sorted(phases.items())
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "database": str(database),
        "run_count": len(run_summaries),
        "span_count": len(rows),
        "runs": run_summaries,
        "phases": phase_summaries,
        "phase_metrics": _METRICS.aggregate_phase_metrics(runs_root),
        "skill_stats": skill_inventory_stats(database),
        "goal_stats": goal_operation_stats(database),
        "diagnosis_stats": diagnosis_distribution_stats(database),
        "optimize_stats": optimize_distribution_stats(database),
        "excluded_database_run_ids": excluded_run_ids,
    }


def render(database: Path, output: Path) -> Path:
    rows = load_rows(database)
    runs_root = database.parent / "runs"
    rows = [
        row
        for row in rows
        if (runs_root / str(row["run_id"])).is_dir()
    ]
    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    phases: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        runs[row["run_id"]].append(row)
        phases[(row["phase"], row["category"])].append(
            row["duration_us"] / 1_000_000
        )

    run_cards: list[str] = []
    for run_id, spans in sorted(
        runs.items(),
        key=lambda item: min(row["started_at_us"] for row in item[1]),
        reverse=True,
    ):
        totals: dict[str, float] = defaultdict(float)
        for row in spans:
            totals[row["category"]] += row["duration_us"] / 1_000_000
        start = min(row["started_at_us"] for row in spans)
        end = max(row["started_at_us"] + row["duration_us"] for row in spans)
        wall = max((end - start) / 1_000_000, 0.001)
        bars = "".join(
            (
                f'<div class="bar {html.escape(category)}" '
                f'style="width:{min(seconds / max(sum(totals.values()), 0.001) * 100, 100):.2f}%">'
                f"{html.escape(category)} {seconds:.1f}s</div>"
            )
            for category, seconds in sorted(totals.items())
        )
        failures = sum(row["status"] != "ok" for row in spans)
        timing = _METRICS.summarize_spans(spans)
        phase_rows_run = "".join(
            "<tr>"
            f"<td>{html.escape(str(row['phase']))}</td>"
            f"<td>{row['count']}</td>"
            f"<td>{row['sum_seconds']:.3f}s</td>"
            f"<td>{row['wall_seconds']:.3f}s</td>"
            f"<td>{row['peak_concurrency']}</td>"
            f"<td>{row['p50_seconds']:.3f}s</td>"
            f"<td>{row['max_seconds']:.3f}s</td>"
            "</tr>"
            for row in timing["phases"]
        )
        span_rows_run = "".join(
            "<tr>"
            f"<td>{html.escape(str(row['phase']))}</td>"
            f"<td>{html.escape(str(row['item']))}</td>"
            f"<td>{row['duration_ms']:.1f}</td>"
            f"<td>{html.escape(str(row['queue_wait_ms']))}</td>"
            f"<td>{html.escape(str(row['slice_tokens']))}</td>"
            f"<td>{html.escape(str(row['slice_user_turns']))}</td>"
            f"<td>{html.escape(str(row['tool_events']))}</td>"
            f"<td>{html.escape(str(row['decision']))}</td>"
            f"<td>{html.escape(str(row['super_score']))}</td>"
            f"<td>{html.escape(str(row['judge_action']))}</td>"
            f"<td>{html.escape(str(row['status']))}</td>"
            "</tr>"
            for row in timing["spans"]
        )
        run_cards.append(
            f"""
            <section class="card">
              <h2>{html.escape(run_id)}</h2>
              <div class="stats">
                <span>wall <b>{wall:.1f}s</b></span>
                <span>agent sum <b>{totals.get("llm_agent", 0):.1f}s</b></span>
                <span>deterministic <b>{totals.get("deterministic", 0):.3f}s</b></span>
                <span>orchestration <b>{totals.get("orchestration", 0):.3f}s</b></span>
                <span>spans <b>{len(spans)}</b></span>
                <span>errors <b>{failures}</b></span>
              </div>
              <div class="bars">{bars}</div>
              <h3>Phase wall</h3>
              <table><thead><tr><th>Phase</th><th>Count</th><th>Sum</th>
              <th>Wall</th><th>Peak</th><th>P50</th><th>Max</th></tr></thead>
              <tbody>{phase_rows_run}</tbody></table>
              <h3>Spans</h3>
              <table><thead><tr><th>Phase</th><th>Item</th><th>ms</th>
              <th>Queue ms</th><th>Slice tokens</th><th>User turns</th>
              <th>Tool events</th><th>Decision</th><th>Super score</th>
              <th>Judge</th><th>Status</th></tr></thead>
              <tbody>{span_rows_run}</tbody></table>
            </section>
            """
        )

    phase_rows: list[str] = []
    for (phase, category), values in sorted(phases.items()):
        phase_rows.append(
            "<tr>"
            f"<td>{html.escape(phase)}</td>"
            f"<td>{html.escape(category)}</td>"
            f"<td>{len(values)}</td>"
            f"<td>{statistics.mean(values):.3f}s</td>"
            f"<td>{percentile(values, 0.5):.3f}s</td>"
            f"<td>{percentile(values, 0.95):.3f}s</td>"
            f"<td>{max(values):.3f}s</td>"
            "</tr>"
        )

    skills = skill_inventory_stats(database)
    domain_rows = "".join(
        f"<tr><td>{html.escape(row['domain'])}</td><td>Recognized domain</td>"
        f"<td>{row['skills']}</td><td>{row['weight']:.3f}</td><td>{row['mean_weight']:.3f}</td></tr>"
        for row in skills["domain_stats"]
    )
    ood_rows = "".join(
        f'<tr class="ood-row"><td>{html.escape(row["type"])}<span class="ood-tag">OOD</span></td>'
        f"<td>Unmatched taxonomy type</td><td>{row['skills']}</td><td>—</td><td>—</td></tr>"
        for row in skills["ood_stats"]
    )
    per_skill_rows_parts = []
    for row in skills["per_skill"]:
        if row["confidence_state"] == "legacy_default":
            confidence = '<span class="confidence uncalibrated">Legacy default</span>'
        elif row["confidence_state"] == "no_evidence":
            confidence = '<span class="confidence uncalibrated">No evidence</span>'
        elif isinstance(row["confidence"], (int, float)):
            level = "high" if row["confidence"] >= .9 else "medium" if row["confidence"] >= .75 else "low"
            confidence = f'<span class="confidence {level}">{row["confidence"]:.2f}</span>'
        else:
            confidence = "—"
        per_skill_rows_parts.append(
            "<tr>" f"<td>{html.escape(row['skill'])}</td>"
            f"<td>{html.escape(row['status'])}</td><td>{confidence}</td>"
            f"<td>{html.escape(row['evaluation_kind'].replace('_', ' '))}</td>"
            f"<td>{row['evidence_records']}</td><td>{row['distinct_sessions']}</td>"
            f"<td>{html.escape(', '.join(value['domain'] for value in row['domains'])) or '—'}</td>"
            f"<td>{html.escape(', '.join(row['ood'])) or '—'}</td></tr>"
        )
    per_skill_rows = "".join(per_skill_rows_parts)

    payload = {
        "database": str(database),
        "run_count": len(runs),
        "span_count": len(rows),
        "skill_stats": skills,
    }
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skill Evolver Pipeline Metrics</title>
<style>
:root {{ color-scheme: dark; font-family: ui-sans-serif, system-ui; }}
body {{ margin: 0; padding: 28px; background: #0b1020; color: #e7eaf0; }}
main {{ max-width: 1200px; margin: auto; }}
h1 {{ margin-bottom: 4px; }} .muted {{ color: #9aa4b8; }}
.card {{ background: #151c30; border: 1px solid #29334d; border-radius: 12px;
  padding: 18px; margin: 16px 0; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 18px; margin-bottom: 12px; }}
.tabs {{ display:flex; gap:8px; flex-wrap:wrap; margin:18px 0; }}
.tab {{ border:1px solid #36415f; background:#151c30; color:#cbd3e5;
  padding:9px 14px; border-radius:9px; cursor:pointer; }}
.tab.active {{ background:#7c5cff; border-color:#9a85ff; color:white; }}
.panel {{ display:none; }} .panel.active {{ display:block; }}
.bars {{ display: flex; overflow: hidden; border-radius: 7px; min-height: 32px; }}
.bar {{ min-width: 5px; padding: 7px; white-space: nowrap; overflow: hidden;
  box-sizing: border-box; font-size: 12px; }}
.llm_agent {{ background: #7c5cff; }} .deterministic {{ background: #19a974; }}
.orchestration {{ background: #ec9f05; }}
table {{ width: 100%; border-collapse: collapse; background: #151c30; }}
th, td {{ padding: 10px; border-bottom: 1px solid #29334d; text-align: left; }}
th {{ position: sticky; top: 0; background: #202943; }}
code {{ color: #9fd3ff; }}
.ood-row {{ background:#2b2118; }} .ood-row td:first-child {{ border-left:3px solid #e89b4a; }}
.ood-tag {{ display:inline-block; margin-left:7px; padding:2px 7px; border-radius:999px;
  font-size:11px; font-weight:700; color:#ffd6a3; background:#5a351d; vertical-align:middle; }}
.table-note {{ color:#9aa4b8; margin-top:-4px; }}
.confidence {{ display:inline-block; min-width:74px; padding:3px 8px; border-radius:999px; text-align:center; font-weight:700; }}
.confidence.high {{ color:#91ead8; background:#173f39; }}
.confidence.medium {{ color:#ffe09a; background:#493915; }}
.confidence.low {{ color:#ffc0c7; background:#47202a; }}
.confidence.uncalibrated {{ color:#b7c0d4; background:#29334d; font-weight:600; }}
.info-button {{ position:relative; display:inline-grid; place-items:center; width:18px; height:18px;
  margin-left:5px; padding:0; border:1px solid #7181a5; border-radius:50%; background:#25314c;
  color:#dbe7ff; font:bold 11px ui-sans-serif,system-ui; cursor:help; vertical-align:middle; }}
.info-button::after {{ content:attr(data-tooltip); position:absolute; z-index:20; left:50%; top:24px;
  width:290px; padding:9px 11px; border:1px solid #566585; border-radius:7px; background:#0c1222;
  color:#e7eaf0; font:12px/1.4 ui-sans-serif,system-ui; transform:translateX(-50%); opacity:0; pointer-events:none; }}
.info-button:hover::after,.info-button:focus::after {{ opacity:1; }}
</style>
</head>
<body><main>
<h1>Skill Evolver Pipeline Metrics</h1>
<p class="muted">{len(runs)} runs · {len(rows)} spans · <code>{html.escape(str(database))}</code></p>
<nav class="tabs" aria-label="Dashboard sections">
<button class="tab active" data-target="overview-panel">Overview</button>
<button class="tab" data-target="skills-panel">Stats</button>
<button class="tab" data-target="runs-panel">Runs ({len(runs)})</button>
</nav>
<section id="overview-panel" class="panel active"><section class="card">
<h2>Cross-run phase statistics</h2>
<table><thead><tr><th>Phase</th><th>Category</th><th>Count</th>
<th>Average</th><th>P50</th><th>P95</th><th>Maximum</th></tr></thead>
<tbody>{''.join(phase_rows)}</tbody></table>
</section></section>
<section id="skills-panel" class="panel"><section class="card">
<h2>Skill statistics</h2><div class="stats"><span>skills <b>{skills['total_skills']}</b></span>
<span>domains <b>{len(skills['domain_stats'])}</b></span><span>OOD types <b>{len(skills['ood_stats'])}</b></span></div>
<h3>Taxonomy coverage</h3>
<p class="table-note">Skill count is the number of assigned skills. OOD means unmatched by the current taxonomy.</p>
<table><thead><tr><th>Type</th><th>Classification</th><th>Skill count</th><th>Assignment weight sum
<button type="button" class="info-button" aria-label="Explain assignment weight sum"
data-tooltip="Raw sum of assignment weights for this type. It grows with inventory size and is not a probability, quality score, or directly comparable coverage metric.">!</button></th><th>Mean weight
<button type="button" class="info-button" aria-label="Explain mean assignment weight" data-tooltip="Assignment weight sum divided by assigned skill count. Use this to compare typical assignment strength across types.">!</button></th></tr></thead>
<tbody>{domain_rows}{ood_rows or '<tr class="ood-row"><td><span class="ood-tag">OOD</span></td><td>No unmatched types</td><td>0</td><td>—</td><td>—</td></tr>'}</tbody></table>
<h3>Per-skill stats</h3><p class="table-note">Confidence is shown only when backed by evidence. Legacy defaults and zero-evidence scores are suppressed.</p>
<table><thead><tr><th>Skill</th><th>Lifecycle</th><th>Confidence <button type="button" class="info-button" aria-label="Explain confidence" data-tooltip="Evaluation confidence, not probability of correctness. Color bands apply only to scores backed by evidence: high ≥ 0.90, medium ≥ 0.75, low &lt; 0.75. Legacy defaults and zero-evidence scores are suppressed.">!</button></th>
<th>Evaluation</th><th>Evidence</th><th>Sessions</th><th>Domains</th><th>OOD types</th></tr></thead><tbody>{per_skill_rows}</tbody></table>
</section></section>
<section id="runs-panel" class="panel">{''.join(run_cards) or '<p>No spans recorded.</p>'}</section>
<script type="application/json" id="dashboard-metadata">{html.escape(json.dumps(payload))}</script>
<script>
document.querySelectorAll('.tab').forEach(button => button.addEventListener('click', () => {{
  document.querySelectorAll('.tab').forEach(node => node.classList.toggle('active', node === button));
  document.querySelectorAll('.panel').forEach(node => node.classList.toggle('active', node.id === button.dataset.target));
}}));
</script>
</main></body></html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document)
    return output


def live_document(refresh_seconds: float) -> str:
    refresh_ms = max(250, round(refresh_seconds * 1000))
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skill Evolver Live Metrics</title>
<style>
:root {{ color-scheme: dark; font-family: ui-sans-serif, system-ui; }}
body {{ margin:0; padding:28px; background:#0b1020; color:#e7eaf0; overflow-x:hidden }}
main {{ max-width:1200px; margin:auto; min-width:0 }}
h1,h2,h3,.active-run {{ overflow-wrap:anywhere }}
.muted {{ color:#9aa4b8 }} .error {{ color:#ff8080 }}
.card {{ background:#151c30; border:1px solid #29334d; border-radius:12px;
padding:18px; margin:16px 0; }}
.stats {{ display:flex; flex-wrap:wrap; gap:18px; margin-bottom:12px; }}
.stats > span {{ min-width:0 }}
.bars {{ display:flex; overflow:hidden; border-radius:7px; min-height:32px; }}
.bar {{ min-width:5px; padding:7px; white-space:nowrap; overflow:hidden;
box-sizing:border-box; font-size:12px; }}
.llm_agent {{ background:#7c5cff }} .deterministic {{ background:#19a974 }}
.orchestration {{ background:#ec9f05 }}
table {{ width:100%; border-collapse:collapse; background:#151c30 }}
th,td {{ padding:10px; border-bottom:1px solid #29334d; text-align:left }}
th {{ background:#202943 }} code {{ color:#9fd3ff }}
.tabs {{ display:flex; gap:8px; flex-wrap:wrap; margin:18px 0 8px }}
.tab {{ border:1px solid #36415f; background:#151c30; color:#cbd3e5;
padding:9px 14px; border-radius:9px; cursor:pointer }}
.tab.active {{ background:#7c5cff; border-color:#9a85ff; color:white }}
.panel {{ display:none }} .panel.active {{ display:block }}
.run-browser {{ margin:16px 0; padding:14px; border:1px solid #29334d; border-radius:10px; background:#10172a }}
.run-filters {{ display:grid; grid-template-columns:minmax(220px,1fr) 180px; gap:10px; margin-bottom:12px }}
.run-filters input,.run-filters select {{ padding:10px 12px; border-radius:8px; background:#151c30;
color:#e7eaf0; border:1px solid #36415f; box-sizing:border-box; width:100% }}
.run-results {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:8px; max-height:330px; overflow:auto }}
.run-option {{ text-align:left; padding:10px; border-radius:8px; background:#151c30; color:#dce3f2;
border:1px solid #303b58; cursor:pointer; min-width:0 }}
.run-option:hover,.run-option.selected {{ border-color:#9a85ff; background:#202943 }}
.run-option strong {{ display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap }}
.run-meta {{ display:flex; gap:6px; margin-top:6px; color:#9aa4b8; font-size:11px }}
.badge {{ padding:2px 6px; border-radius:999px; background:#29334d }} .badge.live {{ color:#95eadb; background:#16433a }}
.badge.error {{ color:#ffc0c7; background:#47202a }}
.ood-row {{ background:#2b2118 }} .ood-row td:first-child {{ border-left:3px solid #e89b4a }}
.ood-tag {{ display:inline-block; margin-left:7px; padding:2px 7px; border-radius:999px;
font-size:11px; font-weight:700; color:#ffd6a3; background:#5a351d; vertical-align:middle }}
.table-note {{ color:#9aa4b8; margin-top:-4px }}
.confidence {{ display:inline-block; min-width:74px; padding:3px 8px; border-radius:999px; text-align:center; font-weight:700 }}
.confidence.high {{ color:#91ead8; background:#173f39 }}
.confidence.medium {{ color:#ffe09a; background:#493915 }}
.confidence.low {{ color:#ffc0c7; background:#47202a }}
.confidence.uncalibrated {{ color:#b7c0d4; background:#29334d; font-weight:600 }}
.info-button {{ position:relative; display:inline-grid; place-items:center; width:18px; height:18px;
margin-left:5px; padding:0; border:1px solid #7181a5; border-radius:50%; background:#25314c;
color:#dbe7ff; font:bold 11px ui-sans-serif,system-ui; cursor:help; vertical-align:middle }}
.info-button::after {{ content:attr(data-tooltip); position:absolute; z-index:20; left:50%; top:24px;
width:290px; padding:9px 11px; border:1px solid #566585; border-radius:7px; background:#0c1222;
color:#e7eaf0; font:12px/1.4 ui-sans-serif,system-ui; box-shadow:0 8px 24px #0008;
transform:translateX(-50%); opacity:0; pointer-events:none; transition:opacity .12s }}
.info-button:hover::after,.info-button:focus::after {{ opacity:1 }}
.audit-phase {{ margin:18px 0; border:1px solid #29334d; border-radius:9px; overflow:hidden }}
.audit-phase summary {{ padding:11px 13px; background:#202943; font-weight:700; cursor:pointer }}
.audit-phase summary span {{ color:#9aa4b8; font-weight:400; font-size:12px; margin-left:8px }}
.phase-nav {{ display:flex; flex-wrap:wrap; gap:7px; margin:12px 0 }}
.phase-nav button {{ padding:7px 10px; border:1px solid #36415f; border-radius:999px;
background:#151c30; color:#cbd3e5; cursor:pointer }}
.phase-nav button:hover {{ border-color:#9a85ff; background:#202943 }}
.json-link {{ color:#9fd3ff; text-decoration:none }} .json-link:hover {{ text-decoration:underline }}
.json-keys {{ max-width:360px; color:#aeb8cc; font:12px ui-monospace,monospace }}
.run-pages {{ display:flex; justify-content:center; align-items:center; gap:12px; margin-top:12px; color:#9aa4b8 }}
.run-pages button {{ padding:7px 11px; border-radius:7px; border:1px solid #36415f; background:#151c30; color:#dce3f2; cursor:pointer }}
.run-pages button:disabled {{ opacity:.4; cursor:not-allowed }}
.phase-flow {{ display:flex; gap:6px; overflow-x:auto; padding:10px 2px 12px; margin:8px 0; scrollbar-width:thin }}
.phase-flow button {{ flex:0 0 auto; border:1px solid #36415f; background:#10172a; color:#b9c3d8; padding:8px 10px; border-radius:8px; cursor:pointer; text-align:left }}
.phase-flow button::after {{ content:'→'; margin-left:8px; color:#65708a }}
.phase-flow button:last-child::after {{ content:''; margin:0 }}
.phase-flow button.active {{ color:white; background:#5140a8; border-color:#9a85ff }}
.phase-flow small {{ display:block; color:#8f9ab2; margin-top:2px }}
.goal-analysis {{ margin:16px 0 22px; padding:14px; border:1px solid #394462; border-radius:10px; background:#10172a }}
.operation-flow {{ display:flex; flex-wrap:wrap; gap:7px; margin:10px 0 16px }}
.operation-flow button {{ border:1px solid #46516e; background:#182139; color:#cbd3e5; padding:8px 11px; border-radius:8px; cursor:pointer }}
.operation-flow button.active {{ background:#167d68; border-color:#4dc6aa; color:white }}
.operation-filter {{ position:sticky; top:8px; z-index:8; display:flex; align-items:center; gap:10px;
background:#11192c; border:1px solid #35415e; border-radius:10px; padding:10px 12px; margin:12px 0 16px }}
.operation-filter label {{ font-weight:700; white-space:nowrap }}
.operation-filter select {{ min-width:180px; background:#182139; color:#f4f7ff; border:1px solid #52617f;
border-radius:7px; padding:8px 32px 8px 10px; font:inherit }}
.analysis-grid {{ display:grid; grid-template-columns:minmax(0,2fr) minmax(260px,1fr); gap:14px }}
.analysis-grid table {{ font-size:13px }}
.expandable-rows tr.after-top-ten,.expandable-rows tr.after-id-top-ten,.expandable-rows tr.after-ood-top-ten {{ display:none }}
.expandable-rows.expand-all tr.after-top-ten,.expandable-rows.expand-id tr.after-id-top-ten,.expandable-rows.expand-ood tr.after-ood-top-ten {{ display:table-row }}
.table-expander {{ margin:9px 0 2px; padding:7px 11px; border:1px solid #9aabc1; border-radius:7px;
background:#fff; color:#29466e; font:inherit; font-weight:700; cursor:pointer }}
.table-expander:hover {{ background:#edf3fb }}
@media (max-width:800px) {{ .analysis-grid {{ grid-template-columns:1fr }} }}
@media (max-width:700px) {{ .run-filters {{ grid-template-columns:1fr }} }}
.active-run {{ margin:12px 0; padding:12px; border-radius:8px;
background:#112d29; border:1px solid #1d7668; color:#95eadb; max-width:100%; box-sizing:border-box }}
.progress {{ margin:14px 0; padding:14px; border-radius:10px; background:#10172a }}
.progress-grid {{ display:grid; grid-template-columns:minmax(150px,1fr) 110px 110px 130px;
gap:7px 16px; align-items:center }}
.state {{ font-weight:700 }} .state.done {{ color:#62d8a8 }}
.state.running {{ color:#f4c15d }} .state.failed {{ color:#ff8080 }}
.state.pending,.state.skipped {{ color:#8f9ab0 }}
.state.stale {{ color:#b45309 }}
.trace-tools {{ position:relative; z-index:6; display:flex; justify-content:space-between; align-items:center; gap:12px;
padding:8px 12px; background:#10182c }}
.trace-expand {{ border:1px solid #36415f; background:#151c30; color:#cbd3e5;
padding:7px 12px; border-radius:8px; cursor:pointer }}
.trace-shell {{ margin:18px 0; border:1px solid #29334d; border-radius:10px;
overflow:auto; max-height:640px; background:#0c1222; cursor:grab }}
.trace-shell .trace-tools {{ position:sticky; top:0; border-bottom:1px solid #29334d }}
.trace-shell.dragging {{ cursor:grabbing; user-select:none }}
.trace-shell.expanded {{ position:fixed; inset:20px; z-index:30; max-height:none;
margin:0; box-shadow:0 0 0 100vmax #070b16cc }}
.trace-view {{ position:relative; width:max-content; min-width:100%; padding:8px 0 12px }}
.trace-ruler,.trace-row {{ display:grid; grid-template-columns:280px var(--timeline, 860px);
align-items:stretch }}
.trace-label {{ position:sticky; left:0; z-index:4; overflow:hidden; padding:6px 10px;
background:#0c1222; color:#aeb8cc; font:12px ui-monospace,monospace;
white-space:nowrap; text-overflow:ellipsis }}
.trace-group {{ padding:8px 10px 2px; color:#d7deef; font-size:12px; font-weight:700 }}
.trace-track {{ position:relative; min-height:74px;
background:repeating-linear-gradient(90deg,#243049 0,#243049 1px,transparent 1px,transparent 20%) }}
.trace-time {{ position:absolute; top:1px; color:#9eb0cc; font:10px ui-monospace,monospace;
white-space:nowrap; pointer-events:none; z-index:3 }}
.trace-ticks {{ position:relative; height:22px; color:#8390aa;
font:11px ui-monospace,monospace }}
.trace-tick {{ position:absolute; transform:translateX(-50%); white-space:nowrap }}
.trace-tick:first-child {{ transform:none }}
.trace-tick:last-child {{ transform:translateX(-100%) }}
.trace-block {{ position:absolute; height:22px; min-width:2px; border-radius:5px;
overflow:hidden; padding:1px 5px; box-sizing:border-box; color:white;
font:11px ui-monospace,monospace; white-space:nowrap; z-index:1;
box-shadow:0 0 0 1px #ffffff18 }}
.trace-block.llm_agent {{ background:#7055de }} .trace-block.deterministic {{ background:#15855c }}
.trace-block.orchestration {{ background:#bb7900 }} .trace-block.audit {{ background:#3f8db8 }}
.trace-block.fanout-parent {{ box-shadow:0 0 0 2px #ff8a3d,0 0 10px #ff8a3d66 }}
.trace-block.fanout-parent::after {{ content:''; position:absolute; right:1px; top:8px;
width:6px; height:6px; border-radius:50%; background:#ffd0ad }}
.trace-block.instant {{ width:9px; min-width:9px; height:9px; padding:0; border-radius:1px;
transform:rotate(45deg); transform-origin:center }}
.trace-block.live {{ background:#d39422; box-shadow:0 0 8px #f4c15d;
background-image:linear-gradient(110deg,transparent 25%,#f4c15d88 45%,transparent 65%);
background-size:200% 100%; animation:trace-pulse 1.4s linear infinite }}
.trace-ghost {{ position:absolute; height:22px; box-sizing:border-box; border:1px dashed #d7deef;
border-radius:5px; color:#d7deef; background:#0c1222; padding:1px 6px;
font:11px ui-monospace,monospace; white-space:nowrap; overflow:hidden; z-index:0 }}
.trace-skill {{ position:absolute; height:16px; color:#f4f7ff;
font:11px ui-monospace,monospace; white-space:nowrap; pointer-events:none;
z-index:4; text-shadow:0 0 4px #0c1222, 0 1px 0 #0c1222 }}
.trace-legend .name {{ height:0; border-top:1px dashed #d7deef; background:transparent }}
.trace-end {{ position:absolute; height:22px; padding:1px 7px; border-radius:5px;
box-sizing:border-box; font:11px ui-monospace,monospace; white-space:nowrap; z-index:5 }}
.trace-end.bad {{ color:#ffd5db; background:#3a1d2a; border:1px solid #ff6b7a }}
.trace-end.ok {{ color:#c8f5e2; background:#12352c; border:1px solid #3dcea0 }}
.trace-arrows {{ position:absolute; inset:0; width:100%; height:100%;
pointer-events:none; z-index:2; overflow:visible }}
.trace-legend {{ display:flex; gap:16px; color:#9aa4b8; font-size:12px; margin:0 0 8px }}
.trace-legend i {{ display:inline-block; width:28px; height:4px; margin-right:6px; vertical-align:middle; border-radius:2px }}
.trace-legend .chain {{ background:#f4f7ff }} .trace-legend .fanout {{ background:#ff8a3d }}
.trace-legend .merge {{ background:#3dffa8 }}
@keyframes trace-pulse {{ to {{ background-position:-200% 0 }} }}
/* Light slate theme: calm neutral surfaces with blue/teal status accents. */
:root {{ color-scheme:light }}
body {{ background:#eef2f7; color:#172033 }}
.muted,.table-note,.run-pages,.run-meta {{ color:#64748b }}
.card,table {{ background:#ffffff }}
.card {{ border-color:#d8e0eb; box-shadow:0 5px 18px #2538580d }}
th {{ background:#e8eef7; color:#1e293b }}
th,td {{ border-bottom-color:#dce3ed }}
code,.json-link {{ color:#1769a6 }}
.tab {{ background:#fff; color:#334155; border-color:#c7d1df }}
.tab:hover {{ background:#edf3fb; border-color:#91a4c0 }}
.tab.active {{ background:#3867c8; border-color:#3867c8; color:#fff }}
.run-browser,.goal-analysis,.progress {{ background:#f7f9fc; border-color:#d5deea }}
.run-filters input,.run-filters select,.run-option {{ background:#fff; color:#243044; border-color:#cbd5e1 }}
.run-option:hover,.run-option.selected {{ background:#eaf1fb; border-color:#6387bd }}
.badge {{ background:#e4eaf3; color:#334155 }}
.badge.live {{ background:#d8f3eb; color:#136b59 }}
.badge.error {{ background:#fee2e2; color:#a72836 }}
.ood-row {{ background:#fff4e6 }} .ood-tag {{ background:#f7d7ae; color:#8a4814 }}
.confidence.high {{ color:#12624f; background:#d8f3eb }}
.confidence.medium {{ color:#7a5200; background:#fff0bf }}
.confidence.low {{ color:#9f2634; background:#fee2e2 }}
.confidence.uncalibrated {{ color:#526174; background:#e4eaf3 }}
.info-button {{ background:#e8eef7; color:#31476a; border-color:#8093b0 }}
.info-button::after {{ background:#26354d; color:#f8fafc; border-color:#526987; box-shadow:0 8px 24px #33415533 }}
.audit-phase {{ border-color:#d5deea }} .audit-phase summary {{ background:#e8eef7 }}
.audit-phase summary span,.phase-flow small,.json-keys {{ color:#64748b }}
.phase-nav button,.run-pages button,.operation-flow button,.trace-expand {{ background:#fff; color:#334155; border-color:#c7d1df }}
.phase-nav button:hover,.operation-flow button:hover {{ background:#edf3fb; border-color:#7d97bd }}
.phase-flow button {{ background:#f5f8fc; color:#42526a; border-color:#cbd5e1 }}
.phase-flow button.active {{ background:#3867c8; border-color:#3867c8; color:#fff }}
.operation-flow button.active {{ background:#16806a; border-color:#16806a; color:#fff }}
.operation-filter {{ background:#edf3f8; border-color:#cbd6e3; box-shadow:0 3px 12px #33415514 }}
.operation-filter select {{ background:#fff; color:#1e293b; border-color:#9aabc1 }}
.active-run {{ background:#e0f5ef; border-color:#6bc0aa; color:#12624f }}
.state.done {{ color:#14745b }} .state.running {{ color:#9a6100 }} .state.failed {{ color:#b52d3d }}
.state.pending,.state.skipped {{ color:#718096 }}
.trace-shell,.trace-label,.trace-ghost {{ background:#f8fafc }}
.trace-shell,.trace-shell .trace-tools {{ border-color:#d4dde8 }}
.trace-tools {{ background:#edf2f7 }}
.trace-label {{ color:#526174 }} .trace-group {{ color:#334155 }}
.trace-track {{ background:repeating-linear-gradient(90deg,#d9e2ed 0,#d9e2ed 1px,transparent 1px,transparent 20%) }}
.trace-time,.trace-ticks,.trace-legend {{ color:#64748b }}
.trace-ghost {{ color:#475569; border-color:#8493a8 }}
.trace-skill {{ color:#172033; text-shadow:0 0 4px #fff,0 1px 0 #fff }}
.trace-end.bad {{ color:#9f2634; background:#fee2e2; border-color:#e56b78 }}
.trace-end.ok {{ color:#12624f; background:#d8f3eb; border-color:#43a98e }}
.trace-shell.expanded {{ box-shadow:0 0 0 100vmax #d9e1eccf }}
@media (max-width:700px) {{ .progress-grid {{ grid-template-columns:1fr 90px }} }}
</style></head><body><main>
<h1>Skill Evolver Live Metrics</h1>
<p id="status" class="muted">Connecting…</p>
<nav id="tabs" class="tabs"></nav>
<div id="panels"></div>
<script>
const esc = value => String(value).replace(/[&<>"']/g, c =>
  ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);
const sec = value => `${{Number(value).toFixed(3)}}s`;
let compactTableSequence = 0;
let compactTablesScheduled = false;
const compactLongTables = (root=document) => {{
  root.querySelectorAll('table tbody').forEach(body => {{
    if (body.classList.contains('expandable-rows') || body.dataset.autoCompacted === 'true') return;
    const rows = [...body.children].filter(row => row.tagName === 'TR');
    if (rows.length <= 10) return;
    body.dataset.autoCompacted = 'true';
    body.classList.add('expandable-rows');
    if (!body.id) body.id = `compact-table-${{++compactTableSequence}}`;
    rows.slice(10).forEach(row => row.classList.add('after-top-ten'));
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'table-expander';
    button.dataset.expandRows = body.id;
    button.dataset.expandClass = 'all';
    button.dataset.label = 'rows';
    button.dataset.total = String(rows.length);
    button.setAttribute('aria-expanded','false');
    button.textContent = `Show all ${{rows.length}} rows`;
    body.closest('table').insertAdjacentElement('afterend',button);
  }});
}};
const compactTableObserver = new MutationObserver(() => {{
  if (compactTablesScheduled) return;
  compactTablesScheduled = true;
  requestAnimationFrame(() => {{
    compactTablesScheduled = false;
    compactLongTables();
  }});
}});
compactTableObserver.observe(document.getElementById('panels'), {{childList:true,subtree:true}});
const VIEW_STORAGE_KEY = 'skill-evolver-dashboard-view-v2';
const readView = () => {{
  try {{
    const data = JSON.parse(window.localStorage.getItem(VIEW_STORAGE_KEY) || '{{}}');
    return data && typeof data === 'object' ? data : {{}};
  }} catch (error) {{
    return {{}};
  }}
}};
const savedView = readView();
let selectedTab = ['total','skills','runs'].includes(savedView.tab) ? savedView.tab : 'total';
let selectedRunId = typeof savedView.run === 'string' ? savedView.run : '';
let runQuery = typeof savedView.query === 'string' ? savedView.query : '';
let runDay = typeof savedView.day === 'string' ? savedView.day : 'all';
let runPage = Number.isInteger(savedView.runPage) && savedView.runPage > 0 ? savedView.runPage : 1;
const RUNS_PER_PAGE = 12;
let auditPhasePage = Number.isInteger(savedView.phasePage) && savedView.phasePage >= 0 ? savedView.phasePage : 0;
let selectedGoalOperation = typeof savedView.goalOperation === 'string' ? savedView.goalOperation : 'create';
let selectedOptimizeOperation = typeof savedView.optimizeOperation === 'string' ? savedView.optimizeOperation : 'all';
let latestGoalStats = null;
let latestDiagnosisStats = null;
let latestOptimizeStats = null;
let renderedSignature = '';
const phaseAuditCache = new Map();
let expandedRun = savedView.expanded === true && selectedRunId ? selectedRunId : '';
let restoreScrollY = Number.isFinite(savedView.scrollY) ? Math.max(0, savedView.scrollY) : null;
const writeView = () => {{
  const run = expandedRun || selectedRunId;
  try {{
    window.localStorage.setItem(VIEW_STORAGE_KEY, JSON.stringify({{
      tab:selectedTab, run, expanded:Boolean(expandedRun), phasePage:auditPhasePage,
      goalOperation:selectedGoalOperation, optimizeOperation:selectedOptimizeOperation,
      query:runQuery, day:runDay, runPage,
      scrollY:Math.round(window.scrollY)
    }}));
  }} catch (error) {{ /* Storage can be disabled without breaking the dashboard. */ }}
}};
window.addEventListener('beforeunload', writeView);
const traceScroll = new Map();
let traceDrag = null;
let runPickerOpen = false;
document.addEventListener('pointerdown', event => {{
  if (event.target.closest('[data-run-picker]')) runPickerOpen = true;
}});
document.addEventListener('focusin', event => {{
  if (event.target.matches('[data-run-picker]')) runPickerOpen = true;
}});
document.addEventListener('focusout', event => {{
  if (event.target.matches('[data-run-picker]')) runPickerOpen = false;
}});
document.addEventListener('click', event => {{
  const choice = event.target.closest('[data-run-choice]');
  if (!choice) return;
  selectedRunId = choice.dataset.runChoice;
  auditPhasePage = 0;
  runPickerOpen = false;
  writeView();
  refresh();
}});
document.addEventListener('change', event => {{
  const select = event.target.closest('[data-goal-operation-select],[data-optimize-operation-select]');
  if (!select) return;
  if (select.matches('[data-goal-operation-select]')) selectedGoalOperation = select.value;
  else selectedOptimizeOperation = select.value;
  writeView();
  const audit = phaseAuditCache.get(select.dataset.runId);
  if (!audit) return;
  document.querySelectorAll(`[data-phase-audit][data-run-id="${{CSS.escape(select.dataset.runId)}}"]`)
    .forEach(target => {{ target.innerHTML = renderPhaseAudit(audit); compactLongTables(target); }});
}});
document.addEventListener('click', event => {{
  const button = event.target.closest('[data-expand-rows]');
  if (!button) return;
  const body = document.getElementById(button.dataset.expandRows);
  if (!body) return;
  const classification = button.dataset.expandClass;
  const expanded = body.classList.toggle(`expand-${{classification}}`);
  const label = button.dataset.label || classification.toUpperCase();
  button.textContent = expanded ? `Show top 10${{label ? ` ${{label}}` : ''}}` : `Show all ${{button.dataset.total}}${{label ? ` ${{label}}` : ''}}`;
  button.setAttribute('aria-expanded', String(expanded));
}});
document.addEventListener('click', event => {{
  const button = event.target.closest('[data-audit-page],[data-audit-index]');
  if (!button) return;
  const audit = phaseAuditCache.get(button.dataset.runId);
  if (!audit) return;
  auditPhasePage = button.dataset.auditIndex == null
    ? auditPhasePage + (button.dataset.auditPage === 'next' ? 1 : -1)
    : Number(button.dataset.auditIndex);
  writeView();
  document.querySelectorAll(`[data-phase-audit][data-run-id="${{CSS.escape(button.dataset.runId)}}"]`)
    .forEach(target => {{ target.innerHTML = renderPhaseAudit(audit); compactLongTables(target); }});
}});
document.addEventListener('click', event => {{
  const button = event.target.closest('[data-goal-operation]');
  if (!button) return;
  selectedGoalOperation = button.dataset.goalOperation;
  writeView();
  const audit = phaseAuditCache.get(button.dataset.runId);
  if (!audit) return;
  document.querySelectorAll(`[data-phase-audit][data-run-id="${{CSS.escape(button.dataset.runId)}}"]`)
    .forEach(target => {{ target.innerHTML = renderPhaseAudit(audit); compactLongTables(target); }});
}});
document.addEventListener('pointerdown', event => {{
  const shell = event.target.closest('.trace-shell');
  if (!shell || event.button !== 0 || event.target.closest('button, a')) return;
  const bounds = shell.getBoundingClientRect();
  if (event.clientX > bounds.left + shell.clientWidth) return;
  if (event.clientY > bounds.top + shell.clientHeight) return;
  traceDrag = {{
    shell, x: event.clientX, left: shell.scrollLeft, id: event.pointerId
  }};
  shell.classList.add('dragging');
  shell.setPointerCapture(event.pointerId);
}});
document.addEventListener('pointermove', event => {{
  if (!traceDrag || event.pointerId !== traceDrag.id) return;
  if (!traceDrag.shell.isConnected) {{ traceDrag = null; return; }}
  traceDrag.shell.scrollLeft = traceDrag.left - (event.clientX - traceDrag.x);
}});
const endTraceDrag = event => {{
  if (!traceDrag || event.pointerId !== traceDrag.id) return;
  traceDrag.shell.classList.remove('dragging');
  traceScroll.set(traceDrag.shell.dataset.run, traceDrag.shell.scrollLeft);
  traceDrag = null;
}};
document.addEventListener('pointerup', endTraceDrag);
document.addEventListener('pointercancel', endTraceDrag);
const applyExpandedTrace = () => {{
  document.querySelectorAll('.trace-shell').forEach(shell =>
    shell.classList.toggle('expanded', shell.dataset.run === expandedRun));
  document.querySelectorAll('[data-trace-expand]').forEach(button => {{
    button.textContent = button.dataset.traceExpand === expandedRun ? 'Close' : 'Expand';
  }});
}};
document.addEventListener('click', event => {{
  const button = event.target.closest('[data-trace-expand]');
  if (!button) return;
  expandedRun = expandedRun === button.dataset.traceExpand ? '' : button.dataset.traceExpand;
  if (expandedRun) selectedTab = 'runs';
  writeView();
  applyExpandedTrace();
  tickTraces();
}});
const selectTab = id => {{
  selectedTab = id;
  document.querySelectorAll('.tab').forEach(node =>
    node.classList.toggle('active', node.dataset.tab === id));
  document.querySelectorAll('.panel').forEach(node =>
    node.classList.toggle('active', node.dataset.panel === id));
  writeView();
  if (typeof tickTraces === 'function') tickTraces();
}};
const phaseTable = rows =>
  `<table><thead><tr><th>Phase</th><th>Category</th><th>Count</th>`+
  `<th>Average</th><th>P50</th><th>P95</th><th>Maximum</th></tr></thead><tbody>`+
  rows.map(row =>
    `<tr><td>${{esc(row.phase)}}</td><td>${{esc(row.category)}}</td><td>${{row.count}}</td>`+
    `<td>${{sec(row.average_seconds)}}</td><td>${{sec(row.p50_seconds)}}</td>`+
    `<td>${{sec(row.p95_seconds)}}</td><td>${{sec(row.maximum_seconds)}}</td></tr>`
  ).join('')+`</tbody></table>`;
const skillStatsPanel = stats => {{
  if (!stats || !stats.total_skills) return `<section class="card"><h2>Skill statistics</h2><p class="muted">No skill metadata.</p></section>`;
  const domains = stats.domain_stats.map(row => `<tr><td>${{esc(row.domain)}}</td><td>Recognized domain</td><td>${{row.skills}}</td><td>${{row.weight}}</td><td>${{row.mean_weight}}</td></tr>`).join('');
  const ood = stats.ood_stats.map(row => `<tr class="ood-row"><td>${{esc(row.type)}}<span class="ood-tag">OOD</span></td>`+
    `<td>Unmatched taxonomy type</td><td>${{row.skills}}</td><td>—</td><td>—</td></tr>`).join('');
  const skills = stats.per_skill.map(row => `<tr><td>${{esc(row.skill)}}</td><td>${{esc(row.status)}}</td>`+
    `<td>${{row.confidence_state === 'legacy_default' ? '<span class="confidence uncalibrated">Legacy default</span>' : row.confidence_state === 'no_evidence' ? '<span class="confidence uncalibrated">No evidence</span>' : row.confidence == null ? '—' : `<span class="confidence ${{Number(row.confidence) >= .9 ? 'high' : Number(row.confidence) >= .75 ? 'medium' : 'low'}}">${{Number(row.confidence).toFixed(2)}}</span>`}}</td>`+
    `<td>${{esc(String(row.evaluation_kind || 'unknown').replaceAll('_', ' '))}}</td><td>${{row.evidence_records}}</td><td>${{row.distinct_sessions}}</td>`+
    `<td>${{row.domains.map(value => esc(value.domain)).join(', ') || '—'}}</td>`+
    `<td>${{row.ood.map(value => `<span class="ood-tag">${{esc(value)}}</span>`).join('') || '—'}}</td></tr>`).join('');
  return `<section class="card"><h2>Skill statistics</h2><h3>Taxonomy coverage</h3>`+
    `<p class="table-note">Skill count is the number of skills assigned to a type. OOD means the type did not match the current taxonomy.</p>`+
    `<table><thead><tr><th>Type</th><th>Classification</th><th>Skill count</th><th>Assignment weight sum `+
    `<button type="button" class="info-button" aria-label="Explain assignment weight sum" data-tooltip="Raw sum of assignment weights for this type. It grows with inventory size and is not a probability, quality score, or directly comparable coverage metric.">!</button></th>`+
    `<th>Mean weight <button type="button" class="info-button" aria-label="Explain mean assignment weight" data-tooltip="Assignment weight sum divided by assigned skill count. Use this to compare typical assignment strength across types.">!</button></th></tr></thead>`+
    `<tbody>${{domains}}${{ood || '<tr class="ood-row"><td><span class="ood-tag">OOD</span></td><td>No unmatched types</td><td>0</td><td>—</td><td>—</td></tr>'}}</tbody></table>`+
    `<h3>Per-skill stats</h3><p class="table-note">Confidence is shown only when backed by evidence. Legacy defaults and zero-evidence scores are suppressed.</p>`+
    `<table><thead><tr><th>Skill</th><th>Lifecycle</th><th>Confidence <button type="button" class="info-button" aria-label="Explain confidence" data-tooltip="Evaluation confidence, not probability of correctness. Color bands apply only to scores backed by evidence: high ≥ 0.90, medium ≥ 0.75, low &lt; 0.75. Legacy defaults and zero-evidence scores are suppressed.">!</button></th><th>Evaluation</th><th>Evidence</th><th>Sessions</th><th>Domains</th><th>OOD types</th></tr></thead>`+
    `<tbody>${{skills}}</tbody></table></section>`;
}};
const TRUNK = ['normalize-traces','detect-signals','deduplicate-and-cluster',
  'validate-preprocessing','label-skills','validate-skill-labels'];
const GRAPH = new Set([...TRUNK, 'label-traces-cluster','goal','reduce-goals',
  'optimize','verifiter','judge']);
const PHASE_COLORS = {{
  'normalize-traces':'#167d68', 'detect-signals':'#198b72',
  'deduplicate-and-cluster':'#1d997e', 'validate-preprocessing':'#25a889',
  'label-skills':'#377bd6', 'validate-skill-labels':'#4c8de0',
  'label-traces-cluster':'#7055de', 'goal':'#9b5de5',
  'reduce-goals':'#c58a18', 'optimize':'#df6f32',
  'verifiter':'#d84f8b', 'judge':'#2ca56f'
}};
const phaseColor = phase => PHASE_COLORS[phase] || '';
const traceLane = (phase, item, runId, names) => {{
  const pipeline = {{id:'pipeline', kind:'pipeline', title:'pipeline', cluster:'', sortKey:'0'}};
  if (TRUNK.includes(phase) || phase === 'reduce-goals' || item === runId ||
      phase === 'preprocessing' || phase === 'label-skills')
    return pipeline;
  const rest = item.startsWith(`${{runId}}-`) ? item.slice(runId.length + 1) : item;
  const match = rest.match(/(sig-[0-9a-f]+)(?:-op-(\\d+))?/);
  if (!match) return pipeline;
  const short = match[1].slice(4, 12);
  const cluster = (names || {{}})[match[1]] || short;
  const opPhases = ['edit-decision','operation-queue','optimize','verifiter',
    'judge','judge-decision','merge-operation'];
  if (match[2] || opPhases.includes(phase)) {{
    const op = match[2] || '1';
    return {{id:`op:${{match[1]}}:${{op}}`, kind:'op', title:`${{cluster}}/op-${{op}}`,
      cluster, sortKey:`1/${{match[1]}}/op-${{op.padStart(4, '0')}}`}};
  }}
  return {{id:`finding:${{match[1]}}`, kind:'finding', title:cluster, cluster,
    sortKey:`1/${{match[1]}}`}};
}};
const tracePanel = run => {{
  const markerSource = String(run.execution_id || run.run_id);
  const markerId = `trace-arrow-${{markerSource.replace(/[^A-Za-z0-9_-]/g, '')}}`;
  const names = run.cluster_labels || {{}};
  const operations = run.operations || {{by_op:{{}}, by_sig:{{}}}};
  const skillBySig = {{}};
  (run.spans || []).forEach(row => {{
    const match = String(row.item || '').match(/sig-[0-9a-f]+/);
    const skills = (Array.isArray(row.conflicts) ? row.conflicts : [])
      .map(name => String(name)).filter(name => name && name !== '*');
    const operation = String(row.operation || '').trim();
    if (!match || !skills.length) return;
    if (!skillBySig[match[0]]) skillBySig[match[0]] = skills.join(', ');
    const opMatch = String(row.item || '').match(/-op-(\\d+)/);
    const key = `${{match[0]}}:${{opMatch ? opMatch[1] : '1'}}`;
    if (operation && operations.by_op && !operations.by_op[key])
      operations.by_op[key] = `${{skills.join(', ')}} · ${{operation}}`;
  }});
  const namedPhase = new Set(['label-traces-cluster','goal','optimize','verifiter','judge']);
  const subjectFor = lane => {{
    const sig = (String(lane.id).match(/sig-[0-9a-f]+/) || [])[0] || '';
    if (lane.kind === 'op') {{
      const op = (String(lane.id).match(/:(\\d+)$/) || [])[1] || '1';
      return (operations.by_op || {{}})[`${{sig}}:${{op}}`] || skillBySig[sig] || lane.cluster || '';
    }}
    if (lane.kind === 'finding')
      return (operations.by_sig || {{}})[sig] || lane.cluster || '';
    return '';
  }};
  const skillNamesFromLabel = label => String(label || '').split(',')
    .map(part => part.split(' · ')[0].trim())
    .filter(name => name && name !== 'no change')
    .filter((name, index, all) => all.indexOf(name) === index)
    .join(', ');
  const skillText = (lane, slice) => {{
    if (slice.phase !== 'goal' && slice.phase !== 'optimize') return '';
    if (Array.isArray(slice.skills) && slice.skills.length)
      return slice.skills.join(', ');
    const sig = (String(lane.id).match(/sig-[0-9a-f]+/) || [])[0] || '';
    const bySig = operations.skills_by_sig || {{}};
    const byOp = operations.skills_by_op || {{}};
    if (lane.kind === 'op') {{
      const op = (String(lane.id).match(/:(\\d+)$/) || [])[1] || '1';
      return byOp[`${{sig}}:${{op}}`]
        || skillNamesFromLabel((operations.by_op || {{}})[`${{sig}}:${{op}}`])
        || bySig[sig]
        || '';
    }}
    return bySig[sig]
      || skillNamesFromLabel((operations.by_sig || {{}})[sig])
      || '';
  }};
  const seen = new Set();
  const slices = [];
  (run.spans || []).forEach(row => {{
    const start = Date.parse(row.started_at);
    if (!Number.isFinite(start)) return;
    const lane = traceLane(row.phase, String(row.item), run.run_id, names);
    const instant = row.phase !== 'reduce-goals' &&
      (row.category === 'audit' || Number(row.duration_ms) === 0);
    const pass = Number(row.pass) || 1;
    const slice = {{id:`${{markerId}}-${{slices.length}}`, phase:row.phase, item:String(row.item),
      category:row.category, start, end:start + Number(row.duration_ms),
      live:false, instant, pass, rejection:String(row.rejection || ''),
      rejectionLabel:String(row.rejection_label || ''),
      endingLabel:String(row.ending_label || ''),
      endingDetail:String(row.ending_detail || ''),
      endingBad:row.ending_bad !== false, lane}};
    seen.add(`${{slice.phase}}|${{slice.item}}|${{slice.pass}}`);
    slices.push(slice);
  }});
  (run.active || []).forEach(row => {{
    const start = Date.parse(row.started_at);
    const phase = String(row.stage);
    const item = String(row.item);
    const pass = Number(row.pass) || 1;
    if (!Number.isFinite(start) || seen.has(`${{phase}}|${{item}}|${{pass}}`)) return;
    const skills = Array.isArray(row.skills)
      ? row.skills.map(name => String(name)).filter(Boolean) : [];
    slices.push({{id:`${{markerId}}-${{slices.length}}`, phase, item, category:'live', start,
      end:null, live:true, instant:false, pass, skills, endingLabel:'', endingDetail:'',
      endingBad:false, lane:traceLane(phase, item, run.run_id, names)}});
  }});
  if (!slices.length) return '';
  const lanes = new Map();
  slices.forEach(slice => {{
    if (!lanes.has(slice.lane.id)) lanes.set(slice.lane.id, {{...slice.lane, slices:[]}});
    lanes.get(slice.lane.id).slices.push(slice);
  }});
  const ordered = [...lanes.values()];
  const byKind = kind => ordered.filter(lane => lane.kind === kind);
  const edges = [];
  const link = (source, target, kind) => {{
    if (source && target && source.id !== target.id)
      edges.push({{from:source.id, to:target.id, kind}});
  }};
  const graphNodes = rows => rows.filter(slice => GRAPH.has(slice.phase) || slice.live);
  const durationOf = slice => (slice.end ?? slice.start) - slice.start;
  const shown = rows => graphNodes(rows).filter(slice =>
    slice.live || durationOf(slice) >= 800);
  const chain = rows => {{
    const nodes = shown(rows);
    nodes.forEach((row, index) => {{
      const next = nodes[index + 1];
      if (next && row.pass === next.pass) link(row, next, 'depends');
    }});
  }};
  const pipeline = byKind('pipeline')[0];
  const trunk = (pipeline?.slices || []).filter(slice => TRUNK.includes(slice.phase))
    .sort((a, b) => a.start - b.start);
  const reduce = (pipeline?.slices || []).find(slice => slice.phase === 'reduce-goals');
  ordered.forEach(lane => lane.slices.sort((a, b) =>
    a.start - b.start || String(a.item).localeCompare(String(b.item))));
  chain(trunk);
  const onTrace = slice => GRAPH.has(slice.phase) || slice.live;
  const displayLanes = [...ordered].filter(lane => lane.slices.some(onTrace)).sort((a, b) =>
    (a.sortKey || a.id).localeCompare(b.sortKey || b.id) || a.id.localeCompare(b.id));
  const findings = displayLanes.filter(lane => lane.kind === 'finding');
  const ops = displayLanes.filter(lane => lane.kind === 'op');
  displayLanes.forEach((lane, row) =>
    lane.slices.forEach(slice => {{ slice.row = row; }}));
  findings.forEach(lane => chain(lane.slices));
  ops.forEach(lane => chain(lane.slices));
  const firstShown = (lane, pass) => shown(
    lane.slices.filter(slice => slice.pass === pass))[0];
  const lastShown = (lane, pass) => shown(
    lane.slices.filter(slice => slice.pass === pass)).at(-1);
  const passes = [...new Set(slices.map(slice => slice.pass))].sort((a, b) => a - b);
  passes.forEach(pass => {{
    const passTrunk = trunk.filter(slice => slice.pass === pass);
    const fork = shown(passTrunk).at(-1) || passTrunk.at(-1);
    const lanes = findings.filter(lane => lane.slices.some(slice => slice.pass === pass));
    lanes.forEach(lane =>
      link(fork, firstShown(lane, pass), lanes.length > 1 ? 'fanout' : 'depends'));
  }});
  const reducePass = reduce ? reduce.pass : null;
  if (reduce) {{
    findings.forEach(lane =>
      link(lastShown(lane, reducePass), reduce, findings.length > 1 ? 'merge' : 'depends'));
    ops.forEach(lane =>
      link(reduce, firstShown(lane, lane.slices[0]?.pass), ops.length > 1 ? 'fanout' : 'depends'));
  }} else {{
    findings.forEach(lane => {{
      const sig = lane.id.replace(/^finding:/, '');
      ops.filter(op => op.id.startsWith(`op:${{sig}}:`)).forEach(op =>
        link(lastShown(lane, lane.slices.at(-1)?.pass), firstShown(op, op.slices[0]?.pass), 'merge'));
    }});
  }}
  const successorStart = new Map();
  edges.forEach(edge => {{
    const target = slices.find(slice => slice.id === edge.to);
    if (!target) return;
    const known = successorStart.get(edge.from);
    if (known == null || target.start < known) successorStart.set(edge.from, target.start);
  }});
  const fanoutSources = new Set(
    edges.filter(edge => edge.kind === 'fanout').map(edge => edge.from)
  );
  const origin = Math.min(...slices.map(slice => slice.start));
  const completedEnds = slices.filter(slice => slice.end != null).map(slice => slice.end);
  const staticEnd = Math.max(origin + 1, ...completedEnds);
  const passCount = new Set(slices.map(slice => slice.pass || 1)).size;
  const renderRow = (lane, row) => {{
    const rowSlices = lane.slices.filter(onTrace);
    const subject = subjectFor(lane);
    const title = lane.kind === 'pipeline' ? 'pipeline'
      : (lane.kind === 'op' && subject ? subject : lane.title);
    const blocks = rowSlices.map(slice => {{
      const cluster = slice.lane.cluster || '';
      const base = slice.phase === 'label-traces-cluster' ? 'diagnosis' : slice.phase;
      const prefix = passCount > 1 ? `pass ${{slice.pass}} · ` : '';
      const skill = skillText(slice.lane, slice);
      const text = skill
        ? `${{prefix}}${{base}}`
        : (subject && namedPhase.has(slice.phase)
          ? `${{prefix}}${{base}} (${{subject}})`
          : `${{prefix}}${{base}}`);
      const verb = subject.includes(' · ') ? subject.split(' · ').pop() : '';
      const skillOnly = verb ? subject.slice(0, subject.lastIndexOf(' · ')) : subject;
      const endingText = !slice.endingLabel || !subject || slice.endingLabel.includes(subject)
        ? slice.endingLabel
        : (verb && skillOnly && slice.endingLabel.includes(skillOnly)
          ? `${{slice.endingLabel}} · ${{verb}}`
          : `${{slice.endingLabel}} (${{subject}})`);
      const shown = skill ? `${{text}} · ${{skill}}` : text;
      const tip = slice.endingDetail
        ? `${{shown}} · ${{slice.endingDetail}}`
        : (slice.rejection ? `${{shown}} · ${{slice.rejection}}` : shown);
      const ending = endingText
        ? `<div class="trace-end ${{slice.endingBad ? 'bad' : 'ok'}}" data-for="${{slice.id}}" `+
          `title="${{esc(slice.endingDetail || endingText)}}">${{esc(endingText)}}</div>`
        : '';
      const edgeNext = successorStart.has(slice.id) ? successorStart.get(slice.id) : null;
      const later = rowSlices.find(other => other !== slice && other.start > slice.start);
      const bounds = [edgeNext, later ? later.start : null].filter(value => value != null);
      const nextStart = bounds.length ? Math.min(...bounds) : '';
      const ghost = `<div class="trace-ghost" data-for="${{slice.id}}" hidden></div>`;
      const skillLine = skill
        ? `<div class="trace-skill" data-for="${{slice.id}}">${{esc(skill)}}</div>`
        : '';
      return `<div id="${{slice.id}}" class="trace-block ${{esc(slice.category)}}${{slice.live ? ' live' : ''}}${{slice.instant ? ' instant' : ''}}${{slice.rejection ? ' rejected' : ''}}${{fanoutSources.has(slice.id) ? ' fanout-parent' : ''}}" `+
      `data-start="${{slice.start}}" data-end="${{slice.end == null ? '' : slice.end}}" `+
      `data-next="${{nextStart}}" `+
      `data-phase="${{esc(slice.phase)}}" data-label="${{esc(text)}}" `+
      `data-cluster="${{esc(cluster)}}" data-item="${{esc(slice.item)}}" `+
      `data-rejection="${{esc(slice.rejection)}}" `+
      `data-sub="0" data-instant="${{slice.instant ? '1' : '0'}}" `+
      `data-graph="${{GRAPH.has(slice.phase) || slice.live ? '1' : '0'}}" `+
      `${{!slice.live && phaseColor(slice.phase) ? `style="background:${{phaseColor(slice.phase)}}"` : ''}} `+
      `title="${{esc(tip)}}">${{esc(text)}}</div>${{ghost}}${{skillLine}}${{ending}}`;
    }}).join('');
    const times = rowSlices.filter(slice =>
      (GRAPH.has(slice.phase) || slice.live) && !slice.instant).map(slice =>
      `<div class="trace-time" data-for="${{slice.id}}"></div>`).join('');
    return `<div class="trace-row"><div class="trace-label" title="${{esc(title)}}">`+
      `${{esc(title)}}</div><div class="trace-track">${{times}}${{blocks}}</div></div>`;
  }};
  const arrowColor = kind => kind === 'merge' ? '#3dffa8' : kind === 'fanout' ? '#ff8a3d' : '#f4f7ff';
  const arrowWidth = kind => kind === 'depends' ? 2.6 : 3.25;
  const arrows = edges.map(edge =>
    `<path data-from="${{edge.from}}" data-to="${{edge.to}}" data-kind="${{edge.kind}}" `+
    `fill="none" stroke="${{arrowColor(edge.kind)}}" stroke-width="${{arrowWidth(edge.kind)}}" `+
    `stroke-linecap="round" stroke-linejoin="round" `+
    `marker-end="url(#${{markerId}}-${{edge.kind}})"/>`
  ).join('');
  const markers = ['depends', 'fanout', 'merge'].map(kind =>
    `<marker id="${{markerId}}-${{kind}}" viewBox="0 0 10 10" refX="10" refY="5" `+
    `markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" orient="auto">`+
    `<path d="M 0 1 L 10 5 L 0 9 z" fill="${{arrowColor(kind)}}"/></marker>`
  ).join('');
  return `<div class="trace-shell" data-run="${{esc(markerSource)}}">`+
    `<div class="trace-tools"><h3>Live trace</h3><div class="trace-legend">`+
    `<span><i class="chain"></i>depends</span><span><i class="fanout"></i>fanout</span>`+
    `<span><i class="merge"></i>merge</span><span><i class="name"></i>name only</span><span>drag to pan</span>`+
    `<button type="button" class="trace-expand" data-trace-expand="${{esc(markerSource)}}">Expand</button>`+
    `</div></div>`+
    `<div class="trace-view" data-trace-origin="${{origin}}" `+
    `data-trace-static-end="${{staticEnd}}" data-trace-active="${{slices.some(slice => slice.live) ? '1' : '0'}}">`+
    `<div class="trace-ruler"><div class="trace-label">start →</div><div class="trace-ticks">`+
    `${{[0,20,40,60,80,100].map(value =>
      `<span class="trace-tick" data-fraction="${{value/100}}" style="left:${{value}}%"></span>`
    ).join('')}}</div></div>`+
    `${{displayLanes.map((lane, row) => renderRow(lane, row)).join('')}}`+
    `<svg class="trace-arrows"><defs>${{markers}}</defs>${{arrows}}</svg>`+
    `</div></div>`;
}};
const tickTraces = () => {{
  const now = Date.now();
  document.querySelectorAll('[data-live-elapsed-start]').forEach(node => {{
    node.textContent = sec(Math.max(0, now-Number(node.dataset.liveElapsedStart))/1000);
  }});
  document.querySelectorAll('[data-live-wall-start]').forEach(node => {{
    node.textContent = sec(Math.max(0, now-Number(node.dataset.liveWallStart))/1000);
  }});
  document.querySelectorAll('[data-trace-origin]').forEach(view => {{
    const origin = Number(view.dataset.traceOrigin);
    const end = view.dataset.traceActive === '1'
      ? Math.max(now, Number(view.dataset.traceStaticEnd))
      : Number(view.dataset.traceStaticEnd);
    const range = Math.max(end-origin, 1);
    const pad = 360;
    const timeline = Math.max(860, Math.ceil(range / 1000 * 6) + pad);
    view.style.setProperty('--timeline', `${{timeline}}px`);
    const track = Math.max(timeline - pad, 1);
    const ticks = view.querySelector('.trace-ticks');
    if (ticks) ticks.style.width = `${{track}}px`;
    view.querySelectorAll('.trace-tick').forEach(tick => {{
      const fraction = Number(tick.dataset.fraction);
      tick.textContent = sec(range * fraction / 1000);
      tick.style.left = `${{fraction * track}}px`;
    }});
    view.querySelectorAll('.trace-block').forEach(block => {{
      const start = Number(block.dataset.start);
      const blockEnd = block.dataset.end ? Number(block.dataset.end) : now;
      const graph = block.dataset.graph !== '0';
      block.style.top = graph ? '16px' : '4px';
      const rawLeft = Math.max(0, (start - origin) / range) * track;
      const started = Math.max(0, (start - origin) / 1000);
      const duration = Math.max(0, (blockEnd - start) / 1000);
      const phase = block.dataset.phase || '';
      const label = block.dataset.label || phase;
      const cluster = block.dataset.cluster || '';
      const rejection = block.dataset.rejection || '';
      const clock = new Date(start).toLocaleTimeString([], {{
        hour:'2-digit', minute:'2-digit', second:'2-digit'}});
      block.title = `${{phase}}${{cluster && cluster !== phase ? ` · ${{cluster}}` : ''}} · start +${{sec(started)}} (${{clock}}) · ${{sec(duration)}}`+
        (rejection ? ` · ${{rejection}}` : '')+
        (block.dataset.item ? ` · ${{block.dataset.item}}` : '');
      if (block.dataset.instant === '1') {{
        block.style.left = `${{rawLeft}}px`;
        block.style.width = '9px';
      }} else {{
        const rawWidth = Math.max(2, (blockEnd - start) / range * track);
        const trim = graph && rawWidth >= 36 ? 8 : 0;
        block.style.left = `${{rawLeft}}px`;
        block.style.width = `${{Math.max(2, rawWidth - trim)}}px`;
        if (!block.dataset.end) block.textContent =
          `${{label}} +${{started.toFixed(1)}}s · ${{sec(duration)}}`;
      }}
      block.dataset.caption = '';
      if (block.dataset.instant === '1') return;
      const name = block.dataset.label || '';
      const textWidth = Math.ceil(name.length * 6.7 + 16);
      const left = parseFloat(block.style.left) || 0;
      let width = parseFloat(block.style.width) || 2;
      const next = block.dataset.next === '' ? NaN : Number(block.dataset.next);
      const nextLeft = Number.isFinite(next)
        ? Math.max(0, (next - origin) / range) * track : NaN;
      if (Number.isFinite(nextLeft)) {{
        const capped = Math.max(2, nextLeft - left - 6);
        if (width > capped) {{
          width = capped;
          block.style.width = `${{width}}px`;
        }}
      }}
      const roomEnd = Number.isFinite(nextLeft) ? nextLeft - 6 : left + width + textWidth;
      const gap = roomEnd - (left + width);
      const ghost = block.parentElement.querySelector(
        `.trace-ghost[data-for="${{CSS.escape(block.id)}}"]`);
      if (width >= textWidth) {{
        if (ghost) ghost.hidden = true;
        if (block.dataset.end) block.textContent = name;
      }} else if (gap >= 28) {{
        if (ghost) {{
          ghost.hidden = false;
          ghost.style.left = `${{left + width}}px`;
          ghost.style.width = `${{Math.min(textWidth, gap)}}px`;
          ghost.style.top = block.style.top;
          ghost.style.borderColor = block.style.background || '#d7deef';
          ghost.textContent = name;
        }}
        block.textContent = '';
      }} else {{
        if (ghost) ghost.hidden = true;
        block.textContent = '';
        block.dataset.caption = name;
      }}
    }});
    view.querySelectorAll('.trace-skill').forEach(node => {{
      const block = view.querySelector(`#${{CSS.escape(node.dataset.for)}}`);
      if (!block) return;
      node.style.left = block.style.left;
      const top = parseFloat(block.style.top);
      node.style.top = `${{(Number.isFinite(top) ? top : 16) + 24}}px`;
    }});
    view.querySelectorAll('.trace-end').forEach(node => {{
      const block = view.querySelector(`#${{node.dataset.for}}`);
      if (!block) return;
      const left = parseFloat(block.style.left) || 0;
      const width = parseFloat(block.style.width) || 0;
      node.style.left = `${{left + width + 8}}px`;
      node.style.top = block.style.top || '16px';
    }});
    view.querySelectorAll('.trace-time').forEach(label => {{
      const block = view.querySelector(`#${{label.dataset.for}}`);
      if (!block) return;
      const start = Number(block.dataset.start);
      label.style.left = block.style.left;
      const caption = block.dataset.caption ? ` · ${{block.dataset.caption}}` : '';
      label.textContent = `+${{Math.max(0, (start - origin) / 1000).toFixed(1)}}s${{caption}}`;
    }});
    view.querySelectorAll('.trace-track').forEach(track => {{
      let lastEnd = -Infinity;
      [...track.querySelectorAll('.trace-time')]
        .sort((a, b) => parseFloat(a.style.left) - parseFloat(b.style.left))
        .forEach(label => {{
          const x = parseFloat(label.style.left);
          const width = Math.ceil(label.textContent.length * 6.2);
          const hide = x < lastEnd + 8;
          label.style.visibility = hide ? 'hidden' : 'visible';
          if (!hide) lastEnd = x + width;
        }});
    }});
    const root = view.getBoundingClientRect();
    if (!root.width) return;
    view.querySelectorAll('.trace-arrows path').forEach(path => {{
      const source = view.querySelector(`#${{path.dataset.from}}`);
      const target = view.querySelector(`#${{path.dataset.to}}`);
      if (!source || !target) return;
      const from = source.getBoundingClientRect();
      const to = target.getBoundingClientRect();
      const x1 = from.right - root.left + 2;
      const y1 = from.top + from.height / 2 - root.top;
      const x2 = to.left - root.left - 3;
      const y2 = to.top + to.height / 2 - root.top;
      const room = x2 - x1;
      if (room < 10 && Math.abs(y1 - y2) < 8) {{
        path.setAttribute('d', '');
        return;
      }}
      if (room < 10) {{
        const knee = x1 + Math.max(4, Math.min(room, 8));
        path.setAttribute('d', `M ${{x1}} ${{y1}} H ${{knee}} V ${{y2}} H ${{Math.max(x2, knee)}}`);
        return;
      }}
      const rail = x1 + Math.min(room * 0.5, 36);
      path.setAttribute('d', Math.abs(y1 - y2) < 8
        ? `M ${{x1}} ${{y1}} H ${{x2}}`
        : `M ${{x1}} ${{y1}} H ${{rail}} V ${{y2}} H ${{x2}}`);
    }});
  }});
}};
const runPanel = run => {{
  const total = Math.max(Object.values(run.category_seconds).reduce((a,b)=>a+b,0), .001);
  const bars = Object.entries(run.category_seconds).map(([category,value]) =>
    `<div class="bar ${{esc(category)}}" style="width:${{Math.min(value/total*100,100)}}%">`+
    `${{esc(category)}} ${{Number(value).toFixed(1)}}s</div>`).join('');
  const active = (run.active || []).map(row =>
    `<div class="active-run"><b>Running now:</b> ${{esc(row.stage)}} · `+
    `${{esc(row.item)}} · <b data-live-elapsed-start="${{Date.parse(row.started_at)}}">`+
    `${{sec(row.elapsed_seconds)}}</b></div>`).join('');
  const progress = run.progress || {{selected_findings:0, stages:[]}};
  const progressRows = (progress.stages || []).map(row => {{
    const duration = ['pending','skipped','stale'].includes(row.state)
      ? '—' : sec(row.duration_seconds);
    const queue = row.queue_wait_ms == null ? '—' : `${{Number(row.queue_wait_ms).toFixed(2)}}ms`;
    const items = row.items_total ? `${{row.items_done}}/${{row.items_total}} items` : '—';
    return `<span>${{esc(row.label)}}</span>`+
      `<span class="state ${{esc(row.state)}}">${{esc(row.state)}}</span>`+
      `<span>${{duration}}</span><span>${{items}} · queue ${{queue}}</span>`;
  }}).join('');
  const phaseRows = (run.phases || []).map(row =>
    `<tr><td>${{esc(row.phase)}}</td><td>${{row.count}}</td>`+
    `<td>${{sec(row.sum_seconds)}}</td><td>${{sec(row.wall_seconds)}}</td>`+
    `<td>${{row.peak_concurrency}}</td><td>${{sec(row.p50_seconds)}}</td>`+
    `<td>${{sec(row.max_seconds)}}</td></tr>`).join('');
  const spanRows = (run.spans || []).map(row =>
    `<tr><td>${{esc(row.phase)}}</td><td>${{esc(row.item)}}</td>`+
    `<td>${{Number(row.duration_ms).toFixed(1)}}</td>`+
    `<td>${{esc(row.queue_wait_ms)}}</td><td>${{esc(row.slice_tokens)}}</td>`+
    `<td>${{esc(row.slice_user_turns)}}</td><td>${{esc(row.tool_events)}}</td>`+
    `<td>${{esc(row.decision)}}</td><td>${{esc(row.super_score)}}</td>`+
    `<td>${{esc(row.judge_action)}}</td><td>${{esc(row.status)}}</td></tr>`).join('');
  const heading = run.execution_id || run.run_id;
  const progressBlock = run.historical ? '' :
    `<section class="progress"><h3>Current progress</h3>`+
    `<p>Selected findings: <b>${{progress.selected_findings}}</b></p>`+
    `<div class="progress-grid">${{progressRows}}</div></section>`;
  return `<section class="card"><h2>${{esc(heading)}}</h2>${{run.historical ? '' : active}}`+
    `${{progressBlock}}<div class="stats">`+
    `<span>live wall <b${{(run.active || []).length ? ` data-live-wall-start="${{Date.parse(run.started_at)}}"` : ''}}>`+
    `${{sec(run.wall_seconds)}}</b></span>`+
    `<span>completed agent sum <b>${{sec(run.category_seconds.llm_agent || 0)}}</b></span>`+
    `<span>deterministic <b>${{sec(run.category_seconds.deterministic || 0)}}</b></span>`+
    `<span>orchestration <b>${{sec(run.category_seconds.orchestration || 0)}}</b></span>`+
    `<span>completed spans <b>${{run.span_count}}</b></span><span>errors <b>${{run.error_count}}</b></span>`+
    `</div><div class="bars">${{bars}}</div>`+
    tracePanel(run)+
    `<h3>Completed phase spans</h3><table><thead><tr><th>Phase</th><th>Count</th><th>Sum</th>`+
    `<th>Wall</th><th>Peak</th><th>P50</th><th>Max</th></tr></thead>`+
    `<tbody>${{phaseRows}}</tbody></table>`+
    `<h3>Completed spans</h3><table><thead><tr><th>Phase</th><th>Item</th><th>ms</th>`+
    `<th>Queue ms</th><th>Slice tokens</th><th>User turns</th>`+
    `<th>Tool events</th><th>Decision</th><th>Super score</th>`+
    `<th>Judge</th><th>Status</th></tr></thead>`+
    `<tbody>${{spanRows}}</tbody></table></section>`;
}};
const runDate = run => String(run.started_at || '').slice(0,10) || 'unknown';
const renderDiagnosisAnalysis = stats => {{
  if (!stats?.distribution) return '';
  const classIndex = {{known:0, ood:0}};
  const rows = stats.distribution.map(row => {{
    const index = classIndex[row.classification]++;
    const overflow = index >= 10 ? `after-${{row.classification === 'ood' ? 'ood' : 'id'}}-top-ten` : '';
    return `<tr class="${{row.classification === 'ood' ? 'ood-row ' : ''}}${{overflow}}">`+
    `<td><span class="${{row.classification === 'ood' ? 'ood-tag' : 'badge'}}">${{row.classification === 'ood' ? 'OOD' : 'ID'}}</span></td>`+
    `<td>${{esc(row.type)}}</td><td>${{esc(row.category)}}</td><td>${{row.count}}</td>`+
    `<td>${{row.mean_confidence == null ? '—' : Number(row.mean_confidence).toFixed(2)}}</td></tr>`;
  }}).join('') ||
    `<tr><td colspan="5" class="muted">No capability diagnoses recorded.</td></tr>`;
  const categoryClassIndex = {{known:0, ood:0}};
  const categoryRows = stats.categories.map(row => {{
    const index = categoryClassIndex[row.classification]++;
    const overflow = index >= 10 ? `after-${{row.classification === 'ood' ? 'ood' : 'id'}}-top-ten` : '';
    return `<tr class="${{row.classification === 'ood' ? 'ood-row ' : ''}}${{overflow}}">`+
      `<td>${{esc(row.category)}}</td><td>${{row.classification === 'ood' ? 'OOD' : 'ID'}}</td><td>${{row.count}}</td></tr>`;
  }}).join('') ||
    `<tr><td colspan="3" class="muted">No categories recorded.</td></tr>`;
  const expanders = (id,values) => ['known','ood'].map(classification => {{
    const total = values.filter(row => row.classification === classification).length;
    const label = classification === 'ood' ? 'OOD' : 'ID';
    return total > 10 ? `<button type="button" class="table-expander" data-expand-rows="${{id}}" data-expand-class="${{label.toLowerCase()}}" data-total="${{total}}" aria-expanded="false">Show all ${{total}} ${{label}}</button>` : '';
  }}).join(' ');
  return `<section class="goal-analysis"><h3>Diagnosis capability distribution</h3>`+
    `<div class="stats"><span>diagnosis JSON <b>${{stats.document_count}}</b></span>`+
    `<span>ID gaps <b>${{stats.known_count}}</b></span><span>OOD detections <b>${{stats.ood_count}}</b></span></div>`+
    `<p class="table-note">ID (in-distribution) gaps are shown first, followed by OOD detections. Long lists show the top 10 by count.</p>`+
    `<div class="analysis-grid"><div><h4>Capability types</h4><table><thead><tr><th>Class</th><th>Type</th><th>Category / domain</th><th>Count</th><th>Mean confidence</th></tr></thead><tbody id="diagnosis-capability-rows" class="expandable-rows">${{rows}}</tbody></table>${{expanders('diagnosis-capability-rows',stats.distribution)}}</div>`+
    `<div><h4>Category distribution</h4><table><thead><tr><th>Category</th><th>Class</th><th>Count</th></tr></thead><tbody id="diagnosis-category-rows" class="expandable-rows">${{categoryRows}}</tbody></table>${{expanders('diagnosis-category-rows',stats.categories)}}</div></div></section>`;
}};
const renderGoalAnalysis = (stats, runId) => {{
  if (!stats?.operations) return '';
  const total = stats.operations.reduce((sum,row) => sum + Number(row.count || 0), 0);
  const valid = ['all', ...stats.operations.map(row => row.operation)];
  if (!valid.includes(selectedGoalOperation)) selectedGoalOperation = 'create';
  const detail = stats.by_operation?.[selectedGoalOperation] || {{skills:[], categories:[], ood:[]}};
  const distribution = stats.operations.map(row => `<tr><td>${{esc(row.operation)}}</td><td>${{row.count}}</td>`+
    `<td>${{total ? (row.count / total * 100).toFixed(1) : '0.0'}}%</td></tr>`).join('');
  const buttons = stats.operations.map(row => `<button type="button" data-goal-operation="${{esc(row.operation)}}" `+
    `data-run-id="${{esc(runId)}}" class="${{row.operation === selectedGoalOperation ? 'active' : ''}}">`+
    `${{esc(row.operation)}} · ${{row.count}}</button>`).join('');
  const options = `<option value="all"${{selectedGoalOperation === 'all' ? ' selected' : ''}}>All operations (${{total}})</option>`+
    stats.operations.map(row => `<option value="${{esc(row.operation)}}"${{row.operation === selectedGoalOperation ? ' selected' : ''}}>`+
    `${{esc(row.operation)}} (${{row.count}})</option>`).join('');
  const goalKey = String(selectedGoalOperation).replace(/[^a-z0-9_-]/gi,'-');
  const rowClass = index => index >= 10 ? ' class="after-top-ten"' : '';
  const expander = (id,total,label='') => total > 10 ? `<button type="button" class="table-expander" data-expand-rows="${{id}}" data-expand-class="all" data-label="${{esc(label)}}" data-total="${{total}}" aria-expanded="false">Show all ${{total}}${{label ? ` ${{esc(label)}}` : ''}}</button>` : '';
  const skillRows = detail.skills.map((row,index) => `<tr${{rowClass(index)}}><td><code>${{esc(row.skill)}}</code></td><td>${{row.count}}</td>`+
    `<td>${{row.sections.map(value => `<span class="badge">${{esc(value)}}</span>`).join(' ') || '—'}}</td>`+
    `<td>${{row.directories.map(value => `<span class="badge">${{esc(value)}}</span>`).join(' ') || '—'}}</td>`+
    `<td>${{row.categories.map(value => `<span class="badge">${{esc(value)}}</span>`).join(' ') || '—'}}</td>`+
    `<td>${{row.ood.map(value => `<span class="ood-tag">${{esc(value)}}</span>`).join(' ') || '—'}}</td></tr>`).join('') ||
    `<tr><td colspan="6" class="muted">No skills are associated with this operation type.</td></tr>`;
  const categoryRows = detail.categories.map((row,index) => `<tr${{rowClass(index)}}><td>${{esc(row.category)}}</td><td>${{row.count}}</td></tr>`).join('') ||
    `<tr><td colspan="2" class="muted">No categories recorded.</td></tr>`;
  const oodRows = detail.ood.map((row,index) => `<tr class="ood-row${{index >= 10 ? ' after-top-ten' : ''}}"><td>${{esc(row.type)}}</td><td>${{row.count}}</td></tr>`).join('') ||
    `<tr><td colspan="2" class="muted">No OOD types recorded.</td></tr>`;
  const simpleRows = values => values.map((row,index) => `<tr${{rowClass(index)}}><td>${{esc(row.name)}}</td><td>${{row.count}}</td></tr>`).join('') ||
    `<tr><td colspan="2" class="muted">No values recorded.</td></tr>`;
  return `<section class="goal-analysis"><h3>Goal operation distribution</h3>`+
    `<p class="table-note">Across ${{stats.goal_documents}} goal JSON documents. Proposed operations are counted even when later phases were skipped.</p>`+
    `<table><thead><tr><th>Operation</th><th>Count</th><th>Share</th></tr></thead><tbody>${{distribution}}</tbody></table>`+
    `<div class="operation-filter"><label for="goal-operation-filter">Filter goal details</label>`+
    `<select id="goal-operation-filter" data-goal-operation-select data-run-id="${{esc(runId)}}">${{options}}</select></div>`+
    `<div class="operation-flow" aria-label="Goal operation filters">${{buttons}}</div>`+
    `<h3>${{esc(selectedGoalOperation)}} details</h3><div>`+
    `<h4>Per-skill distribution</h4><table><thead><tr><th>Skill title</th><th>Count</th><th>Sections</th><th>Resources</th><th>Categories</th><th>OOD</th></tr></thead><tbody id="goal-${{goalKey}}-skills" class="expandable-rows">${{skillRows}}</tbody></table>${{expander(`goal-${{goalKey}}-skills`,detail.skills.length,'skills')}}</div>`+
    `<div class="analysis-grid"><div>`+
    `<h4>Section distribution</h4><table><thead><tr><th>Section</th><th>Count</th></tr></thead><tbody id="goal-${{goalKey}}-sections" class="expandable-rows">${{simpleRows(detail.sections)}}</tbody></table>${{expander(`goal-${{goalKey}}-sections`,detail.sections.length,'sections')}}`+
    `<h4>Resource directory distribution</h4><table><thead><tr><th>Directory</th><th>Count</th></tr></thead><tbody id="goal-${{goalKey}}-directories" class="expandable-rows">${{simpleRows(detail.directories)}}</tbody></table>${{expander(`goal-${{goalKey}}-directories`,detail.directories.length,'directories')}}`+
    `</div><div><h4>Category distribution</h4><table><thead><tr><th>Category</th><th>Count</th></tr></thead><tbody id="goal-${{goalKey}}-categories" class="expandable-rows">${{categoryRows}}</tbody></table>${{expander(`goal-${{goalKey}}-categories`,detail.categories.length,'categories')}}`+
    `<h4>Resource-plan decisions</h4><table><thead><tr><th>Resource : decision</th><th>Count</th></tr></thead><tbody id="goal-${{goalKey}}-decisions" class="expandable-rows">${{simpleRows(detail.resource_decisions)}}</tbody></table>${{expander(`goal-${{goalKey}}-decisions`,detail.resource_decisions.length,'decisions')}}`+
    `<h4>OOD distribution</h4><table><thead><tr><th>OOD type</th><th>Count</th></tr></thead><tbody id="goal-${{goalKey}}-ood" class="expandable-rows">${{oodRows}}</tbody></table>${{expander(`goal-${{goalKey}}-ood`,detail.ood.length,'OOD types')}}</div></div></section>`;
}};
const renderOptimizeAnalysis = (stats, runId) => {{
  if (!stats) return '';
  const observedOperations = (stats.operations || []).map(row => row.name);
  const operations = ['all', ...new Set(['create','update','delete','merge','split','no_change', ...observedOperations])];
  if (!operations.includes(selectedOptimizeOperation)) selectedOptimizeOperation = 'all';
  const detail = selectedOptimizeOperation === 'all' ? stats :
    (stats.by_operation?.[selectedOptimizeOperation] || {{skills:[], sections:[], directories:[]}});
  const operationOptions = operations.map(operation => {{
    const count = operation === 'all' ? stats.change_count :
      (stats.operations.find(row => row.name === operation)?.count || 0);
    return `<option value="${{esc(operation)}}"${{operation === selectedOptimizeOperation ? ' selected' : ''}}>`+
      `${{operation === 'all' ? 'All operations' : esc(operation)}} (${{count}})</option>`;
  }}).join('');
  const table = (title, label, values) => `<div><h4>${{title}}</h4><table><thead><tr><th>${{label}}</th><th>Count</th></tr></thead><tbody>`+
    `${{values.map(row => `<tr><td>${{esc(row.name)}}</td><td>${{row.count}}</td></tr>`).join('') || `<tr><td colspan="2" class="muted">No values recorded.</td></tr>`}}`+
    `</tbody></table></div>`;
  return `<section class="goal-analysis"><h3>Optimize change distribution</h3>`+
    `<div class="stats"><span>changelog JSON <b>${{stats.document_count}}</b></span><span>skill changes <b>${{stats.change_count}}</b></span></div>`+
    `<div class="operation-filter"><label for="optimize-operation-filter">Filter optimize details</label>`+
    `<select id="optimize-operation-filter" data-optimize-operation-select data-run-id="${{esc(runId)}}">${{operationOptions}}</select></div>`+
    `<div class="analysis-grid">${{table('Operation distribution','Operation',stats.operations)}}${{table('Skill title distribution','Skill',detail.skills)}}`+
    `${{table('Section distribution','Section',detail.sections)}}${{table('Resource directory distribution','Directory',detail.directories)}}</div></section>`;
}};
const renderPhaseAudit = audit => {{
  if (!audit.phases?.length) return `<h3>Phase output JSON</h3><p class="muted">No phase-output JSON found for this run.</p>`;
  auditPhasePage = Math.min(Math.max(auditPhasePage, 0), audit.phases.length - 1);
  const group = audit.phases[auditPhasePage];
  const phaseLabels = {{
    'detect-signals':'Detect signals', 'label-traces-cluster':'Label traces / diagnose',
    'label-skills':'Label skills', goal:'Goal', optimize:'Optimize',
    verification:'Verification', judge:'Judge', publication:'Publication', summary:'Summary'
  }};
  const rows = group.documents.map(row => `<tr${{row.has_ood ? ' class="ood-row"' : ''}}>`+
      `<td><code>${{esc(row.id)}}</code></td>`+
      `<td><a class="json-link" href="${{esc(row.url)}}" target="_blank" rel="noopener">${{esc(row.path)}}</a></td>`+
      `<td>${{row.has_ood ? row.ood.map(value => `<span class="ood-tag">${{esc(value)}}</span>`).join('') : '—'}}</td>`+
      `<td class="json-keys">${{row.keys.map(esc).join(', ') || 'array/value'}}</td>`+
      `<td>${{Number(row.bytes).toLocaleString()}}</td></tr>`).join('') ||
      `<tr><td colspan="5" class="muted">No output JSON found for this phase. The phase may not have triggered, may have been skipped, or may have failed before writing its contract artifact.</td></tr>`;
  const flow = audit.phases.map((phase, index) =>
    `<button type="button" data-audit-index="${{index}}" data-run-id="${{esc(audit.run_id)}}" class="${{index === auditPhasePage ? 'active' : ''}}"${{index === auditPhasePage ? ' aria-current="step"' : ''}}>`+
    `${{index + 1}}. ${{esc(phaseLabels[phase.phase] || phase.phase)}}<small>${{phase.document_count}} JSON · ${{phase.ood_count}} OOD</small></button>`
  ).join('');
  return `<h3>Phase output JSON</h3><p class="table-note">Run scope: <code>${{esc(audit.run_id)}}</code>. Operational status, configuration, logs, and intermediate trace files are excluded. OOD rows are highlighted.</p>`+
    `<nav class="phase-flow" aria-label="Pipeline phase flow">${{flow}}</nav>`+
    `<nav class="run-pages" aria-label="JSON audit phase pages">`+
    `<button data-audit-page="prev" data-run-id="${{esc(audit.run_id)}}"${{auditPhasePage === 0 ? ' disabled' : ''}}>← Previous phase</button>`+
    `<strong>${{esc(phaseLabels[group.phase] || group.phase)}}</strong><span>Phase ${{auditPhasePage + 1}} of ${{audit.phases.length}} · ${{group.document_count}} JSON · ${{group.ood_count}} OOD</span>`+
    `<button data-audit-page="next" data-run-id="${{esc(audit.run_id)}}"${{auditPhasePage >= audit.phases.length - 1 ? ' disabled' : ''}}>Next phase →</button></nav>`+
    `${{group.phase === 'label-traces-cluster' ? renderDiagnosisAnalysis(latestDiagnosisStats) : ''}}`+
    `${{group.phase === 'goal' ? renderGoalAnalysis(latestGoalStats, audit.run_id) : ''}}`+
    `${{group.phase === 'optimize' ? renderOptimizeAnalysis(latestOptimizeStats, audit.run_id) : ''}}`+
    `<section class="audit-phase"><table><thead><tr><th>ID</th><th>Output JSON</th><th>OOD detections</th>`+
    `<th>Top-level fields</th><th>Bytes</th></tr></thead><tbody>${{rows}}</tbody></table></section>`;
}};
const loadPhaseAudit = async runId => {{
  const targets = [...document.querySelectorAll(`[data-phase-audit][data-run-id="${{CSS.escape(runId)}}"]`)];
  if (!targets.length) return;
  try {{
    const response = await fetch(`/api/audit?run=${{encodeURIComponent(runId)}}`, {{cache:'no-store'}});
    if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
    const audit = await response.json();
    const previous = phaseAuditCache.get(runId);
    phaseAuditCache.set(runId, audit);
    if (previous && JSON.stringify(previous) === JSON.stringify(audit) &&
        targets.every(target => target.querySelector('.audit-phase'))) return;
    targets.forEach(target => {{ target.innerHTML = renderPhaseAudit(audit); compactLongTables(target); }});
  }} catch (error) {{
    targets.forEach(target => target.innerHTML = `<h3>Phase JSON audit</h3><p class="error">Audit failed: ${{esc(error)}}</p>`);
  }}
}};
const matchingRuns = data => data.runs.filter(run => {{
  const id = String(run.execution_id || run.run_id);
  return (runDay === 'all' || runDate(run) === runDay) && id.toLowerCase().includes(runQuery.toLowerCase());
}}).sort((a,b) => Number(Boolean((b.active || []).length)) - Number(Boolean((a.active || []).length)));
const runChoices = data => {{
  const matches = matchingRuns(data);
  const pages = Math.max(1, Math.ceil(matches.length / RUNS_PER_PAGE));
  runPage = Math.min(Math.max(runPage, 1), pages);
  const rows = matches.slice((runPage - 1) * RUNS_PER_PAGE, runPage * RUNS_PER_PAGE);
  if (!rows.length) return `<p class="muted">No runs match these filters.</p>`;
  return rows.map(run => {{
    const id = String(run.execution_id || run.run_id);
    const live = (run.active || []).length;
    return `<button class="run-option${{id === selectedRunId ? ' selected' : ''}}" data-run-choice="${{esc(id)}}" title="${{esc(id)}}">`+
      `<strong>${{esc(id)}}</strong><span class="run-meta"><span class="badge">${{esc(runDate(run))}}</span>`+
      `${{live ? '<span class="badge live">live</span>' : ''}}${{run.error_count ? `<span class="badge error">${{run.error_count}} errors</span>` : ''}}`+
      `${{run.historical ? '<span class="badge">history</span>' : ''}}</span></button>`;
  }}).join('');
}};
const runPicker = (data, run) => {{
  const days = [...new Set(data.runs.map(runDate))].sort().reverse();
  const matches = matchingRuns(data);
  const pages = Math.max(1, Math.ceil(matches.length / RUNS_PER_PAGE));
  runPage = Math.min(Math.max(runPage, 1), pages);
  return `<section class="run-browser"><div class="run-filters">`+
    `<input data-run-picker data-run-search type="search" value="${{esc(runQuery)}}" placeholder="Search run name or tag…" aria-label="Search runs">`+
    `<select data-run-picker data-run-day aria-label="Filter runs by day"><option value="all">All days</option>`+
    `${{days.map(day => `<option value="${{esc(day)}}"${{day === runDay ? ' selected' : ''}}>${{esc(day)}}</option>`).join('')}}</select></div>`+
    `<div class="run-results" data-run-results>${{runChoices(data)}}</div>`+
    `<div class="run-pages"><button data-run-page="prev"${{runPage <= 1 ? ' disabled' : ''}}>← Previous</button>`+
    `<span>Page ${{runPage}} of ${{pages}} · ${{matches.length}} matches</span>`+
    `<button data-run-page="next"${{runPage >= pages ? ' disabled' : ''}}>Next →</button></div></section>`;
}};
async function refresh() {{
  if (runPickerOpen) return;
  try {{
    const response = await fetch('/api/metrics', {{cache:'no-store'}});
    if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
    const data = await response.json();
    if (runPickerOpen) return;
    latestGoalStats = data.goal_stats || null;
    latestDiagnosisStats = data.diagnosis_stats || null;
    latestOptimizeStats = data.optimize_stats || null;
    document.getElementById('status').className = 'muted';
    document.getElementById('status').innerHTML =
      `${{data.run_count}} runs · ${{data.span_count}} spans · refreshed ${{esc(data.generated_at)}} · <code>${{esc(data.database)}}</code>`;
    const runIds = data.runs.map(run => String(run.execution_id || run.run_id));
    if (expandedRun && !runIds.includes(expandedRun)) expandedRun = '';
    if (!['total','skills','runs'].includes(selectedTab)) selectedTab = 'total';
    if (!runIds.includes(selectedRunId)) selectedRunId = runIds[0] || '';
    const selectedRun = data.runs.find(run => String(run.execution_id || run.run_id) === selectedRunId);
    const signature = JSON.stringify({{
      view:[selectedRunId, runQuery, runDay, runPage],
      totals:[data.run_count, data.span_count], phases:data.phases,
      skillStats:data.skill_stats, goalStats:data.goal_stats, diagnosisStats:data.diagnosis_stats,
      optimizeStats:data.optimize_stats,
      runs:data.runs.map(run => ({{
        id:String(run.execution_id || run.run_id), historical:run.historical,
        spans:run.span_count, errors:run.error_count, started:run.started_at,
        categories:run.category_seconds, phases:run.phases,
        // Running durations are clocks, not structural data. Including them here
        // caused every poll to replace the dashboard DOM and visibly flash.
        // tickTraces() owns live elapsed-time updates; this signature only tracks
        // changes that require rebuilding a panel.
        progress:run.progress ? {{
          selected_findings:run.progress.selected_findings,
          stages:(run.progress.stages || []).map(stage => [
            stage.name, stage.label, stage.state, stage.items_done,
            stage.items_total, stage.queue_wait_ms
          ])
        }} : null,
        active:(run.active || []).map(row => [row.stage,row.item,row.started_at])
      }}))
    }});
    if (signature === renderedSignature) {{
      if (selectedRun) await loadPhaseAudit(selectedRun.run_id);
      tickTraces();
      return;
    }}
    renderedSignature = signature;
    document.getElementById('tabs').innerHTML =
      `<button class="tab" data-tab="total">Overview</button>`+
      `<button class="tab" data-tab="skills">Stats</button>`+
      `<button class="tab" data-tab="runs">Runs (${{data.run_count}})</button>`;
    document.querySelectorAll('.trace-shell').forEach(shell => {{
      traceScroll.set(shell.dataset.run, shell.scrollLeft);
    }});
    const empty = data.run_count ? '' : `<p class="muted">No runs recorded.</p>`;
    document.getElementById('panels').innerHTML =
      `<section class="panel" data-panel="total"><section class="card">`+
      `<h2>Total across runs</h2>${{empty}}<div class="stats"><span>runs <b>${{data.run_count}}</b></span>`+
      `<span>completed spans <b>${{data.span_count}}</b></span></div>`+
      `<h3>Cross-run phase statistics</h3>${{phaseTable(data.phases)}}</section></section>`+
      `<section class="panel" data-panel="skills">`+
      `${{selectedRun ? `<section class="card phase-audit" data-phase-audit data-run-id="${{esc(selectedRun.run_id)}}"><h2>Phase-by-phase output review</h2><p class="muted">Loading phase outputs…</p></section>` : ''}}`+
      `${{skillStatsPanel(data.skill_stats)}}</section>`+
      `<section class="panel" data-panel="runs">${{selectedRun ? runPicker(data, selectedRun)+runPanel(selectedRun) : empty}}</section>`;
    compactLongTables(document.getElementById('panels'));
    document.querySelectorAll('.tab').forEach(node =>
      node.addEventListener('click', () => selectTab(node.dataset.tab)));
    document.querySelectorAll('[data-run-search]').forEach(node =>
      node.addEventListener('input', () => {{
        runQuery = node.value;
        runPage = 1;
        writeView();
        document.querySelectorAll('[data-run-search]').forEach(other => {{ if (other !== node) other.value = runQuery; }});
        document.querySelectorAll('[data-run-results]').forEach(target => target.innerHTML = runChoices(data));
      }}));
    document.querySelectorAll('[data-run-day]').forEach(node =>
      node.addEventListener('change', () => {{
        runDay = node.value;
        runPage = 1;
        writeView();
        document.querySelectorAll('[data-run-day]').forEach(other => other.value = runDay);
        document.querySelectorAll('[data-run-results]').forEach(target => target.innerHTML = runChoices(data));
      }}));
    document.querySelectorAll('[data-run-page]').forEach(node =>
      node.addEventListener('click', () => {{
        runPage += node.dataset.runPage === 'next' ? 1 : -1;
        runPickerOpen = false;
        writeView();
        refresh();
      }}));
    selectTab(selectedTab);
    if (selectedRun) await loadPhaseAudit(selectedRun.run_id);
    applyExpandedTrace();
    tickTraces();
    document.querySelectorAll('.trace-shell').forEach(shell => {{
      const left = traceScroll.get(shell.dataset.run);
      if (left) shell.scrollLeft = left;
    }});
    if (restoreScrollY != null) {{
      const targetScrollY = restoreScrollY;
      restoreScrollY = null;
      requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo(0, targetScrollY)));
    }}
  }} catch (error) {{
    document.getElementById('status').className = 'error';
    document.getElementById('status').textContent = `Refresh failed: ${{error}}`;
  }}
}}
refresh(); setInterval(refresh, {refresh_ms}); setInterval(tickTraces, 100);
</script></main></body></html>"""


def make_server(
    database: Path,
    host: str,
    port: int,
    refresh_seconds: float = 2.0,
) -> ThreadingHTTPServer:
    document = live_document(refresh_seconds).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request = urlparse(self.path)
            if request.path == "/" or request.path.startswith("/index.html"):
                self._reply(200, "text/html; charset=utf-8", document)
                return
            if request.path == "/api/metrics":
                try:
                    payload = json.dumps(
                        metrics_payload(database), ensure_ascii=False
                    ).encode()
                except (OSError, sqlite3.Error, SystemExit) as error:
                    self._reply(
                        500,
                        "application/json",
                        json.dumps({"error": str(error)}).encode(),
                    )
                    return
                self._reply(200, "application/json", payload)
                return
            if request.path == "/api/audit":
                run_id = parse_qs(request.query).get("run", [""])[0]
                payload = json.dumps(
                    phase_json_audit(database, run_id), ensure_ascii=False
                ).encode()
                self._reply(200, "application/json", payload)
                return
            if request.path == "/api/artifact":
                query = parse_qs(request.query)
                run_id = query.get("run", [""])[0]
                relative = unquote(query.get("path", [""])[0])
                runs_root = (database.parent / "runs").resolve()
                run_root = (runs_root / run_id).resolve()
                target = (run_root / relative).resolve()
                if (run_root.parent != runs_root or run_root not in target.parents
                        or target.suffix != ".json" or not target.is_file()):
                    self._reply(404, "application/json", b'{"error":"not found"}')
                    return
                self._reply(200, "application/json; charset=utf-8", target.read_bytes())
                return
            if request.path == "/health":
                self._reply(200, "application/json", b'{"status":"ok"}')
                return
            self._reply(404, "text/plain; charset=utf-8", b"not found")

        def _reply(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=root / "workspace/metrics.sqlite",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "workspace/metrics-dashboard.html",
    )
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--refresh-seconds", type=float, default=2.0)
    args = parser.parse_args()
    database = args.database.resolve()
    if args.snapshot:
        print(render(database, args.output.resolve()))
        return
    server = make_server(
        database, args.host, args.port, args.refresh_seconds
    )
    print(f"http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
