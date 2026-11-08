from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "01_preprocessing_agent/scripts/enrich_skillsbench_acp.py"
)
SPEC = importlib.util.spec_from_file_location("enrich_skillsbench_acp", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_extract_failure_summaries_keeps_test_and_assertion() -> None:
    output = """
FAILED ::test_growth_values[B8-7444.4-Science Avg Budget] - AssertionError
E           AssertionError: Science Avg Budget (B8): expected 7444.4, got 7610.3
"""

    assert MODULE.extract_failure_summaries(output) == [
        {
            "test": "::test_growth_values[B8-7444.4-Science Avg Budget]",
            "assertion": (
                "AssertionError: Science Avg Budget (B8): "
                "expected 7444.4, got 7610.3"
            ),
        }
    ]


def test_extract_failure_summaries_is_bounded() -> None:
    output = "\n".join(
        f"FAILED ::test_{index} - AssertionError: failure {index}"
        for index in range(MODULE.MAX_FAILURE_SUMMARIES + 3)
    )

    assert len(MODULE.extract_failure_summaries(output)) == MODULE.MAX_FAILURE_SUMMARIES
