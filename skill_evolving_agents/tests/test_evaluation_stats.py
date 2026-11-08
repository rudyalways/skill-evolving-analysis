import json
from pathlib import Path

from evaluation.paired_benchmark_report import build_report
from evaluation.pipeline_stats import aggregate
from evaluation.benchmark_resource_feedback import build_feedback
from evaluation.benchmark_skill_router import tree_hash


def _trial(root: Path, task: str, suffix: str, passed: float, calls: int, seconds: int) -> None:
    path = root / f"{task}__{suffix}"
    (path / "verifier").mkdir(parents=True)
    (path / "verifier/reward.txt").write_text(str(passed))
    (path / "result.json").write_text(json.dumps({"n_tool_calls": calls}))
    (path / "timing.json").write_text(json.dumps({"agent_execution": seconds}))


def test_paired_report_preserves_repeated_trials(tmp_path: Path) -> None:
    baseline, treatment = tmp_path / "base", tmp_path / "treated"
    baseline.mkdir(); treatment.mkdir()
    _trial(baseline, "task-a", "01", 0, 4, 10)
    _trial(baseline, "task-a", "02", 1, 5, 12)
    _trial(treatment, "task-a", "01", 1, 6, 14)
    _trial(treatment, "task-a", "02", 1, 4, 9)
    report = build_report(baseline, treatment, benchmark="b@1", cohort="c", exposure="selective", domains={"task-a": "data"})
    assert report["paired_tasks"] == 2
    assert report["accuracy"]["absolute_lift"] == 0.5
    assert report["coverage"]["tasks_by_domain"] == {"data": 2}


def test_paired_report_discovers_timestamped_job_directories(tmp_path: Path) -> None:
    baseline, treatment = tmp_path / "base", tmp_path / "treated"
    baseline.mkdir(); treatment.mkdir()
    _trial(baseline / "2026-11-08__10-00-00", "task-a", "01", 0, 4, 10)
    _trial(treatment / "2026-11-08__10-10-00", "task-a", "01", 1, 5, 11)
    report = build_report(
        baseline,
        treatment,
        benchmark="b@1",
        cohort="nested",
        exposure="selective",
        domains={},
    )
    assert report["paired_tasks"] == 1
    assert report["accuracy"]["lifts"] == 1


def test_partial_reward_is_not_counted_as_pass(tmp_path: Path) -> None:
    baseline, treatment = tmp_path / "base", tmp_path / "treated"
    baseline.mkdir(); treatment.mkdir()
    _trial(baseline, "task-a", "01", 0, 1, 1)
    _trial(treatment, "task-a", "01", 0.792, 1, 1)
    report = build_report(baseline, treatment, benchmark="b@1", cohort="c", exposure="full", domains={})
    assert report["accuracy"]["treatment_passes"] == 0
    assert report["reward"]["mean_delta"] == 0.792


def test_paired_report_excludes_answer_contaminated_trial(tmp_path: Path) -> None:
    baseline, treatment = tmp_path / "base", tmp_path / "treated"
    baseline.mkdir(); treatment.mkdir()
    _trial(baseline, "task-a", "01", 1, 1, 1)
    _trial(treatment, "task-a", "01", 1, 1, 1)
    trace = treatment / "task-a__01/trajectory/acp_trajectory.jsonl"
    trace.parent.mkdir()
    trace.write_text(json.dumps({
        "type": "tool_call",
        "title": "execute",
        "content": "github task-a artifacts/solutions/task-a/solution.py",
    }) + "\n")
    report = build_report(
        baseline, treatment, benchmark="b@1", cohort="c", exposure="selective", domains={}
    )
    assert report["paired_tasks"] == 0
    assert report["excluded_contaminated"][0]["task_id"] == "task-a"


def test_pipeline_stats_aggregates_funnel_and_cost(tmp_path: Path) -> None:
    run = tmp_path / "run-1"
    (run / "logs").mkdir(parents=True); (run / "run").mkdir()
    (run / "logs/phase-metrics.json").write_text(json.dumps({
        "funnel": {"selected_findings": 2, "diagnosed_findings": 1, "novel_goal_scopes": 1,
                   "proposed_operations": 1, "accepted_proposals": 1, "changed_scopes": 1,
                   "accepted_operation_type_distribution": {"update": 1}, "run_disposition": "changed"},
        "phases": {"cost": {"agent_calls_actual": 3, "estimated_agent_calls_avoided": 2},
                   "resources": {"skills": 1, "operations": 1, "unused_resources": 0,
                                 "resource_plan_noncompliance": 0}}
    }))
    (run / "run/pipeline-summary.json").write_text(json.dumps({"outcome": "changed"}))
    report = aggregate([run])
    assert report["rates"]["agent_call_avoidance"] == 0.4
    assert report["accepted_operations"] == {"update": 1}


def test_benchmark_resource_feedback_joins_outcome_to_observed_skill(tmp_path: Path) -> None:
    baseline, treatment = tmp_path / "base", tmp_path / "treated"
    baseline.mkdir(); treatment.mkdir()
    _trial(baseline, "task-a", "01", 0, 4, 10)
    _trial(treatment, "task-a", "01", 1, 6, 14)
    trial = treatment / "task-a__01"
    bundle = tmp_path / "bundle"
    skill = bundle / "repair"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: repair\ndescription: Repair outputs.\n---\n"
    )
    (trial / "config.json").write_text(
        json.dumps({"requested_skills_dir": str(bundle)})
    )
    (trial / "trajectory").mkdir()
    (trial / "trajectory/acp_trajectory.jsonl").write_text(json.dumps({
        "type": "user_message",
        "text": "---\nname: repair\ndescription: Repair outputs.\n---\n",
    }))
    report = build_feedback(baseline, treatment, run_id="run-a")
    assert report["paired_tasks"] == 1
    event = report["feedback_events"][0]
    assert event["source"] == "benchmark"
    assert event["signal"] == "skill-runtime-outcome"
    assert event["value"]["skill"] == "repair"
    assert event["value"]["reward_delta"] == 1.0
    assert event["value"]["activation_mode"] == "injected"
    assert event["value"]["skill_hash"] == tree_hash(skill)
