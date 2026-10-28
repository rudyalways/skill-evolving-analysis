from __future__ import annotations

import asyncio
import json
import os
import urllib.request

from matrix_sampler.models import AdapterCapabilities, CanonicalEvent, CanonicalRequest, HealthResult, stable_id, utcnow


class AgentHTTPAdapter:
    """Submit/poll/cancel adapter for a conventional asynchronous agent API."""
    name = "agent_http"

    def __init__(self, base_url: str, api_key_env: str | None = None, poll_seconds: float = .25):
        self.base_url, self.api_key_env, self.poll_seconds = base_url.rstrip("/"), api_key_env, poll_seconds
        self.remote_runs = {}

    def _call(self, method, path, body=None):
        headers = {"content-type": "application/json"}
        if self.api_key_env: headers["authorization"] = "Bearer " + os.environ[self.api_key_env]
        req = urllib.request.Request(self.base_url + path, json.dumps(body).encode() if body is not None else None, headers, method=method)
        with urllib.request.urlopen(req, timeout=120) as response: return json.load(response)

    async def health(self):
        try: await asyncio.to_thread(self._call, "GET", "/health")
        except Exception as exc: return HealthResult(False, type(exc).__name__)
        return HealthResult(True, "agent endpoint")

    async def capabilities(self): return AdapterCapabilities(True, True, True)

    async def invoke(self, request: CanonicalRequest):
        submitted = await asyncio.to_thread(self._call, "POST", "/runs", {"run_id": request.run_id, "messages": request.messages, "metadata": request.metadata})
        remote_id = submitted.get("id", request.run_id); self.remote_runs[request.run_id] = remote_id
        cursor = None
        while True:
            suffix = f"?cursor={cursor}" if cursor else ""
            state = await asyncio.to_thread(self._call, "GET", f"/runs/{remote_id}{suffix}")
            for i, item in enumerate(state.get("events", [])):
                yield CanonicalEvent(1, stable_id("evt", [request.run_id, cursor, i, item]), request.run_id, item.get("event_type", "agent.event"), item.get("timestamp", utcnow()), item.get("data", item), {"adapter": self.name, "remote_run_id": remote_id})
            cursor = state.get("cursor", cursor)
            if state.get("status") in {"completed", "failed", "cancelled"}: break
            await asyncio.sleep(self.poll_seconds)

    async def cancel(self, run_id: str):
        if run_id in self.remote_runs: await asyncio.to_thread(self._call, "POST", f"/runs/{self.remote_runs[run_id]}/cancel", {})

