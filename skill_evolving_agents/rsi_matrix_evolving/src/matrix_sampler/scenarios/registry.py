from __future__ import annotations

import json
from pathlib import Path
from jsonschema import Draft202012Validator


def load(path: str | Path = "scenarios/bootstrap/scenarios.json") -> list[dict]:
    data = json.loads(Path(path).read_text())
    rows = data["scenarios"] if isinstance(data, dict) else data
    expanded = []
    for row in rows:
        if "scenario_id" in row:
            expanded.append(row)
            continue
        expanded.append({
            "schema_version": 1,
            "scenario_id": f"bootstrap.{row['key']}.v1",
            "title": row["title"],
            "domain": row["domain"],
            "distribution": {"status": "id_declared", "reference_population": "draft-unknown-target", "reason_codes": ["bootstrap_contract"], "confidence": 0.5, "axis": "none"},
            "capabilities": {"required": [row["cap"]], "prohibited": ["fabricate_tool_result"], "optional": ["ask_clarifying_question"]},
            "interface_requirements": [row["iface"]],
            "risk": {"level": "low", "sandbox_required": row["iface"] in {"agent", "agent_cli", "filesystem", "multi_agent"}},
            "generator": {"kind": "template", "template_id": row["key"] + "-v1", "prompt": row["title"] + ". Difficulty: {difficulty}. Use only synthetic data and provide observable evidence.", "parameter_schema": {"difficulty": ["easy", "medium", "hard"]}},
            "oracle": {"kind": "deterministic", "checks": [row["check"]]},
            "tags": ["bootstrap", "three-difficulty-bands"]
        })
    return expanded


def validate(registry_path: str | Path, schema_path: str | Path = "schemas/scenario.schema.json") -> list[str]:
    validator = Draft202012Validator(json.loads(Path(schema_path).read_text()))
    errors = []
    scenarios = load(registry_path)
    ids = set()
    for i, scenario in enumerate(scenarios):
        errors.extend(f"[{i}] {e.message}" for e in validator.iter_errors(scenario))
        if scenario.get("scenario_id") in ids:
            errors.append(f"[{i}] duplicate scenario_id")
        ids.add(scenario.get("scenario_id"))
    return errors

