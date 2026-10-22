"""Allowlisted strategy registry and profile validation."""

from __future__ import annotations

import re
from typing import Any, Iterable

from .contracts import MiningConfigError, Profile, STAGES, RunSpec, StrategySpec
from .strategies import BUILTINS


class Registry:
    def __init__(self, strategies: Iterable[StrategySpec] = BUILTINS) -> None:
        self._strategies: dict[tuple[str, str], StrategySpec] = {}
        for strategy in strategies:
            if strategy.stage not in STAGES:
                raise MiningConfigError(f"unknown strategy stage: {strategy.stage}")
            key = (strategy.stage, strategy.name)
            if key in self._strategies:
                raise MiningConfigError(
                    f"duplicate strategy registration: {strategy.stage}.{strategy.name}"
                )
            self._strategies[key] = strategy

    def get(self, stage: str, name: str) -> StrategySpec:
        try:
            return self._strategies[(stage, name)]
        except KeyError as error:
            raise MiningConfigError(
                f"unknown {stage} strategy: {name}"
            ) from error

    def configure(self, profile: Profile) -> tuple[RunSpec, list[StrategySpec]]:
        run = RunSpec()
        selected: list[StrategySpec] = []
        for stage in STAGES:
            strategy = self.get(stage, profile.stages[stage])
            strategy.configure(run, profile.options.get(stage, {}))
            selected.append(strategy)
        by_stage = {strategy.stage: strategy for strategy in selected}
        links = (
            ("adapter", "selector"),
            ("selector", "evidence"),
            ("selector", "projector"),
            ("projector", "feature"),
            ("clusterer", "namer"),
        )
        for source, target in links:
            if by_stage[source].produces != by_stage[target].accepts:
                raise MiningConfigError(
                    f"incompatible strategies: {by_stage[source].identity} -> "
                    f"{by_stage[target].identity}"
                )
        feature_output = by_stage["feature"].produces
        if not (
            by_stage["clusterer"].accepts == feature_output
            or (
                by_stage["clusterer"].accepts == "vectors"
                and feature_output.endswith("_vectors")
            )
        ):
            raise MiningConfigError(
                f"incompatible strategies: {by_stage['feature'].identity} -> "
                f"{by_stage['clusterer'].identity}"
            )
        return run, selected


def load_profile(config: dict[str, Any], name: str | None = None) -> Profile:
    profile_name = name or config.get("active_profile")
    profiles = config.get("profiles")
    if not isinstance(profile_name, str) or not isinstance(profiles, dict):
        raise MiningConfigError("config requires active_profile and profiles")
    if (
        not re.fullmatch(r"[A-Za-z0-9_-]+", profile_name)
        or profile_name in {".", ".."}
    ):
        raise MiningConfigError(f"unsafe mining profile name: {profile_name}")
    raw = profiles.get(profile_name)
    if not isinstance(raw, dict):
        raise MiningConfigError(f"unknown mining profile: {profile_name}")
    stages = raw.get("stages")
    if not isinstance(stages, dict):
        raise MiningConfigError(f"profile {profile_name} requires stages")
    missing = [stage for stage in STAGES if not isinstance(stages.get(stage), str)]
    extra = sorted(set(stages) - set(STAGES))
    if missing or extra:
        raise MiningConfigError(
            f"profile {profile_name} stage mismatch; missing={missing}, extra={extra}"
        )
    options = raw.get("options", {})
    if not isinstance(options, dict) or any(
        stage not in STAGES or not isinstance(value, dict)
        for stage, value in options.items()
    ):
        raise MiningConfigError(f"profile {profile_name} has invalid options")
    return Profile(profile_name, dict(stages), dict(options))
