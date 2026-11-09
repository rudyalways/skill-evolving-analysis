#!/usr/bin/env python3
"""Build auditable per-task skill bundles with the configured embedding service."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.embedding_api.provider import EmbeddingProvider  # noqa: E402
from common import skill_resources  # noqa: E402
from common.task_intent import compatibility as task_intent_compatibility  # noqa: E402


DEFAULT_POLICY_PATH = Path(__file__).with_name("router-policy.json")


def load_router_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text())
    required = {
        "strategy", "recall_k", "top_k", "minimum_score", "minimum_margin",
        "document_max_chars", "feedback_formula",
    }
    missing = sorted(required - set(policy))
    if missing:
        raise ValueError(f"router policy missing: {', '.join(missing)}")
    return policy


ROUTER_POLICY = load_router_policy()
FEEDBACK_FORMULA = dict(ROUTER_POLICY["feedback_formula"])


def load_feedback_calibration(
    path: Path | None,
    formula: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Aggregate immutable benchmark outcomes into per-skill calibration."""
    active_formula = dict(formula or FEEDBACK_FORMULA)
    if path is None or not path.is_file():
        return {"database": str(path) if path else None, "skills": {}, "events": 0}
    rows: list[tuple[str, str, str | None]] = []
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as database:
        rows = database.execute(
            "SELECT feedback_id, value_json, supersedes FROM feedback_events "
            "WHERE source = 'benchmark' AND signal = 'skill-runtime-outcome' "
            "ORDER BY feedback_id"
        ).fetchall()
    digest = hashlib.sha256()
    grouped: dict[str, list[dict[str, Any]]] = {}
    grouped_by_task: dict[str, list[dict[str, Any]]] = {}
    superseded = {row[2] for row in rows if row[2]}
    active_rows = [row for row in rows if row[0] not in superseded]
    for feedback_id, value_json, _ in active_rows:
        digest.update(str(feedback_id).encode())
        digest.update(b"\0")
        digest.update(str(value_json).encode())
        digest.update(b"\0")
        value = json.loads(value_json)
        if not (
            bool(value.get("skill_md_read"))
            or bool(value.get("skill_md_injected"))
        ):
            # Discovery-only exposure is useful deployment telemetry, but it
            # is not evidence that the skill caused the task outcome.
            continue
        skill = value.get("skill")
        if isinstance(skill, str) and skill:
            version = value.get("skill_hash") or "unversioned"
            versioned = f"{skill}@{version}"
            task_id = value.get("task_id")
            if isinstance(task_id, str) and task_id:
                # Task-scoped evidence must not leak into the global prior.
                # Otherwise one costly task suppresses the skill everywhere.
                grouped_by_task.setdefault(f"{task_id}|{versioned}", []).append(value)
            else:
                grouped.setdefault(versioned, []).append(value)

    def summarize(groups: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        summaries: dict[str, Any] = {}
        for key, events in sorted(groups.items()):
            reward_deltas = [float(row.get("reward_delta") or 0) for row in events]
            ratios = []
            for row in events:
                baseline = max(1, int(row.get("baseline_tool_calls") or 0))
                treatment = int(row.get("treatment_tool_calls") or 0)
                ratios.append(max(0.0, min(2.0, (treatment - baseline) / baseline)))
            count = len(events)
            no_benefit_rate = sum(delta <= 0 for delta in reward_deltas) / count
            regression_rate = sum(delta < 0 for delta in reward_deltas) / count
            mean_reward_delta = sum(reward_deltas) / count
            mean_call_ratio = sum(ratios) / count
            adjustment = (
                active_formula["reward_delta_weight"] * mean_reward_delta
                + active_formula["no_benefit_rate_weight"] * no_benefit_rate
                + active_formula["regression_rate_weight"] * regression_rate
                + active_formula["positive_tool_call_ratio_weight"] * mean_call_ratio
            )
            summaries[key] = {
                "observations": count,
                "mean_reward_delta": round(mean_reward_delta, 6),
                "no_benefit_rate": round(no_benefit_rate, 6),
                "regression_rate": round(regression_rate, 6),
                "mean_positive_tool_call_ratio": round(mean_call_ratio, 6),
                "score_adjustment": round(adjustment, 6),
            }
        return summaries

    skills = summarize(grouped)
    task_skills = summarize(grouped_by_task)
    return {
        "database": str(path.resolve()),
        "events": len(active_rows),
        "superseded_events": len(rows) - len(active_rows),
        "digest": "sha256:" + digest.hexdigest(),
        "formula": active_formula,
        "skills": skills,
        "task_skills": task_skills,
    }


def skill_document(path: Path, max_chars: int) -> str:
    text = path.read_text(errors="replace")
    return text[:max_chars]


def intent_compatibility(task: str, skill_text: str) -> tuple[bool, str | None]:
    """Reject high-similarity candidates whose intent contradicts the task.

    The gate is offline and generalizes from declared object/action scope, not
    from task names.  A skill scoped to XML document variants cannot own a
    single presentation-formatting request merely because both mention titles;
    a Three.js OBJ exporter still owns a Three.js export request, and a
    plan-view accessibility method still owns an ADA bathroom repair.

    This cheap precision gate is deliberately asymmetric: uncertain cases
    remain eligible.
    """
    return task_intent_compatibility(task, skill_text)


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def select_task_skills(
    *,
    tasks: dict[str, str],
    skills_root: Path,
    provider: EmbeddingProvider,
    top_k: int,
    minimum_score: float,
    document_max_chars: int,
    feedback_calibration: dict[str, Any] | None = None,
    recall_k: int | None = None,
    minimum_margin: float = 0.04,
    feedback_min_observations: int = 1,
    strategy: str = str(ROUTER_POLICY["strategy"]),
) -> dict[str, Any]:
    all_skill_paths = {
        path.parent.name: path
        for path in sorted(skills_root.glob("*/SKILL.md"))
    }
    if not all_skill_paths:
        raise ValueError(f"no skills found under {skills_root}")
    policy = json.loads((REPO_ROOT / "common/preprocessing-config.json").read_text())[
        "evolution_policy"
    ]
    required_above = int(policy["progressive_disclosure_required_above_tokens"])
    minimum_share = float(policy["progressive_disclosure_min_reference_share"])
    maximum_tokens = int(policy["max_skill_md_tokens"])
    excluded: dict[str, dict[str, Any]] = {}
    skill_paths: dict[str, Path] = {}
    for name, path in all_skill_paths.items():
        metrics = skill_resources.measure_skill_resources(
            path.parent, runtime_observation_available=False
        )["progressive_disclosure"]
        tokens = int(metrics["skill_md_tokens"])
        share = float(metrics["estimated_skill_md_token_reduction"])
        reasons = []
        if tokens > maximum_tokens:
            reasons.append("skill-md-token-cap")
        if tokens > required_above and share < minimum_share:
            reasons.append("missing-progressive-disclosure")
        if reasons:
            excluded[name] = {
                "reasons": reasons,
                "skill_md_tokens": tokens,
                "reference_share": share,
            }
        else:
            skill_paths[name] = path
    if not skill_paths:
        raise ValueError("no quality-eligible skills remain after routing gates")
    documents = {
        name: skill_document(path, document_max_chars)
        for name, path in skill_paths.items()
    }
    skill_hashes = {name: tree_hash(path.parent) for name, path in skill_paths.items()}
    task_ids = sorted(tasks)
    response = provider.search(
        [tasks[task_id] for task_id in task_ids],
        documents,
        top_k=recall_k or top_k,
    )
    selections: dict[str, Any] = {}
    calibration = feedback_calibration or {"skills": {}}
    skill_feedback = calibration.get("skills") or {}
    task_skill_feedback = calibration.get("task_skills") or {}
    for task_id, result in zip(task_ids, response.get("results") or []):
        ranked = []
        for row in result.get("matches") or []:
            skill = str(row["id"])
            raw_score = float(row["score"])
            versioned = f"{skill}@{skill_hashes[skill]}"
            task_feedback = task_skill_feedback.get(f"{task_id}|{versioned}")
            feedback = task_feedback or skill_feedback.get(versioned)
            if feedback:
                score = max(0.0, min(1.0, raw_score + float(feedback["score_adjustment"])))
                ranked.append({
                    "skill": skill,
                    "score": round(score, 6),
                    "raw_score": round(raw_score, 6),
                    "feedback": feedback,
                    "feedback_scope": "task" if task_feedback else "global",
                })
            else:
                ranked.append({"skill": skill, "score": raw_score})
        # Calibration is an abstention gate, not permission to backfill a
        # weaker semantic candidate.  Preserve embedding rank so negative
        # evidence for the best match cannot accidentally promote an
        # unrelated runner-up.
        proven = [
            row for row in ranked
            if row.get("feedback_scope") == "task"
            and float((row.get("feedback") or {}).get("mean_reward_delta") or 0) > 0
            and float(row["score"]) >= minimum_score
        ]
        selected = (
            sorted(proven, key=lambda row: float(row["score"]), reverse=True)[:top_k]
            if proven
            else [row for row in ranked[:top_k] if row["score"] >= minimum_score]
        )
        raw_margin = None
        if len(ranked) >= 2:
            first_raw = float(ranked[0].get("raw_score", ranked[0]["score"]))
            second_raw = float(ranked[1].get("raw_score", ranked[1]["score"]))
            raw_margin = round(first_raw - second_raw, 6)
        positive_feedback = bool(
            ranked
            and isinstance(ranked[0].get("feedback"), dict)
            and float(ranked[0]["feedback"].get("mean_reward_delta") or 0) > 0
        )
        abstention_reasons: list[str] = []
        if ranked and float(ranked[0]["score"]) < minimum_score:
            abstention_reasons.append("below-minimum-score")
        top_task_feedback = (
            ranked[0].get("feedback")
            if ranked and ranked[0].get("feedback_scope") == "task"
            else None
        )
        calibrated_regression = bool(
            top_task_feedback
            and int(top_task_feedback.get("observations") or 0)
            >= feedback_min_observations
            and float(top_task_feedback.get("mean_reward_delta") or 0) < 0
            and float(top_task_feedback.get("regression_rate") or 0) > 0
        )
        if (
            top_k == 1
            and raw_margin is not None
            and raw_margin < minimum_margin
            and not positive_feedback
        ):
            selected = []
            abstention_reasons.append("insufficient-semantic-margin")
        if calibrated_regression:
            # Task-scoped benchmark evidence outranks embedding similarity.
            # A confirmed regression on this exact task cannot be promoted by a
            # runner-up candidate; abstain and name the cause even when the
            # calibrated score already fell below the threshold.
            selected = []
            abstention_reasons.append("feedback-regression")
        if selected:
            # Use the full SKILL.md for intent checks.  The embedding document
            # is deliberately truncated, but a scope statement such as
            # "Do not use for non-XML formats" often sits below the truncation.
            compatible, mismatch = intent_compatibility(
                tasks[task_id],
                skill_paths[selected[0]["skill"]].read_text(errors="replace"),
            )
            if not compatible:
                selected = []
                abstention_reasons.append(f"intent-mismatch:{mismatch}")
        selections[task_id] = {
            "selected": selected,
            "ranked": ranked,
            "selection_count": len(selected),
            "raw_margin": raw_margin,
            "abstention_reasons": abstention_reasons,
        }
    return {
        "schema_version": 1,
        "strategy": strategy,
        "model": response.get("model"),
        "model_revision": response.get("model_revision"),
        "index_revision": response.get("index_revision"),
        "service_ms": response.get("service_ms"),
        "embedding_cache": response.get("cache"),
        "top_k": top_k,
        "recall_k": recall_k or top_k,
        "minimum_score": minimum_score,
        "minimum_margin": minimum_margin,
        "feedback_min_observations": feedback_min_observations,
        "document_max_chars": document_max_chars,
        "skills_root": str(skills_root.resolve()),
        "skills_root_hash": tree_hash(skills_root),
        "eligible_skill_count": len(skill_paths),
        "eligible_skill_hashes": skill_hashes,
        "excluded_skills": excluded,
        "feedback_calibration": {
            key: value for key, value in calibration.items()
            if key not in {"skills", "task_skills"}
        },
        "tasks": selections,
    }


def fallback_embedding_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    """Return the deterministic no-download runtime used on local model failure."""
    fallback = {
        **runtime,
        "transport": "in_process",
        "backend": "hashing-reference",
    }
    for field in ("model", "revision", "device", "query_instruction", "endpoint"):
        fallback.pop(field, None)
    return fallback


def materialize(report: dict[str, Any], skills_root: Path, out_root: Path) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    for task_id, row in report["tasks"].items():
        bundle = out_root / task_id
        if bundle.exists() and any(bundle.iterdir()):
            raise ValueError(f"refusing to replace non-empty bundle {bundle}")
        bundle.mkdir(parents=True, exist_ok=True)
        for selected in row["selected"]:
            name = selected["skill"]
            shutil.copytree(
                skills_root / name,
                bundle / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        row["bundle"] = str(bundle.resolve())
        row["bundle_hash"] = tree_hash(bundle)


def parse_tasks(values: list[str]) -> dict[str, str]:
    tasks: dict[str, str] = {}
    for value in values:
        task_id, separator, prompt_path = value.partition("=")
        if not separator or not task_id or not prompt_path:
            raise ValueError("--task must be TASK_ID=PROMPT_FILE")
        path = Path(prompt_path)
        if path.suffix == ".jsonl":
            prompt = ""
            for line in path.read_text(errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "user_message" and isinstance(event.get("text"), str):
                    prompt = event["text"]
                    break
            if not prompt:
                raise ValueError(f"trajectory has no user_message text: {prompt_path}")
        elif path.suffix.lower() in {".md", ".txt"}:
            prompt = path.read_text(errors="replace").strip()
            if not prompt:
                raise ValueError(f"prompt file is empty: {prompt_path}")
        else:
            payload = json.loads(path.read_text())
            if isinstance(payload, list) and payload and isinstance(payload[0], str):
                prompt = payload[0]
            elif isinstance(payload, str):
                prompt = payload
            else:
                raise ValueError(
                    f"prompt file must be Markdown, text, a string, or a string list: {prompt_path}"
                )
        tasks[task_id] = prompt
    return tasks


def main() -> None:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    bootstrap_args, _ = bootstrap.parse_known_args()
    policy = load_router_policy(bootstrap_args.policy)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=bootstrap_args.policy)
    parser.add_argument("--task", action="append", required=True, help="TASK_ID=PROMPT_FILE")
    parser.add_argument("--skills-root", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=Path("profiles/low-cost-local-service.json"))
    parser.add_argument("--top-k", type=int, default=int(policy["top_k"]))
    parser.add_argument("--recall-k", type=int, default=int(policy["recall_k"]))
    parser.add_argument("--minimum-score", type=float, default=float(policy["minimum_score"]))
    parser.add_argument("--minimum-margin", type=float, default=float(policy["minimum_margin"]))
    parser.add_argument(
        "--feedback-min-observations",
        type=int,
        default=int(policy.get("feedback_min_observations", 1)),
        help="task-scoped observations required before negative feedback abstains",
    )
    parser.add_argument("--document-max-chars", type=int, default=int(policy["document_max_chars"]))
    parser.add_argument(
        "--feedback-database",
        type=Path,
        help="optimization SQLite DB containing benchmark skill-runtime feedback",
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.top_k <= 10:
        parser.error("--top-k must be 1..10")
    if not args.top_k <= args.recall_k <= 25:
        parser.error("--recall-k must be between --top-k and 25")
    if not 0 <= args.minimum_score <= 1:
        parser.error("--minimum-score must be 0..1")
    if not 0 <= args.minimum_margin <= 1:
        parser.error("--minimum-margin must be 0..1")
    if args.feedback_min_observations < 1:
        parser.error("--feedback-min-observations must be at least 1")
    tasks = parse_tasks(args.task)
    feedback_calibration = load_feedback_calibration(
        args.feedback_database,
        formula=policy["feedback_formula"],
    )
    feedback_calibration["policy"] = str(args.policy.resolve())
    feedback_calibration["policy_digest"] = (
        "sha256:" + hashlib.sha256(args.policy.read_bytes()).hexdigest()
    )
    profile = json.loads(args.profile.read_text())
    runtime = profile["embedding_runtime"]
    server = Path(__file__).resolve().parents[1] / "services/embedding_api/server.py"
    selection_args = {
        "tasks": tasks,
        "skills_root": args.skills_root,
        "top_k": args.top_k,
        "minimum_score": args.minimum_score,
        "document_max_chars": args.document_max_chars,
        "feedback_calibration": feedback_calibration,
        "recall_k": args.recall_k,
        "minimum_margin": args.minimum_margin,
        "feedback_min_observations": args.feedback_min_observations,
        "strategy": str(policy["strategy"]),
    }
    try:
        with EmbeddingProvider(runtime, server) as provider:
            report = select_task_skills(provider=provider, **selection_args)
    except (ImportError, OSError, RuntimeError) as error:
        fallback = fallback_embedding_runtime(runtime)
        with EmbeddingProvider(fallback, server) as provider:
            report = select_task_skills(provider=provider, **selection_args)
        report["embedding_fallback"] = {
            "requested_backend": runtime.get("backend"),
            "selected_backend": "hashing-reference",
            "reason": f"{type(error).__name__}: {error}",
        }
    materialize(report, args.skills_root, args.out_root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
