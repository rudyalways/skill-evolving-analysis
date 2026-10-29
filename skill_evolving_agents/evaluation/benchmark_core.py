#!/usr/bin/env python3
"""Stage-addressable benchmark runner with golden decisions and review gates.

The runner treats a benchmark case as a stage contract plus expected behavior,
not as a fixed position in the current workflow.  Deterministic adapters reuse
the funnel harness.  Golden adapters validate a human-reviewable diagnosis and
action against the pipeline contracts without invoking an agent.

Generated reports and dashboards are local artifacts; cases and fixtures are
the versioned inputs.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


EVALUATION = Path(__file__).resolve().parent
AGENTS = EVALUATION.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


funnel = _load("benchmark_funnel", EVALUATION / "funnel_benchmark.py")
runner = funnel.runner
contracts = runner.pipeline_contracts
DEFAULT_CASES = EVALUATION / "cases"
DEFAULT_PROFILE = AGENTS / "profiles/action-oriented-local-service.json"
RESOURCE_KINDS = ("scripts", "references", "assets", "agents", "evals")
OPERATION_KINDS = ("create", "update", "merge", "split", "delete", "no_change")
REVIEW_STATES = ("pending", "approved", "rejected")
SECTIONS = ("overview", "when_to_use", "workflow", "verification")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_cases(root: Path) -> list[dict[str, Any]]:
    root = root.resolve()
    paths: list[Path]
    if root.is_file():
        paths = [root]
    else:
        paths = sorted(root.rglob("*.json"))
    cases: list[dict[str, Any]] = []
    for path in paths:
        value = _read_json(path)
        rows = value if isinstance(value, list) else [value]
        for row in rows:
            if not isinstance(row, dict):
                raise SystemExit(f"{path}: case must be an object or list of objects")
            case = dict(row)
            try:
                case_file = str(path.resolve().relative_to(EVALUATION.resolve()))
            except ValueError:
                case_file = str(path)
            case.setdefault("case_file", case_file)
            case.setdefault("review", {"status": "pending"})
            review = case["review"]
            if not isinstance(review, dict):
                raise SystemExit(f"{case.get('case_id', path)}: review must be an object")
            status = str(review.get("status") or "pending")
            if status not in REVIEW_STATES:
                raise SystemExit(
                    f"{case.get('case_id', path)}: review.status must be one of "
                    f"{', '.join(REVIEW_STATES)}"
                )
            case["review"] = {**review, "status": status}
            if not case.get("case_id"):
                raise SystemExit(f"{path}: case_id is required")
            if not case.get("stage"):
                raise SystemExit(f"{case['case_id']}: stage is required")
            cases.append(case)
    ids = [str(case["case_id"]) for case in cases]
    duplicates = sorted(name for name, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise SystemExit("duplicate case ids: " + ", ".join(duplicates))
    return cases


def _operation_records(operation: dict[str, Any]) -> list[dict[str, Any]]:
    kind = str(operation.get("op") or "")
    if kind in {"create", "update"}:
        return [
            row for row in operation.get("skills") or []
            if isinstance(row, dict) and row.get("skill")
        ]
    if kind == "merge":
        into = operation.get("into")
        return [into] if isinstance(into, dict) and into.get("skill") else []
    if kind == "split":
        return [
            row for row in operation.get("into") or []
            if isinstance(row, dict) and row.get("skill")
        ]
    return []


def _resource_plan(resources: list[str]) -> list[dict[str, Any]]:
    selected = set(resources)
    return [
        {
            "resource": resource,
            "decision": "use" if resource in selected else "omit",
            "reason": (
                "The golden action names this resource."
                if resource in selected
                else "The golden action does not justify this resource."
            ),
            "confidence": 0.9,
        }
        for resource in RESOURCE_KINDS
    ]


def _dirs(resources: list[str], skill: str) -> list[dict[str, str]]:
    return [
        {"dir": resource, "goal": f"Author the {resource} resource for {skill}."}
        for resource in resources
    ]


def _sections(names: list[str], skill: str) -> list[dict[str, str]]:
    return [
        {"section": name, "goal": f"Preserve the {name} behavior in {skill}."}
        for name in names
    ]


def _labels() -> list[dict[str, Any]]:
    return [
        {"type": "job/methodology", "weight": 0.9},
        {"type": "form/pattern", "weight": 0.8},
        {"type": "artifact/document", "weight": 0.7},
    ]


def _skill_record(
    compact: dict[str, Any], *, operation: str
) -> dict[str, Any]:
    skill = str(compact.get("skill") or "")
    if not skill:
        raise ValueError(f"{operation} action requires skill")
    resources = [
        str(value) for value in compact.get("resources") or []
        if str(value) in RESOURCE_KINDS
    ]
    sections = [
        str(value) for value in compact.get("sections") or SECTIONS
        if str(value)
    ]
    record: dict[str, Any] = {
        "skill": skill,
        "description": str(
            compact.get("description") or f"Reusable {skill} workflow."
        ),
        "sections": _sections(sections, skill),
        "dirs": _dirs(resources, skill),
        "resource_plan": _resource_plan(resources),
    }
    if operation == "update":
        record["goal"] = str(compact.get("goal") or f"Improve {skill}.")
        record["facet"] = str(compact.get("facet") or "workflow")
    if operation == "create":
        record["labels"] = compact.get("labels") or _labels()
        record["dependencies"] = []
    return record


def compile_golden_goal(case: dict[str, Any]) -> dict[str, Any]:
    golden = case.get("golden") or {}
    compact = golden.get("action") or {}
    kind = str(compact.get("op") or "no_change")
    cluster = str(case.get("cluster") or case["case_id"])
    source = str(compact.get("skill") or "")
    if kind == "no_change":
        ops: list[dict[str, Any]] = []
        disposition = "no_change"
    elif kind in {"create", "update"}:
        if compact.get("skills"):
            records = [dict(row) for row in compact["skills"] if isinstance(row, dict)]
        else:
            records = [compact]
        ops = [{"op": kind, "skills": [
            _skill_record(record, operation=kind) for record in records
        ]}]
        disposition = kind
    elif kind == "merge":
        sources = [str(value) for value in compact.get("sources") or []]
        into = dict(compact.get("into") or compact)
        into["skill"] = str(into.get("skill") or "")
        if len(sources) < 2:
            raise ValueError("merge action requires at least two sources")
        if not into["skill"]:
            raise ValueError("merge action requires into.skill")
        ops = [{
            "op": "merge",
            "skills": sources,
            "into": _skill_record(into, operation="merge"),
        }]
        disposition = "merge"
    elif kind == "split":
        if not source:
            raise ValueError("split action requires skill")
        parts = [
            _skill_record(dict(part), operation="split")
            for part in compact.get("into") or []
            if isinstance(part, dict)
        ]
        if len(parts) < 2:
            raise ValueError("split action requires at least two into parts")
        ops = [{"op": "split", "skill": source, "into": parts}]
        disposition = "split"
    elif kind == "delete":
        if not source:
            raise ValueError("delete action requires skill")
        ops = [{
            "op": "delete",
            "skills": [{"skill": source, "reason": str(compact.get("reason") or "Retired by golden case.")}],
        }]
        disposition = "delete"
    else:
        raise ValueError(f"unsupported golden action: {kind}")
    improve = sorted({
        name for op in ops for name in _operation_skill_names(op)
    })
    return {
        "goal": {
            "improve_harness": {"scope": "out_of_scope"},
            "improve_skills": improve,
            "avoid": "Do not invent behavior absent from the golden decision.",
        },
        "reasoning": str(golden.get("reasoning") or "Golden decision for this stage."),
        "plan": str(golden.get("plan") or "Apply the named operation."),
        "feedback_to": "diagnosis",
        "action": {
            "disposition": disposition,
            "reason": str(compact.get("reason") or "Golden no-change decision."),
            "ops": ops,
        },
    }


def _operation_skill_names(operation: dict[str, Any]) -> list[str]:
    names: list[str] = []
    if operation.get("op") in {"create", "update"}:
        for row in operation.get("skills") or []:
            if isinstance(row, dict) and row.get("skill"):
                names.append(str(row["skill"]))
    elif operation.get("op") == "merge":
        names.extend(str(value) for value in operation.get("skills") or [])
        into = operation.get("into")
        if isinstance(into, dict) and into.get("skill"):
            names.append(str(into["skill"]))
    elif operation.get("op") == "split":
        if operation.get("skill"):
            names.append(str(operation["skill"]))
        for row in operation.get("into") or []:
            if isinstance(row, dict) and row.get("skill"):
                names.append(str(row["skill"]))
    elif operation.get("op") == "delete":
        for row in operation.get("skills") or []:
            if isinstance(row, dict) and row.get("skill"):
                names.append(str(row["skill"]))
    result: list[str] = []
    for name in names:
        if name not in result:
            result.append(name)
    return result


def compile_golden_diagnosis(case: dict[str, Any]) -> dict[str, Any]:
    golden = case.get("golden") or {}
    diagnosis = golden.get("diagnosis") or {}
    cluster = str(case.get("cluster") or case["case_id"])
    gaps = []
    for gap in diagnosis.get("gaps") or []:
        if not isinstance(gap, dict):
            continue
        evidence = [
            str(value) for value in gap.get("evidence") or []
            if str(value).strip()
        ] or [str(gap.get("description") or "Golden case evidence.")]
        gaps.append({
            "type": str(gap.get("type") or "job/methodology"),
            "cluster": cluster,
            "description": str(gap.get("description") or "Golden capability gap."),
            "confidence": float(gap.get("confidence") or 0.9),
            "reasoning": str(gap.get("reasoning") or "Golden diagnosis reasoning."),
            "evidence_list": evidence,
        })
    return {
        "skill_capabilities_missing": gaps,
        "newly_detected_skill_capabilites_missing": [],
    }


def _validate_golden(case: dict[str, Any], root: Path) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    cluster = str(case.get("cluster") or case["case_id"])
    diagnosis = compile_golden_diagnosis(case)
    goal = compile_golden_goal(case)
    case_root = root / case["case_id"]
    case_root.mkdir(parents=True, exist_ok=True)
    diagnosis_path = case_root / "diagnosis.json"
    goal_path = case_root / "goal.json"
    _write_json(diagnosis_path, diagnosis)
    _write_json(goal_path, goal)
    try:
        contracts.validate_diagnosis(
            diagnosis_path, {cluster} if diagnosis["skill_capabilities_missing"] else None
        )
    except Exception as error:
        failures.append(f"golden diagnosis contract: {type(error).__name__}: {error}")
    try:
        if goal["action"]["ops"]:
            contracts.validate_goal(goal_path, exactly_one_op=True)
        else:
            contracts.validate_goal(goal_path)
    except Exception as error:
        failures.append(f"golden goal contract: {type(error).__name__}: {error}")
    expect = case.get("expect") or {}
    operation_types = [
        str(op.get("op") or "unknown") for op in goal["action"]["ops"]
    ]
    if expect.get("operation_types") is not None:
        expected_types = [str(value) for value in expect["operation_types"]]
        if operation_types != expected_types:
            failures.append(
                f"golden action: expected operations {expected_types}, "
                f"compiled {operation_types}"
            )
    if expect.get("diagnosis_gap_types") is not None:
        actual = [
            str(row.get("type")) for row in diagnosis["skill_capabilities_missing"]
        ]
        expected = [str(value) for value in expect["diagnosis_gap_types"]]
        if actual != expected:
            failures.append(
                f"golden diagnosis: expected {expected}, compiled {actual}"
            )
    if expect.get("resource_decisions") is not None:
        expected = {
            str(row.get("resource")): str(row.get("decision"))
            for row in expect["resource_decisions"] if isinstance(row, dict)
        }
        actual: dict[str, str] = {}
        for operation in goal["action"]["ops"]:
            for record in _operation_records(operation):
                for row in record.get("resource_plan") or []:
                    if isinstance(row, dict) and row.get("resource"):
                        actual[str(row["resource"])] = str(row.get("decision"))
        for resource, decision in expected.items():
            if actual.get(resource) != decision:
                failures.append(
                    f"golden resources: {resource} expected {decision}, "
                    f"compiled {actual.get(resource)}"
                )
    return {
        "diagnosis": diagnosis,
        "goal": goal,
        "operation_types": operation_types,
    }, failures


def run_golden_case(
    case: dict[str, Any], root: Path, profile: dict[str, Any]
) -> dict[str, Any]:
    failures: list[str] = []
    observed: dict[str, Any] = {}
    if case.get("sessions"):
        trace_case = dict(case)
        trace_expect = {
            key: value
            for key, value in (case.get("expect") or {}).items()
            if key not in {
                "operation_types",
                "diagnosis_gap_types",
                "resource_decisions",
            }
        }
        trace_expect.setdefault("replay_after_apply", False)
        trace_case["expect"] = trace_expect
        trace_result = funnel.run_trace_case(trace_case, root, profile)
        observed["trace"] = trace_result.get("observed")
        failures.extend(trace_result.get("failures") or [])
    golden, golden_failures = _validate_golden(case, root)
    observed["golden"] = golden
    failures.extend(golden_failures)
    return {
        "case_id": case["case_id"],
        "stage": case.get("stage", "golden"),
        "split": case.get("split", "calibration"),
        "layer": "golden",
        "passed": not failures,
        "failures": failures,
        "review": case.get("review") or {"status": "pending"},
        "boundaries": {"golden_decisions": 1},
        "observed": observed,
    }


STAGE_ADAPTERS = {
    "trace": funnel.run_trace_case,
    "signals": funnel.run_trace_case,
    "preprocessing": funnel.run_trace_case,
    "admission": funnel.run_trace_case,
    "semantic": funnel.run_semantic_case,
    "semantic_prefilter": funnel.run_semantic_case,
    "idempotency": funnel.run_idempotency_case,
    "replay": funnel.run_idempotency_case,
    "creation_policy": funnel.run_creation_case,
    "goal_policy": funnel.run_creation_case,
    "resource": funnel.run_resource_case,
    "resource_usefulness": funnel.run_resource_case,
}


def register_adapter(stage: str, handler) -> None:
    """Register a stage runner for future workflow stages."""
    STAGE_ADAPTERS[str(stage)] = handler


def run_case(
    case: dict[str, Any], root: Path, profile: dict[str, Any],
    *, require_reviewed: bool = False,
) -> dict[str, Any]:
    stage = str(case.get("stage") or "")
    if case.get("golden"):
        result = run_golden_case(case, root, profile)
    elif stage in STAGE_ADAPTERS:
        result = STAGE_ADAPTERS[stage](case, root, profile)
    else:
        result = {
            "case_id": case["case_id"],
            "stage": stage,
            "split": case.get("split", "calibration"),
            "layer": "unknown",
            "passed": False,
            "failures": [f"unknown case stage: {stage}"],
            "review": case.get("review") or {"status": "pending"},
            "boundaries": {},
            "observed": {},
        }
    result["stage"] = str(result.get("stage") or stage)
    result["review"] = case.get("review") or {"status": "pending"}
    result["case_file"] = case.get("case_file")
    if require_reviewed and result["review"].get("status") != "approved":
        result["passed"] = False
        result["failures"] = list(result.get("failures") or []) + [
            "review: required approval, status is "
            + str(result["review"].get("status") or "pending")
        ]
    return result


def run_suite(
    cases: list[dict[str, Any]],
    root: Path,
    profile: dict[str, Any],
    *,
    require_reviewed: bool = False,
    stage: str | None = None,
    split: str | None = None,
) -> dict[str, Any]:
    selected = [
        case for case in cases
        if (stage is None or case.get("stage") == stage)
        and (split is None or case.get("split") == split)
    ]
    results = [
        run_case(case, root, profile, require_reviewed=require_reviewed)
        for case in selected
    ]
    return _aggregate(results)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(bool(row.get("passed")) for row in rows)
    reviews = Counter(str((row.get("review") or {}).get("status") or "pending") for row in rows)
    return {
        "cases": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "pass_rate": round(passed / len(rows), 6) if rows else None,
        "review_pending": reviews.get("pending", 0),
        "review_approved": reviews.get("approved", 0),
        "review_rejected": reviews.get("rejected", 0),
        "failure_reasons": dict(sorted(Counter(
            str(reason).split(":", 1)[0]
            for row in rows for reason in row.get("failures") or []
        ).items())),
    }


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_stage = {
        stage: _summary([row for row in results if row.get("stage") == stage])
        for stage in sorted({str(row.get("stage")) for row in results})
    }
    by_split = {
        split: _summary([row for row in results if row.get("split") == split])
        for split in sorted({str(row.get("split")) for row in results})
    }
    boundaries: dict[str, int] = defaultdict(int)
    for row in results:
        for key, value in (row.get("boundaries") or {}).items():
            boundaries[key] += int(value)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "overall": _summary(results),
        "by_stage": by_stage,
        "by_split": by_split,
        "boundaries": dict(sorted(boundaries.items())),
        "cases": results,
    }


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_dashboard(report: dict[str, Any], path: Path) -> Path:
    rows = report.get("cases") or []
    summary = report.get("overall") or {}
    review = {
        "pending": summary.get("review_pending", 0),
        "approved": summary.get("review_approved", 0),
        "rejected": summary.get("review_rejected", 0),
    }
    stage_rows = "".join(
        f"<tr><td>{_esc(stage)}</td><td>{_esc(data.get('cases'))}</td>"
        f"<td>{_esc(data.get('passed'))}</td><td>{_esc(data.get('failed'))}</td>"
        f"<td>{_esc(data.get('review_pending'))}</td></tr>"
        for stage, data in (report.get("by_stage") or {}).items()
    )
    case_rows = []
    details = []
    for row in rows:
        status = "PASS" if row.get("passed") else "FAIL"
        review_status = (row.get("review") or {}).get("status", "pending")
        failures = "<br>".join(_esc(value) for value in row.get("failures") or []) or "—"
        case_rows.append(
            "<tr>"
            f"<td>{_esc(row.get('case_id'))}</td>"
            f"<td>{_esc(row.get('stage'))}</td>"
            f"<td>{_esc(row.get('split'))}</td>"
            f"<td class=\"{'ok' if status == 'PASS' else 'bad'}\">{status}</td>"
            f"<td>{_esc(review_status)}</td>"
            f"<td>{failures}</td>"
            "</tr>"
        )
        golden = (row.get("observed") or {}).get("golden") or {}
        details.append(
            "<details>"
            f"<summary>{_esc(row.get('case_id'))} — {status} / {_esc(review_status)}</summary>"
            f"<h3>Failures</h3><pre>{_esc(json.dumps(row.get('failures') or [], indent=2))}</pre>"
            f"<h3>Golden diagnosis</h3><pre>{_esc(json.dumps(golden.get('diagnosis'), indent=2))}</pre>"
            f"<h3>Golden action</h3><pre>{_esc(json.dumps(golden.get('goal'), indent=2))}</pre>"
            f"<h3>Trace observations</h3><pre>{_esc(json.dumps((row.get('observed') or {}).get('trace'), indent=2))}</pre>"
            "</details>"
        )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Skill evolution benchmark</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       margin: 2rem auto; max-width: 1200px; padding: 0 1rem; line-height: 1.45; }}
h1 {{ margin-bottom: .2rem; }}
.muted {{ color: #777; }}
.cards {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1rem 0; }}
.card {{ border: 1px solid #8884; border-radius: .5rem; padding: .75rem 1rem; min-width: 9rem; }}
.card b {{ display: block; font-size: 1.6rem; }}
table {{ border-collapse: collapse; width: 100%; margin: .75rem 0 1.5rem; }}
th, td {{ text-align: left; border-bottom: 1px solid #8884; padding: .4rem .5rem; vertical-align: top; }}
th {{ font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; }}
.ok {{ color: #16803c; font-weight: 600; }}
.bad {{ color: #b42318; font-weight: 600; }}
pre {{ white-space: pre-wrap; overflow-wrap: anywhere; font-size: .78rem;
       background: #8881; padding: .75rem; border-radius: .4rem; }}
details {{ margin: .6rem 0; }}
summary {{ cursor: pointer; font-weight: 600; }}
</style></head><body>
<h1>Skill evolution benchmark</h1>
<p class="muted">Generated {_esc(report.get('generated_at'))} · stage-addressable cases</p>
<div class="cards">
  <div class="card"><span>Cases</span><b>{_esc(summary.get('cases'))}</b></div>
  <div class="card"><span>Passed</span><b>{_esc(summary.get('passed'))}</b></div>
  <div class="card"><span>Failed</span><b>{_esc(summary.get('failed'))}</b></div>
  <div class="card"><span>Review pending</span><b>{_esc(review['pending'])}</b></div>
  <div class="card"><span>Approved</span><b>{_esc(review['approved'])}</b></div>
</div>
<h2>By stage</h2>
<table><thead><tr><th>Stage</th><th>Cases</th><th>Passed</th><th>Failed</th><th>Pending review</th></tr></thead>
<tbody>{stage_rows or '<tr><td colspan="5">No cases.</td></tr>'}</tbody></table>
<h2>Cases</h2>
<table><thead><tr><th>Case</th><th>Stage</th><th>Split</th><th>Status</th><th>Review</th><th>Failures</th></tr></thead>
<tbody>{''.join(case_rows) or '<tr><td colspan="6">No cases.</td></tr>'}</tbody></table>
<h2>Review details</h2>
{''.join(details) or '<p>No case details.</p>'}
</body></html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--stage", help="run one stage only")
    parser.add_argument("--split", choices=("calibration", "heldout"))
    parser.add_argument("--require-reviewed", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--dashboard", type=Path)
    parser.add_argument("--keep-workspaces", type=Path)
    args = parser.parse_args()
    cases = load_cases(args.cases)
    profile = _read_json(args.profile)
    if args.keep_workspaces:
        root = args.keep_workspaces
        root.mkdir(parents=True, exist_ok=True)
    else:
        root = Path(tempfile.mkdtemp(prefix="stage-benchmark-"))
    try:
        report = run_suite(
            cases,
            root,
            profile,
            require_reviewed=args.require_reviewed,
            stage=args.stage,
            split=args.split,
        )
    finally:
        if not args.keep_workspaces:
            shutil.rmtree(root, ignore_errors=True)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered)
    if args.dashboard:
        render_dashboard(report, args.dashboard)
    print(rendered)
    raise SystemExit(0 if report["overall"]["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
