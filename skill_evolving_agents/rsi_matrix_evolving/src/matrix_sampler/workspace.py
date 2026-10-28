from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from matrix_sampler.run_config import default_run_config, validate_run_config


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-.")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("run name must contain a letter or number")
    return cleaned[:80]


class RunWorkspace:
    """One independently movable run with immutable inputs and local outputs."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.input = self.root / "input"
        self.output = self.root / "output"
        self.logs = self.output / "logs"
        self.artifacts = self.output / "artifacts"
        self.database = self.output / "sampler.db"
        self.manifest = self.root / "manifest.json"

    @classmethod
    def allocate(cls, runs_root: str | Path, name: str, moment: datetime | None = None) -> "RunWorkspace":
        moment = moment or datetime.now().astimezone()
        # Match skill-evolving-agents: human run id plus a local minute stamp.
        base = f"{safe_name(name)}@{moment.strftime('%Y-%m-%dT%H:%M')}"
        runs_root = Path(runs_root).resolve()
        candidate = runs_root / base
        suffix = 2
        while candidate.exists():
            candidate = runs_root / f"{base}-{suffix}"
            suffix += 1
        workspace = cls(candidate)
        for directory in (workspace.input / "traces", workspace.output / "events", workspace.logs, workspace.artifacts):
            directory.mkdir(parents=True, exist_ok=False)
        return workspace

    @classmethod
    def create(cls, runs_root: str | Path, name: str, target_profile: str | Path, scenarios: str | Path, configs: list[str | Path] = (), run_config: dict[str, Any] | None = None) -> "RunWorkspace":
        workspace = cls.allocate(runs_root, name)
        sources = [(Path(target_profile), workspace.input / "target-profile.json"), (Path(scenarios), workspace.input / "scenarios.json")]
        sources += [(Path(p), workspace.input / "configs" / Path(p).name) for p in configs]
        files = []
        for source, destination in sources:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            files.append({"path": str(destination.relative_to(workspace.root)), "sha256": _digest(destination), "source": str(source.resolve())})
        profile = json.loads((workspace.input / "target-profile.json").read_text())
        resolved_config = validate_run_config(run_config or default_run_config(profile))
        config_path = workspace.input / "run-config.json"
        _write_json(config_path, resolved_config)
        files.append({"path": "input/run-config.json", "sha256": _digest(config_path), "source": "generated:run-config"})
        _write_json(workspace.manifest, {"schema_version": 1, "run_name": workspace.root.name, "run_directory": workspace.root.name, "created_at": datetime.now().astimezone().isoformat(), "status": "initialized", "input_files": files, "output_contract": {"database": "output/sampler.db", "events": "output/events", "logs": "output/logs", "artifacts": "output/artifacts", "report": "output/report.md"}})
        return workspace

    def require(self) -> "RunWorkspace":
        if not self.manifest.is_file() or not self.input.is_dir() or not self.output.is_dir():
            raise ValueError(f"not a run workspace: {self.root}")
        return self

    def snapshot_trace(self, source: str | Path) -> Path:
        source = Path(source).resolve()
        digest = _digest(source)
        destination = self.input / "traces" / f"{digest[:12]}-{source.name}"
        if not destination.exists():
            shutil.copy2(source, destination)
        manifest = json.loads(self.manifest.read_text())
        entry = {"path": str(destination.relative_to(self.root)), "sha256": digest, "source": str(source)}
        if entry not in manifest["input_files"]:
            manifest["input_files"].append(entry)
            _write_json(self.manifest, manifest)
        return destination

    def update_status(self, status: str, **details: Any) -> None:
        manifest = json.loads(self.manifest.read_text())
        manifest["status"] = status
        manifest["updated_at"] = datetime.now().astimezone().isoformat()
        manifest.update(details)
        _write_json(self.manifest, manifest)

