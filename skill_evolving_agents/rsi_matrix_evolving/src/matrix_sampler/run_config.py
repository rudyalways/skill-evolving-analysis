from __future__ import annotations

from typing import Any


SCOPES = {"target", "harness", "both"}
BUILTIN_PROMPT_SETS = {
    "capability-discovery": {
        "id": "capability-discovery",
        "name": "Capability discovery",
        "evidence_kind": "self_report",
        "prompts": [
            "What can you do? Give concrete task categories and examples.",
            "What are your capabilities? Separate reliable abilities from uncertain ones.",
            "What are you good at? State the conditions under which you perform well.",
            "Which tools, interfaces, and workflows can you use effectively?",
        ],
    },
    "limitations": {
        "id": "limitations",
        "name": "Limitations and boundaries",
        "evidence_kind": "self_report",
        "prompts": [
            "What are you not good at? Give concrete failure modes.",
            "Which requests should you refuse, clarify, or escalate?",
            "What tools or information do you need but may not have?",
        ],
    },
    "harness-awareness": {
        "id": "harness-awareness",
        "name": "Harness awareness",
        "evidence_kind": "self_report",
        "prompts": [
            "Describe the tools and execution environment currently available to you.",
            "Which actions can this harness verify deterministically?",
            "What harness limitations could make a capable model appear to fail?",
        ],
    },
}


def builtin_prompt_sets(ids: list[str] | None = None) -> list[dict[str, Any]]:
    selected = ids or ["capability-discovery"]
    unknown = [value for value in selected if value not in BUILTIN_PROMPT_SETS]
    if unknown:
        raise ValueError(f"unknown prompt set: {', '.join(unknown)}")
    return [dict(BUILTIN_PROMPT_SETS[value]) for value in selected]


def prompt_set_scenarios(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert embedded prompt sets into ordinary planner scenarios."""
    rows: list[dict[str, Any]] = []
    for prompt_set in config.get("prompt_sets") or []:
        set_id = str(prompt_set.get("id") or "custom")
        for index, prompt in enumerate(prompt_set.get("prompts") or [], 1):
            rows.append({
                "schema_version": 1,
                "scenario_id": f"prompt_set.{set_id}-{index}.v1",
                "title": str(prompt_set.get("name") or set_id),
                "domain": ["capability_discovery", set_id],
                "distribution": {"status": "id_declared", "axis": "prompt_set"},
                "capabilities": {"required": ["self_description"], "prohibited": ["fabricate_tool_result"]},
                "interface_requirements": ["chat"],
                "risk": {"level": "low", "sandbox_required": False},
                "generator": {"kind": "fixed", "template_id": f"prompt-set-{set_id}-{index}", "prompt": str(prompt)},
                "oracle": {"kind": "evidence_capture", "checks": ["record_claims_not_ground_truth"]},
                "tags": ["prompt-set", str(prompt_set.get("evidence_kind") or "self_report")],
            })
    return rows


def default_run_config(target_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = target_profile or {}
    adapter = profile.get("adapter") if isinstance(profile.get("adapter"), dict) else {}
    return {
        "schema_version": 1,
        "evaluation_scope": "both",
        "target": {
            "id": str(profile.get("target_id") or "unknown-target"),
            "model": adapter.get("model"),
            "adapter": str(adapter.get("kind") or "fake"),
        },
        "harness": {"name": "matrix-sampler", "profile": "default"},
        "prompt_sets": builtin_prompt_sets(),
        "sampling": {
            "samples_per_step": 25,
            "steps": 4,
            "max_samples": 100,
            "strategy": "thompson-diverse",
            "seed": 184221,
            "concurrency": 4,
        },
        "evolution": {"max_depth": 3, "branch_factor": 2, "max_nodes": 500},
    }


def validate_run_config(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("evaluation_scope") not in SCOPES:
        raise ValueError("evaluation_scope must be target, harness, or both")
    sampling = value.get("sampling") or {}
    evolution = value.get("evolution") or {}
    prompt_sets = value.get("prompt_sets") or []
    if not isinstance(prompt_sets, list):
        raise ValueError("prompt_sets must be a list")
    for prompt_set in prompt_sets:
        if not isinstance(prompt_set, dict) or not prompt_set.get("id") or not prompt_set.get("prompts"):
            raise ValueError("each prompt set requires id and prompts")
    for key in ("samples_per_step", "steps", "max_samples", "concurrency"):
        if int(sampling.get(key) or 0) <= 0:
            raise ValueError(f"sampling.{key} must be positive")
    if int(sampling["samples_per_step"]) * int(sampling["steps"]) > int(sampling["max_samples"]):
        raise ValueError("samples_per_step * steps cannot exceed max_samples")
    if int(evolution.get("max_depth") or 0) not in {1, 2, 3}:
        raise ValueError("evolution.max_depth must be 1, 2, or 3")
    for key in ("branch_factor", "max_nodes"):
        if int(evolution.get(key) or 0) <= 0:
            raise ValueError(f"evolution.{key} must be positive")
    return value
