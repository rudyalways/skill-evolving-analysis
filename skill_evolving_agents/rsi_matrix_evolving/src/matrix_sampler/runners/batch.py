from __future__ import annotations

import asyncio
import inspect
from matrix_sampler.models import CanonicalRequest, stable_id, utcnow
from matrix_sampler.verifiers.deterministic import verify_events


async def run_plan(store, adapter, plan: dict, target_id: str, concurrency: int = 4, on_progress=None) -> dict:
    sem = asyncio.Semaphore(concurrency)
    progress_lock = asyncio.Lock()
    results = {"completed": 0, "skipped": 0, "adapter_errors": 0, "target_failures": 0}

    async def one(sample):
        run_id = stable_id("run", [plan["plan_id"], sample["sample_id"], target_id])
        run = {"schema_version": 1, "run_id": run_id, "sample_id": sample["sample_id"], "target_id": target_id, "adapter": adapter.name, "started_at": utcnow()}
        if not store.claim_run(run):
            results["skipped"] += 1
            return
        events = []
        try:
            async with sem:
                request = CanonicalRequest(1, run_id, sample["sample_id"], sample["messages"], sample.get("cell", {}))
                async for event in adapter.invoke(request):
                    row = event.to_dict()
                    events.append(row)
                    store.add_event(row)
            labels = verify_events(events)
            for label in labels:
                store.add_label(run_id, label["source"], label["name"], label["value"], label["confidence"])
            if not labels[0]["value"]:
                results["target_failures"] += 1
            store.finish_run(run_id, "completed", utcnow())
            results["completed"] += 1
        except Exception as exc:
            store.finish_run(run_id, "failed", utcnow(), "adapter_error")
            results["adapter_errors"] += 1
        finally:
            if on_progress:
                async with progress_lock:
                    value = on_progress(dict(results))
                    if inspect.isawaitable(value):
                        await value

    await asyncio.gather(*(one(x) for x in plan["samples"]))
    return results

