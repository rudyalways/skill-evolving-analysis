from matrix_sampler.scenarios.registry import load, validate


def test_at_least_30_scenarios_validate():
    scenarios = load()
    assert len(scenarios) >= 30
    assert validate("scenarios/bootstrap/scenarios.json") == []
    assert all(len(s["generator"]["parameter_schema"]["difficulty"]) == 3 for s in scenarios)

