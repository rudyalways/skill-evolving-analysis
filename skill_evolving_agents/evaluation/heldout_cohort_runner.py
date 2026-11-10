#!/usr/bin/env python3
"""Run a pre-registered held-out cohort in parallel with an auditable manifest.

This is the stable loop driver: the cohort spec is frozen before execution, each
task/condition/repetition becomes one ``bench eval run`` command, and the runner
records the exact command, exit code, duration, and jobs directory.  It never
edits skills, never chooses tasks from outcomes, and inherits provider
credentials from the process environment.

Example spec::

    {
      "schema_version": 1,
      "jobs_root": "workspace/skillbench/cohort-x",
      "max_parallel": 2,
      "bench": "bench",
      "agent": "deepagents",
      "model": "deepseek/deepseek-chat",
      "sandbox": "docker",
      "common_args": ["--concurrency", "1", "--usage-tracking", "auto"],
      "tasks": [
        {"id": "task-a", "tasks_dir": "path/to/task-a", "bundle": "path/to/bundle", "repetitions": 3}
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text())
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise ValueError("cohort spec schema_version must be 1")
    tasks = spec.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("cohort spec must contain a non-empty tasks list")
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("each task must be an object")
        if not isinstance(task.get("id"), str) or not task["id"]:
            raise ValueError("each task needs a non-empty id")
        if not isinstance(task.get("tasks_dir"), str) or not task["tasks_dir"]:
            raise ValueError(f"{task.get('id')}: missing tasks_dir")
        repetitions = task.get("repetitions", 1)
        if not isinstance(repetitions, int) or isinstance(repetitions, bool) or repetitions < 1:
            raise ValueError(f"{task['id']}: repetitions must be a positive integer")
    max_parallel = spec.get("max_parallel", 1)
    if not isinstance(max_parallel, int) or isinstance(max_parallel, bool) or max_parallel < 1:
        raise ValueError("max_parallel must be a positive integer")
    return spec


def commands(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the frozen spec into deterministic baseline/treatment commands."""
    base = [
        str(spec.get("bench", "bench")),
        "eval",
        "run",
        "--agent",
        str(spec.get("agent", "deepagents")),
        "--model",
        str(spec.get("model", "deepseek/deepseek-chat")),
        "--sandbox",
        str(spec.get("sandbox", "docker")),
    ]
    common = [str(value) for value in spec.get("common_args") or []]
    jobs_root = Path(spec["jobs_root"])
    rows: list[dict[str, Any]] = []
    for task in spec["tasks"]:
        conditions = task.get("conditions", ["baseline", "treatment"])
        if (
            not isinstance(conditions, list)
            or not conditions
            or any(value not in {"baseline", "treatment"} for value in conditions)
        ):
            raise ValueError(f"{task['id']}: invalid conditions")
        for condition in conditions:
            for repetition in range(1, int(task.get("repetitions", 1)) + 1):
                jobs_dir = jobs_root / f"{task['id']}-{condition}-r{repetition}"
                command = [
                    *base,
                    *common,
                    "--tasks-dir",
                    str(task["tasks_dir"]),
                    "--jobs-dir",
                    str(jobs_dir),
                ]
                if condition == "baseline":
                    command.extend(["--skill-mode", "no-skill"])
                else:
                    bundle = task.get("bundle")
                    if not isinstance(bundle, str) or not bundle:
                        raise ValueError(f"{task['id']}: treatment needs a bundle")
                    command.extend(
                        ["--skill-mode", "with-skill", "--skills-dir", bundle]
                    )
                rows.append({
                    "task_id": task["id"],
                    "condition": condition,
                    "repetition": repetition,
                    "jobs_dir": str(jobs_dir),
                    "command": command,
                })
    return rows


def _valid_result(jobs_dir: Path) -> bool:
    for path in jobs_dir.rglob("result.json"):
        try:
            value = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        reward = (value.get("rewards") or {}).get("reward")
        if reward is not None and not value.get("error"):
            return True
    return False


def _cleanup_docker() -> None:
    """Reclaim stopped benchmark containers and build cache between cells."""
    for args in (["container", "prune", "-f"], ["builder", "prune", "-f"]):
        try:
            subprocess.run(
                ["docker", *args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def _execute(command: list[str], log_path: Path, timeout: float | None) -> tuple[int, str | None]:
    """Run one bench command with a process-group kill on timeout."""
    started = time.time()
    with log_path.open("w") as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=timeout)
            error = None
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                code = process.wait()
            error = "wall-clock-cap"
    return code, error


def run(spec: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    rows = commands(spec)
    started_at = time.time()
    cap = spec.get("max_wall_seconds")
    cap = float(cap) if isinstance(cap, (int, float)) and cap > 0 else None
    deadline = started_at + cap if cap else None
    per_trial = spec.get("per_trial_timeout_seconds")
    per_trial = float(per_trial) if isinstance(per_trial, (int, float)) and per_trial > 0 else None
    resume = bool(spec.get("resume", False))
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "spec": spec,
        "started_at": started_at,
        "dry_run": dry_run,
        "wall_clock_cap_seconds": cap,
        "per_trial_timeout_seconds": per_trial,
        "resume": resume,
        "skipped_existing": 0,
        "stopped_by_wall_clock": 0,
        "timed_out": 0,
        "runs": [],
    }
    if dry_run:
        manifest["runs"] = [
            {**row, "command": shlex.join(row["command"]), "exit_code": None}
            for row in rows
        ]
        return manifest

    jobs_root = Path(spec["jobs_root"])
    jobs_root.mkdir(parents=True, exist_ok=True)

    def one(row: dict[str, Any]) -> dict[str, Any]:
        jobs_dir = Path(row["jobs_dir"])
        jobs_dir.mkdir(parents=True, exist_ok=True)
        if resume and _valid_result(jobs_dir):
            return {**row, "status": "skipped-existing", "exit_code": None}
        if deadline is not None and time.time() >= deadline:
            return {**row, "status": "stopped-wall-clock", "exit_code": None}
        timeout = None
        if deadline is not None:
            timeout = max(1.0, deadline - time.time())
        if per_trial is not None:
            timeout = min(timeout, per_trial) if timeout is not None else per_trial
        log_path = jobs_dir / "runner.log"
        started = time.time()
        code, error = _execute(row["command"], log_path, timeout)
        if spec.get("cleanup_docker", True):
            _cleanup_docker()
        status = "completed" if code == 0 else "failed"
        if error:
            status = "timed-out"
        return {
            **row,
            "command": shlex.join(row["command"]),
            "log": str(log_path),
            "exit_code": code,
            "status": status,
            "error": error,
            "duration_seconds": round(time.time() - started, 3),
        }

    max_parallel = int(spec.get("max_parallel", 1))
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = {pool.submit(one, row): row for row in rows}
        for future in as_completed(futures):
            manifest["runs"].append(future.result())
    manifest["runs"].sort(key=lambda row: (
        row["task_id"], row["condition"], row["repetition"]
    ))
    manifest["skipped_existing"] = sum(
        row.get("status") == "skipped-existing" for row in manifest["runs"]
    )
    manifest["stopped_by_wall_clock"] = sum(
        row.get("status") == "stopped-wall-clock" for row in manifest["runs"]
    )
    manifest["timed_out"] = sum(
        row.get("status") == "timed-out" for row in manifest["runs"]
    )
    manifest["finished_at"] = time.time()
    manifest["elapsed_seconds"] = round(
        manifest["finished_at"] - manifest["started_at"], 3
    )
    return manifest

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-wall-seconds", type=float)
    parser.add_argument("--per-trial-timeout", type=float)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    spec = load_spec(args.spec)
    if args.max_wall_seconds is not None:
        spec["max_wall_seconds"] = args.max_wall_seconds
    if args.per_trial_timeout is not None:
        spec["per_trial_timeout_seconds"] = args.per_trial_timeout
    if args.resume:
        spec["resume"] = True
    manifest = run(spec, dry_run=args.dry_run)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "runs": len(manifest["runs"]),
        "dry_run": manifest["dry_run"],
        "elapsed_seconds": manifest.get("elapsed_seconds"),
        "failed": [
            row["task_id"] for row in manifest["runs"]
            if row.get("exit_code") not in (None, 0)
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
