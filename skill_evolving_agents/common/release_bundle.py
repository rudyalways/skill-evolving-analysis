"""Content-addressed, recoverable release bundles for skill publication."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator


SKILLS = Path("target/to_be_improved_skills")
METADATA = Path("target/to_be_improved_skills_metadata/metadata.json")
CHANGELOGS = Path("target/skill_changelogs")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _tree_digest(root: Path) -> str | None:
    if not root.exists():
        return None
    rows: list[tuple[str, str]] = []
    if root.is_file():
        rows.append((root.name, hashlib.sha256(root.read_bytes()).hexdigest()))
    else:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                rows.append(
                    (
                        path.relative_to(root).as_posix(),
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                    )
                )
    return hashlib.sha256(_canonical(rows)).hexdigest()


def _copy_optional(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)
    return True


def _replay_channel(verification: dict[str, object]) -> tuple[str, str]:
    feedback = verification.get("feedback")
    replay = feedback.get("replay") if isinstance(feedback, dict) else None
    if not isinstance(replay, dict):
        return "provisional", "missing-replay"
    after = replay.get("after")
    if (
        replay.get("available") is True
        and replay.get("status") == "pass"
        and replay.get("kind") == "paired_skill_eval"
        and isinstance(after, dict)
        and int(after.get("held_out_cases") or 0) >= 2
        and float(after.get("held_out_pass_rate", 0)) >= 0.8
        and float(after.get("activation_false_positive_rate", 1)) <= 0.2
    ):
        return "canary", "paired-held-out-replay-pass-awaiting-runtime-observation"
    return "provisional", "held-out-replay-unavailable-or-below-gate"


def prepare_release(
    workspace: Path,
    worker: Path,
    cluster: str,
    op_index: int,
    operation: dict[str, object],
    affected: set[str],
) -> dict[str, object]:
    """Snapshot a candidate and its rollback state before active inventory merge."""
    operation_root = worker / "run" / cluster / "ops" / str(op_index)
    verification_path = operation_root / "verification.json"
    verification = json.loads(verification_path.read_text())
    channel, channel_reason = _replay_channel(verification)
    releases = workspace / "run/releases"
    releases.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".prepare-", dir=releases))
    try:
        inventory: dict[str, dict[str, object]] = {}
        for name in sorted(affected):
            before = workspace / SKILLS / name
            after = worker / SKILLS / name
            before_present = _copy_optional(
                before, staging / "before/skills" / name
            )
            after_present = _copy_optional(after, staging / "after/skills" / name)
            _copy_optional(
                workspace / CHANGELOGS / f"{name}.md",
                staging / "before/changelogs" / f"{name}.md",
            )
            _copy_optional(
                worker / CHANGELOGS / f"{name}.md",
                staging / "after/changelogs" / f"{name}.md",
            )
            inventory[name] = {
                "before_present": before_present,
                "before_sha256": _tree_digest(before),
                "after_present": after_present,
                "after_sha256": _tree_digest(after),
            }
        _copy_optional(workspace / METADATA, staging / "before/metadata.json")
        _copy_optional(worker / METADATA, staging / "after/metadata.json")
        for filename in (
            "evolve-goal.json",
            "verification-input.json",
            "verification.json",
            "judge.json",
            "changelog.json",
        ):
            _copy_optional(operation_root / filename, staging / "evidence" / filename)
        payload: dict[str, object] = {
            "schema_version": 1,
            "run_id": workspace.name,
            "cluster": cluster,
            "op_index": op_index,
            "operation": operation,
            "affected": sorted(affected),
            "channel": channel,
            "channel_reason": channel_reason,
            "inventory": inventory,
            "metadata": {
                "before_sha256": _tree_digest(workspace / METADATA),
                "after_sha256": _tree_digest(worker / METADATA),
            },
            "evidence_sha256": _tree_digest(staging / "evidence"),
        }
        identity = {
            key: value for key, value in payload.items() if key != "run_id"
        }
        release_id = hashlib.sha256(_canonical(identity)).hexdigest()
        manifest = {
            **payload,
            "release_id": release_id,
            "prepared_at": datetime.now(UTC).isoformat(),
            "status": "prepared",
        }
        _write_json(staging / "manifest.json", manifest)
        destination = releases / release_id
        if destination.exists():
            existing = json.loads((destination / "manifest.json").read_text())
            if existing.get("release_id") != release_id:
                raise RuntimeError(f"release collision: {release_id}")
            shutil.rmtree(staging)
        else:
            os.replace(staging, destination)
        return manifest
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise


@contextmanager
def release_lock(workspace: Path) -> Iterator[None]:
    path = workspace / "run/releases/.release.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def commit_release(workspace: Path, release_id: str) -> dict[str, object]:
    root = workspace / "run/releases"
    manifest_path = root / release_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    with release_lock(workspace):
        current_path = root / "active.json"
        current = json.loads(current_path.read_text()) if current_path.is_file() else None
        pointer = {
            "schema_version": 1,
            "release_id": release_id,
            "channel": manifest["channel"],
            "previous_release_id": (
                current.get("release_id") if isinstance(current, dict) else None
            ),
            "committed_at": datetime.now(UTC).isoformat(),
        }
        _write_json(current_path, pointer)
        _write_json(
            root / release_id / "commit.json",
            {**pointer, "status": "committed"},
        )
        return pointer


def observe_canary(
    workspace: Path,
    release_id: str,
    observation: dict[str, object],
    *,
    min_samples: int = 20,
    max_failure_rate: float = 0.05,
    max_latency_regression: float = 0.25,
    max_cost_regression: float = 0.25,
) -> dict[str, object]:
    """Accumulate canary evidence and promote or roll back deterministically."""
    root = workspace / "run/releases"
    release = root / release_id
    manifest = json.loads((release / "manifest.json").read_text())
    if manifest.get("channel") != "canary":
        raise ValueError("runtime observations are accepted only for canary releases")
    samples = int(observation.get("samples", 0))
    failures = int(observation.get("failures", 0))
    if samples < 1 or failures < 0 or failures > samples:
        raise ValueError("observation requires samples >= 1 and 0 <= failures <= samples")
    for field in ("latency_regression", "cost_regression"):
        if not isinstance(observation.get(field), (int, float)):
            raise ValueError(f"observation requires numeric {field}")
    path = release / "canary.json"
    current = json.loads(path.read_text()) if path.is_file() else {"observations": []}
    rows = [*current.get("observations", []), observation]
    total_samples = sum(int(row["samples"]) for row in rows)
    total_failures = sum(int(row["failures"]) for row in rows)
    failure_rate = total_failures / total_samples
    latency = max(float(row["latency_regression"]) for row in rows)
    cost = max(float(row["cost_regression"]) for row in rows)
    severe = any(bool(row.get("severe_regression")) for row in rows)
    failed = severe or failure_rate > max_failure_rate or latency > max_latency_regression or cost > max_cost_regression
    state = "rolled_back" if failed else "stable" if total_samples >= min_samples else "canary"
    report = {
        "schema_version": 1,
        "release_id": release_id,
        "state": state,
        "observations": rows,
        "summary": {
            "samples": total_samples,
            "failures": total_failures,
            "failure_rate": failure_rate,
            "max_latency_regression": latency,
            "max_cost_regression": cost,
        },
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _write_json(path, report)
    if failed:
        rollback_release(workspace, release_id)
    elif state == "stable":
        with release_lock(workspace):
            pointer = {
                "schema_version": 1,
                "release_id": release_id,
                "channel": "stable",
                "committed_at": datetime.now(UTC).isoformat(),
            }
            _write_json(root / "stable.json", pointer)
            _write_json(root / "active.json", pointer)
    return report


def rollback_release(workspace: Path, release_id: str) -> dict[str, object]:
    """Restore the run inventory snapshot captured before a release."""
    root = workspace / "run/releases" / release_id
    manifest = json.loads((root / "manifest.json").read_text())
    with release_lock(workspace):
        for name in manifest.get("affected") or []:
            destination = workspace / SKILLS / str(name)
            before = root / "before/skills" / str(name)
            if destination.exists():
                shutil.rmtree(destination) if destination.is_dir() else destination.unlink()
            if before.is_dir():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(before, destination)
            changelog = workspace / CHANGELOGS / f"{name}.md"
            before_log = root / "before/changelogs" / f"{name}.md"
            if changelog.exists():
                changelog.unlink()
            if before_log.is_file():
                changelog.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(before_log, changelog)
        before_metadata = root / "before/metadata.json"
        metadata = workspace / METADATA
        if before_metadata.is_file():
            metadata.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(before_metadata, metadata)
        elif metadata.exists():
            metadata.unlink()
        pointer = {
            "schema_version": 1,
            "rolled_back_release_id": release_id,
            "release_id": None,
            "channel": "rollback",
            "committed_at": datetime.now(UTC).isoformat(),
        }
        _write_json(workspace / "run/releases/active.json", pointer)
        _write_json(root / "rollback.json", pointer)
        return pointer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("rollback", "observe"))
    parser.add_argument("workspace", type=Path)
    parser.add_argument("release_id")
    parser.add_argument("--samples", type=int)
    parser.add_argument("--failures", type=int, default=0)
    parser.add_argument("--latency-regression", type=float, default=0.0)
    parser.add_argument("--cost-regression", type=float, default=0.0)
    parser.add_argument("--severe-regression", action="store_true")
    args = parser.parse_args()
    if args.command == "rollback":
        print(json.dumps(rollback_release(args.workspace.resolve(), args.release_id)))
    else:
        if args.samples is None:
            parser.error("observe requires --samples")
        print(json.dumps(observe_canary(args.workspace.resolve(), args.release_id, {
            "samples": args.samples,
            "failures": args.failures,
            "latency_regression": args.latency_regression,
            "cost_regression": args.cost_regression,
            "severe_regression": args.severe_regression,
        })))


if __name__ == "__main__":
    main()
