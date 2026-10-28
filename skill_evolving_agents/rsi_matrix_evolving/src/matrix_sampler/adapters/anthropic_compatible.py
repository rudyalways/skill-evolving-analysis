from __future__ import annotations

import asyncio
import json
import os
import urllib.request

from matrix_sampler.models import AdapterCapabilities, CanonicalEvent, CanonicalRequest, HealthResult, stable_id, utcnow


class AnthropicCompatibleAdapter:
    name = "anthropic_compatible"

    def __init__(self, base_url: str, model: str, api_key_env: str):
        self.base_url, self.model, self.api_key_env = base_url.rstrip("/"), model, api_key_env

    async def health(self):
        return HealthResult(bool(os.getenv(self.api_key_env)), f"credential env {self.api_key_env}")

    async def capabilities(self):
        return AdapterCapabilities(streaming=False, cancellation=False, tools=True)

    async def invoke(self, request: CanonicalRequest):
        def call():
            body = json.dumps({"model": self.model, "max_tokens": 2048, "messages": request.messages}).encode()
            headers = {"content-type": "application/json", "x-api-key": os.environ[self.api_key_env], "anthropic-version": "2023-06-01"}
            with urllib.request.urlopen(urllib.request.Request(self.base_url + "/messages", body, headers), timeout=120) as response:
                return json.load(response)
        data = await asyncio.to_thread(call)
        text = "".join(x.get("text", "") for x in data.get("content", []) if x.get("type") == "text")
        yield CanonicalEvent(1, stable_id("evt", request.run_id), request.run_id, "response.completed", utcnow(), {"text": text, "usage": data.get("usage", {})}, {"adapter": self.name})

    async def cancel(self, run_id: str):
        return None

