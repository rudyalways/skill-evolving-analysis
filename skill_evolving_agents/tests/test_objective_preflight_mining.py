from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "objective_preflight_methodology",
    ROOT / "01_preprocessing_agent/trace_mining/methodology.py",
)
methodology = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(methodology)


def _trajectory(
    session: str, task: str, failures: list[dict[str, str]],
    activated_skills: list[str] | None = None,
) -> dict:
    result = json.dumps({
        "reward": 0,
        "verifier_failures": failures,
        "activated_skills": activated_skills or [],
    })
    return {
        "trace_id": f"trace-{session}",
        "session_id": session,
        "task": {"text": task},
        "outcome": {"status": "completed", "error": None},
        "events": [{
            "sequence": 1,
            "status": "failed",
            "phase": "verify",
            "tool": "skillsbench_objective_verifier",
            "arguments_preview": "verify",
            "result_preview": result,
            "targets": [],
        }],
        "phases": [{"phase": "verify"}],
    }


def test_objective_failure_retains_portable_contract_and_classifies() -> None:
    finding = methodology._objective_verifier_failure(
        _trajectory("a", "normalize labs", [{
            "test": "test_range",
            "assertion": "Range errors in Magnesium expected [0.5, 10.0]",
        }]),
        "turn.json",
    )[0]
    lesson = finding["features"]["lesson"]
    assert lesson["failure_classes"] == [
        "numeric-range-invariant",
        "expected-actual-equivalence",
    ]
    assert lesson["portable_preflight_required"] is True
    assert lesson["resource_hint"]["resource"] == "scripts"


def test_objective_failure_attributes_activated_skill() -> None:
    finding = methodology._objective_verifier_failure(
        _trajectory(
            "a", "normalize labs",
            [{"test": "test_range", "assertion": "expected [0, 1]"}],
            ["range-check"],
        ),
        "turn.json",
    )[0]
    assert finding["features"]["lesson"]["attributed_skills"] == ["range-check"]


def test_truncated_objective_payload_retains_activated_skill() -> None:
    trajectory = _trajectory(
        "a", "normalize labs",
        [{"test": "test_range", "assertion": "expected [0, 1]"}],
    )
    trajectory["events"][0]["result_preview"] = (
        '{"reward":0,"activated_skills":["range-check"],"verifier_output":"'
        + "x" * 100
    )
    finding = methodology._objective_verifier_failure(trajectory, "turn.json")[0]
    assert finding["features"]["lesson"]["attributed_skills"] == ["range-check"]


def test_cross_task_objective_failures_consolidate_resource_contract() -> None:
    first = methodology._objective_verifier_failure(
        _trajectory("a", "normalize labs", [{
            "test": "test_range", "assertion": "Range errors expected [0, 1]",
        }]), "a.json")[0]
    second = methodology._objective_verifier_failure(
        _trajectory("b", "classify records", [{
            "test": "test_confidence", "assertion": "Confidence not aligned with evidence",
        }]), "b.json")[0]
    rows = methodology.consolidate_cross_task(
        [first, second], {"cross_task_min_sessions": 2}
    )
    assert len(rows) == 1
    lesson = rows[0]["features"]["lesson"]
    assert lesson["kind"] == "cross_task_portable_preflight"
    assert set(lesson["failure_classes"]) >= {
        "numeric-range-invariant",
        "evidence-calibration-invariant",
    }
    assert lesson["resource_hint"]["decision"] == "use"
    assert set(rows[0]["trace_ids"]) == {"trace-a", "trace-b"}
    assert len(rows[0]["evidence"]) == 2


def test_numeric_oracle_mismatch_requires_independent_recomputation() -> None:
    finding = methodology._objective_verifier_failure(
        _trajectory("geo", "derive a distance", [{
            "test": "test_distance_within_tolerance",
            "assertion": "Expected 3878.27 ± 0.01 km, got 3551.98 km (delta=0.01)",
        }]),
        "geo.json",
    )[0]
    lesson = finding["features"]["lesson"]
    assert "derived-numeric-oracle-mismatch" in lesson["failure_classes"]
    assert lesson["oracle_independence_required"] is True
    assert lesson["validation_strategies"] == [
        "independent-recomputation",
        "metamorphic-checks",
    ]
    assert "must not copy" in lesson["resource_hint"]["reason"]


def test_independent_local_pass_vs_objective_failure_is_contract_conflict() -> None:
    trajectory = _trajectory("geo", "derive a distance", [{
        "test": "test_distance_within_tolerance",
        "assertion": "Expected 3878.27 ± 0.01 km, got 3551.98 km",
    }])
    trajectory["events"].insert(0, {
        "sequence": 0,
        "status": "completed",
        "phase": "verify",
        "tool": "execute",
        "arguments_preview": "python local_check.py",
        "result_preview": "three independent implementations agree; preflight exit=0 status clean",
        "targets": [],
    })
    finding = methodology._objective_verifier_failure(trajectory, "geo.json")[0]
    lesson = finding["features"]["lesson"]
    assert lesson["local_objective_conflict"] is True
    assert lesson["learning_disposition"] == "evaluation-contract-conflict"
    assert len(finding["slice"]["events"]) == 2
