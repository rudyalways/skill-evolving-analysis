"""Small configuration helpers shared by built-in strategies."""

from __future__ import annotations

from typing import Any

from ..contracts import RunSpec


def set_choice(field: str, value: str):
    def configure(run: RunSpec, options: dict[str, Any]) -> None:
        setattr(run, field, value)
        run.options[field] = dict(options)

    return configure


def evidence_policy(policy: str):
    def configure(run: RunSpec, options: dict[str, Any]) -> None:
        run.evidence_policy = policy
        run.options["evidence_policy"] = dict(options)

    return configure


def clusterer(name: str, enabled: bool):
    def configure(run: RunSpec, options: dict[str, Any]) -> None:
        run.clusterer = name
        run.clustered = enabled
        run.options["clusterer"] = dict(options)

    return configure
