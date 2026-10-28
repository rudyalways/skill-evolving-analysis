from __future__ import annotations

import json
from pathlib import Path

from matrix_sampler.models import AdapterCapabilities, CanonicalEvent, CanonicalRequest, HealthResult, stable_id, utcnow


class TraceReplayAdapter:
    name = "trace_replay"

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None

    async def health(self):
        return HealthResult(self.path is None or self.path.exists(), "replay source")

    async def capabilities(self):
        return AdapterCapabilities(streaming=True, cancellation=False, tools=True)

    async def invoke(self, request: CanonicalRequest):
        emitted = False
        if self.path:
            for i, line in enumerate(self.path.read_text().splitlines()):
                if not line.strip():
                    continue
                row = json.loads(line)
                emitted = True
                yield CanonicalEvent(1, stable_id("evt", [request.run_id, i]), request.run_id, row.get("event_type", row.get("type", "trace.event")), row.get("timestamp", utcnow()), row, {"adapter": self.name, "source": str(self.path)})
        if not emitted:
            yield CanonicalEvent(1, stable_id("evt", request.run_id), request.run_id, "response.completed", utcnow(), {"text": "PASS", "structured": {"success": True}}, {"adapter": self.name})

    async def cancel(self, run_id: str):
        return None

