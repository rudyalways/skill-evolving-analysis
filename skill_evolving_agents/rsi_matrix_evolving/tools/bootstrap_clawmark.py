#!/usr/bin/env python3
"""Build a matrix-sampler bootstrap registry from ClawMark task metadata.

The source files are parsed as Python syntax and never imported or executed.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path


def assignment(tree: ast.AST, name: str):
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"missing {name}")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def scenario(path: Path) -> dict:
    tree = ast.parse(path.read_text(), filename=str(path))
    metadata = assignment(tree, "METADATA")
    source_prompt = assignment(tree, "PROMPT")
    category = slug(str(metadata.get("category") or path.parent.parent.name))
    environments = [slug(str(value)) for value in metadata.get("environments", [])]
    tags = [slug(str(value)) for value in metadata.get("tags", [])]
    topic = tags[0] if tags else slug(str(metadata["name"]))
    environment = environments[0] if environments else "general_workspace"
    capability = topic or "stateful_workspace_execution"
    task_id = slug(str(metadata["id"]))
    role = str(metadata.get("role") or category.replace("_", " "))
    title = str(metadata["name"])
    prompt = (
        f"ClawMark capability probe: {title}. You are acting as {role}. "
        f"The source task begins: {source_prompt} "
        f"It may involve these stateful services: {', '.join(environments) or 'workspace'}. "
        "For difficulty {difficulty}, give a concise execution plan, name the state you would re-check after an unannounced next-day change, "
        "and state one deterministic success criterion. Do not claim that you actually accessed unavailable services."
    )
    return {
        "schema_version": 1,
        "scenario_id": f"clawmark.{task_id}.v1",
        "title": title,
        "domain": [category, environment, topic],
        "distribution": {
            "status": "id_declared",
            "reference_population": "ClawMark-100",
            "reason_codes": ["imported_benchmark_contract"],
            "confidence": 1.0,
            "axis": "multi_day_state_change",
        },
        "capabilities": {
            "required": [capability],
            "prohibited": ["fabricate_tool_result"],
            "optional": ["detect_exogenous_change", "revalidate_external_state"],
        },
        "interface_requirements": ["stateful_workspace"],
        "risk": {"level": "low", "sandbox_required": True},
        "generator": {
            "kind": "benchmark_metadata_probe",
            "template_id": f"clawmark-{task_id}-v1",
            "prompt": prompt,
            "parameter_schema": {"difficulty": ["easy", "medium", "hard"]},
        },
        "oracle": {"kind": "evidence_capture", "checks": ["nonempty_response", "no_fabricated_access"]},
        "tags": [
            "bootstrap", "clawmark", f"benchmark_task:{metadata['id']}",
            f"source_file:{path.resolve()}", f"source_difficulty:{metadata.get('difficulty')}",
            f"source_mm_level:{metadata.get('mm_level')}", *tags, *environments,
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    paths = sorted(args.source.glob("*/*/task.py"))
    scenarios = [scenario(path) for path in paths]
    payload = {
        "schema_version": 1,
        "name": "ClawMark-100 bootstrap matrix",
        "source": str(args.source.resolve()),
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(scenarios)} scenarios to {args.output}")


if __name__ == "__main__":
    main()
