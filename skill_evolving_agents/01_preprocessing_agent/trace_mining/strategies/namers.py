"""Cluster naming strategies."""

from ..contracts import StrategySpec
from ._helpers import set_choice

STRATEGIES = (
    StrategySpec(
        "namer", "top_terms", "1", set_choice("namer", "top_terms"),
        "cluster_assignments", "named_clusters",
    ),
)
