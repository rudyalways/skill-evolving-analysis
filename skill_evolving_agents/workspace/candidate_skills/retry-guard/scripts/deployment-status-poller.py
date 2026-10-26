#!/usr/bin/env python3
"""Poll a managed deployment to a terminal status with a bounded watch.

The helper reads the deployment status from a caller-supplied command, stops at
a declared terminal value or deadline, and writes one machine-readable JSON
line to stdout. Exit codes: 0 terminal success, 2 terminal failure, 3 timeout,
4 status-command failure, 5 invalid configuration.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

TERMINAL_SUCCESS = frozenset({"SUCCESS"})
TERMINAL_FAILURE = frozenset({"FAILED", "CRASHED", "REMOVED"})
TERMINAL_STATUSES = TERMINAL_SUCCESS | TERMINAL_FAILURE
DEMO_FIXTURE = "BUILDING,BUILDING,SUCCESS"

EXIT_SUCCESS = 0
EXIT_TERMINAL_FAILURE = 2
EXIT_TIMEOUT = 3
EXIT_COMMAND_FAILURE = 4
EXIT_CONFIGURATION = 5

EXIT_RESULTS = {
    EXIT_SUCCESS: "success",
    EXIT_TERMINAL_FAILURE: "terminal_failure",
    EXIT_TIMEOUT: "timeout",
    EXIT_COMMAND_FAILURE: "command_failure",
    EXIT_CONFIGURATION: "configuration_error",
}

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TERMINAL_TOKEN = re.compile(r"\b(SUCCESS|FAILED|CRASHED|REMOVED)\b", re.IGNORECASE)
STATUS_FIELDS = (
    "status",
    "state",
    "phase",
    "deploymentStatus",
    "deployment_status",
    "result",
)


def _normalise_status(value: str) -> str:
    return ANSI_ESCAPE.sub("", value).strip().strip('"').strip("'").upper()


def _json_status(value: Any) -> str | None:
    """Return an explicit status field from a JSON-like payload."""
    if isinstance(value, dict):
        for key in STATUS_FIELDS:
            candidate = value.get(key)
            if isinstance(candidate, str) and _normalise_status(candidate):
                return _normalise_status(candidate)
        for nested in value.values():
            found = _json_status(nested)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _json_status(item)
            if found:
                return found
    return None


def extract_status(output: str) -> str:
    """Extract the observed status, preferring an explicit JSON field."""
    cleaned = ANSI_ESCAPE.sub("", output or "").strip()
    if not cleaned:
        return "UNKNOWN"

    try:
        payload = json.loads(cleaned)
    except (ValueError, TypeError):
        payload = None
    if payload is not None:
        explicit = _json_status(payload)
        if explicit:
            return explicit

    matches = TERMINAL_TOKEN.findall(cleaned)
    if matches:
        return matches[-1].upper()

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if lines:
        return lines[-1][:120]
    return "UNKNOWN"


def load_fixture(value: str) -> list[str]:
    """Load a comma/newline/JSON fixture sequence from an inline value or file."""
    text = value
    candidate = Path(value[1:]) if value.startswith("@") else Path(value)
    if (value.startswith("@") or candidate.is_file()) and candidate.is_file():
        text = candidate.read_text(encoding="utf-8")

    statuses: list[str]
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        payload = None
    if isinstance(payload, list):
        statuses = [str(item) for item in payload]
    elif isinstance(payload, str):
        statuses = [payload]
    else:
        statuses = [part for part in re.split(r"[,\n]", text) if part.strip()]

    cleaned = [_normalise_status(item) for item in statuses]
    cleaned = [item for item in cleaned if item]
    if not cleaned:
        raise ValueError("fixture sequence is empty")
    return cleaned


def run_status_command(command: str, args: argparse.Namespace, timeout: float) -> str:
    """Run the status command once and return its combined output."""
    rendered = command
    for placeholder, value in (
        ("{service}", args.service),
        ("{environment}", args.environment),
        ("{deployment_id}", args.deployment_id),
        ("{deploymentId}", args.deployment_id),
    ):
        rendered = rendered.replace(placeholder, value)
    try:
        argv = shlex.split(rendered)
    except ValueError as error:
        raise RuntimeError(f"cannot parse status command: {error}") from error
    if not argv:
        raise RuntimeError("status command is empty")

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=max(0.1, timeout),
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("status command timed out") from error
    except OSError as error:
        raise RuntimeError(f"cannot run status command: {error}") from error

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        detail = ANSI_ESCAPE.sub("", detail).splitlines()
        suffix = f": {detail[-1][:200]}" if detail else ""
        raise RuntimeError(
            f"status command exited {completed.returncode}{suffix}"
        )

    return completed.stdout or completed.stderr or ""


def emit(report: dict[str, Any], exit_code: int) -> None:
    report["exit_code"] = exit_code
    report["result"] = EXIT_RESULTS.get(exit_code, "error")
    print(json.dumps(report, sort_keys=True))
    sys.stdout.flush()


def base_report(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "service": args.service,
        "environment": args.environment,
        "deployment_id": args.deployment_id,
        "status": "UNKNOWN",
        "terminal": False,
        "polls": 0,
        "elapsed_seconds": 0.0,
        "timeout_seconds": args.timeout,
        "poll_interval_seconds": args.poll_interval,
        "reason": "",
    }


def poll(args: argparse.Namespace, fixture: Sequence[str] | None) -> tuple[dict[str, Any], int]:
    report = base_report(args)
    started = time.monotonic()
    deadline = started + args.timeout
    polls = 0
    status = "UNKNOWN"

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            report.update(
                status=status,
                polls=polls,
                elapsed_seconds=round(time.monotonic() - started, 3),
                reason="deadline reached before the deployment reached a terminal status",
            )
            return report, EXIT_TIMEOUT

        polls += 1
        if fixture is not None:
            status = fixture[min(polls - 1, len(fixture) - 1)]
        else:
            try:
                status = extract_status(
                    run_status_command(args.status_command, args, remaining)
                )
            except RuntimeError as error:
                report.update(
                    status=status,
                    polls=polls,
                    elapsed_seconds=round(time.monotonic() - started, 3),
                    reason=str(error),
                )
                return report, EXIT_COMMAND_FAILURE

        if status in TERMINAL_SUCCESS:
            report.update(
                status=status,
                terminal=True,
                polls=polls,
                elapsed_seconds=round(time.monotonic() - started, 3),
                reason="observed terminal success status",
            )
            return report, EXIT_SUCCESS

        if status in TERMINAL_FAILURE:
            report.update(
                status=status,
                terminal=True,
                polls=polls,
                elapsed_seconds=round(time.monotonic() - started, 3),
                reason="observed terminal failure status",
            )
            return report, EXIT_TERMINAL_FAILURE

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            report.update(
                status=status,
                polls=polls,
                elapsed_seconds=round(time.monotonic() - started, 3),
                reason="deadline reached without a terminal status",
            )
            return report, EXIT_TIMEOUT

        time.sleep(min(args.poll_interval, remaining))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Poll a managed deployment to SUCCESS, FAILED, CRASHED, or REMOVED "
            "with a bounded deadline and fixed poll interval."
        )
    )
    parser.add_argument("--service", required=True, help="managed service name")
    parser.add_argument("--environment", required=True, help="deployment environment")
    parser.add_argument(
        "--deployment-id",
        "--deployment_id",
        dest="deployment_id",
        required=True,
        help="deployment identifier to poll",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="maximum wall-clock seconds before a timeout (default: 600)",
    )
    parser.add_argument(
        "--poll-interval",
        "--poll_interval",
        dest="poll_interval",
        type=float,
        default=15.0,
        help="seconds between status queries (default: 15)",
    )
    parser.add_argument(
        "--status-command",
        "--status_command",
        dest="status_command",
        default=os.environ.get("DEPLOYMENT_STATUS_COMMAND", ""),
        help=(
            "status command; may use {service}, {environment}, and "
            "{deployment_id} placeholders"
        ),
    )
    parser.add_argument(
        "--fixture",
        nargs="?",
        const=DEMO_FIXTURE,
        default=os.environ.get("DEPLOYMENT_STATUS_FIXTURE", ""),
        help=(
            "test-only comma/newline/JSON status sequence, or @path; "
            f"omit the value for the {DEMO_FIXTURE} demo sequence"
        ),
    )
    parser.add_argument(
        "--fixture-file",
        "--fixture_file",
        dest="fixture_file",
        default="",
        help="test-only path to a status sequence fixture",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.timeout <= 0:
        report = base_report(args)
        report["reason"] = "--timeout must be greater than zero"
        emit(report, EXIT_CONFIGURATION)
        return EXIT_CONFIGURATION
    if args.poll_interval <= 0:
        report = base_report(args)
        report["reason"] = "--poll-interval must be greater than zero"
        emit(report, EXIT_CONFIGURATION)
        return EXIT_CONFIGURATION

    fixture: list[str] | None = None
    fixture_source = args.fixture_file or args.fixture
    if fixture_source:
        try:
            fixture = load_fixture(fixture_source)
        except (OSError, ValueError) as error:
            report = base_report(args)
            report["reason"] = f"cannot load fixture: {error}"
            emit(report, EXIT_CONFIGURATION)
            return EXIT_CONFIGURATION
    elif not args.status_command:
        report = base_report(args)
        report["reason"] = (
            "provide --status-command or DEPLOYMENT_STATUS_COMMAND, "
            "or use --fixture for a deterministic check"
        )
        emit(report, EXIT_CONFIGURATION)
        return EXIT_CONFIGURATION

    report, exit_code = poll(args, fixture)
    emit(report, exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
