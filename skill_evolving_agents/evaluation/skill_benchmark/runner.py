"""Run the golden-skill benchmark against deterministic agents."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .agent import IncompleteAgent, ReferenceAgent
from .cms import CMS
from .golden import GoldenSkill
from .simulator import Simulator
from .tasks import Task, load_task_cards


AGENTS = {
    "reference": ReferenceAgent,
    "incomplete": IncompleteAgent,
}


def _build_cms(task: Task) -> CMS:
    cms = CMS()
    if task.seed_slug:
        cms.seed_page(
            title=task.seed_title or task.seed_slug,
            slug=task.seed_slug,
            body=task.seed_body,
        )
    for fault in task.faults:
        cms.inject_fault(str(fault.get("tool")), str(fault.get("code")))
    return cms


def run_task(
    skill: GoldenSkill,
    task: Task,
    *,
    agent_name: str = "reference",
) -> dict[str, Any]:
    agent_cls = AGENTS.get(agent_name)
    if agent_cls is None:
        raise ValueError(f"unknown agent: {agent_name}")
    cms = _build_cms(task)
    simulator = Simulator(skill, task, cms, agent=agent_cls(task))
    trace = simulator.run()
    trace["agent"] = agent_name
    trace["seed"] = task.seed
    return trace


def _summary(traces: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(bool(trace.get("passed")) for trace in traces)
    failures = Counter(
        failure
        for trace in traces
        for failure in (trace.get("verification") or {}).get("failures") or []
    )
    return {
        "tasks": len(traces),
        "passed": passed,
        "failed": len(traces) - passed,
        "pass_rate": round(passed / len(traces), 4) if traces else None,
        "expected_refusals": sum(
            trace.get("expected") == "refusal" for trace in traces
        ),
        "refusals_passed": sum(
            trace.get("expected") == "refusal" and trace.get("passed")
            for trace in traces
        ),
        "repaired": sum(bool(trace.get("repaired")) for trace in traces),
        "tool_calls": sum(int(trace.get("tool_call_count") or 0) for trace in traces),
        "verification_failures": dict(sorted(failures.items())),
    }


def run_benchmark(
    skill_root: Path | str,
    *,
    count: int = 10,
    agent_name: str = "reference",
) -> dict[str, Any]:
    skill = GoldenSkill.load(skill_root)
    tasks = load_task_cards(skill.root, count)
    traces = [
        run_task(skill, task, agent_name=agent_name)
        for task in tasks
    ]
    return {
        "schema_version": 1,
        "skill": {
            "skill_id": skill.skill_id,
            "title": skill.title,
            "source": skill.source,
            "review": skill.review,
        },
        "agent": agent_name,
        "overall": _summary(traces),
        "tasks": traces,
    }


def write_report(report: dict[str, Any], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return path
