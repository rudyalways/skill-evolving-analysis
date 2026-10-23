"""Versioned contracts shared by heuristic, search, and neural policies."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class PolicyContractError(ValueError):
    pass


def stable_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def validate_feature_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise PolicyContractError("feature record schema_version must be 1")
    for field in ("run_id", "feature_schema", "created_at"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise PolicyContractError(f"feature record requires {field}")
    if not isinstance(value.get("dense"), dict):
        raise PolicyContractError("feature record dense must be an object")
    if not isinstance(value.get("tokens"), list):
        raise PolicyContractError("feature record tokens must be an array")
    return value


def validate_policy_decision(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise PolicyContractError("policy decision schema_version must be 1")
    for field in ("decision_id", "run_id", "provider", "provider_revision"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise PolicyContractError(f"policy decision requires {field}")
    actions = value.get("actions")
    if not isinstance(actions, dict):
        raise PolicyContractError("policy decision actions must be an object")
    for name, row in actions.items():
        if not isinstance(row, dict) or "value" not in row:
            raise PolicyContractError(f"policy action {name} requires value")
        probability = row.get("probability")
        if probability is not None and (
            not isinstance(probability, (int, float))
            or isinstance(probability, bool)
            or not 0 <= float(probability) <= 1
        ):
            raise PolicyContractError(f"policy action {name} probability must be 0..1")
    return value


def validate_compiled_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise PolicyContractError("compiled policy schema_version must be 1")
    if value.get("status") not in {"valid", "rejected"}:
        raise PolicyContractError("compiled policy status must be valid or rejected")
    if not isinstance(value.get("documents"), dict):
        raise PolicyContractError("compiled policy documents must be an object")
    return value
