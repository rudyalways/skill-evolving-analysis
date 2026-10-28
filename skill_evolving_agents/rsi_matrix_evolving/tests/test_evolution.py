import json

from jsonschema import Draft202012Validator

from matrix_sampler.evolution import EvolutionConfig, OODTree, parse_category_path, parse_expansion_output
from matrix_sampler.reporting.dashboard import append_tree_history, build_dashboard
from matrix_sampler.scenarios.registry import load


def test_hierarchical_ood_tree_has_lineage_and_three_layers():
    scenarios = load()[:2]
    tree = OODTree(scenarios).build(EvolutionConfig(max_layer=3, branch_factor=2, max_nodes=50))
    assert tree["summary"]["maximum_layer"] == 3
    assert [row["layer"] for row in tree["layer_metrics"]] == [0, 1, 2, 3]
    by_id = {node["node_id"]: node for node in tree["nodes"]}
    schema = json.loads(open("schemas/ood-node.schema.json").read())
    validator = Draft202012Validator(schema)
    for node in tree["nodes"]:
        assert not list(validator.iter_errors(node))
        if node["layer"]:
            assert node["parent_id"] in by_id
            assert by_id[node["parent_id"]]["layer"] == node["layer"] - 1
            assert node["display_name"] != by_id[node["parent_id"]]["display_name"]
            assert len(node["shift_axes"]) == node["layer"]
    hierarchy = tree["hierarchy"]
    hierarchy_by_id = {node["node_id"]: node for node in hierarchy["nodes"]}
    roots = [node for node in hierarchy["nodes"] if node["parent_id"] is None]
    assert [node["node_id"] for node in roots] == [hierarchy["root_id"]]
    visited, stack = set(), [hierarchy["root_id"]]
    while stack:
        node_id = stack.pop()
        assert node_id not in visited
        visited.add(node_id)
        stack.extend(hierarchy_by_id[node_id]["child_ids"])
    assert visited == set(hierarchy_by_id)
    assert any(len(node["child_ids"]) > 1 for node in hierarchy["nodes"])


def test_evolution_gate_stops_settled_parent():
    scenario = load()[:1]
    observations = {scenario[0]["scenario_id"]: {"attempts": 108, "successes": 98}}
    tree = OODTree(scenario, observations).build(EvolutionConfig(max_layer=3, branch_factor=2, min_parent_attempts=4))
    assert tree["summary"]["total_nodes"] == 1


def test_dashboard_embeds_tree_without_dependencies(tmp_path):
    tree = OODTree(load()[:1]).build(EvolutionConfig(max_layer=3, branch_factor=1))
    source = tmp_path / "tree.json"; source.write_text(json.dumps(tree))
    output = build_dashboard(source, tmp_path / "dashboard.html", "Test Evolver")
    text = output.read_text()
    assert "Test Evolver" in text
    assert "Watch the evidence tree grow" in text
    assert tree["nodes"][0]["node_id"] in text


def test_dashboard_history_replays_tree_growth(tmp_path):
    tree = OODTree(load()[:1]).build(EvolutionConfig(max_layer=3, branch_factor=1))
    source = tmp_path / "tree.json"; source.write_text(json.dumps(tree))
    history = append_tree_history(tree, tmp_path / "history.jsonl")
    frames = [json.loads(line) for line in history.read_text().splitlines()]
    assert [frame["summary"]["maximum_layer"] for frame in frames] == [0, 1, 2, 3]
    assert all(len(frames[i]["nodes"]) < len(frames[i + 1]["nodes"]) for i in range(3))
    assert all(sum(node["parent_id"] is None for node in frame["hierarchy"]["nodes"]) == 1 for frame in frames)
    assert [frame["timeline"]["step"] for frame in frames] == [1, 2, 3, 4]
    assert all(set(frames[i]["timeline"]["carried_node_ids"]) == {node["node_id"] for node in frames[i - 1]["nodes"]} for i in range(1, 4))
    output = build_dashboard(source, tmp_path / "dashboard.html", history_path=history)
    text = output.read_text()
    assert "Play evolution" in text
    assert "new this step" in text
    assert "#f4f7fb" in text
    assert "Compact · top 10 layer 1" in text
    assert "Compact · top 10 L1 + top 20 L2" in text
    assert "Expand whole tree" in text
    assert "Use compact budget" in text
    assert "more ID" in text
    assert "more OOD" in text
    assert "Rank: samples" in text
    assert "Rank: success rate" in text
    assert "Rank: sample share" in text
    assert "Rank: Δ samples" in text
    assert "Rank: Δ success rate" in text
    assert 'data-orientation="top-down"' in text
    assert "renderStrictTopDownTree" in text
    assert ">OOD</span>" in text
    assert ">NEW</span>" in text
    assert "performanceStops" in text
    assert "canonicalDomainPath" in text
    assert "interfaceDomainTokens" in text
    assert "if(!node||node.kind==='placeholder')return" in text
    assert "if(!node||!core)return" not in text
    assert "scale-key" in text
    assert "<b>20</b>" in text
    assert "<b>85</b>" in text
    assert "mixColor" in text
    assert "ood-core" in text
    assert "node-badges" in text
    assert "delta-metric" in text
    assert "Δ success" in text
    assert "pp.toFixed(1)" in text
    assert "compactRoot" in text
    assert "compactScenarios" in text
    assert "compactOod" in text
    assert "Previous step" in text
    assert "Next step" in text
    assert "First step" in text
    assert "Last step" in text
    assert "jumpStep(0)" in text
    assert "jumpStep(frames.length-1)" in text
    assert "if(index>=frames.length-1)return" in text
    assert "manualTimelineSelection=true" in text
    assert "followLatest=!manualTimelineSelection" in text
    assert "if(index===frames.length-1)index=0" not in text
    assert "0 samples · — share · — success" in text
    assert "m.successes/m.attempts" in text
    assert "Sample share" in text
    assert "% share" in text
    assert "#d65454" in text
    assert "#2563eb" in text
    assert "renderVerticalTree" in text
    assert "input → output samples" in text


def test_hierarchy_metrics_roll_up_and_accumulate_between_sampling_steps(tmp_path):
    tree = OODTree(load()[:1]).build(EvolutionConfig(max_layer=2, branch_factor=2))
    leaves = [node for node in tree["nodes"] if not node["child_ids"]]
    for index, node in enumerate(leaves):
        node["metrics"]["attempts"] = 7 if index == 0 else 6
        node["metrics"]["successes"] = 5
    history = append_tree_history(tree, tmp_path / "history.jsonl", progressive=False)
    for index, node in enumerate(leaves):
        node["metrics"]["attempts"] = 13 if index < 2 else 12
        node["metrics"]["successes"] = 9 if index < 3 else 8
    append_tree_history(tree, history, progressive=False)
    frames = [json.loads(line) for line in history.read_text().splitlines()]
    roots = [next(node for node in frame["hierarchy"]["nodes"] if node["node_id"] == frame["hierarchy"]["root_id"]) for frame in frames]
    assert [root["metrics"]["attempts"] for root in roots] == [25, 50]
    assert [root["metrics"]["successes"] for root in roots] == [20, 35]
    assert [root["metrics"]["success_mean"] for root in roots] == [.8, .7]


def test_agent_category_paths_determine_depth_not_step_number():
    scenario = load()[:1]
    proposals = parse_expansion_output({"proposals": [
        {"scenario_id": scenario[0]["scenario_id"], "category_path": "tool_use", "display_name": "Tool use"},
        {"scenario_id": scenario[0]["scenario_id"], "category_path": "tool_use/recovery", "display_name": "Recovery"},
        {"scenario_id": scenario[0]["scenario_id"], "category_path": "tool_use/recovery/retryable", "display_name": "Retryable"},
        {"scenario_id": scenario[0]["scenario_id"], "category_path": "tool_use/selection", "display_name": "Selection"},
    ]})
    tree = OODTree(scenario).build_from_category_proposals(proposals, EvolutionConfig(max_layer=3))
    paths = {node["dimensions"].get("category_path"): node["layer"] for node in tree["nodes"] if node["layer"]}
    assert paths == {"tool_use": 1, "tool_use/recovery": 2, "tool_use/recovery/retryable": 3, "tool_use/selection": 2}


def test_category_path_parser_enforces_slash_depth_limit():
    assert parse_category_path("tool use/recovery/retryable") == ("tool_use", "recovery", "retryable")
    try:
        parse_category_path("a/b/c/d")
    except ValueError as error:
        assert "maximum depth 3" in str(error)
    else:
        raise AssertionError("four category segments must be rejected")
