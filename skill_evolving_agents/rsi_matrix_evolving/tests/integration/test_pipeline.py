import asyncio
from pathlib import Path

from matrix_sampler.adapters.fake import FakeTargetAdapter
from matrix_sampler.mining.traces import ingest
from matrix_sampler.runners.batch import run_plan
from matrix_sampler.sampling.planner import plan
from matrix_sampler.scenarios.registry import load
from matrix_sampler.storage.sqlite import Store


def test_resume_and_trace_mining(tmp_path: Path):
    store = Store(tmp_path / "test.db")
    batch = plan(load(), 5, 7, "target")
    for sample in batch["samples"]:
        assert store.add_sample(sample)
    first = asyncio.run(run_plan(store, FakeTargetAdapter(), batch, "fake", 2))
    second = asyncio.run(run_plan(store, FakeTargetAdapter(), batch, "fake", 2))
    assert first["completed"] == 5
    assert second["skipped"] == 5
    summary = ingest("tests/fixtures/synthetic-traces.jsonl", store)
    assert summary["records"] == 2
    assert summary["ood_proposals"]

