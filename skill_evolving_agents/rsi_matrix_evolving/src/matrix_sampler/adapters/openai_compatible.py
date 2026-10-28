from __future__ import annotations

import asyncio
import json
import os
import urllib.request

from matrix_sampler.models import AdapterCapabilities, CanonicalEvent, CanonicalRequest, HealthResult, stable_id, utcnow


class OpenAICompatibleAdapter:
    name = "openai_compatible"

    def __init__(self, base_url: str, model: str, api_key_env: str):
        self.base_url, self.model, self.api_key_env = base_url.rstrip("/"), model, api_key_env

    async def health(self):
        return HealthResult(bool(os.getenv(self.api_key_env)), f"credential env {self.api_key_env}")

    async def capabilities(self):
        return AdapterCapabilities(streaming=False, cancellation=False, tools=True)

    async def invoke(self, request: CanonicalRequest):
        def call():
            body = json.dumps({"model": self.model, "messages": request.messages}).encode()
            req = urllib.request.Request(self.base_url + "/chat/completions", body, {"Content-Type": "application/json", "Authorization": "Bearer " + os.environ[self.api_key_env]})
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.load(response)
        data = await asyncio.to_thread(call)
        yield CanonicalEvent(1, stable_id("evt", request.run_id), request.run_id, "response.completed", utcnow(), {"text": data["choices"][0]["message"].get("content", ""), "usage": data.get("usage", {})}, {"adapter": self.name})

    async def cancel(self, run_id: str):
        return None

