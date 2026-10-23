"""Constrained, persistent dynamic workflow state machine."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from policy.contracts import stable_digest


class StateMachineError(ValueError):
    pass


def load_machine(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise StateMachineError(f"cannot load state machine {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise StateMachineError("state machine schema_version must be 1")
    states = value.get("states")
    transitions = value.get("transitions")
    if not isinstance(states, dict) or not states:
        raise StateMachineError("state machine requires states")
    if value.get("initial_state") not in states:
        raise StateMachineError("initial state is not registered")
    if not isinstance(transitions, list):
        raise StateMachineError("state machine transitions must be an array")
    seen = set()
    for index, row in enumerate(transitions):
        if not isinstance(row, dict) or row.get("from") not in states or row.get("to") not in states:
            raise StateMachineError(f"transition {index} references an unknown state")
        key = (row["from"], row["to"])
        if key in seen:
            raise StateMachineError(f"duplicate transition {key}")
        seen.add(key)
        if not isinstance(row.get("reasons"), list) or not row["reasons"]:
            raise StateMachineError(f"transition {key} requires reasons")
    terminals = set(value.get("terminal_states") or [])
    if not terminals or not terminals <= set(states):
        raise StateMachineError("terminal states are invalid")
    return value


@dataclass(frozen=True)
class TransitionDecision:
    next_state: str
    reason: str
    implementation: str | None = None
    probability: float | None = None
    predicted_quality: float | None = None
    predicted_cost: float | None = None
    uncertainty: float | None = None
    metadata: dict[str, Any] | None = None


class StateMachineRuntime:
    def __init__(
        self,
        definition: dict[str, Any],
        *,
        run_id: str,
        item_id: str,
        database: Path,
        journal: Path | None = None,
    ):
        self.definition = definition
        self.run_id = run_id
        self.item_id = item_id
        self.database = database
        self.journal = journal
        self.state = str(definition["initial_state"])
        self.step = 0
        self.visits: Counter[str] = Counter({self.state: 1})
        self.edge_uses: Counter[tuple[str, str]] = Counter()
        self.history: list[dict[str, Any]] = []
        self._transitions = {
            (row["from"], row["to"]): row for row in definition["transitions"]
        }
        self._initialize_store()

    @property
    def terminal(self) -> bool:
        return self.state in set(self.definition["terminal_states"])

    def allowed(self) -> list[str]:
        return sorted(target for source, target in self._transitions if source == self.state)

    @classmethod
    def restore(
        cls,
        definition: dict[str, Any],
        snapshot: dict[str, Any],
        *,
        database: Path,
        journal: Path | None = None,
    ) -> "StateMachineRuntime":
        if snapshot.get("schema_version") != 1:
            raise StateMachineError("snapshot schema_version must be 1")
        machine = cls(
            definition,
            run_id=str(snapshot["run_id"]),
            item_id=str(snapshot["item_id"]),
            database=database,
            journal=journal,
        )
        state = str(snapshot.get("state"))
        if state not in definition["states"]:
            raise StateMachineError("snapshot contains unknown state")
        history = snapshot.get("history")
        visits = snapshot.get("visits")
        if not isinstance(history, list) or not isinstance(visits, dict):
            raise StateMachineError("snapshot history and visits are required")
        machine.state = state
        machine.step = int(snapshot.get("step") or 0)
        machine.history = list(history)
        machine.visits = Counter({str(key): int(value) for key, value in visits.items()})
        machine.edge_uses = Counter(
            (str(row["from_state"]), str(row["to_state"]))
            for row in history
            if isinstance(row, dict) and "from_state" in row and "to_state" in row
        )
        if machine.step != len(machine.history):
            raise StateMachineError("snapshot step does not match history length")
        return machine

    def transition(self, decision: TransitionDecision) -> dict[str, Any]:
        if self.terminal:
            raise StateMachineError(f"cannot transition terminal state {self.state}")
        edge = (self.state, decision.next_state)
        rule = self._transitions.get(edge)
        if rule is None:
            raise StateMachineError(f"transition {edge[0]} -> {edge[1]} is not allowed")
        if decision.reason not in rule["reasons"]:
            raise StateMachineError(
                f"reason {decision.reason!r} is invalid for {edge[0]} -> {edge[1]}"
            )
        target_spec = self.definition["states"][decision.next_state]
        implementations = target_spec.get("implementations") or []
        if decision.implementation is not None and decision.implementation not in implementations:
            raise StateMachineError(
                f"implementation {decision.implementation!r} is invalid for {decision.next_state}"
            )
        probability = decision.probability
        if probability is not None and not 0 <= probability <= 1:
            raise StateMachineError("transition probability must be from 0 to 1")
        defaults = self.definition.get("defaults") or {}
        if self.step + 1 > int(defaults.get("max_steps", 32)):
            raise StateMachineError("state machine max_steps exceeded")
        if self.visits[decision.next_state] + 1 > int(defaults.get("max_visits_per_state", 3)):
            raise StateMachineError(f"visit limit exceeded for {decision.next_state}")
        edge_limit = rule.get("max_uses")
        if edge_limit is not None and self.edge_uses[edge] + 1 > int(edge_limit):
            raise StateMachineError(f"edge use limit exceeded for {edge}")
        if decision.next_state == "PUBLISH":
            required = (self.definition.get("immutable_rules") or {}).get("publish_requires_visit")
            if required and self.visits[str(required)] < 1:
                raise StateMachineError(f"publish requires prior visit to {required}")
        self.step += 1
        previous = self.state
        self.state = decision.next_state
        self.visits[self.state] += 1
        self.edge_uses[edge] += 1
        event = {
            "schema_version": 1,
            "transition_id": "transition-" + stable_digest(
                {"run": self.run_id, "item": self.item_id, "step": self.step, "from": previous, "to": self.state}
            )[7:19],
            "run_id": self.run_id,
            "item_id": self.item_id,
            "step": self.step,
            "from_state": previous,
            "to_state": self.state,
            "reason": decision.reason,
            "implementation": decision.implementation,
            "probability": probability,
            "predicted_quality": decision.predicted_quality,
            "predicted_cost": decision.predicted_cost,
            "uncertainty": decision.uncertainty,
            "metadata": decision.metadata or {},
            "at": datetime.now(UTC).isoformat(),
        }
        self.history.append(event)
        self._persist(event)
        return event

    def run(
        self,
        handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]],
        policy: Callable[[str, dict[str, Any], list[str]], TransitionDecision],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a genuinely dynamic flow using registered state handlers."""
        context = dict(context or {})
        while not self.terminal:
            handler = handlers.get(self.state)
            if handler is not None:
                update = handler(context)
                if update:
                    context.update(update)
            decision = policy(self.state, context, self.allowed())
            self.transition(decision)
        return {"state": self.state, "steps": self.step, "context": context, "history": self.history}

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "machine": self.definition["machine"],
            "run_id": self.run_id,
            "item_id": self.item_id,
            "state": self.state,
            "step": self.step,
            "terminal": self.terminal,
            "visits": dict(self.visits),
            "history": self.history,
        }

    def _initialize_store(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database, timeout=30) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS state_transitions (
                    transition_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    item_id TEXT NOT NULL, step INTEGER NOT NULL,
                    from_state TEXT NOT NULL, to_state TEXT NOT NULL,
                    reason TEXT NOT NULL, implementation TEXT,
                    probability REAL, predicted_quality REAL,
                    predicted_cost REAL, uncertainty REAL,
                    metadata_json TEXT NOT NULL, at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS state_transitions_run
                ON state_transitions(run_id, item_id, step);
                """
            )

    def _persist(self, event: dict[str, Any]) -> None:
        with sqlite3.connect(self.database, timeout=30) as db:
            db.execute(
                "INSERT INTO state_transitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event["transition_id"], event["run_id"], event["item_id"], event["step"],
                    event["from_state"], event["to_state"], event["reason"],
                    event["implementation"], event["probability"], event["predicted_quality"],
                    event["predicted_cost"], event["uncertainty"],
                    json.dumps(event["metadata"], sort_keys=True), event["at"],
                ),
            )
        if self.journal is not None:
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            with self.journal.open("a") as stream:
                stream.write(json.dumps(event, sort_keys=True) + "\n")
