#!/usr/bin/env python3
"""Turn a paired held-out bench into a repeatable gap-and-rerun iteration.

The controller never starts a paid run.  It reads completed jobs, joins paired
reward/call/time evidence with activation and executable-leverage audits, and
emits a bounded gap list plus the next offline actions.  A later iteration is
allowed only when instrumentation gaps are absent; skill-quality gaps are the
work items for the next authoring round.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.benchmark_trial_validity import audit as audit_trial_validity
from evaluation.executable_leverage import measure as measure_leverage
from evaluation.paired_benchmark_report import build_report, load_budgets
from evaluation.skillsbench_skill_usage import audit as audit_skill_usage

INSTRUMENTATION_GAPS = {
    "validity_failure",
    "activation_missing",
    "baseline_drift",
    "baseline_efficiency_failure",
    "task_budget_infeasible",
}


def _trial_dirs(jobs: Path | list[Path]) -> dict[str, list[Path]]:
    rows: dict[str, list[Path]] = defaultdict(list)
    for job in [jobs] if isinstance(jobs, Path) else jobs:
        for result_path in sorted(job.rglob("result.json")):
            path = result_path.parent
            if "__" not in path.name:
                continue
            if not (path / "verifier/reward.txt").is_file():
                continue
            rows[path.name.split("__", 1)[0]].append(path)
    return {task: sorted(paths) for task, paths in rows.items()}


def _selection(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    source = json.loads(path.read_text())
    return {
        task: {
            "selected": [row.get("skill") for row in (value.get("selected") or [])],
            "abstention_reasons": value.get("abstention_reasons") or [],
        }
        for task, value in (source.get("tasks") or {}).items()
    }


def _gap(
    code: str,
    *,
    task_id: str,
    trial: int,
    severity: str,
    evidence: dict[str, Any],
    next_action: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "task_id": task_id,
        "trial": trial,
        "severity": severity,
        "evidence": evidence,
        "next_action": next_action,
    }


def build_iteration(
    baseline: Path | list[Path],
    treatment: Path | list[Path],
    *,
    benchmark: str,
    cohort: str,
    domains: dict[str, str] | None = None,
    budgets: dict[str, Any] | None = None,
    selection: Path | None = None,
    round_id: str = "round-1",
) -> dict[str, Any]:
    active_budgets = budgets if budgets is not None else load_budgets()
    selection_rows = _selection(selection)
    report_selection = (
        {"tasks": selection_rows, "report": str(selection)}
        if selection is not None else None
    )
    report = build_report(
        baseline,
        treatment,
        benchmark=benchmark,
        cohort=cohort,
        exposure="selective-read",
        domains=domains or {},
        selection=report_selection,
        budgets=active_budgets,
    )
    treated = _trial_dirs(treatment)
    gaps: list[dict[str, Any]] = []
    trial_evidence: list[dict[str, Any]] = []
    for row in report["tasks"]:
        task_id = row["task_id"]
        trial = int(row["trial"])
        paths = treated.get(task_id) or []
        path = paths[trial - 1] if trial - 1 < len(paths) else None
        audit: dict[str, Any] = {}
        leverage: dict[str, Any] = {}
        validity: dict[str, Any] = {"valid": True}
        selected = (selection_rows.get(task_id) or {}).get("selected") or []
        expects_activation = bool(selected) if selection_rows else True
        if path is not None:
            trajectory = path / "trajectory/acp_trajectory.jsonl"
            if trajectory.is_file():
                audit = audit_skill_usage(trajectory)
                leverage = measure_leverage(
                    audit,
                    baseline_tool_calls=row["baseline_tool_calls"],
                    treatment_tool_calls=row["treatment_tool_calls"],
                )
                validity = audit_trial_validity(trajectory, task_id)
        trial_evidence.append({
            "task_id": task_id,
            "trial": trial,
            "treatment_path": str(path) if path else None,
            "valid": bool(validity.get("valid")),
            "activated": bool(audit.get("activated")),
            "expected_activation": expects_activation,
            "leverage_claim": leverage.get("claim"),
            "baseline_outcome": row["baseline_outcome"],
            "treatment_outcome": row["treatment_outcome"],
        })
        if not validity.get("valid", True):
            gaps.append(_gap(
                "validity_failure",
                task_id=task_id,
                trial=trial,
                severity="instrumentation",
                evidence={"reasons": validity.get("reasons") or []},
                next_action="Exclude the contaminated trial and rerun the cell.",
            ))
        if expects_activation and audit and not audit.get("activated"):
            gaps.append(_gap(
                "activation_missing",
                task_id=task_id,
                trial=trial,
                severity="instrumentation",
                evidence={"activation_mode": audit.get("activation_mode")},
                next_action=(
                    "Fix skill discovery/advertising and rerun; do not treat this "
                    "as a no-effect result."
                ),
            ))
        if row["treatment_outcome"] == "efficiency_failure":
            gaps.append(_gap(
                "efficiency_failure",
                task_id=task_id,
                trial=trial,
                severity="efficiency",
                evidence=row["treatment_budget"],
                next_action=(
                    "Tighten the skill workflow or scope; keep the hard budget "
                    "and rerun only after the expected call/time path is shorter."
                ),
            ))
        if row["baseline_outcome"] == "efficiency_failure":
            infeasible = not row["baseline_passed"]
            gaps.append(_gap(
                "task_budget_infeasible"
                if infeasible
                else "baseline_efficiency_failure",
                task_id=task_id,
                trial=trial,
                severity="efficiency",
                evidence=row["baseline_budget"],
                next_action=(
                    "The task is not feasible under the hard call budget: its "
                    "baseline already failed while exceeding the limit. Do not "
                    "rerun the same setup; raise the budget only with approval, "
                    "or abstain/remove the task."
                )
                if infeasible
                else (
                    "The baseline exceeded the current hard budget. Run a "
                    "matched baseline under the same budget before attributing "
                    "the treatment delta to the skill."
                ),
            ))
        if row["baseline_passed"] and not row["treatment_passed"] and expects_activation:
            gaps.append(_gap(
                "regression",
                task_id=task_id,
                trial=trial,
                severity="quality",
                evidence={
                    "baseline_tool_calls": row["baseline_tool_calls"],
                    "treatment_tool_calls": row["treatment_tool_calls"],
                    "selection": selection_rows.get(task_id),
                },
                next_action=(
                    "Do not promote this skill for the task. Inspect the first "
                    "wrong action and add an intent/abstention or workflow fix."
                ),
            ))
            selected = (selection_rows.get(task_id) or {}).get("selected") or []
            if selected:
                gaps.append(_gap(
                    "router_false_positive",
                    task_id=task_id,
                    trial=trial,
                    severity="routing",
                    evidence={"selected": selected},
                    next_action=(
                        "Add object/action compatibility evidence or calibrated "
                        "negative feedback so the pair abstains."
                    ),
                ))
        if (
            row["baseline_passed"]
            and not row["treatment_passed"]
            and not expects_activation
        ):
            gaps.append(_gap(
                "baseline_drift",
                task_id=task_id,
                trial=trial,
                severity="validity",
                evidence={
                    "baseline_tool_calls": row["baseline_tool_calls"],
                    "treatment_tool_calls": row["treatment_tool_calls"],
                    "selection": selection_rows.get(task_id),
                },
                next_action=(
                    "No skill was expected. This is baseline/model drift or task "
                    "flakiness; rerun a matched baseline under the same setup and "
                    "do not attribute it to a skill."
                ),
            ))
        if audit.get("activated") and leverage:
            if leverage.get("claim") == "reported-executable-leverage":
                gaps.append(_gap(
                    "execution_evidence_reported",
                    task_id=task_id,
                    trial=trial,
                    severity="instrumentation-weak",
                    evidence={
                        "claim": leverage.get("claim"),
                        "reported": leverage.get("resources", {}).get("reported"),
                        "tool_call_reduction": leverage.get("tool_call_reduction"),
                    },
                    next_action=(
                        "Preserve tool-call command input in the ACP export; "
                        "execution is currently self-reported rather than "
                        "observed. Keep the observed output and exit status."
                    ),
                ))
            elif leverage.get("executable_available") and leverage.get("claim") in {
                "discovered-only",
                "opened-only",
                "executed-not-succeeded",
                "succeeded-no-reduction",
            }:
                passed = row["treatment_outcome"] == "passed"
                gaps.append(_gap(
                    "execution_evidence_missing"
                    if passed
                    else "no_executable_leverage",
                    task_id=task_id,
                    trial=trial,
                    severity="instrumentation-weak" if passed else "skill-design",
                    evidence={
                        "claim": leverage.get("claim"),
                        "tool_call_reduction": leverage.get("tool_call_reduction"),
                        "resources": leverage.get("resources"),
                    },
                    next_action=(
                        "The treatment passed and reduced calls, but ACP did "
                        "not retain command input. Preserve tool-call inputs; "
                        "do not treat this as missing skill execution."
                    )
                    if passed
                    else (
                        "Put the exact producer/checker command at the top of "
                        "SKILL.md and make direct execution the first step."
                    ),
                ))
        if not row["baseline_passed"] and not row["treatment_passed"]:
            gaps.append(_gap(
                "still_failing",
                task_id=task_id,
                trial=trial,
                severity="quality",
                evidence={
                    "baseline_tool_calls": row["baseline_tool_calls"],
                    "treatment_tool_calls": row["treatment_tool_calls"],
                    "activation": audit.get("activation_mode"),
                    "leverage_claim": leverage.get("claim"),
                },
                next_action=(
                    "Inspect the treatment trajectory's first wrong action and "
                    "the verifier failure; change the skill or abstain before "
                    "rerunning."
                ),
            ))
        if (
            row["baseline_passed"]
            and row["treatment_passed"]
            and row["treatment_tool_calls"] >= row["baseline_tool_calls"] + 10
            and row["treatment_tool_calls"] > row["baseline_tool_calls"] * 1.25
        ):
            gaps.append(_gap(
                "efficiency_regression",
                task_id=task_id,
                trial=trial,
                severity="efficiency",
                evidence={
                    "baseline_tool_calls": row["baseline_tool_calls"],
                    "treatment_tool_calls": row["treatment_tool_calls"],
                    "additional_calls": (
                        row["treatment_tool_calls"] - row["baseline_tool_calls"]
                    ),
                },
                next_action=(
                    "Quality is preserved but cost regressed. Do not promote for "
                    "this task until the skill removes over-verification or the "
                    "router abstains."
                ),
            ))
        if (
            not row["baseline_passed"]
            and not row["treatment_passed"]
            and row["treatment_tool_calls"] >= row["baseline_tool_calls"]
        ):
            gaps.append(_gap(
                "no_lift_no_efficiency",
                task_id=task_id,
                trial=trial,
                severity="quality",
                evidence={
                    "baseline_tool_calls": row["baseline_tool_calls"],
                    "treatment_tool_calls": row["treatment_tool_calls"],
                },
                next_action=(
                    "Do not iterate this skill blindly; change the finding, the "
                    "workflow, or the router evidence first."
                ),
            ))
    gaps.sort(key=lambda gap: (
        {"instrumentation": 0, "efficiency": 1, "routing": 2, "quality": 3, "skill-design": 4}
        .get(gap["severity"], 9),
        gap["task_id"],
        gap["trial"],
        gap["code"],
    ))
    instrumentation_gaps = [gap for gap in gaps if gap["code"] in INSTRUMENTATION_GAPS]
    summary = {
        "schema_version": 1,
        "round_id": round_id,
        "benchmark": benchmark,
        "cohort": cohort,
        "paired_tasks": report["paired_tasks"],
        "budgets": active_budgets,
        "accuracy": report["accuracy"],
        "efficiency": report["efficiency"],
        "gap_count": len(gaps),
        "gaps_by_code": {
            code: sum(gap["code"] == code for gap in gaps)
            for code in sorted({gap["code"] for gap in gaps})
        },
        "instrumentation_gaps": len(instrumentation_gaps),
        "ready_for_next_round": not instrumentation_gaps,
        "next_round_blocked_by": [gap["code"] for gap in instrumentation_gaps],
        "gaps": gaps,
        "trials": trial_evidence,
        "paired_report": report,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, nargs="+", required=True)
    parser.add_argument("--treatment", type=Path, nargs="+", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--domains", type=Path)
    parser.add_argument("--budgets", type=Path)
    parser.add_argument("--selection-report", type=Path)
    parser.add_argument("--round-id", default="round-1")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    domains = json.loads(args.domains.read_text()) if args.domains else {}
    budgets = load_budgets(args.budgets) if args.budgets else None
    report = build_iteration(
        args.baseline,
        args.treatment,
        benchmark=args.benchmark,
        cohort=args.cohort,
        domains=domains,
        budgets=budgets,
        selection=args.selection_report,
        round_id=args.round_id,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "round_id": report["round_id"],
        "paired_tasks": report["paired_tasks"],
        "gap_count": report["gap_count"],
        "gaps_by_code": report["gaps_by_code"],
        "ready_for_next_round": report["ready_for_next_round"],
        "next_round_blocked_by": report["next_round_blocked_by"],
    }, indent=2))


if __name__ == "__main__":
    main()
