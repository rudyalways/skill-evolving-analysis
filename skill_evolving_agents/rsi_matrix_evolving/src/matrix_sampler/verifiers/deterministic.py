from __future__ import annotations


def fuse(labels: list[dict]) -> dict:
    deterministic_failures = [x for x in labels if x["source"] in {"deterministic", "schema", "invariant"} and x["value"] is False]
    if deterministic_failures:
        return {"value": False, "source": "deterministic_precedence", "confidence": 1.0, "disagreement": any(x["value"] is True for x in labels)}
    true_weight = sum(x.get("confidence", 1) for x in labels if x["value"] is True)
    false_weight = sum(x.get("confidence", 1) for x in labels if x["value"] is False)
    return {"value": true_weight >= false_weight, "source": "label_fusion", "confidence": max(true_weight, false_weight) / max(1e-9, true_weight + false_weight), "disagreement": true_weight > 0 and false_weight > 0}


def verify_events(events: list[dict]) -> list[dict]:
    completed = [e for e in events if e["event_type"] == "response.completed"]
    ok = bool(completed) and completed[-1]["data"].get("structured", {}).get("success", completed[-1]["data"].get("text") == "PASS")
    return [{"name": "task_success", "source": "deterministic", "value": bool(ok), "confidence": 1.0}]

