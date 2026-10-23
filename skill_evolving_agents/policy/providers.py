"""Policy-provider interface with a fixed-profile implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Callable

from core.optimization import OptimizationError

from .contracts import stable_digest, validate_policy_decision


def _get_path(document: dict[str, Any], dotted: str) -> Any:
    value: Any = document
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise OptimizationError(f"configuration path does not exist: {dotted}")
        value = value[part]
    return value


class PolicyProvider(ABC):
    @abstractmethod
    def decide(
        self,
        features: dict[str, Any],
        base_documents: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        raise NotImplementedError


class FixedPolicy(PolicyProvider):
    """Represent existing configuration as a deterministic policy decision."""

    def __init__(self, registry: dict[str, Any], revision: str = "fixed-profile/v1"):
        self.registry = registry
        self.revision = revision

    def decide(
        self,
        features: dict[str, Any],
        base_documents: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        actions = {}
        for name, spec in self.registry["knobs"].items():
            if not spec.get("mutable") or spec["target"] not in base_documents:
                continue
            try:
                value = _get_path(base_documents[spec["target"]], spec["path"])
            except OptimizationError:
                continue
            actions[name] = {
                "value": value,
                "probability": 1.0,
                "head_type": "fixed",
            }
        identity = {
            "run_id": features["run_id"],
            "provider": "fixed",
            "provider_revision": self.revision,
            "feature_digest": features["feature_digest"],
            "actions": actions,
        }
        decision = {
            "schema_version": 1,
            "decision_id": "decision-" + stable_digest(identity)[7:19],
            **identity,
            "created_at": datetime.now(UTC).isoformat(),
            "uncertainty": 0.0,
            "stage": "production",
        }
        return validate_policy_decision(decision)


class CandidatePolicy(PolicyProvider):
    """Adapt grid/random/wide-deep/MCTS candidates to the policy contract."""

    def __init__(
        self,
        candidate: dict[str, Any],
        *,
        provider: str = "search",
        revision: str = "candidate-policy/v1",
        stage: str = "offline",
    ):
        self.candidate = candidate
        self.provider = provider
        self.revision = revision
        self.stage = stage

    def decide(self, features: dict[str, Any], base_documents: dict[str, dict[str, Any]]) -> dict[str, Any]:
        del base_documents
        actions = {
            name: {
                "value": value,
                "probability": (self.candidate.get("probabilities") or {}).get(name),
                "head_type": "search",
            }
            for name, value in (self.candidate.get("overrides") or {}).items()
        }
        identity = {
            "run_id": features["run_id"],
            "provider": self.provider,
            "provider_revision": self.revision,
            "feature_digest": features["feature_digest"],
            "actions": actions,
        }
        return validate_policy_decision(
            {
                "schema_version": 1,
                "decision_id": "decision-" + stable_digest(identity)[7:19],
                **identity,
                "created_at": datetime.now(UTC).isoformat(),
                "uncertainty": self.candidate.get("uncertainty"),
                "stage": self.stage,
            }
        )


class ModelPolicy(PolicyProvider):
    """Model-agnostic adapter for a future transformer inference runtime."""

    def __init__(
        self,
        infer: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        checkpoint_revision: str,
        stage: str = "shadow",
    ):
        self.infer = infer
        self.checkpoint_revision = checkpoint_revision
        self.stage = stage

    def decide(self, features: dict[str, Any], base_documents: dict[str, dict[str, Any]]) -> dict[str, Any]:
        del base_documents
        output = self.infer(features)
        actions = output.get("actions")
        identity = {
            "run_id": features["run_id"],
            "provider": "transformer",
            "provider_revision": self.checkpoint_revision,
            "feature_digest": features["feature_digest"],
            "actions": actions,
        }
        return validate_policy_decision(
            {
                "schema_version": 1,
                "decision_id": "decision-" + stable_digest(identity)[7:19],
                **identity,
                "created_at": datetime.now(UTC).isoformat(),
                "uncertainty": output.get("uncertainty"),
                "ood_score": output.get("ood_score"),
                "value_predictions": output.get("value_predictions", {}),
                "stage": self.stage,
                "checkpoint": self.checkpoint_revision,
            }
        )
