#!/usr/bin/env python3
"""Generate bounded experiments and evaluate recorded metric results."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.optimization import (  # noqa: E402
    evaluate_candidate,
    experiment_manifest,
    generate_grid,
    load_spec,
    objective_reward,
    summarize_observations,
    validate_knob_registry,
    validate_metric_spec,
)
from core.online_learning import StudyStore, mcts_search, random_search, wide_deep_search  # noqa: E402
from policy.store import PolicyStore  # noqa: E402
from policy.contracts import stable_digest  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=ROOT / "config/knob-registry.json")
    parser.add_argument("--metrics", type=Path, default=ROOT / "config/metric-spec.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    summarize = sub.add_parser("summarize")
    summarize.add_argument("--observations", type=Path, required=True)
    summarize.add_argument("--output", type=Path, required=True)
    grid = sub.add_parser("grid")
    grid.add_argument("--knob", action="append", required=True)
    grid.add_argument("--max-candidates", type=int, default=256)
    grid.add_argument("--code-revision", required=True)
    grid.add_argument("--dataset-revision", required=True)
    grid.add_argument("--profile-digest", required=True)
    grid.add_argument("--model-revisions", type=Path, required=True)
    grid.add_argument("--seed", type=int, default=0)
    grid.add_argument("--output", type=Path, required=True)
    decide = sub.add_parser("decide")
    decide.add_argument("--baseline", type=Path, required=True)
    decide.add_argument("--candidate", type=Path, required=True)
    decide.add_argument("--output", type=Path, required=True)
    search = sub.add_parser("search")
    search.add_argument("--algorithm", choices=["random", "wide-deep", "mcts"], required=True)
    search.add_argument("--knob", action="append", required=True)
    search.add_argument("--count", type=int, default=16)
    search.add_argument("--seed", type=int, default=0)
    search.add_argument("--database", type=Path, required=True)
    search.add_argument("--output", type=Path, required=True)
    learn = sub.add_parser("learn")
    learn.add_argument("--database", type=Path, required=True)
    learn.add_argument("--run-id", required=True)
    learn.add_argument("--algorithm", required=True)
    learn.add_argument("--candidate-config", type=Path, required=True)
    learn.add_argument("--baseline", type=Path, required=True)
    learn.add_argument("--candidate", type=Path, required=True)
    learn.add_argument("--config-digest", required=True)
    learn.add_argument("--ema-alpha", type=float, default=0.2)
    learn.add_argument("--output", type=Path, required=True)
    feedback = sub.add_parser("feedback")
    feedback.add_argument("--database", type=Path, required=True)
    feedback.add_argument("--run-id", required=True)
    feedback.add_argument("--decision-id")
    feedback.add_argument("--source", choices=["human", "verifier", "benchmark", "runtime"], required=True)
    feedback.add_argument("--signal", required=True)
    feedback.add_argument("--value", required=True, help="JSON value: true, false, 1-5, number, string, or object")
    feedback.add_argument("--confidence", type=float, default=1.0)
    feedback.add_argument("--supersedes")
    args = parser.parse_args()

    registry = validate_knob_registry(load_spec(args.registry, "knob registry"))
    metrics = validate_metric_spec(load_spec(args.metrics, "metric spec"))
    if args.command == "validate":
        print("optimization configuration valid")
    elif args.command == "summarize":
        observations = [
            json.loads(line)
            for line in args.observations.read_text().splitlines()
            if line.strip()
        ]
        summary = summarize_observations(observations, metrics)
        write_json(args.output, summary)
        print(f"summarized {len(observations)} observations to {args.output}")
    elif args.command == "grid":
        candidates = generate_grid(registry, args.knob, max_candidates=args.max_candidates)
        models = json.loads(args.model_revisions.read_text())
        manifest = experiment_manifest(
            code_revision=args.code_revision,
            dataset_revision=args.dataset_revision,
            profile_digest=args.profile_digest,
            model_revisions=models,
            seed=args.seed,
            candidates=candidates,
            registry=registry,
            metric_spec=metrics,
        )
        write_json(args.output, manifest)
        print(f"wrote {len(candidates)} candidates to {args.output}")
    elif args.command == "search":
        store = StudyStore(args.database)
        if args.algorithm == "random":
            candidates = random_search(registry, args.knob, args.count, args.seed)
        elif args.algorithm == "wide-deep":
            candidates = wide_deep_search(registry, args.knob, args.count, args.seed, store)
        else:
            candidates = mcts_search(registry, args.knob, args.count, args.seed, store)
        write_json(args.output, {"schema_version": 1, "algorithm": args.algorithm, "candidates": candidates})
        print(f"wrote {len(candidates)} {args.algorithm} candidates to {args.output}")
    elif args.command == "learn":
        store = StudyStore(args.database)
        baseline = json.loads(args.baseline.read_text())
        candidate_metrics = json.loads(args.candidate.read_text())
        candidate_config = json.loads(args.candidate_config.read_text())
        decision = evaluate_candidate(baseline, candidate_metrics, metrics)
        reward = objective_reward(baseline, candidate_metrics, metrics)
        store.record_run(args.run_id, args.config_digest, candidate_config, candidate_metrics)
        trial_id = store.record_trial(
            run_id=args.run_id, algorithm=args.algorithm, candidate=candidate_config,
            reward=reward, decision=decision, ema_alpha=args.ema_alpha,
        )
        policy_id = store.promote_shadow(candidate_config, {"trial_id": trial_id, "decision": decision}) if decision["eligible"] else None
        result = {**decision, "reward": reward, "trial_id": trial_id, "shadow_policy_id": policy_id}
        write_json(args.output, result)
        print(result["decision"])
    elif args.command == "feedback":
        value = json.loads(args.value)
        identity = {
            "run_id": args.run_id,
            "decision_id": args.decision_id,
            "source": args.source,
            "signal": args.signal,
            "value": value,
            "supersedes": args.supersedes,
        }
        event = {
            "feedback_id": "feedback-" + stable_digest(identity)[7:19],
            **identity,
            "confidence": args.confidence,
        }
        PolicyStore(args.database).record_feedback(event)
        print(event["feedback_id"])
    else:
        baseline = json.loads(args.baseline.read_text())
        candidate = json.loads(args.candidate.read_text())
        result = evaluate_candidate(baseline, candidate, metrics)
        write_json(args.output, result)
        print(result["decision"])


if __name__ == "__main__":
    main()
