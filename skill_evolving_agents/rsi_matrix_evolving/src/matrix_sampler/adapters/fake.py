from __future__ import annotations

import random

from matrix_sampler.models import AdapterCapabilities, CanonicalEvent, CanonicalRequest, HealthResult, stable_id, utcnow


class FakeTargetAdapter:
    name = "model_callable"

    def __init__(self, success_rate: float = 0.7):
        self.success_rate = success_rate

    async def health(self):
        return HealthResult(True, "in-process deterministic fake")

    async def capabilities(self):
        return AdapterCapabilities(streaming=True, cancellation=False, tools=False)

    async def invoke(self, request: CanonicalRequest):
        seed = int(stable_id("", request.sample_id)[1:9], 16)
        ok = random.Random(seed).random() < self.success_rate
        data = {"text": "PASS" if ok else "FAIL", "structured": {"success": ok}}
        yield CanonicalEvent(1, stable_id("evt", [request.run_id, "response"]), request.run_id, "response.completed", utcnow(), data, {"adapter": self.name})

    async def cancel(self, run_id: str):
        return None

