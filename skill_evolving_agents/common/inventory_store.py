"""Immutable, pointer-addressed candidate inventory revisions."""

from __future__ import annotations

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


COMPONENTS = ("candidate_skills", "candidate_skills_metadata", "candidate_skills_changelog")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
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


def _digest(root: Path) -> str:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rows.append((path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


@contextmanager
def _lock(root: Path) -> Iterator[None]:
    path = root / "inventory_releases/.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def snapshot(root: Path) -> dict[str, object]:
    """Snapshot the compatibility inventory and atomically activate its revision."""
    releases = root / "inventory_releases"
    releases.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".inventory-", dir=releases))
    try:
        for component in COMPONENTS:
            source = root / component
            if source.is_dir():
                shutil.copytree(source, staging / component)
        revision_id = _digest(staging)
        destination = releases / revision_id
        if destination.exists():
            shutil.rmtree(staging)
        else:
            os.replace(staging, destination)
        with _lock(root):
            prior_path = root / "active-inventory.json"
            prior = json.loads(prior_path.read_text()) if prior_path.is_file() else {}
            pointer = {
                "schema_version": 1,
                "revision_id": revision_id,
                "path": f"inventory_releases/{revision_id}",
                "previous_revision_id": prior.get("revision_id"),
                "activated_at": datetime.now(UTC).isoformat(),
            }
            _write_json(prior_path, pointer)
        return pointer
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def resolve(root: Path) -> Path:
    """Return the immutable active inventory, with legacy fallback for migration."""
    pointer = root / "active-inventory.json"
    if not pointer.is_file():
        return root
    data = json.loads(pointer.read_text())
    relative = data.get("path")
    if not isinstance(relative, str):
        raise RuntimeError("active inventory pointer has no path")
    target = (root / relative).resolve()
    target.relative_to(root.resolve())
    if not target.is_dir() or target.name != data.get("revision_id"):
        raise RuntimeError("active inventory pointer is invalid")
    return target
