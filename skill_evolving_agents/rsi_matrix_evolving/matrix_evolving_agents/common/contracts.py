from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGES = (
    "01_preprocessing", "02_diagnosis", "03_goal", "04_sampling",
    "05_verification", "06_judge", "07_dashboard",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: str | Path, value: Any) -> Path:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True); handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return path


def append_event(workspace: Path, agent: str, state: str, event: str, detail: dict | None = None) -> None:
    path = workspace / "output/logs/agent-execution.jsonl"; path.parent.mkdir(parents=True, exist_ok=True)
    row = {"schema_version": 1, "agent": agent, "state": state, "event": event, "at": now(), "detail": detail or {}}
    with path.open("a") as handle: handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_status(workspace: Path, stage: str, state: str, artifacts: list[str], error: str | None = None) -> Path:
    if stage not in STAGES: raise ValueError(f"unknown stage: {stage}")
    return write_json(workspace / "output/run/status" / f"{stage}.json", {"schema_version": 1, "stage": stage, "state": state, "at": now(), "artifacts": artifacts, "error": error})


def validate_lineage(tree: dict) -> list[str]:
    errors, by_id = [], {n["node_id"]: n for n in tree.get("nodes", [])}
    for node in by_id.values():
        parent_id = node.get("parent_id")
        if node.get("layer") == 0 and parent_id is not None: errors.append(f"{node['node_id']}: root has parent")
        if node.get("layer", 0) > 0:
            if parent_id not in by_id: errors.append(f"{node['node_id']}: missing parent")
            elif by_id[parent_id]["layer"] != node["layer"] - 1: errors.append(f"{node['node_id']}: parent layer mismatch")
            if len(node.get("shift_axes", [])) != node["layer"]: errors.append(f"{node['node_id']}: shift depth mismatch")
    return errors


def validate_hierarchy(tree: dict) -> list[str]:
    hierarchy = tree.get("hierarchy", {})
    nodes = hierarchy.get("nodes", [])
    errors: list[str] = []
    ids = [node.get("node_id") for node in nodes]
    if len(ids) != len(set(ids)):
        errors.append("duplicate hierarchy node ids")
    by_id = {node.get("node_id"): node for node in nodes}
    roots = [node for node in nodes if node.get("parent_id") is None]
    root_id = hierarchy.get("root_id")
    if len(roots) != 1:
        errors.append(f"expected one hierarchy root, found {len(roots)}")
    if root_id not in by_id or (root_id in by_id and by_id[root_id].get("parent_id") is not None):
        errors.append("hierarchy root_id is missing or is not a root")
    expected_children = {node_id: [] for node_id in by_id}
    for node in nodes:
        parent_id = node.get("parent_id")
        if parent_id is not None:
            if parent_id not in by_id:
                errors.append(f"{node.get('node_id')}: missing hierarchy parent")
            else:
                expected_children[parent_id].append(node.get("node_id"))
    for node_id, node in by_id.items():
        if set(node.get("child_ids", [])) != set(expected_children[node_id]):
            errors.append(f"{node_id}: child_ids mismatch")
    seen: set[str] = set()
    stack = [root_id] if root_id in by_id else []
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            errors.append(f"{node_id}: cycle or duplicate traversal")
            continue
        seen.add(node_id)
        stack.extend(by_id[node_id].get("child_ids", []))
    if len(seen) != len(nodes):
        errors.append(f"hierarchy has {len(nodes) - len(seen)} unreachable nodes")
    return errors

