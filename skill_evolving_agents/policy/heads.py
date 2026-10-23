"""Translate the knob registry into neural/search output-head metadata."""

from __future__ import annotations

from typing import Any

from core.optimization import _domain_values


def build_head_specs(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    heads: dict[str, dict[str, Any]] = {}
    for name, knob in registry["knobs"].items():
        if not knob.get("mutable"):
            continue
        kind = knob.get("type")
        domain = knob.get("domain") or {}
        values = _domain_values(knob)
        if kind == "boolean":
            head_type = "binary"
        elif "values" in domain or kind == "integer":
            head_type = "categorical"
        else:
            head_type = "bounded_numeric"
        if name.startswith("score.") and name.endswith("_weight"):
            head_type = "simplex_member"
        heads[name] = {
            "head_type": head_type,
            "target": knob["target"],
            "path": knob["path"],
            "risk": knob.get("risk", "quality"),
            "default": knob.get("default"),
            "domain": domain,
            "choices": values if head_type == "categorical" else None,
            "dependencies": knob.get("requires", {}),
        }
    return heads
