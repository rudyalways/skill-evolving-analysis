#!/usr/bin/env python3
"""Attach objective SkillsBench outcome evidence to an ACP trajectory.

BenchFlow stores the model trajectory, result, reward, and verifier output in
separate files. The evolving pipeline otherwise sees agent activity without
the terminal ground truth. This command emits a single immutable JSONL stream
whose final tool event contains bounded verifier evidence and scalar outcome.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


MAX_VERIFIER_CHARS = 24_000
MAX_FAILURE_SUMMARIES = 8


def extract_failure_summaries(verifier: str) -> list[dict[str, str]]:
    """Extract compact pytest ground truth before the full bounded transcript.

    Normalized methodology events intentionally have small previews. Keeping the
    failed test and its final assertion in a first-class field prevents package
    installation noise from hiding the only objective learning signal.
    """
    summaries: list[dict[str, str]] = []
    failed_tests = re.findall(r"^FAILED\s+(.+?)(?:\s+-\s+(.+))?$", verifier, re.MULTILINE)
    assertions = re.findall(
        r"^E\s+(AssertionError:.+|assert\s+.+)$", verifier, re.MULTILINE
    )
    for index, (test_id, short_reason) in enumerate(failed_tests[:MAX_FAILURE_SUMMARIES]):
        assertion = assertions[index] if index < len(assertions) else short_reason
        summaries.append(
            {
                "test": test_id.strip()[:500],
                "assertion": str(assertion or "").strip()[:1200],
            }
        )
    return summaries


def build_outcome(result_path: Path, verifier_path: Path, reward_path: Path) -> dict:
    result = json.loads(result_path.read_text())
    verifier = verifier_path.read_text(errors="replace")
    reward_text = reward_path.read_text(errors="replace").strip()
    try:
        reward: int | float | str = float(reward_text)
        if reward.is_integer():
            reward = int(reward)
    except ValueError:
        reward = reward_text
    return {
        "reward": reward,
        "rewards": result.get("rewards") or {},
        "error": result.get("error"),
        "skill_mode": result.get("skill_mode"),
        "tool_calls": result.get("n_tool_calls"),
        "verifier_failures": extract_failure_summaries(verifier),
        "verifier_output": verifier[:MAX_VERIFIER_CHARS],
        "verifier_output_truncated": len(verifier) > MAX_VERIFIER_CHARS,
    }


def enrich(
    trajectory_path: Path,
    result_path: Path,
    verifier_path: Path,
    reward_path: Path,
    output_path: Path,
) -> None:
    rows = trajectory_path.read_text(errors="replace").splitlines()
    outcome = build_outcome(result_path, verifier_path, reward_path)
    terminal = {
        "type": "tool_call",
        "tool_call_id": "skillsbench-objective-verifier",
        "kind": "verify",
        "title": "skillsbench_objective_verifier",
        "status": "completed" if outcome["reward"] == 1 else "failed",
        "input": {"source": "benchflow", "objective": True},
        "content": [
            {
                "type": "content",
                "content": {
                    "type": "text",
                    "text": json.dumps(outcome, ensure_ascii=False, sort_keys=True),
                },
            }
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join([*rows, json.dumps(terminal)]) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--verifier", type=Path, required=True)
    parser.add_argument("--reward", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    enrich(args.trajectory, args.result, args.verifier, args.reward, args.output)


if __name__ == "__main__":
    main()
