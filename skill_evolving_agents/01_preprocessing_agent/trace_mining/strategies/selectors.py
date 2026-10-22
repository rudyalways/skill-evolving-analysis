"""Candidate-turn selection strategies."""

from ..contracts import StrategySpec
from ._helpers import set_choice

STRATEGIES = (
    StrategySpec(
        "selector", "substantive_turns", "1",
        set_choice("selector", "substantive_turns"),
        "candidate_turns", "canonical_turns",
    ),
)
