from matrix_sampler.verifiers.deterministic import fuse


def test_judge_cannot_override_deterministic_failure():
    result = fuse([
        {"source": "deterministic", "value": False, "confidence": 1},
        {"source": "judge", "value": True, "confidence": 1},
    ])
    assert result["value"] is False
    assert result["disagreement"] is True

