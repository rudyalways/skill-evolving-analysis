"""Compile typed policy actions into validated runtime configuration documents."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.optimization import (
    OptimizationError,
    _constraints_hold,
    _domain_values,
    materialize_candidate,
)
from core.profile import validate_profile

from .contracts import stable_digest, validate_compiled_policy, validate_policy_decision


class PolicyCompileError(ValueError):
    pass


class PolicyCompiler:
    def __init__(self, registry: dict[str, Any]):
        self.registry = registry

    def compile(
        self,
        decision: dict[str, Any],
        base_documents: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        validate_policy_decision(decision)
        overrides = {name: row["value"] for name, row in decision["actions"].items()}
        defaults = {
            name: row.get("default") for name, row in self.registry["knobs"].items()
        }
        complete = {**defaults, **overrides}
        errors: list[str] = []
        for name, value in overrides.items():
            spec = self.registry["knobs"].get(name)
            if not spec or not spec.get("mutable"):
                errors.append(f"unknown_or_locked_knob:{name}")
                continue
            values = _domain_values(spec)
            if (spec.get("domain") or {}).get("values") is not None:
                if value not in values:
                    errors.append(f"value_outside_domain:{name}")
            elif not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"non_numeric_value:{name}")
            else:
                domain = spec["domain"]
                if not float(domain["min"]) <= float(value) <= float(domain["max"]):
                    errors.append(f"value_outside_domain:{name}")
        try:
            constraints_hold = _constraints_hold(complete, self.registry)
        except (KeyError, TypeError, ValueError):
            constraints_hold = False
        if not constraints_hold:
            errors.append("cross_knob_constraint_failed")
        try:
            if errors:
                raise OptimizationError(";".join(errors))
            documents = materialize_candidate(
                deepcopy(base_documents), self.registry, {"overrides": overrides}
            )
            if "profile" in documents:
                documents["profile"] = validate_profile(documents["profile"])
        except (OptimizationError, ValueError) as error:
            documents = deepcopy(base_documents)
            message = str(error)
            if message and message not in errors:
                errors.append(message)
        compiled = {
            "schema_version": 1,
            "decision_id": decision["decision_id"],
            "status": "rejected" if errors else "valid",
            "documents": documents,
            "applied_overrides": overrides if not errors else {},
            "errors": errors,
            "compiler_revision": "typed-policy-compiler/v1",
            "registry_digest": stable_digest(self.registry),
        }
        compiled["compiled_digest"] = stable_digest(compiled)
        return validate_compiled_policy(compiled)
