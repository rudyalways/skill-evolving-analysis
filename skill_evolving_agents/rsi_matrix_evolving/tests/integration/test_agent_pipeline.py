import json

from matrix_evolving_agents.run_pipeline import Pipeline
from matrix_sampler.storage.sqlite import Store
from matrix_sampler.workspace import RunWorkspace


def test_seven_stage_agent_pipeline_writes_contract_artifacts(tmp_path):
    workspace = RunWorkspace.create(tmp_path / "runs", "agent-pipeline", "target-profile.json", "scenarios/bootstrap/scenarios.json", ["configs/sampling-policy.yaml"])
    Store(workspace.database)
    summary = Pipeline(workspace.root, max_layer=3, branch_factor=1, max_nodes=120).execute()
    assert summary["status"] == "completed"
    assert summary["stages"] == 7
    expected = [
        "output/traces/derived/observable-evidence.json",
        "output/run/diagnosis.json",
        "output/run/goal-reduction.json",
        "output/run/sample-queue.json",
        "output/run/verification.json",
        "output/run/judge.json",
        "output/run/pipeline-summary.json",
        "output/evolution/ood-tree.json",
        "output/evolution/history.jsonl",
        "output/dashboard.html",
        "output/logs/agent-execution.jsonl",
    ]
    assert all((workspace.root / path).is_file() for path in expected)
    statuses = list((workspace.root / "output/run/status").glob("*.json"))
    assert len(statuses) == 7
    assert all(json.loads(path.read_text())["state"] == "done" for path in statuses)
    events = [json.loads(line) for line in (workspace.root / "output/logs/agent-execution.jsonl").read_text().splitlines()]
    assert len(events) == 14
    assert {row["agent"] for row in events} == {"01", "02", "03", "04", "05", "06", "07"}
