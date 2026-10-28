from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


SEGMENT = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class CategoryProposal:
    scenario_id: str
    category_path: str
    display_name: str
    evidence: tuple[str, ...]

    @property
    def segments(self) -> tuple[str, ...]:
        return tuple(self.category_path.split("/"))


def parse_category_path(value: str, maximum_depth: int = 3) -> tuple[str, ...]:
    """Parse a slash-separated agent category path with a hard depth limit."""
    if not isinstance(value, str):
        raise ValueError("category_path must be a string")
    segments = tuple(part.strip().lower().replace(" ", "_") for part in value.split("/"))
    if not segments or any(not part for part in segments):
        raise ValueError("category_path contains an empty segment")
    if len(segments) > maximum_depth:
        raise ValueError(f"category_path exceeds maximum depth {maximum_depth}")
    if any(not SEGMENT.fullmatch(part) for part in segments):
        raise ValueError("category_path segments may contain lowercase letters, digits, '_' and '-'")
    return segments


def parse_expansion_output(payload: dict[str, Any], maximum_depth: int = 3) -> list[CategoryProposal]:
    """Validate untrusted agent proposals; step number never determines depth."""
    if not isinstance(payload, dict) or not isinstance(payload.get("proposals"), list):
        raise ValueError("agent output must contain a proposals array")
    proposals: list[CategoryProposal] = []
    seen: set[tuple[str, str]] = set()
    for row in payload["proposals"]:
        if not isinstance(row, dict):
            raise ValueError("each proposal must be an object")
        scenario_id = str(row.get("scenario_id", "")).strip()
        if not scenario_id:
            raise ValueError("proposal requires scenario_id")
        segments = parse_category_path(row.get("category_path"), maximum_depth)
        path = "/".join(segments)
        key = (scenario_id, path)
        if key in seen:
            continue
        seen.add(key)
        name = str(row.get("display_name") or segments[-1].replace("_", " ").title()).strip()
        evidence = tuple(str(item) for item in row.get("evidence", []))
        proposals.append(CategoryProposal(scenario_id, path, name, evidence))
    return proposals


AGENT_CATEGORY_INSTRUCTION = """Propose zero or more category additions. A step may update statistics only, add siblings, or add deeper categories. Do not infer depth from the step number. Return JSON with a `proposals` array. Each proposal must include `scenario_id`, `category_path`, optional `display_name`, and `evidence`. `category_path` uses `/` as the separator and may contain at most 3 segments, for example `tool_use/recovery/retryable`. Include every missing prefix needed by a deeper proposal."""
