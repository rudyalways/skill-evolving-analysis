"""Resolve phase algorithms against shared canonical contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .service_tiers import ServiceTierError, resolve_service


class SuperConfigError(ValueError):
    pass


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def load_super_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SuperConfigError(f"cannot load super config {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise SuperConfigError("super config schema_version must be 1")
    if not isinstance(value.get("contracts"), dict):
        raise SuperConfigError("super config contracts must be an object")
    if not isinstance(value.get("algorithms"), dict):
        raise SuperConfigError("super config algorithms must be an object")
    value = json.loads(json.dumps(value))
    value["config_digest"] = _digest(value)
    return value


def resolve_execution_config(
    profile: dict[str, Any], super_config: dict[str, Any], service_tiers: dict[str, Any]
) -> dict[str, Any]:
    algorithms = super_config["algorithms"]
    contracts = super_config["contracts"]
    resolved: dict[str, Any] = {}
    max_cost_tier = profile.get("max_cost_tier", 3)
    if not isinstance(max_cost_tier, int) or isinstance(max_cost_tier, bool) or max_cost_tier not in range(4):
        raise SuperConfigError("profile max_cost_tier must be 0, 1, 2, or 3")
    for phase, selection in profile["phases"].items():
        algorithm_name = selection.get("algorithm")
        if selection["mode"] == "disabled":
            resolved[phase] = {**selection, "algorithm": "disabled"}
            continue
        if not isinstance(algorithm_name, str) or not algorithm_name:
            raise SuperConfigError(f"phase {phase} must select an algorithm")
        algorithm = algorithms.get(algorithm_name)
        if not isinstance(algorithm, dict):
            raise SuperConfigError(
                f"phase {phase} selects unknown algorithm {algorithm_name!r}"
            )
        if algorithm.get("phase") != phase:
            raise SuperConfigError(
                f"algorithm {algorithm_name!r} belongs to phase "
                f"{algorithm.get('phase')!r}, not {phase!r}"
            )
        if algorithm.get("status", "implemented") != "implemented":
            raise SuperConfigError(
                f"algorithm {algorithm_name!r} is registered but not implemented"
            )
        if algorithm.get("kind") != selection.get("kind"):
            raise SuperConfigError(
                f"phase {phase} kind {selection.get('kind')!r} does not match "
                f"algorithm {algorithm_name!r} kind {algorithm.get('kind')!r}"
            )
        contract = contracts.get(phase)
        if not isinstance(contract, dict):
            raise SuperConfigError(f"phase {phase} has no canonical contract")
        if algorithm.get("canonical_input") != contract.get("input"):
            raise SuperConfigError(
                f"algorithm {algorithm_name!r} has incompatible canonical input"
            )
        if algorithm.get("canonical_output") != contract.get("output"):
            raise SuperConfigError(
                f"algorithm {algorithm_name!r} has incompatible canonical output"
            )
        try:
            service = resolve_service(
                algorithm_name, algorithm, selection, service_tiers, max_cost_tier
            )
        except ServiceTierError as error:
            raise SuperConfigError(str(error)) from error
        resolved[phase] = {
            **selection,
            "algorithm_spec": algorithm,
            "contract": contract,
            "service": service,
        }
    document = {
        "schema_version": 1,
        "profile": profile["name"],
        "profile_digest": profile["config_digest"],
        "super_config_digest": super_config["config_digest"],
        "service_tiers_digest": service_tiers["config_digest"],
        "max_cost_tier": max_cost_tier,
        "preferred_cost_tier": profile.get("preferred_cost_tier", max_cost_tier),
        "budgets": profile.get("budgets", {}),
        "shared": super_config.get("shared", {}),
        "phases": resolved,
    }
    document["config_digest"] = _digest(document)
    return document

