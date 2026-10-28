from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Protocol
import hashlib
import json


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}_{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


@dataclass(frozen=True)
class CanonicalRequest:
    schema_version: int
    run_id: str
    sample_id: str
    messages: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalEvent:
    schema_version: int
    event_id: str
    run_id: str
    event_type: str
    timestamp: str
    data: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HealthResult:
    healthy: bool
    detail: str = ""


@dataclass(frozen=True)
class AdapterCapabilities:
    streaming: bool = True
    cancellation: bool = False
    tools: bool = False


class TargetAdapter(Protocol):
    name: str

    async def health(self) -> HealthResult: ...
    async def capabilities(self) -> AdapterCapabilities: ...
    def invoke(self, request: CanonicalRequest) -> AsyncIterator[CanonicalEvent]: ...
    async def cancel(self, run_id: str) -> None: ...

