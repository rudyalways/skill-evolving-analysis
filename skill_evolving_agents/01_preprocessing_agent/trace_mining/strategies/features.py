"""Feature-vector strategies."""

from ..contracts import StrategySpec
from ._helpers import set_choice

STRATEGIES = (
    StrategySpec(
        "feature", "tfidf", "1", set_choice("vector_strategy", "tfidf"),
        "feature_documents", "sparse_vectors",
    ),
    StrategySpec(
        "feature", "precomputed_embeddings", "1",
        set_choice("vector_strategy", "embedding"),
        "feature_documents", "dense_vectors",
    ),
)
