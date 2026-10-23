"""Persistent feedback learning and bounded configuration search."""

from __future__ import annotations

import json
import math
import random
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .optimization import OptimizationError, _constraints_hold, _domain_values, digest


def _now() -> str:
    return datetime.now(UTC).isoformat()


class StudyStore:
    """SQLite ledger for runs, trials, feedback, posteriors, and policies."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS learning_runs (
                    run_id TEXT PRIMARY KEY, recorded_at TEXT NOT NULL,
                    config_digest TEXT NOT NULL, candidate_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL, context_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS search_trials (
                    trial_id TEXT PRIMARY KEY, run_id TEXT, algorithm TEXT NOT NULL,
                    candidate_json TEXT NOT NULL, reward REAL, eligible INTEGER,
                    decision_json TEXT, recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS choice_posteriors (
                    knob TEXT NOT NULL, choice_json TEXT NOT NULL,
                    alpha REAL NOT NULL, beta REAL NOT NULL,
                    reward_ema REAL, reward_count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (knob, choice_json)
                );
                CREATE TABLE IF NOT EXISTS policy_versions (
                    policy_id TEXT PRIMARY KEY, parent_policy_id TEXT,
                    stage TEXT NOT NULL, candidate_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS trials_algorithm ON search_trials(algorithm);
                CREATE INDEX IF NOT EXISTS policies_stage ON policy_versions(stage, active);
                """
            )

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def record_run(
        self, run_id: str, config_digest: str, candidate: dict[str, Any],
        metrics: dict[str, Any], context: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO learning_runs VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, _now(), config_digest, json.dumps(candidate, sort_keys=True),
                 json.dumps(metrics, sort_keys=True), json.dumps(context or {}, sort_keys=True)),
            )

    def record_trial(
        self, *, run_id: str | None, algorithm: str, candidate: dict[str, Any],
        reward: float, decision: dict[str, Any], ema_alpha: float = 0.2,
    ) -> str:
        if not 0 < ema_alpha <= 1:
            raise OptimizationError("ema_alpha must be in (0, 1]")
        trial_body = {"run_id": run_id, "algorithm": algorithm, "candidate": candidate, "at": _now()}
        trial_id = "trial-" + digest(trial_body)[7:19]
        eligible = bool(decision.get("eligible"))
        with self.connect() as db:
            db.execute(
                "INSERT INTO search_trials VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (trial_id, run_id, algorithm, json.dumps(candidate, sort_keys=True),
                 float(reward), int(eligible), json.dumps(decision, sort_keys=True), _now()),
            )
            for knob, choice in (candidate.get("overrides") or {}).items():
                encoded = json.dumps(choice, sort_keys=True)
                row = db.execute(
                    "SELECT alpha, beta, reward_ema, reward_count FROM choice_posteriors "
                    "WHERE knob = ? AND choice_json = ?", (knob, encoded)
                ).fetchone()
                alpha, beta, old_ema, count = row or (1.0, 1.0, None, 0)
                alpha += 1.0 if eligible else 0.0
                beta += 0.0 if eligible else 1.0
                ema = float(reward) if old_ema is None else ema_alpha * float(reward) + (1 - ema_alpha) * float(old_ema)
                db.execute(
                    "INSERT OR REPLACE INTO choice_posteriors VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (knob, encoded, alpha, beta, ema, count + 1, _now()),
                )
        return trial_id

    def posterior(self, knob: str, choice: Any) -> dict[str, Any]:
        encoded = json.dumps(choice, sort_keys=True)
        with self.connect() as db:
            row = db.execute(
                "SELECT alpha, beta, reward_ema, reward_count FROM choice_posteriors "
                "WHERE knob = ? AND choice_json = ?", (knob, encoded)
            ).fetchone()
        alpha, beta, ema, count = row or (1.0, 1.0, None, 0)
        return {
            "alpha": alpha, "beta": beta,
            "success_probability": alpha / (alpha + beta),
            "reward_ema": ema, "count": count,
        }

    def prefix_stats(self, ordered_knobs: list[str], prefix: dict[str, Any]) -> dict[str, Any]:
        """Aggregate evaluated descendants, equivalent to MCTS backpropagation."""
        rewards, successes = [], 0
        with self.connect() as db:
            rows = db.execute(
                "SELECT candidate_json, reward, eligible FROM search_trials "
                "WHERE reward IS NOT NULL"
            ).fetchall()
        prefix_names = ordered_knobs[: len(prefix)]
        for raw_candidate, reward, eligible in rows:
            try:
                overrides = (json.loads(raw_candidate).get("overrides") or {})
            except (json.JSONDecodeError, AttributeError):
                continue
            if all(overrides.get(name) == prefix.get(name) for name in prefix_names):
                rewards.append(float(reward))
                successes += int(bool(eligible))
        return {
            "visits": len(rewards),
            "mean_reward": sum(rewards) / len(rewards) if rewards else 0.0,
            "success_rate": successes / len(rewards) if rewards else 0.5,
        }

    def promote_shadow(self, candidate: dict[str, Any], evidence: dict[str, Any]) -> str:
        with self.connect() as db:
            parent = db.execute(
                "SELECT policy_id FROM policy_versions WHERE active = 1 ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            body = {"candidate": candidate, "evidence": evidence, "stage": "shadow"}
            policy_id = "policy-" + digest(body)[7:19]
            db.execute("UPDATE policy_versions SET active = 0 WHERE active = 1")
            db.execute(
                "INSERT OR REPLACE INTO policy_versions VALUES (?, ?, 'shadow', ?, ?, ?, 1)",
                (policy_id, parent[0] if parent else None, json.dumps(candidate, sort_keys=True),
                 json.dumps(evidence, sort_keys=True), _now()),
            )
        return policy_id


def _mutable_domains(registry: dict[str, Any], selected: list[str]) -> dict[str, list[Any]]:
    domains = {}
    for name in selected:
        spec = registry["knobs"].get(name)
        if not spec or not spec.get("mutable"):
            raise OptimizationError(f"unknown or locked knob {name}")
        domains[name] = _domain_values(spec)
    return domains


def random_search(
    registry: dict[str, Any], selected: list[str], count: int, seed: int
) -> list[dict[str, Any]]:
    domains = _mutable_domains(registry, selected)
    rng = random.Random(seed)
    defaults = {name: row.get("default") for name, row in registry["knobs"].items()}
    results, seen = [], set()
    attempts = max(100, count * 50)
    for _ in range(attempts):
        overrides = {name: rng.choice(values) for name, values in domains.items()}
        key = json.dumps(overrides, sort_keys=True)
        if key in seen or not _constraints_hold({**defaults, **overrides}, registry):
            continue
        seen.add(key)
        results.append({"candidate_id": "candidate-" + digest(overrides)[7:19], "overrides": overrides})
        if len(results) == count:
            break
    return results


def wide_deep_search(
    registry: dict[str, Any], selected: list[str], count: int,
    seed: int, store: StudyStore | None = None,
) -> list[dict[str, Any]]:
    """Mix broad one-knob probes with local combinations around learned choices."""
    domains = _mutable_domains(registry, selected)
    defaults = {name: row.get("default") for name, row in registry["knobs"].items()}
    candidates: list[dict[str, Any]] = []
    # Wide: isolate every value's marginal effect.
    for name, values in domains.items():
        for value in values:
            candidates.append({"overrides": {name: value}})
    # Deep: center each knob on its best posterior/EMA choice, then perturb jointly.
    center = {}
    for name, values in domains.items():
        if store:
            center[name] = max(
                values,
                key=lambda value: (
                    store.posterior(name, value)["reward_ema"]
                    if store.posterior(name, value)["reward_ema"] is not None else -math.inf,
                    store.posterior(name, value)["success_probability"],
                ),
            )
        else:
            center[name] = defaults[name]
    candidates.append({"overrides": center})
    candidates.extend(random_search(registry, selected, max(count, 1), seed))
    unique, output = set(), []
    for row in candidates:
        overrides = row["overrides"]
        complete = {**defaults, **overrides}
        key = json.dumps(overrides, sort_keys=True)
        if key in unique or not _constraints_hold(complete, registry):
            continue
        unique.add(key)
        output.append({"candidate_id": "candidate-" + digest(overrides)[7:19], "overrides": overrides})
        if len(output) == count:
            break
    return output


def mcts_search(
    registry: dict[str, Any], selected: list[str], count: int, seed: int,
    store: StudyStore, exploration: float = 1.414,
) -> list[dict[str, Any]]:
    """Persistent MCTS over knob assignments with prefix reward backpropagation."""
    domains = _mutable_domains(registry, selected)
    defaults = {name: row.get("default") for name, row in registry["knobs"].items()}
    rng = random.Random(seed)
    output, seen = [], set()
    for rollout in range(max(count * 20, 50)):
        overrides = {}
        for name in selected:
            scored = []
            parent = store.prefix_stats(selected, overrides)
            total = parent["visits"] + 1
            for value in domains[name]:
                child = {**overrides, name: value}
                stats = store.prefix_stats(selected, child)
                visits = stats["visits"]
                # Reward leads; eligibility confidence breaks equal-reward ties.
                exploitation = stats["mean_reward"] + 0.05 * stats["success_rate"]
                bonus = exploration * math.sqrt(math.log(total + 1) / (visits + 1))
                scored.append((exploitation + bonus + rng.random() * 1e-9, value))
            overrides[name] = max(scored, key=lambda item: item[0])[1]
        key = json.dumps(overrides, sort_keys=True)
        if key in seen or not _constraints_hold({**defaults, **overrides}, registry):
            # Stochastic rollout preserves exploration when UCB choices collide.
            random_rows = random_search(registry, selected, 1, seed + rollout + 1)
            if not random_rows:
                continue
            overrides = random_rows[0]["overrides"]
            key = json.dumps(overrides, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        output.append({"candidate_id": "candidate-" + digest(overrides)[7:19], "overrides": overrides})
        if len(output) == count:
            break
    return output
