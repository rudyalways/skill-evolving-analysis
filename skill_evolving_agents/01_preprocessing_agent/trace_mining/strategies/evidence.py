"""Tool-evidence retention strategies."""

from ..contracts import StrategySpec
from ._helpers import evidence_policy

STRATEGIES = tuple(
    StrategySpec(
        "evidence", policy, "1", evidence_policy(policy),
        "canonical_turns", "tool_evidence",
    )
    for policy in ("on_signal", "always", "never")
)
