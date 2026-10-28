#!/usr/bin/env python3
"""Measure the deterministic evidence-to-publication funnel against labels.

The benchmark intentionally stops before hosted agent calls. It exercises the
cheap, reproducible boundaries that decide whether an expensive stage should
run at all:

  trace -> normalized turns -> deterministic signals -> selection
        -> evolution-gate admission -> resource decisions
  existing changelog + finding -> exact-finding idempotency
  labeled finding + goal operation -> deterministic creation policy
  synthetic embedding scores -> semantic category policy
  authored skill resources + observed use -> resource-usefulness scores

Each case is privacy-safe and synthetic. Run artifacts are written to a
temporary directory by default; only the JSON scorecard is retained when the
caller asks for it.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


AGENTS = Path(__file__).resolve().parents[1]
DEFAULT_CASES = AGENTS / "evaluation/funnel_cases.json"
DEFAULT_PROFILE = AGENTS / "profiles/action-oriented-local-service.json"
CONFIG_PATH = AGENTS / "common/preprocessing-config.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load("funnel_runner", AGENTS / "run_pipeline.py")
contracts = runner.pipeline_contracts
skill_resources = _load(
    "funnel_skill_resources", AGENTS / "common/skill_resources.py"
)

sys.path.insert(0, str(AGENTS / "01_preprocessing_agent"))
from trace_mining import engine as mining_engine  # noqa: E402


class CaseFailure(Exception):
    """A labeled expectation was not met."""


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


def _skill_files(skill: str, files: dict[str, str] | None) -> dict[str, str]:
    base = {
        "SKILL.md": (
            "---\n"
            f"name: {skill}\n"
            "description: Use when the labeled benchmark workflow applies.\n"
            "---\n\n"
            "# Labeled benchmark skill\n\n"
            "Follow the observed workflow and report its verified result.\n"
        )
    }
    base.update(files or {})
    return base


def _seed_skills(workspace: Path, skills: dict[str, Any] | None) -> None:
    for skill, files in sorted((skills or {}).items()):
        directory = workspace / "target/to_be_improved_skills" / skill
        for relative, content in _skill_files(skill, files).items():
            _write_text(directory / relative, str(content))


def _seed_changelogs(workspace: Path, changelogs: dict[str, str] | None) -> None:
    for skill, content in sorted((changelogs or {}).items()):
        _write_text(workspace / "target/skill_changelogs" / f"{skill}.md", content)


def _codex_rows(session: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "timestamp": "2026-10-24T00:00:00Z",
            "ordinal": 1,
            "type": "session_meta",
            "payload": {"session_id": session["id"]},
        }
    ]
    ordinal = 2
    for index, turn in enumerate(session.get("turns") or []):
        turn_id = f"{session['id']}-turn-{index + 1}"
        rows.append(
            {
                "timestamp": f"2026-10-24T00:{index:02d}:00Z",
                "ordinal": ordinal,
                "type": "event_msg",
                "payload": {
                    "type": "task_started",
                    "turn_id": turn_id,
                    "root_turn_id": turn_id,
                },
            }
        )
        ordinal += 1
        rows.append(
            {
                "timestamp": f"2026-10-24T00:{index:02d}:01Z",
                "ordinal": ordinal,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": turn["user"]}],
                },
            }
        )
        ordinal += 1
        for tool_index, tool in enumerate(turn.get("tools") or []):
            call_id = f"{turn_id}-call-{tool_index + 1}"
            rows.append(
                {
                    "timestamp": f"2026-10-24T00:{index:02d}:02Z",
                    "ordinal": ordinal,
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "call_id": call_id,
                        "name": tool.get("name", "exec"),
                        "arguments": tool["arguments"],
                    },
                }
            )
            ordinal += 1
            rows.append(
                {
                    "timestamp": f"2026-10-24T00:{index:02d}:03Z",
                    "ordinal": ordinal,
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": tool.get("output", "ok"),
                    },
                }
            )
            ordinal += 1
        rows.append(
            {
                "timestamp": f"2026-10-24T00:{index:02d}:04Z",
                "ordinal": ordinal,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": turn.get("assistant", "Completed the request."),
                        }
                    ],
                },
            }
        )
        ordinal += 1
        completion: dict[str, Any] = {"type": "task_complete", "turn_id": turn_id}
        if turn.get("outcome_error"):
            completion["error"] = turn["outcome_error"]
        rows.append(
            {
                "timestamp": f"2026-10-24T00:{index:02d}:05Z",
                "ordinal": ordinal,
                "type": "event_msg",
                "payload": completion,
            }
        )
        ordinal += 1
    return rows


def _trace_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for session in case.get("sessions") or []:
        rows.extend(_codex_rows(session))
    return rows


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    result = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def _finding_detectors(findings: list[dict[str, Any]]) -> list[str]:
    return sorted({str(row.get("detector") or "") for row in findings})


def _resource_decisions(workspace: Path) -> list[dict[str, Any]]:
    return _read_jsonl(
        workspace / "traces/derived/signals/resource-opportunity-decisions.jsonl"
    )


def _selection_decisions(workspace: Path) -> list[dict[str, Any]]:
    return _read_jsonl(
        workspace / "traces/derived/signals/selection-decisions.jsonl"
    )


def _expect_subset(
    label: str,
    observed: set[str],
    expected_any: list[str] | None,
    expected_none: list[str] | None,
) -> list[str]:
    failures = []
    if expected_any:
        missing = sorted(set(expected_any) - observed)
        if missing:
            failures.append(f"{label}: missing {missing}")
    if expected_none:
        unexpected = sorted(set(expected_none) & observed)
        if unexpected:
            failures.append(f"{label}: unexpected {unexpected}")
    return failures


def _resource_expectation(
    expect: dict[str, Any], decisions: list[dict[str, Any]]
) -> list[str]:
    failures: list[str] = []
    expected = expect.get("resource_decisions") or []
    for row in expected:
        kind = row.get("resource")
        disposition = row.get("disposition")
        matches = [
            value
            for value in decisions
            if (kind is None or value.get("resource") == kind)
            and (disposition is None or value.get("disposition") == disposition)
        ]
        if not matches:
            failures.append(
                f"resource decisions: expected {kind or 'any'} {disposition or 'any'}"
            )
        elif row.get("reason_contains"):
            reason = str(row["reason_contains"])
            if not any(
                reason in " ".join(str(item) for item in value.get("reason_codes") or [])
                for value in matches
            ):
                failures.append(
                    f"resource decisions: {kind or 'any'} missing reason {reason}"
                )
    forbidden = expect.get("no_resource_decisions") or []
    for row in forbidden:
        kind = row.get("resource")
        disposition = row.get("disposition")
        if any(
            (kind is None or value.get("resource") == kind)
            and (disposition is None or value.get("disposition") == disposition)
            for value in decisions
        ):
            failures.append(
                f"resource decisions: unexpected {kind or 'any'} {disposition or 'any'}"
            )
    return failures


def run_trace_case(case: dict[str, Any], root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    workspace = root / case["case_id"] / "workspace/runs" / case["case_id"]
    (workspace / "traces/raw/codex").mkdir(parents=True)
    for session in case.get("sessions") or []:
        path = workspace / "traces/raw/codex" / f"{session['id']}.jsonl"
        path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in _codex_rows(session))
        )
    _seed_skills(workspace, case.get("skills"))
    _seed_changelogs(workspace, case.get("changelogs"))
    mining_engine.run(
        workspace,
        CONFIG_PATH,
        clustered=False,
        profile_name=case.get("mining_profile", "default"),
    )
    findings = _read_jsonl(workspace / "traces/derived/signals/findings.jsonl")
    selected = _read_jsonl(
        workspace / "traces/derived/signals/selected-manifest.jsonl"
    )
    decisions = _resource_decisions(workspace)
    selected_scopes = sorted(
        path.parent.name
        for path in (workspace / "traces/derived/findings").glob("*/finding.json")
    )
    admitted = runner.low_cost_allowed_scopes(workspace, selected_scopes, profile)
    gate = json.loads(
        (workspace / "traces/derived/evolution-gate.json").read_text()
    )
    found_detectors = set(_finding_detectors(findings))
    selected_detectors = {
        str(row.get("detector") or "") for row in selected if isinstance(row, dict)
    }
    expect = case.get("expect") or {}
    failures: list[str] = []
    failures.extend(
        _expect_subset(
            "findings",
            found_detectors,
            expect.get("findings_any"),
            expect.get("findings_none"),
        )
    )
    if expect.get("selected_any_of"):
        if not any(
            set(group) <= selected_detectors
            for group in expect["selected_any_of"]
        ):
            failures.append(
                "selected: none of "
                f"{expect['selected_any_of']} were selected ({sorted(selected_detectors)})"
            )
    failures.extend(
        _expect_subset(
            "selected",
            selected_detectors,
            expect.get("selected_any"),
            expect.get("selected_none"),
        )
    )
    failures.extend(_resource_expectation(expect, decisions))
    if "admitted" in expect:
        actual = bool(admitted)
        if actual != bool(expect["admitted"]):
            failures.append(
                f"admission: expected {expect['admitted']}, admitted={admitted}"
            )
    if expect.get("admission_reason"):
        reason = str(expect["admission_reason"])
        gate_decisions = {
            str(row.get("scope")): row
            for row in gate.get("decisions") or []
            if isinstance(row, dict)
        }
        reasons = {
            code
            for row in gate_decisions.values()
            if row.get("disposition") == "selected"
            for code in (row.get("reason_codes") or [])
        }
        if reason not in reasons:
            failures.append(f"admission reason missing: {reason} (have {sorted(reasons)})")
    selected_ids = {
        str(row.get("finding_id") or "") for row in selected
    }
    selected_findings = [
        row for row in findings if str(row.get("signal_id") or "") in selected_ids
    ]
    replay_checks = 0
    if expect.get("replay_after_apply", True) and selected_findings:
        replay_skill = "benchmark-replay"
        lines = [f"# {replay_skill}"]
        for row in selected_findings:
            lines.append(
                f"- 2026-10-24 update {row['signal_id']}/1 | benchmark"
            )
        _seed_changelogs(
            workspace, {replay_skill: "\n".join(lines) + "\n"}
        )
        for row in selected_findings:
            applied = runner.previously_applied_finding_skills(
                workspace, str(row["signal_id"]), [], row
            )
            replay_checks += 1
            resource = bool(
                (row.get("features") or {}).get("candidate_source")
                == "resource_opportunity"
            )
            expected_applied = [] if resource else [replay_skill]
            if sorted(applied) != expected_applied:
                failures.append(
                    "idempotent replay: expected "
                    f"{expected_applied} for {row['signal_id']}, got {sorted(applied)}"
                )
    idempotent = expect.get("idempotent_skills")
    if idempotent is not None:
        finding = {
            "session_id": case.get("sessions", [{}])[0].get("id", ""),
            "features": expect.get("idempotent_finding_features") or {},
        }
        applied = runner.previously_applied_finding_skills(
            workspace,
            str(expect.get("finding_id") or ""),
            [],
            finding,
        )
        if sorted(applied) != sorted(idempotent):
            failures.append(
                f"idempotency: expected {sorted(idempotent)}, got {sorted(applied)}"
            )
    return {
        "case_id": case["case_id"],
        "kind": "trace",
        "split": case.get("split", "calibration"),
        "passed": not failures,
        "failures": failures,
        "boundaries": {
            "sessions": len(case.get("sessions") or []),
            "turns": sum(len(session.get("turns") or []) for session in case.get("sessions") or []),
            "findings": len(findings),
            "selected": len(selected),
            "admitted": len(admitted),
            "resource_decisions": len(decisions),
            "replay_checks": replay_checks,
        },
        "observed": {
            "findings": _finding_detectors(findings),
            "selected": sorted(selected_detectors),
            "admitted": sorted(admitted),
            "gate": gate.get("decisions") or [],
            "resource_decisions": decisions,
            "selection_decisions": _selection_decisions(workspace),
        },
    }


def run_semantic_case(case: dict[str, Any], root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    config = dict(profile["phases"]["semantic_prefilter"])
    decision = runner.semantic_category_decision(
        list(case.get("matches") or []), config
    )
    expect = case.get("expect") or {}
    failures = []
    if expect.get("disposition") and decision["disposition"] != expect["disposition"]:
        failures.append(
            f"semantic: expected {expect['disposition']}, got {decision['disposition']}"
        )
    if expect.get("reason_code") and decision["reason_code"] != expect["reason_code"]:
        failures.append(
            f"semantic: expected {expect['reason_code']}, got {decision['reason_code']}"
        )
    return {
        "case_id": case["case_id"],
        "kind": "semantic",
        "split": case.get("split", "calibration"),
        "passed": not failures,
        "failures": failures,
        "boundaries": {"semantic_decisions": 1},
        "observed": decision,
    }


def run_idempotency_case(
    case: dict[str, Any], root: Path, profile: dict[str, Any]
) -> dict[str, Any]:
    workspace = root / case["case_id"] / "workspace/runs" / case["case_id"]
    workspace.mkdir(parents=True)
    _seed_skills(workspace, case.get("skills"))
    _seed_changelogs(workspace, case.get("changelogs"))
    finding = case.get("finding") or {}
    recalled = list(case.get("recalled") or [])
    applied = runner.previously_applied_finding_skills(
        workspace, str(finding.get("signal_id") or ""), recalled, finding
    )
    expect = case.get("expect") or {}
    failures = []
    expected = sorted(expect.get("applied_skills") or [])
    if sorted(applied) != expected:
        failures.append(f"idempotency: expected {expected}, got {sorted(applied)}")
    return {
        "case_id": case["case_id"],
        "kind": "idempotency",
        "split": case.get("split", "calibration"),
        "passed": not failures,
        "failures": failures,
        "boundaries": {"idempotency_checks": 1},
        "observed": {"applied_skills": sorted(applied), "recalled": recalled},
    }


def run_creation_case(
    case: dict[str, Any], root: Path, profile: dict[str, Any]
) -> dict[str, Any]:
    workspace = root / case["case_id"] / "workspace/runs" / case["case_id"]
    cluster = str(case.get("cluster") or "finding")
    finding = dict(case.get("finding") or {})
    finding.setdefault("detector", "labeled-case")
    finding.setdefault("confidence", 0.9)
    finding.setdefault("evidence", [{"trace_id": "labeled:evidence:1"}])
    finding.setdefault("session_id", "labeled-session")
    _write_json(
        workspace / "traces/derived/findings" / cluster / "finding.json", finding
    )
    _write_json(
        workspace / "run" / cluster / "diagnosis.json",
        case.get("diagnosis")
        or {
            "skill_capabilities_missing": [],
            "newly_detected_skill_capabilites_missing": [],
        },
    )
    _seed_skills(workspace, case.get("skills"))
    expect = case.get("expect") or {}
    allowed = True
    error = ""
    try:
        runner.enforce_creation_policy(
            workspace, cluster, {}, dict(case.get("goal_op") or {})
        )
    except contracts.ContractError as exc:
        allowed = False
        error = str(exc)
    failures = []
    if "allowed" in expect and allowed != bool(expect["allowed"]):
        failures.append(
            f"creation policy: expected allowed={expect['allowed']}, got {allowed}"
        )
    if expect.get("error_contains") and expect["error_contains"] not in error:
        failures.append(
            f"creation policy: expected error containing {expect['error_contains']!r}"
        )
    return {
        "case_id": case["case_id"],
        "kind": "creation_policy",
        "split": case.get("split", "calibration"),
        "passed": not failures,
        "failures": failures,
        "boundaries": {"creation_decisions": 1},
        "observed": {"allowed": allowed, "error": error},
    }


def _resource_score(
    document: dict[str, Any], key: str
) -> float | None:
    value: Any = document
    for part in key.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def run_resource_case(
    case: dict[str, Any], root: Path, profile: dict[str, Any]
) -> dict[str, Any]:
    workspace = root / case["case_id"] / "workspace/runs" / case["case_id"]
    skill = str(case.get("skill") or case["case_id"])
    directory = workspace / "target/to_be_improved_skills" / skill
    for relative, content in _skill_files(skill, case.get("files")).items():
        _write_text(directory / relative, str(content))
    document = skill_resources.measure_skill_resources(
        directory,
        evidence=str(case.get("evidence") or ""),
        use_evidence=str(case.get("use_evidence") or ""),
        resource_plan=list(case.get("resource_plan") or []),
        runtime_observation_available=bool(case.get("runtime_observation_available", True)),
    )
    expect = case.get("expect") or {}
    failures = []
    for key, limit in (("min_usefulness", "min"), ("max_usefulness", "max")):
        if key not in expect:
            continue
        actual = _resource_score(document, "observed_usefulness_score")
        if actual is None:
            failures.append(f"resource: {key} unavailable")
            continue
        if limit == "min" and actual < float(expect[key]):
            failures.append(f"resource: usefulness {actual} < {expect[key]}")
        if limit == "max" and actual > float(expect[key]):
            failures.append(f"resource: usefulness {actual} > {expect[key]}")
    penalty_fields = {
        "min_unused_rate": "unused_resource_rate",
        "max_unused_rate": "unused_resource_rate",
        "min_duplicate_rate": "duplicated_content_rate",
        "max_duplicate_rate": "duplicated_content_rate",
    }
    for key, field in penalty_fields.items():
        if key not in expect:
            continue
        actual = _resource_score(document, f"penalties.{field}")
        if actual is None:
            failures.append(f"resource: {field} unavailable")
            continue
        if key.startswith("min") and actual < float(expect[key]):
            failures.append(f"resource: {field} {actual} < {expect[key]}")
        if key.startswith("max") and actual > float(expect[key]):
            failures.append(f"resource: {field} {actual} > {expect[key]}")
    expected_penalized = expect.get("unused_resources")
    if expected_penalized is not None:
        actual = document["penalties"]["unused_resources"]
        if sorted(actual) != sorted(expected_penalized):
            failures.append(
                f"resource: unused {sorted(actual)} != {sorted(expected_penalized)}"
            )
    return {
        "case_id": case["case_id"],
        "kind": "resource",
        "split": case.get("split", "calibration"),
        "passed": not failures,
        "failures": failures,
        "boundaries": {"resource_measurements": 1},
        "observed": {
            "usefulness": document.get("observed_usefulness_score"),
            "penalties": document.get("penalties"),
            "resource_counts": document.get("resource_counts"),
            "progressive_disclosure": document.get("progressive_disclosure"),
        },
    }


RUNNERS = {
    "trace": run_trace_case,
    "semantic": run_semantic_case,
    "idempotency": run_idempotency_case,
    "creation_policy": run_creation_case,
    "resource": run_resource_case,
}


def evaluate(
    cases: list[dict[str, Any]], profile: dict[str, Any], temp_root: Path
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in cases:
        kind = str(case.get("kind") or "trace")
        handler = RUNNERS.get(kind)
        if handler is None:
            results.append(
                {
                    "case_id": case.get("case_id", "unknown"),
                    "kind": kind,
                    "split": case.get("split", "calibration"),
                    "passed": False,
                    "failures": [f"unknown case kind: {kind}"],
                    "boundaries": {},
                    "observed": {},
                }
            )
            continue
        try:
            results.append(handler(case, temp_root, profile))
        except BaseException as exc:  # noqa: BLE001 - benchmark must record every failure
            results.append(
                {
                    "case_id": case.get("case_id", "unknown"),
                    "kind": kind,
                    "split": case.get("split", "calibration"),
                    "passed": False,
                    "failures": [f"execution: {type(exc).__name__}: {exc}"],
                    "boundaries": {},
                    "observed": {},
                }
            )
    return _aggregate(results)


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        passed = sum(bool(row["passed"]) for row in rows)
        return {
            "cases": len(rows),
            "passed": passed,
            "failed": len(rows) - passed,
            "pass_rate": round(passed / len(rows), 6) if rows else None,
            "failure_reasons": dict(
                sorted(
                    Counter(
                        reason.split(":", 1)[0]
                        for row in rows
                        for reason in row.get("failures") or []
                    ).items()
                )
            ),
        }

    by_split = {
        split: summary([row for row in results if row["split"] == split])
        for split in sorted({row["split"] for row in results})
    }
    by_kind = {
        kind: summary([row for row in results if row["kind"] == kind])
        for kind in sorted({row["kind"] for row in results})
    }
    boundaries: dict[str, int] = defaultdict(int)
    for row in results:
        for key, value in (row.get("boundaries") or {}).items():
            boundaries[key] += int(value)
    return {
        "schema_version": 1,
        "overall": summary(results),
        "by_split": by_split,
        "by_kind": by_kind,
        "boundaries": dict(sorted(boundaries.items())),
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--out", type=Path, help="write the full scorecard here")
    parser.add_argument(
        "--keep-workspaces",
        type=Path,
        help="retain per-case workspaces under this directory for inspection",
    )
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())
    if not isinstance(cases, list):
        raise SystemExit("cases file must contain a JSON list")
    profile = json.loads(args.profile.read_text())
    if args.keep_workspaces:
        root = args.keep_workspaces
        root.mkdir(parents=True, exist_ok=True)
    else:
        root = Path(tempfile.mkdtemp(prefix="funnel-benchmark-"))
    try:
        report = evaluate(cases, profile, root)
    finally:
        if not args.keep_workspaces:
            shutil.rmtree(root, ignore_errors=True)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered)
    print(rendered)
    raise SystemExit(0 if report["overall"]["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
