"""CLI for the golden-skill benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import run_benchmark, write_report


DEFAULT_SKILL = (
    Path(__file__).resolve().parents[1]
    / "golden_skills"
    / "report-publishing"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", type=Path, default=DEFAULT_SKILL)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--agent", choices=("reference", "incomplete"), default="reference")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_benchmark(
        args.skill,
        count=args.count,
        agent_name=args.agent,
    )
    if args.out:
        write_report(report, args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["overall"]["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
