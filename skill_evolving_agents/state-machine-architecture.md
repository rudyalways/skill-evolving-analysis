# Dynamic pipeline state machine

The pipeline now uses a constrained state-machine control plane. Phase
implementations and canonical artifacts remain stable; orchestration may choose
among registered transitions and implementations.

The machine definition is [`config/state-machine.json`](config/state-machine.json)
and the executor is [`core/state_machine.py`](core/state_machine.py).

## Runtime model

One evolution item has one state-machine instance. Many items may execute in
parallel through the existing scheduler. Each transition records source,
target, reason, implementation, probability, predicted quality/cost,
uncertainty, metadata, and timestamp.

Transitions are persisted to:

- `logs/state-transitions.jsonl` for local replay;
- `workspace/optimization.sqlite/state_transitions` for cross-run learning;
- `run/state-machine/snapshot.json` for current state, audit, and restoration.

The generic executor accepts state handlers plus a transition policy. That
policy may be deterministic, search/MCTS-based, or transformer-based. The
production compatibility path currently follows the existing phase order while
recording the same contracts that dynamic policies will use.

## Enforced constraints

- Only registered edges and reason codes are accepted.
- Implementations must be registered for the target state.
- Transition probabilities must be in `[0, 1]`.
- Global step, per-state visit, and per-edge loop limits are enforced.
- Publication requires a prior verification visit.
- Publication remains the deterministic atomic implementation.
- Terminal states cannot transition again.

The state graph includes optional semantic filtering, deferral, human review,
OOD escalation, no-change completion, verification retry, rejection, and
failure paths. Adding a state or edge requires a versioned definition change;
the policy cannot invent one during a run.

## Migration status

The top-level runner now enters and validates the states `NORMALIZE`, `DETECT`,
`POLICY`, optional `SEMANTIC_FILTER`, `LABEL_SKILLS`, `SELECT_UNITS`,
`DIAGNOSE`, `RECALL`, `GOAL`, `OPTIMIZE`, `VERIFY`, `PUBLISH`, and `COMPLETE`.

Some existing functions still execute composite work—for example diagnosis and
goal fanout, or optimize/verify/publish fanout. The next refactor should create
one state-machine instance per finding and replace those composites with state
handlers. The current compatibility migration intentionally preserves their
tested concurrency and skill-conflict behavior.
