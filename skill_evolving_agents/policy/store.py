"""Immutable policy features, decisions, feedback, and deployment lineage."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import validate_feature_record, validate_policy_decision


class PolicyStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS feature_records (
                    feature_digest TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    feature_schema TEXT NOT NULL, record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS policy_decisions (
                    decision_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    feature_digest TEXT NOT NULL, provider TEXT NOT NULL,
                    provider_revision TEXT NOT NULL, stage TEXT NOT NULL,
                    decision_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback_events (
                    feedback_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    decision_id TEXT, source TEXT NOT NULL, signal TEXT NOT NULL,
                    value_json TEXT NOT NULL, confidence REAL,
                    supersedes TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY, architecture TEXT NOT NULL,
                    feature_schema TEXT NOT NULL, taxonomy_revision TEXT,
                    training_data_digest TEXT NOT NULL, artifact_ref TEXT NOT NULL,
                    metrics_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS policy_decisions_run ON policy_decisions(run_id);
                CREATE INDEX IF NOT EXISTS feedback_events_run ON feedback_events(run_id);
                """
            )

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def record_features(self, record: dict[str, Any]) -> None:
        validate_feature_record(record)
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO feature_records VALUES (?, ?, ?, ?, ?)",
                (record["feature_digest"], record["run_id"], record["feature_schema"],
                 json.dumps(record, sort_keys=True), record["created_at"]),
            )

    def record_decision(self, decision: dict[str, Any]) -> None:
        validate_policy_decision(decision)
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO policy_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (decision["decision_id"], decision["run_id"], decision["feature_digest"],
                 decision["provider"], decision["provider_revision"], decision.get("stage", "offline"),
                 json.dumps(decision, sort_keys=True), decision.get("created_at") or datetime.now(UTC).isoformat()),
            )

    def record_feedback(self, event: dict[str, Any]) -> None:
        required = ("feedback_id", "run_id", "source", "signal", "value")
        if any(field not in event for field in required):
            raise ValueError("feedback event is missing required fields")
        with self.connect() as db:
            db.execute(
                "INSERT INTO feedback_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event["feedback_id"], event["run_id"], event.get("decision_id"),
                 event["source"], event["signal"], json.dumps(event["value"], sort_keys=True),
                 event.get("confidence"), event.get("supersedes"),
                 event.get("created_at") or datetime.now(UTC).isoformat()),
            )
