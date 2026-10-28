from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from matrix_sampler.redaction import redact

MIGRATIONS = ["""
CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS targets(target_id TEXT PRIMARY KEY, profile_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scenarios(scenario_id TEXT PRIMARY KEY, scenario_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS samples(sample_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, prompt_hash TEXT UNIQUE NOT NULL, sample_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, sample_id TEXT NOT NULL, target_id TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT, completed_at TEXT, error_kind TEXT, run_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, event_type TEXT NOT NULL, event_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS labels(label_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, source TEXT NOT NULL, name TEXT NOT NULL, value_json TEXT NOT NULL, confidence REAL NOT NULL);
CREATE TABLE IF NOT EXISTS matrix_cells(cell_id TEXT PRIMARY KEY, attempts INTEGER NOT NULL DEFAULT 0, successes INTEGER NOT NULL DEFAULT 0, alpha REAL NOT NULL DEFAULT 1, beta REAL NOT NULL DEFAULT 1, cell_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS policies(policy_id TEXT PRIMARY KEY, policy_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts(sha256 TEXT PRIMARY KEY, path TEXT NOT NULL, media_type TEXT);
CREATE TABLE IF NOT EXISTS trace_features(trace_id TEXT PRIMARY KEY, feature_json TEXT NOT NULL);
""", """
CREATE TABLE IF NOT EXISTS ood_nodes(node_id TEXT PRIMARY KEY, parent_id TEXT, layer INTEGER NOT NULL, status TEXT NOT NULL, node_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evolution_cycles(cycle_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, maximum_layer INTEGER NOT NULL, metrics_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_ood_nodes_parent ON ood_nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_ood_nodes_layer ON ood_nodes(layer);
"""]


class Store:
    def __init__(self, path: str | Path = ".sampler/sampler.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.migrate()

    def migrate(self):
        for version, sql in enumerate(MIGRATIONS, 1):
            self.db.executescript(sql)
            self.db.execute("INSERT OR IGNORE INTO migrations(version) VALUES (?)", (version,))
        self.db.commit()

    def put_json(self, table: str, key_col: str, key: str, json_col: str, value: dict[str, Any]):
        allowed = {("targets", "target_id", "profile_json"), ("scenarios", "scenario_id", "scenario_json"), ("policies", "policy_id", "policy_json"), ("trace_features", "trace_id", "feature_json")}
        if (table, key_col, json_col) not in allowed:
            raise ValueError("unsupported table")
        payload = json.dumps(redact(value), sort_keys=True)
        self.db.execute(f"INSERT OR REPLACE INTO {table}({key_col},{json_col}) VALUES (?,?)", (key, payload))
        self.db.commit()

    def add_sample(self, sample: dict[str, Any]) -> bool:
        prompt = json.dumps(sample.get("messages", []), sort_keys=True)
        digest = hashlib.sha256(" ".join(prompt.lower().split()).encode()).hexdigest()
        try:
            self.db.execute("INSERT INTO samples VALUES (?,?,?,?)", (sample["sample_id"], sample["scenario_id"], digest, json.dumps(redact(sample), sort_keys=True)))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def claim_run(self, run: dict[str, Any]) -> bool:
        try:
            self.db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)", (run["run_id"], run["sample_id"], run["target_id"], "running", run["started_at"], None, None, json.dumps(redact(run), sort_keys=True)))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def add_event(self, event: dict[str, Any]):
        self.db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?)", (event["event_id"], event["run_id"], event["event_type"], json.dumps(redact(event), sort_keys=True)))
        self.db.commit()

    def finish_run(self, run_id: str, status: str, completed_at: str, error_kind: str | None = None):
        self.db.execute("UPDATE runs SET status=?,completed_at=?,error_kind=? WHERE run_id=?", (status, completed_at, error_kind, run_id))
        self.db.commit()

    def add_label(self, run_id: str, source: str, name: str, value: Any, confidence: float):
        self.db.execute("INSERT INTO labels(run_id,source,name,value_json,confidence) VALUES (?,?,?,?,?)", (run_id, source, name, json.dumps(value), confidence))
        self.db.commit()

    def add_artifact(self, data: bytes, artifact_dir: str | Path = ".sampler/artifacts", media_type: str = "application/octet-stream") -> str:
        digest = hashlib.sha256(data).hexdigest()
        path = Path(artifact_dir) / "sha256" / digest[:2] / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        self.db.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?,?)", (digest, str(path), media_type))
        self.db.commit()
        return digest

    def counts(self) -> dict[str, int]:
        return {table: self.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in ("targets", "scenarios", "samples", "runs", "events", "labels", "matrix_cells", "trace_features", "ood_nodes", "evolution_cycles")}

    def put_ood_tree(self, tree: dict[str, Any]) -> None:
        for node in tree["nodes"]:
            self.db.execute("INSERT OR REPLACE INTO ood_nodes VALUES (?,?,?,?,?)", (node["node_id"], node["parent_id"], node["layer"], node["status"], json.dumps(node, sort_keys=True)))
        cycle_id = hashlib.sha256(json.dumps(tree["summary"], sort_keys=True).encode() + tree["generated_at"].encode()).hexdigest()[:20]
        self.db.execute("INSERT INTO evolution_cycles VALUES (?,?,?,?)", (cycle_id, tree["generated_at"], tree["summary"]["maximum_layer"], json.dumps({"layer_metrics": tree["layer_metrics"], "summary": tree["summary"]}, sort_keys=True)))
        self.db.commit()

