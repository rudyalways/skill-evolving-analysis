"""Canonical-turn text projection strategies."""

from ..contracts import StrategySpec
from ._helpers import set_choice

STRATEGIES = (
    StrategySpec(
        "projector", "core_text", "1", set_choice("projector", "core_text"),
        "canonical_turns", "feature_documents",
    ),
)
