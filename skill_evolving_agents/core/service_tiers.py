"""Validate the execution-service layer beneath phase algorithms."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ServiceTierError(ValueError):
    pass


def load_service_tiers(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ServiceTierError(f"cannot load service tiers {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ServiceTierError("service tiers schema_version must be 1")
    services = value.get("services")
    if not isinstance(services, dict) or not services:
        raise ServiceTierError("service tiers must define services")
    for name, service in services.items():
        if not isinstance(service, dict):
            raise ServiceTierError(f"service {name} must be an object")
        tier = service.get("cost_tier")
        if not isinstance(tier, int) or isinstance(tier, bool) or tier not in range(4):
            raise ServiceTierError(f"service {name} cost_tier must be 0, 1, 2, or 3")
        capabilities = service.get("capabilities")
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) and item for item in capabilities
        ):
            raise ServiceTierError(f"service {name} capabilities must be strings")
    normalized = json.loads(json.dumps(value))
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    normalized["config_digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    return normalized


def resolve_service(
    algorithm_name: str,
    algorithm: dict[str, Any],
    selection: dict[str, Any],
    registry: dict[str, Any],
    max_cost_tier: int,
) -> dict[str, Any]:
    service_name = selection.get("service") or algorithm.get("default_service")
    service = registry["services"].get(service_name)
    if not isinstance(service, dict):
        raise ServiceTierError(
            f"algorithm {algorithm_name!r} selects unknown service {service_name!r}"
        )
    required = set(algorithm.get("required_capabilities") or [])
    available = set(service.get("capabilities") or [])
    missing = sorted(required - available)
    if missing:
        raise ServiceTierError(
            f"service {service_name!r} lacks capabilities for {algorithm_name!r}: "
            + ", ".join(missing)
        )
    tier = int(service["cost_tier"])
    if tier > max_cost_tier:
        raise ServiceTierError(
            f"service {service_name!r} tier {tier} exceeds profile max_cost_tier "
            f"{max_cost_tier}"
        )
    return {"name": service_name, **service}

