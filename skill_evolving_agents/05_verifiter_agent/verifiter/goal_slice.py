"""Keep one goal op for the optimize loop."""

from __future__ import annotations

import copy


def slice_goal(goal: dict, op: int | None) -> dict:
    if op is None:
        return goal
    ops = (goal.get("action") or {}).get("ops") or []
    if not isinstance(ops, list) or op < 1 or op > len(ops):
        count = len(ops) if isinstance(ops, list) else 0
        raise SystemExit(f"op {op} is outside 1..{count}")
    narrowed = copy.deepcopy(goal)
    narrowed["action"]["ops"] = [ops[op - 1]]
    return narrowed
