"""Aggregate the explicitly allowlisted built-in strategy modules."""

from . import adapters, clusterers, evidence, features, namers, projectors, selectors

BUILTINS = (
    *adapters.STRATEGIES,
    *selectors.STRATEGIES,
    *evidence.STRATEGIES,
    *projectors.STRATEGIES,
    *features.STRATEGIES,
    *clusterers.STRATEGIES,
    *namers.STRATEGIES,
)
