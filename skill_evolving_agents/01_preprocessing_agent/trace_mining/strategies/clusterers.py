"""Vector clustering strategies."""

from ..contracts import StrategySpec
from ._helpers import clusterer

STRATEGIES = (
    StrategySpec(
        "clusterer", "incremental_threshold", "1",
        clusterer("incremental_threshold", True),
        "vectors", "cluster_assignments",
    ),
    StrategySpec(
        "clusterer", "no_clustering", "1",
        clusterer("no_clustering", False),
        "vectors", "cluster_assignments",
    ),
)
