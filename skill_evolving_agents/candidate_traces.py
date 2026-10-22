#!/usr/bin/env python3
"""Index candidate traces and start a run that copies one of them.

The pool lives beside the runs directory. A run name is
``run-<source>-<session hex>-<turns>turns``. The hex starts at six
characters and grows only when two traces would otherwise share a name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
POOL = ROOT / "workspace/candidate_traces"
RUNS = ROOT / "workspace/runs"
INDEX_NAME = "index.json"
HEX_WIDTH = 6


def _records(path: Path):
    with path.open(errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def inspect_trace(path: Path) -> dict[str, object]:
    """Read source, session id, and turn count from one JSONL trace."""
    source = "unknown"
    session_id = ""
    turns: set[str] = set()
    user_messages = 0
    for record in _records(path):
        kind = record.get("type")
        payload = record.get("payload")
        if kind == "session_meta" and isinstance(payload, dict):
            source = "codex"
            session_id = str(
                payload.get("session_id") or payload.get("id") or session_id
            )
            continue
        if (
            source == "codex"
            and kind == "event_msg"
            and isinstance(payload, dict)
            and payload.get("type") == "task_started"
        ):
            turn_id = payload.get("turn_id") or payload.get("root_turn_id")
            if isinstance(turn_id, str) and turn_id:
                turns.add(turn_id)
            continue
        if kind in {"user", "assistant"} and isinstance(record.get("message"), dict):
            if "sessionId" in record or "uuid" in record:
                source = "claude" if source == "unknown" else source
                if not session_id and isinstance(record.get("sessionId"), str):
                    session_id = record["sessionId"]
                if kind == "user":
                    user_messages += 1
                continue
        role = record.get("role")
        message = record.get("message")
        if isinstance(message, dict) and role is None:
            role = message.get("role")
        if role in {"user", "assistant", "tool"} and source == "unknown":
            source = "cursor"
        if source == "cursor" and role == "user":
            user_messages += 1
    if not session_id:
        session_id = path.stem
    turn_count = len(turns) if source == "codex" else user_messages
    return {
        "file": path.name,
        "source": source,
        "session_id": session_id,
        "turns": turn_count,
        "bytes": path.stat().st_size,
    }


def session_hex(session_id: str) -> str:
    hex_id = re.sub(r"[^0-9a-fA-F]", "", session_id).lower()
    if hex_id:
        return hex_id
    return hashlib.sha256(session_id.encode()).hexdigest()


def run_id_for(row: dict[str, object], used: set[str], width: int = HEX_WIDTH) -> str:
    hex_id = session_hex(str(row["session_id"]))
    source = str(row["source"])
    turns = int(row["turns"])
    size = width
    while size <= len(hex_id):
        name = f"run-{source}-{hex_id[:size]}-{turns}turns"
        if name not in used:
            return name
        size += 2
    digest = hashlib.sha256(str(row["file"]).encode()).hexdigest()[:HEX_WIDTH]
    name = f"run-{source}-{digest}-{turns}turns"
    suffix = 2
    while name in used:
        name = f"run-{source}-{digest}-{turns}turns-{suffix}"
        suffix += 1
    return name


def index_traces(pool: Path = POOL) -> list[dict[str, object]]:
    pool.mkdir(parents=True, exist_ok=True)
    rows = [inspect_trace(path) for path in sorted(pool.glob("*.jsonl"))]
    used: set[str] = set()
    for row in rows:
        name = run_id_for(row, used)
        used.add(name)
        row["run_id"] = name
    document = {"schema_version": 1, "traces": rows}
    (pool / INDEX_NAME).write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    )
    return rows


def _select(rows: list[dict[str, object]], selector: str) -> dict[str, object]:
    needle = selector.strip()
    matches = [
        row
        for row in rows
        if needle in {str(row["file"]), str(row["run_id"]), str(row["session_id"])}
        or needle in str(row["file"])
        or needle in str(row["run_id"])
    ]
    unique: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in matches:
        file_name = str(row["file"])
        if file_name not in seen:
            seen.add(file_name)
            unique.append(row)
    if len(unique) != 1:
        found = ", ".join(str(row["run_id"]) for row in unique) or "none"
        raise SystemExit(f"selector {selector!r} matched {len(unique)} traces: {found}")
    return unique[0]


def create_run(
    selector: str,
    pool: Path = POOL,
    runs: Path = RUNS,
    seed_run: str | None = None,
    replace: bool = False,
    source_path: Path | None = None,
) -> Path:
    """Copy one candidate into a new run named from its metadata."""
    if source_path is not None:
        source_path = source_path.expanduser().resolve()
        if not source_path.is_file() or source_path.suffix != ".jsonl":
            raise SystemExit(f"source trace is not a JSONL file: {source_path}")
        row = inspect_trace(source_path)
        used = {
            path.name
            for path in runs.glob("run-*")
            if path.is_dir()
        }
        row["run_id"] = run_id_for(row, used)
        trace_source = source_path
    else:
        rows = index_traces(pool)
        row = _select(rows, selector)
        trace_source = pool / str(row["file"])
    run_id = str(row["run_id"])
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
        raise SystemExit(f"refusing unsafe run id: {run_id}")
    source = str(row["source"])
    if source not in {"codex", "claude", "cursor"}:
        raise SystemExit(f"{row['file']} has no supported trace source")
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    import run_pipeline

    workspace = runs / run_id
    if replace and workspace.is_dir():
        shutil.rmtree(workspace)
    run_pipeline.initialize_workspace(workspace)
    if seed_run:
        seed = runs / seed_run
        if not seed.is_dir():
            raise SystemExit(f"seed run does not exist: {seed}")
        for relative in (
            "target/to_be_improved_skills",
            "target/to_be_improved_skills_metadata",
        ):
            source_dir = seed / relative
            if source_dir.is_dir():
                shutil.copytree(
                    source_dir,
                    workspace / relative,
                    dirs_exist_ok=True,
                )
    destination = workspace / "traces/raw" / source / str(row["file"])
    shutil.copy2(trace_source, destination)
    selection = {
        "schema_version": 1,
        "run_id": run_id,
        "source": source,
        "session_id": row["session_id"],
        "turns": row["turns"],
        "candidate": (
            str(source_path)
            if source_path is not None
            else f"workspace/candidate_traces/{row['file']}"
        ),
        "copied_to": destination.relative_to(workspace).as_posix(),
    }
    if seed_run:
        selection["seeded_from"] = seed_run
    (workspace / "run/trace-selection.json").write_text(
        json.dumps(selection, indent=2, ensure_ascii=False) + "\n"
    )
    copied = list((workspace / "traces/raw").rglob("*.jsonl"))
    if copied != [destination]:
        raise SystemExit(f"run {run_id} did not receive exactly one trace")
    print(f"created {run_id}: {destination}")
    return workspace


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("index", help="write candidate_traces/index.json")
    create = subparsers.add_parser("new", help="copy one candidate into a new run")
    create.add_argument(
        "selector",
        help="candidate filename, session id, or generated run id",
    )
    create.add_argument(
        "--seed-run",
        help="copy the existing skill inventory from this run",
    )
    create.add_argument(
        "--replace",
        action="store_true",
        help="replace an existing generated run workspace",
    )
    create.add_argument(
        "--source",
        type=Path,
        help="import an explicit local JSONL trace instead of the candidate pool",
    )
    args = parser.parse_args()
    if args.command == "new":
        create_run(
            args.selector,
            seed_run=args.seed_run,
            replace=args.replace,
            source_path=args.source,
        )
        return
    rows = index_traces()
    if not rows:
        print(f"no traces in {POOL}")
        return
    for row in rows:
        print(
            f"{row['run_id']}\t{row['turns']} turns\t{row['source']}\t{row['file']}"
        )


if __name__ == "__main__":
    main()
