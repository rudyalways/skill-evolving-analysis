import json
from datetime import datetime, timezone

from matrix_sampler.workspace import RunWorkspace
from matrix_sampler.evolution import EvolutionConfig, OODTree
from matrix_sampler.reporting.dashboard import append_tree_history
from matrix_sampler.reporting.run_dashboard import build_runs_dashboard, discover_runs
from matrix_sampler.run_config import default_run_config, prompt_set_scenarios, validate_run_config
from matrix_sampler.scenarios.registry import load


def test_runs_have_standalone_segregated_io(tmp_path):
    profile = tmp_path / "profile.json"; profile.write_text('{"target_id":"test"}')
    scenarios = tmp_path / "scenarios.json"; scenarios.write_text('{"scenarios":[]}')
    config = tmp_path / "policy.yaml"; config.write_text("seed: 1\n")
    moment = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)
    first = RunWorkspace.allocate(tmp_path / "runs", "experiment", moment)
    second = RunWorkspace.allocate(tmp_path / "runs", "experiment", moment)
    assert first.root != second.root
    created = RunWorkspace.create(tmp_path / "complete", "experiment", profile, scenarios, [config])
    assert (created.input / "target-profile.json").read_text() == profile.read_text()
    assert (created.input / "scenarios.json").read_text() == scenarios.read_text()
    assert created.database.parent == created.output
    manifest = json.loads(created.manifest.read_text())
    assert len(manifest["input_files"]) == 4
    assert all(item["sha256"] for item in manifest["input_files"])
    run_config = json.loads((created.input / "run-config.json").read_text())
    assert run_config["evaluation_scope"] == "both"
    assert run_config["sampling"]["samples_per_step"] == 25
    assert run_config["sampling"]["steps"] == 4
    assert run_config["prompt_sets"][0]["id"] == "capability-discovery"
    assert "What can you do?" in run_config["prompt_sets"][0]["prompts"][0]


def test_trace_snapshot_is_content_named_and_idempotent(tmp_path):
    profile = tmp_path / "profile.json"; profile.write_text('{}')
    scenarios = tmp_path / "scenarios.json"; scenarios.write_text('{"scenarios":[]}')
    source = tmp_path / "trace.jsonl"; source.write_text('{}\n')
    workspace = RunWorkspace.create(tmp_path / "runs", "trace", profile, scenarios)
    first = workspace.snapshot_trace(source)
    second = workspace.snapshot_trace(source)
    assert first == second
    assert first.parent == workspace.input / "traces"
    assert first.read_text() == '{}\n'
    manifest = json.loads(workspace.manifest.read_text())
    assert len(manifest["input_files"]) == 4


def test_runs_dashboard_keeps_one_tree_per_run(tmp_path):
    profile = tmp_path / "profile.json"; profile.write_text('{"target_id":"test"}')
    scenarios = tmp_path / "scenarios.json"; scenarios.write_text(json.dumps({"scenarios": load()[:1]}))
    runs_root = tmp_path / "runs"
    first = RunWorkspace.create(runs_root, "first", profile, scenarios)
    second = RunWorkspace.create(runs_root, "second", profile, scenarios)
    for workspace in (first, second):
        tree = OODTree(load()[:1]).build(EvolutionConfig(max_layer=2, branch_factor=1))
        evolution = workspace.output / "evolution"; evolution.mkdir()
        tree_path = evolution / "ood-tree.json"; tree_path.write_text(json.dumps(tree))
        append_tree_history(tree, evolution / "history.jsonl", progressive=False)
    rows = discover_runs(runs_root)
    assert {row["name"].split("@", 1)[0] for row in rows} == {"first", "second"}
    assert all("@" in row["name"] for row in rows)
    assert all(row["has_tree"] and row["steps"] for row in rows)
    output = build_runs_dashboard(runs_root)
    text = output.read_text()
    assert "Each run keeps standalone input/output artifacts" in text
    assert "first" in text and "second" in text
    assert "tree ready" in text
    assert "samples_per_step" in text
    assert "target_model" in text
    assert "harness_profile" in text
    assert "prompt_count" in text
    assert "discovery prompts" in text
    assert (first.output / "dashboard.html").is_file()
    assert (second.output / "dashboard.html").is_file()


def test_prompt_sets_are_validated_and_become_sampling_scenarios():
    config = validate_run_config(default_run_config({"target_id": "model-under-test"}))
    scenarios = prompt_set_scenarios(config)
    assert len(scenarios) == 4
    assert scenarios[0]["generator"]["prompt"].startswith("What can you do?")
    assert scenarios[0]["oracle"]["checks"] == ["record_claims_not_ground_truth"]
    assert all("self_report" in row["tags"] for row in scenarios)
