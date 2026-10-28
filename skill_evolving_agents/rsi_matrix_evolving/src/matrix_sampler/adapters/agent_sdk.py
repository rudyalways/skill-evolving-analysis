from __future__ import annotations

import inspect

from matrix_sampler.models import AdapterCapabilities, CanonicalEvent, CanonicalRequest, HealthResult, stable_id, utcnow


class AgentSDKAdapter:
    """Bridge a local SDK callable returning a result or (async) event iterable."""
    name = "agent_sdk"

    def __init__(self, invoke_callable):
        self.invoke_callable = invoke_callable

    async def health(self): return HealthResult(callable(self.invoke_callable), "SDK callback")
    async def capabilities(self): return AdapterCapabilities(True, False, True)

    async def invoke(self, request: CanonicalRequest):
        result = self.invoke_callable(request)
        if inspect.isawaitable(result): result = await result
        if hasattr(result, "__aiter__"):
            async for item in result:
                yield item if isinstance(item, CanonicalEvent) else self._event(request, item)
        elif isinstance(result, list):
            for item in result: yield item if isinstance(item, CanonicalEvent) else self._event(request, item)
        else:
            yield self._event(request, result)

    def _event(self, request, value):
        data = value if isinstance(value, dict) else {"text": str(value)}
        return CanonicalEvent(1, stable_id("evt", [request.run_id, data]), request.run_id, "response.completed", utcnow(), data, {"adapter": self.name})

    async def cancel(self, run_id: str): return None

