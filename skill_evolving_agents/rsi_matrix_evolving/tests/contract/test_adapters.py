import pytest

from matrix_sampler.adapters.fake import FakeTargetAdapter
from matrix_sampler.adapters.replay import TraceReplayAdapter
from matrix_sampler.models import CanonicalRequest


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", [FakeTargetAdapter(1), TraceReplayAdapter(), TraceReplayAdapter("tests/fixtures/synthetic-traces.jsonl")])
async def test_adapter_contract(adapter):
    assert (await adapter.health()).healthy
    assert (await adapter.capabilities()).streaming
    events = [event async for event in adapter.invoke(CanonicalRequest(1, "run_1", "sample_1", [{"role": "user", "content": "hello"}]))]
    assert events and all(event.run_id == "run_1" for event in events)
    await adapter.cancel("run_1")

