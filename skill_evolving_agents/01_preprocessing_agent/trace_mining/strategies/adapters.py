"""Raw trace source adapters."""

from ..contracts import StrategySpec
from ._helpers import set_choice

STRATEGIES = (
    StrategySpec(
        "adapter", "multi_source", "1",
        set_choice("source_adapter", "multi_source"),
        "raw_jsonl", "candidate_turns",
    ),
    StrategySpec(
        "adapter", "codex", "1", set_choice("source_adapter", "codex"),
        "raw_jsonl", "candidate_turns",
    ),
    StrategySpec(
        "adapter", "claude", "1", set_choice("source_adapter", "claude"),
        "raw_jsonl", "candidate_turns",
    ),
    StrategySpec(
        "adapter", "cursor", "1", set_choice("source_adapter", "cursor"),
        "raw_jsonl", "candidate_turns",
    ),
)
