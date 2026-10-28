from matrix_sampler.sampling.planner import plan, select_uncertain, should_stop
from matrix_sampler.scenarios.registry import load


def test_seeded_sparse_covering_plan():
    scenarios = load()
    a = plan(scenarios, 25, 42, "target")
    b = plan(scenarios, 25, 42, "target")
    assert a == b
    assert len(a["samples"]) == 25
    assert len(a["samples"]) < len(scenarios) * 3
    assert a["coverage_pairs"] > 25
    assert len({tuple(x["messages"][0].items()) for x in a["samples"]}) == 25


def test_uncertainty_stop_condition():
    assert not should_stop(2, 2, 2)
    assert should_stop(100, 10, 108)
    selected = select_uncertain([
        {"cell_id": "settled", "alpha": 100, "beta": 10, "attempts": 108},
        {"cell_id": "uncertain", "alpha": 2, "beta": 2, "attempts": 2},
    ], 2, 42)
    assert [x["cell_id"] for x in selected] == ["uncertain"]

