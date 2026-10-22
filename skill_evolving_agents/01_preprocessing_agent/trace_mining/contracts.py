"""Contracts shared by trace-mining strategies and the execution engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


STAGES = (
    "adapter",
    "selector",
    "evidence",
    "projector",
    "feature",
    "clusterer",
    "namer",
)


class MiningConfigError(ValueError):
    """Raised before processing when a mining profile is invalid."""


@dataclass
class RunSpec:
    """Mutable execution choices configured by registered strategies."""

    source_adapter: str = ""
    selector: str = ""
    evidence_policy: str = ""
    projector: str = ""
    vector_strategy: str = ""
    clusterer: str = ""
    namer: str = ""
    clustered: bool = True
    options: dict[str, Any] = field(default_factory=dict)


Configure = Callable[[RunSpec, dict[str, Any]], None]


@dataclass(frozen=True)
class StrategySpec:
    stage: str
    name: str
    version: str
    configure: Configure
    accepts: str
    produces: str

    @property
    def identity(self) -> str:
        return f"{self.stage}:{self.name}@{self.version}"


@dataclass(frozen=True)
class Profile:
    name: str
    stages: dict[str, str]
    options: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class MiningResult:
    profile: str
    output_root: str
    fingerprint: str
    normalization: dict[str, Any]
    signals: dict[str, Any]
    clustering: dict[str, Any]
