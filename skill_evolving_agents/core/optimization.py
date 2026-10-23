"""Reproducible, constraint-first configuration experiment utilities."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class OptimizationError(ValueError):
    pass


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def load_spec(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise OptimizationError(f"cannot load {name} {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise OptimizationError(f"{name} schema_version must be 1")
    return value


def _domain_values(spec: dict[str, Any]) -> list[Any]:
    domain = spec.get("domain") or {}
    if isinstance(domain.get("values"), list) and domain["values"]:
        return domain["values"]
    if all(isinstance(domain.get(key), (int, float)) for key in ("min", "max", "step")):
        minimum, maximum, step = (float(domain[key]) for key in ("min", "max", "step"))
        if step <= 0 or maximum < minimum:
            raise OptimizationError("invalid numeric knob domain")
        values = []
        current = minimum
        while current <= maximum + step / 1000:
            value: Any = round(current, 10)
            if spec.get("type") == "integer":
                value = int(value)
            values.append(value)
            current += step
        return values
    raise OptimizationError("mutable knob requires domain.values or min/max/step")


def validate_knob_registry(registry: dict[str, Any]) -> dict[str, Any]:
    knobs = registry.get("knobs")
    if not isinstance(knobs, dict) or not knobs:
        raise OptimizationError("knob registry requires knobs")
    for name, spec in knobs.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("path"), str):
            raise OptimizationError(f"knob {name} requires a path")
        if spec.get("mutable"):
            values = _domain_values(spec)
            if spec.get("default") not in values:
                raise OptimizationError(f"knob {name} default is outside its domain")
        elif spec.get("type") != "locked":
            raise OptimizationError(f"immutable knob {name} must have type locked")
    return registry


def _constraints_hold(candidate: dict[str, Any], registry: dict[str, Any]) -> bool:
    for rule in registry.get("constraints") or []:
        if rule.get("kind") == "less_equal":
            if candidate[rule["left"]] > candidate[rule["right"]]:
                return False
        elif rule.get("kind") == "sum_between":
            total = sum(float(candidate[name]) for name in rule["members"])
            if not float(rule["min"]) <= total <= float(rule["max"]):
                return False
        else:
            raise OptimizationError(f"unsupported knob constraint {rule.get('kind')!r}")
    return True


def generate_grid(
    registry: dict[str, Any], selected: list[str], *, max_candidates: int = 256
) -> list[dict[str, Any]]:
    validate_knob_registry(registry)
    if max_candidates < 1:
        raise OptimizationError("max_candidates must be positive")
    unknown = set(selected) - set(registry["knobs"])
    if unknown:
        raise OptimizationError(f"unknown knobs: {', '.join(sorted(unknown))}")
    locked = [name for name in selected if not registry["knobs"][name].get("mutable")]
    if locked:
        raise OptimizationError(f"locked knobs cannot be searched: {', '.join(locked)}")
    defaults = {name: spec.get("default") for name, spec in registry["knobs"].items()}
    domains = [_domain_values(registry["knobs"][name]) for name in selected]
    candidates = []
    for values in itertools.product(*domains):
        overrides = dict(zip(selected, values))
        complete = {**defaults, **overrides}
        if not _constraints_hold(complete, registry):
            continue
        row = {"overrides": overrides}
        row["candidate_id"] = "candidate-" + digest(row)[7:19]
        candidates.append(row)
        if len(candidates) > max_candidates:
            raise OptimizationError(
                f"grid exceeds max_candidates={max_candidates}; search fewer knobs"
            )
    return candidates


def set_path(document: dict[str, Any], dotted_path: str, value: Any) -> None:
    target = document
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        child = target.get(part)
        if not isinstance(child, dict):
            raise OptimizationError(f"configuration path does not exist: {dotted_path}")
        target = child
    if parts[-1] not in target:
        raise OptimizationError(f"configuration path does not exist: {dotted_path}")
    target[parts[-1]] = value


def materialize_candidate(
    base_documents: dict[str, dict[str, Any]],
    registry: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    documents = deepcopy(base_documents)
    for name, value in candidate.get("overrides", {}).items():
        spec = registry["knobs"].get(name)
        if not spec or not spec.get("mutable"):
            raise OptimizationError(f"candidate changes unknown or locked knob {name}")
        target = spec["target"]
        if target not in documents:
            raise OptimizationError(f"candidate requires missing document {target}")
        set_path(documents[target], spec["path"], value)
    return documents


def validate_metric_spec(spec: dict[str, Any]) -> dict[str, Any]:
    metrics = spec.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise OptimizationError("metric spec requires metrics")
    for name, row in metrics.items():
        if row.get("direction") not in {"maximize", "minimize"}:
            raise OptimizationError(f"metric {name} has invalid direction")
        if row.get("role") not in {"hard_constraint", "objective"}:
            raise OptimizationError(f"metric {name} has invalid role")
        if not isinstance(row.get("minimum_samples"), int) or row["minimum_samples"] < 1:
            raise OptimizationError(f"metric {name} needs minimum_samples")
    return spec


def summarize_observations(
    observations: list[dict[str, Any]], metric_spec: dict[str, Any]
) -> dict[str, Any]:
    """Aggregate per-example metric values with deterministic 95% intervals."""
    validate_metric_spec(metric_spec)
    result: dict[str, Any] = {}
    for name in metric_spec["metrics"]:
        values = []
        for row in observations:
            metrics = row.get("metrics") if isinstance(row, dict) else None
            value = metrics.get(name) if isinstance(metrics, dict) else None
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))
        if not values:
            continue
        count = len(values)
        mean = sum(values) / count
        if all(value in {0.0, 1.0} for value in values):
            # Wilson score interval behaves sensibly at p=0 and p=1.
            z = 1.959963984540054
            denominator = 1 + z * z / count
            center = (mean + z * z / (2 * count)) / denominator
            radius = z * math.sqrt(
                mean * (1 - mean) / count + z * z / (4 * count * count)
            ) / denominator
            low, high = center - radius, center + radius
            method = "wilson-95"
        elif count > 1:
            variance = sum((value - mean) ** 2 for value in values) / (count - 1)
            radius = 1.959963984540054 * math.sqrt(variance / count)
            low, high = mean - radius, mean + radius
            method = "normal-mean-95"
        else:
            low = high = mean
            method = "single-observation"
        result[name] = {
            "value": round(mean, 8),
            "samples": count,
            "ci95": [round(low, 8), round(high, 8)],
            "interval_method": method,
        }
    return result


def evaluate_candidate(
    baseline: dict[str, Any], candidate: dict[str, Any], metric_spec: dict[str, Any]
) -> dict[str, Any]:
    """Apply hard constraints first, then require a Pareto improvement."""
    validate_metric_spec(metric_spec)
    violations: list[dict[str, Any]] = []
    improvements, regressions = [], []
    for name, spec in metric_spec["metrics"].items():
        base = baseline.get(name)
        trial = candidate.get(name)
        if not isinstance(trial, dict) or not isinstance(trial.get("value"), (int, float)):
            if spec.get("missing") == "fail":
                violations.append({"metric": name, "reason": "missing"})
            continue
        value = float(trial["value"])
        samples = int(trial.get("samples") or 0)
        if samples < spec["minimum_samples"]:
            if spec.get("role") == "hard_constraint":
                violations.append({"metric": name, "reason": "insufficient_samples", "samples": samples})
            continue
        if "minimum" in spec and value < float(spec["minimum"]):
            violations.append({"metric": name, "reason": "below_minimum", "value": value})
        if "maximum" in spec and value > float(spec["maximum"]):
            violations.append({"metric": name, "reason": "above_maximum", "value": value})
        base_value = float(base["value"]) if isinstance(base, dict) and isinstance(base.get("value"), (int, float)) else None
        if base_value is None:
            continue
        delta = value - base_value
        regression = -delta if spec["direction"] == "maximize" else delta
        improvement = delta if spec["direction"] == "maximize" else -delta
        if spec.get("role") == "hard_constraint" and regression > float(spec.get("maximum_regression", 0.0)):
            violations.append({"metric": name, "reason": "regression", "delta": round(delta, 8)})
        if spec.get("role") == "objective":
            if improvement > 0:
                improvements.append(name)
            elif improvement < 0:
                regressions.append(name)
    promotion = metric_spec.get("promotion") or {}
    eligible = not violations
    if not promotion.get("allow_objective_regression", False) and regressions:
        eligible = False
    if len(improvements) < int(promotion.get("minimum_objective_improvements", 1)):
        eligible = False
    return {
        "eligible": eligible,
        "decision": "advance_to_" + str(promotion.get("next_stage", "shadow")) if eligible else "reject",
        "violations": violations,
        "objective_improvements": improvements,
        "objective_regressions": regressions,
    }


def objective_reward(
    baseline: dict[str, Any], candidate: dict[str, Any], metric_spec: dict[str, Any]
) -> float:
    """Weighted relative objective improvement, clipped for stable online EMA."""
    terms = []
    for name, spec in metric_spec["metrics"].items():
        if spec.get("role") != "objective":
            continue
        left, right = baseline.get(name), candidate.get(name)
        if not isinstance(left, dict) or not isinstance(right, dict):
            continue
        if not isinstance(left.get("value"), (int, float)) or not isinstance(right.get("value"), (int, float)):
            continue
        base, trial = float(left["value"]), float(right["value"])
        scale = max(abs(base), 1e-9)
        improvement = (trial - base) / scale
        if spec["direction"] == "minimize":
            improvement = -improvement
        terms.append(float(spec.get("weight", 1.0)) * max(-1.0, min(1.0, improvement)))
    return round(sum(terms) / max(sum(float(row.get("weight", 1.0)) for row in metric_spec["metrics"].values() if row.get("role") == "objective"), 1e-9), 8)


def experiment_manifest(
    *, code_revision: str, dataset_revision: str, profile_digest: str,
    model_revisions: dict[str, str], seed: int, candidates: list[dict[str, Any]],
    registry: dict[str, Any], metric_spec: dict[str, Any]
) -> dict[str, Any]:
    if not all((code_revision, dataset_revision, profile_digest)):
        raise OptimizationError("experiment revisions and profile digest are required")
    body = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "code_revision": code_revision,
        "dataset_revision": dataset_revision,
        "profile_digest": profile_digest,
        "model_revisions": model_revisions,
        "seed": seed,
        "knob_registry_digest": digest(registry),
        "metric_spec_digest": digest(metric_spec),
        "candidates": candidates,
        "stage": "offline",
    }
    body["experiment_id"] = "experiment-" + digest({k: v for k, v in body.items() if k != "created_at"})[7:19]
    return body
