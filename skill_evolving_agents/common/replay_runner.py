"""Execute paired held-out skill replay through a configured evaluator command."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import skill_evaluation


def _sha(path: Path | None) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path and path.is_file() else None


def _evaluate(command: str, request: dict[str, Any], timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(
        shlex.split(command),
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        env={**os.environ, "SKILL_EVOLVER_REPLAY": "1"},
    )
    elapsed = time.monotonic() - started
    if completed.returncode:
        return {"passed": False, "activated": False, "errors": 1, "time_seconds": elapsed, "tokens": 0, "tool_calls": 0}
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("replay evaluator must return one JSON object on stdout") from error
    if not isinstance(response, dict) or not isinstance(response.get("passed"), bool) or not isinstance(response.get("activated"), bool):
        raise RuntimeError("replay evaluator response requires boolean passed and activated")
    return {
        "passed": response["passed"],
        "activated": response["activated"],
        "errors": int(response.get("errors", 0)),
        "time_seconds": float(response.get("time_seconds", elapsed)),
        "tokens": int(response.get("tokens", 0)),
        "tool_calls": int(response.get("tool_calls", 0)),
    }


def execute(
    workspace: Path,
    skill: str,
    candidate: Path,
    development: Path,
    held_out: Path,
    *,
    command: str | None = None,
    trials: int = 1,
    timeout: int = 120,
) -> dict[str, Any]:
    """Run a real external evaluator; never synthesize an unavailable replay."""
    command = command or os.environ.get("SKILL_EVOLVER_REPLAY_COMMAND")
    if not command:
        return {"available": False, "status": "not_run", "reason": "SKILL_EVOLVER_REPLAY_COMMAND is not configured", "before": None, "after": None}
    development_data = json.loads(development.read_text())
    held_out_data = json.loads(held_out.read_text())
    problems = skill_evaluation.validate_held_out_evals_data(held_out_data, skill, development_data)
    if problems:
        raise RuntimeError("invalid held-out evals: " + "; ".join(problems))
    replay_root = workspace / "run/replay"
    replay_root.mkdir(parents=True, exist_ok=True)
    copied_held_out = replay_root / "held-out-evals.json"
    copied_held_out.write_bytes(held_out.read_bytes())
    runs: list[dict[str, Any]] = []
    activation_rows: list[dict[str, Any]] = []
    cases = [row for row in held_out_data["evals"] if isinstance(row, dict)]
    for configuration in ("without_skill", "with_skill"):
        for run_number in range(1, trials + 1):
            results = []
            for case in cases:
                outcome = _evaluate(command, {
                    "schema_version": 1,
                    "configuration": configuration,
                    "skill": skill,
                    "skill_path": str(candidate) if configuration == "with_skill" else None,
                    "case": case,
                }, timeout)
                results.append(outcome)
                if configuration == "with_skill" and run_number == 1:
                    activation_rows.append({"eval_id": case["id"], "kind": case.get("kind"), "activated": outcome["activated"]})
            runs.append({
                "configuration": configuration,
                "split": "held_out",
                "run_number": run_number,
                "result": {
                    "pass_rate": sum(row["passed"] for row in results) / len(results),
                    "time_seconds": sum(row["time_seconds"] for row in results),
                    "tokens": sum(row["tokens"] for row in results),
                    "tool_calls": sum(row["tool_calls"] for row in results),
                    "errors": sum(row["errors"] for row in results),
                },
            })
    benchmark = {"schema_version": 1, "runs": runs, "run_summary": skill_evaluation.aggregate_benchmark(runs)}
    (replay_root / "benchmark.json").write_text(json.dumps(benchmark, indent=2) + "\n")
    activation = skill_evaluation.aggregate_activation(activation_rows)
    after_runs = [row for row in runs if row["configuration"] == "with_skill"]
    before_runs = [row for row in runs if row["configuration"] == "without_skill"]
    after = {
        "held_out_cases": len(cases),
        "held_out_pass_rate": sum(row["result"]["pass_rate"] for row in after_runs) / len(after_runs),
        "activation_false_positive_rate": activation["false_positive_rate"],
    }
    before = {"held_out_cases": len(cases), "held_out_pass_rate": sum(row["result"]["pass_rate"] for row in before_runs) / len(before_runs)}
    manifest = {
        "run_id": workspace.name,
        "skill": skill,
        "backend": "command",
        "model": os.environ.get("SKILL_EVOLVER_REPLAY_MODEL", "external-evaluator"),
        "generated_at": datetime.now(UTC).isoformat(),
        "candidate_sha256": _sha(candidate / "SKILL.md"),
        "baseline_sha256": None,
        "held_out_sha256": _sha(copied_held_out),
        "configurations": ["without_skill", "with_skill"],
        "trials_per_configuration": trials,
        "eval_ids": [row["id"] for row in development_data["evals"]],
        "held_out_eval_ids": [row["id"] for row in cases],
        "executed": True,
    }
    (replay_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    status = "pass" if after["held_out_pass_rate"] >= before["held_out_pass_rate"] else "fail"
    return {"available": True, "kind": "paired_skill_eval", "status": status, "reason": "Paired held-out evaluator command completed", "before": before, "after": after}
