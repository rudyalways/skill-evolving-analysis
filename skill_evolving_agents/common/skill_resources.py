#!/usr/bin/env python3
"""Deterministic skill interface generation and resource usefulness metrics."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


RESOURCE_KINDS = ("scripts", "references", "assets", "agents", "evals")
GENERATED_INTERFACE = Path("agents/openai.yaml")
FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)
WORD_OR_PUNCTUATION = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def _frontmatter(skill: Path) -> dict[str, str]:
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)
    if match is None:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if line.startswith((" ", "\t")):
            continue
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip().strip("\"'")
    return fields


def _top_level_blocks(text: str) -> dict[str, list[str]]:
    """Split simple YAML into top-level blocks without a YAML dependency."""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s|$)", line)
        if match:
            current = match.group(1)
            blocks[current] = [line]
        elif current is not None:
            blocks[current].append(line)
    return blocks


def _interface_extras(lines: list[str]) -> list[str]:
    standard = {"display_name", "short_description", "default_prompt"}
    extras: list[str] = []
    index = 1
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):(?:\s|$)", line)
        if not match:
            index += 1
            continue
        start = index
        index += 1
        while index < len(lines) and not re.match(
            r"^  [A-Za-z_][A-Za-z0-9_-]*:(?:\s|$)", lines[index]
        ):
            index += 1
        if match.group(1) not in standard:
            extras.extend(lines[start:index])
    return extras


def _display_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


def _short_description(description: str, limit: int = 80) -> str:
    value = " ".join(description.split())
    if len(value) <= limit:
        return value
    shortened = value[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;: ")
    return (shortened or value[: limit - 1]).rstrip() + "…"


def generate_openai_yaml(skill: Path) -> Path:
    """Regenerate standard interface fields and preserve unrelated YAML blocks."""
    fields = _frontmatter(skill)
    name = fields.get("name") or skill.name
    description = fields.get("description") or (
        f"Apply the {_display_name(name)} workflow when its documented conditions match."
    )
    path = skill / GENERATED_INTERFACE
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    blocks = _top_level_blocks(existing)
    lines = [
        "interface:",
        f"  display_name: {json.dumps(_display_name(name), ensure_ascii=False)}",
        f"  short_description: {json.dumps(_short_description(description), ensure_ascii=False)}",
        f"  default_prompt: {json.dumps(f'Use ${name} for this request.', ensure_ascii=False)}",
    ]
    lines.extend(_interface_extras(blocks.get("interface", [])))
    for key, block in blocks.items():
        if key != "interface":
            lines.extend(block)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _resource_files(skill: Path) -> dict[str, list[Path]]:
    return {
        kind: sorted(
            path
            for path in (skill / kind).rglob("*")
            if path.is_file() and path != skill / GENERATED_INTERFACE
        )
        if (skill / kind).is_dir()
        else []
        for kind in RESOURCE_KINDS
    }


def _readable_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _tokens(text: str) -> int:
    return len(WORD_OR_PUNCTUATION.findall(text))


def _observed_exit_codes(records: Iterable[str], relative: str) -> list[int]:
    codes: list[int] = []
    for raw in records:
        if relative not in raw and Path(relative).name not in raw:
            continue
        for pattern in (
            r'"exit_code"\s*:\s*(-?\d+)',
            r'"exitCode"\s*:\s*(-?\d+)',
            r'process exited with code\s+(-?\d+)',
        ):
            codes.extend(int(value) for value in re.findall(pattern, raw))
    return codes


def measure_skill_resources(
    skill: Path,
    evidence: str = "",
    use_evidence: str | None = None,
) -> dict[str, Any]:
    """Measure observed use separately from static progressive-disclosure proxies."""
    use_evidence = evidence if use_evidence is None else use_evidence
    skill_text = _readable_text(skill / "SKILL.md")
    by_kind = _resource_files(skill)
    all_files = [path for paths in by_kind.values() for path in paths]
    evidence_lines = evidence.splitlines()
    resource_text = {
        path: _readable_text(path)
        for path in all_files
    }
    all_instruction_text = "\n".join(
        [skill_text, *[text for text in resource_text.values() if text]]
    )

    def relative(path: Path) -> str:
        return path.relative_to(skill).as_posix()

    observed: dict[str, set[str]] = {kind: set() for kind in RESOURCE_KINDS}
    discoverable: set[str] = set()
    for path in all_files:
        rel = relative(path)
        name = path.name
        if rel in all_instruction_text or name in skill_text:
            discoverable.add(rel)
        kind = rel.split("/", 1)[0]
        if rel in use_evidence or name in use_evidence:
            observed[kind].add(rel)

    scripts = by_kind["scripts"]
    execution_codes = {
        relative(path): _observed_exit_codes(evidence_lines, relative(path))
        for path in scripts
        if path.suffix in {".py", ".sh", ".js", ".ts", ".rb"}
    }
    attempts = sum(len(codes) for codes in execution_codes.values())
    successes = sum(code == 0 for codes in execution_codes.values() for code in codes)

    reference_count = len(by_kind["references"])
    asset_count = len(by_kind["assets"])
    reference_uses = len(observed["references"])
    asset_uses = len(observed["assets"])
    skill_tokens = _tokens(skill_text)
    reference_tokens = sum(_tokens(resource_text[path]) for path in by_kind["references"])
    disclosure_total = skill_tokens + reference_tokens

    duplicated_lines: set[str] = set()
    skill_lines = {
        " ".join(line.split()).casefold()
        for line in skill_text.splitlines()
        if len(" ".join(line.split())) >= 40
    }
    for text in resource_text.values():
        duplicated_lines.update(
            skill_lines
            & {
                " ".join(line.split()).casefold()
                for line in text.splitlines()
                if len(" ".join(line.split())) >= 40
            }
        )

    penalized = [
        relative(path)
        for path in all_files
        if relative(path) not in discoverable
        and relative(path) not in observed[relative(path).split("/", 1)[0]]
        and not relative(path).startswith("evals/")
    ]
    denominator = max(len(all_files) - len(by_kind["evals"]), 0)
    unused_rate = len(penalized) / denominator if denominator else 0.0
    duplicate_rate = len(duplicated_lines) / max(len(skill_lines), 1)
    positive_rates = [
        value
        for value in (
            successes / attempts if attempts else None,
            reference_uses / reference_count if reference_count else None,
            asset_uses / asset_count if asset_count else None,
        )
        if value is not None
    ]
    observed_score = sum(positive_rates) / len(positive_rates) if positive_rates else None
    usefulness = (
        max(0.0, min(1.0, observed_score - 0.35 * unused_rate - 0.25 * duplicate_rate))
        if observed_score is not None
        else None
    )
    return {
        "skill": skill.name,
        "resource_counts": {kind: len(paths) for kind, paths in by_kind.items()},
        "script_execution": {
            "attempts": attempts,
            "successes": successes,
            "success_rate": round(successes / attempts, 6) if attempts else None,
            "reason": None if attempts else "no script execution result was observed",
        },
        "reference_use": {
            "files": reference_count,
            "used": reference_uses,
            "use_rate": round(reference_uses / reference_count, 6) if reference_count else None,
            "reason": (
                None
                if reference_uses
                else (
                    "no reference retrieval or use was observed"
                    if reference_count
                    else "skill has no reference files"
                )
            ),
        },
        "asset_reuse": {
            "files": asset_count,
            "reused": asset_uses,
            "reuse_rate": round(asset_uses / asset_count, 6) if asset_count else None,
            "reason": (
                None
                if asset_uses
                else (
                    "no asset reuse was observed"
                    if asset_count
                    else "skill has no asset files"
                )
            ),
        },
        "progressive_disclosure": {
            "skill_md_tokens": skill_tokens,
            "reference_tokens": reference_tokens,
            "estimated_skill_md_token_reduction": (
                round(reference_tokens / disclosure_total, 6)
                if disclosure_total
                else 0.0
            ),
            "semantics": "proxy: share of instruction tokens deferred to references",
        },
        "penalties": {
            "unused_resources": penalized,
            "unused_resource_rate": round(unused_rate, 6),
            "duplicated_content_lines": len(duplicated_lines),
            "duplicated_content_rate": round(duplicate_rate, 6),
        },
        "observed_usefulness_score": round(usefulness, 6) if usefulness is not None else None,
    }


def aggregate_resource_metrics(documents: Iterable[dict[str, Any]]) -> dict[str, Any]:
    documents = list(documents)
    skills = [skill for document in documents for skill in document.get("skills", [])]

    def sum_field(section: str, field: str) -> int:
        return sum(int((row.get(section) or {}).get(field) or 0) for row in skills)

    attempts = sum_field("script_execution", "attempts")
    successes = sum_field("script_execution", "successes")
    references = sum_field("reference_use", "files")
    reference_uses = sum_field("reference_use", "used")
    assets = sum_field("asset_reuse", "files")
    asset_uses = sum_field("asset_reuse", "reused")
    scores = [
        float(row["observed_usefulness_score"])
        for row in skills
        if isinstance(row.get("observed_usefulness_score"), (int, float))
    ]
    return {
        "operations": len(documents),
        "skills": len(skills),
        "script_execution_success_rate": round(successes / attempts, 6) if attempts else None,
        "reference_use_rate": round(reference_uses / references, 6) if references else None,
        "asset_reuse_rate": round(asset_uses / assets, 6) if assets else None,
        "mean_observed_usefulness_score": round(sum(scores) / len(scores), 6) if scores else None,
        "unused_resources": sum(
            len((row.get("penalties") or {}).get("unused_resources") or []) for row in skills
        ),
        "duplicated_content_lines": sum_field("penalties", "duplicated_content_lines"),
    }
