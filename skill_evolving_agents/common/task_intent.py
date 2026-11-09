"""Offline object/action compatibility checks between a task and a skill.

Embedding similarity is a recall signal, not proof that a skill owns the task's
object and action.  A skill about publishing many XML document variants can be
semantically close to a single presentation-formatting request while being
operationally wrong.  This module extracts cheap, auditable intent evidence
from the task text and the skill document and rejects only *contradictions*:

* a skill that explicitly scopes itself to one format family when the task
  names a disjoint family;
* a skill that requires a multi-document/batch action when the task is a
  single-artifact transformation;
* a repair-only method for a clean creation request (the existing gate).

Uncertain combinations stay eligible.  The gate never promotes a candidate; it
only causes the router to abstain.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# Format families are intentionally coarse.  They describe the artifact the
# task operates on, not every incidental noun in the prompt.
FORMAT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "pptx": (
        re.compile(r"\.pptx?\b"),
        re.compile(r"\bslides?\b"),
        re.compile(r"\bpowerpoint\b"),
        re.compile(r"\bpresentation\b"),
        re.compile(r"\bslide deck\b"),
    ),
    "docx": (
        re.compile(r"\.docx?\b"),
        re.compile(r"\bword document\b"),
        re.compile(r"\bparagraphs?\b"),
    ),
    "xlsx": (
        re.compile(r"\.xlsx?\b"),
        re.compile(r"\.csv\b"),
        re.compile(r"\bworkbooks?\b"),
        re.compile(r"\bspreadsheets?\b"),
        re.compile(r"\bworksheets?\b"),
        re.compile(r"\bpivot tables?\b"),
        re.compile(r"\bexcel\b"),
    ),
    "dxf": (
        re.compile(r"\.dxf\b"),
        re.compile(r"\.dwg\b"),
        re.compile(r"\bdxf\b"),
        re.compile(r"\bcad\b"),
        re.compile(r"\bfloor plan\b"),
    ),
    "threejs": (
        re.compile(r"\bthree\.?js\b"),
        re.compile(r"\bcreatescene\b"),
        re.compile(r"\bbuffergeometry\b"),
        re.compile(r"\bpart_meshes\b"),
        re.compile(r"\bscene graph\b"),
        re.compile(r"\.m?js\b"),
    ),
    "obj": (
        re.compile(r"\.obj\b"),
        re.compile(r"\bobj\b"),
    ),
    "xml": (
        re.compile(r"\.xml\b"),
        re.compile(r"\bxml\b"),
    ),
    "json": (
        re.compile(r"\.json\b"),
        re.compile(r"\bjson\b"),
    ),
    "pdf": (re.compile(r"\.pdf\b"), re.compile(r"\bpdf\b")),
    "image": (
        re.compile(r"\.(?:png|jpe?g|webp|gif|svg)\b"),
        re.compile(r"\bimages?\b"),
        re.compile(r"\bscreenshots?\b"),
    ),
    "markdown": (re.compile(r"\.md\b"), re.compile(r"\bmarkdown\b")),
    "html": (re.compile(r"\.html?\b"), re.compile(r"\bhtml\b")),
}

ACTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "inspect": re.compile(
        r"\b(?:detect|find|identify|locate|extract|parse|analy[sz]e|inspect|"
        r"read|review|audit)\b"
    ),
    "transform": re.compile(
        r"\b(?:change|modify|edit|adjust|format|reformat|repair|fix|update|"
        r"move|resize|rewrite)\b"
    ),
    "create": re.compile(
        r"\b(?:create|build|generate|produce|make|add|insert)\b"
    ),
    "save": re.compile(r"\b(?:save|write|export|output|persist)\b"),
    "publish": re.compile(
        r"\b(?:publish|batch[- ]publish|locali[sz]e|translate|deploy|share)\b"
    ),
    "verify": re.compile(r"\b(?:verify|validate|check|test)\b"),
}

MULTI_VARIANT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:multiple|several|many|batch)\b[^.\n]{0,48}"
        r"\b(?:copies|versions|variants|documents|drafts?)\b"
    ),
    re.compile(r"\bcopies of\b"),
    re.compile(r"\blanguage versions?\b"),
    re.compile(
        r"\btranslat(?:e|ed|ing)\b[^.\n]{0,48}"
        r"\b(?:text|documents?|titles?|content|language|locale|drafts?)\b"
    ),
    re.compile(r"\bper (?:language|locale)\b"),
    re.compile(r"\bone document per draft\b"),
    re.compile(r"\bmore than one\b[^.\n]{0,32}\b(?:draft|document|file)\b"),
)

NON_FORMAT_PATTERN = re.compile(
    r"\bnon[- ]([a-z0-9]+)\s+(?:formats?|files?|inputs?)\b"
)
SCOPE_ONLY_PATTERN = re.compile(r"\b(?:only|exclusively)\b", re.IGNORECASE)
NEGATIVE_SCOPE_PATTERN = re.compile(
    r"\b(?:do not|don't|not)\s+(?:use|be used)\b|\bnot for\b|"
    r"\bout of scope\b|\bnever use\b",
    re.IGNORECASE,
)

CREATION_TERMS = ("create ", "build ", "generate ", "produce ", "make a new")
REPAIR_TERMS = (
    "repair ",
    "fix ",
    "recover ",
    "failing",
    "failure",
    "wrong",
    "broken",
    "incorrect",
    "error",
    "incomplete",
    "missing data",
)
REPAIR_ONLY_TERMS = (
    "repair failing",
    "repair a failing",
    "fix failing",
    "localizes the failing",
    "failing assertion",
    "verifier reports a failing",
)


def _matches(patterns: Iterable[re.Pattern[str]], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def format_families(text: str) -> set[str]:
    """Return the coarse artifact families named by a task or skill."""
    lowered = text.casefold()
    return {
        family
        for family, patterns in FORMAT_PATTERNS.items()
        if _matches(patterns, lowered)
    }


def action_families(text: str) -> set[str]:
    lowered = text.casefold()
    return {
        action
        for action, pattern in ACTION_PATTERNS.items()
        if pattern.search(lowered)
    }


def requires_multi_variant(text: str) -> bool:
    lowered = text.casefold()
    return _matches(MULTI_VARIANT_PATTERNS, lowered)


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.casefold())
    return re.split(r"(?<=[.!?])\s+", normalized)


def exclusive_formats(skill_text: str) -> set[str]:
    """Extract format families a skill explicitly claims as its only scope.

    ``non-XML formats`` means the skill owns XML and excludes everything else.
    ``covers only ... XML-draft path`` is the same claim in positive form.  We
    only read sentences that contain ``only``/``exclusively`` or ``non-`` so a
    passing mention of an output format cannot narrow the skill.
    """
    lowered = skill_text.casefold()
    exclusive: set[str] = set()
    for match in NON_FORMAT_PATTERN.finditer(lowered):
        family = match.group(1).strip("`'\"")
        if family in FORMAT_PATTERNS:
            exclusive.add(family)
    for sentence in _sentences(lowered):
        if not SCOPE_ONLY_PATTERN.search(sentence):
            continue
        if NON_FORMAT_PATTERN.search(sentence):
            continue
        if NEGATIVE_SCOPE_PATTERN.search(sentence):
            continue
        families = format_families(sentence)
        # A sentence such as "Use it only for a Three.js module and OBJ output"
        # is an explicit scope.  A sentence that merely says "only one call"
        # names no format family and is ignored.
        if families:
            exclusive.update(families)
    return exclusive


def excluded_formats(skill_text: str) -> set[str]:
    """Extract format families that a Do-Not-Use scope explicitly rejects.

    A negative sentence such as "do not use for lark-sheets, lark-slides" must
    never be read as ownership of those formats.
    """
    excluded: set[str] = set()
    for sentence in _sentences(skill_text):
        if not NEGATIVE_SCOPE_PATTERN.search(sentence):
            continue
        if NON_FORMAT_PATTERN.search(sentence):
            # "Do not use for non-XML formats" owns XML; it is positive scope.
            continue
        excluded.update(format_families(sentence))
    return excluded


def task_intent(task: str) -> dict[str, Any]:
    lowered = task.casefold()
    return {
        "formats": sorted(format_families(lowered)),
        "actions": sorted(action_families(lowered)),
        "multi_variant": requires_multi_variant(lowered),
        "clean_creation": (
            any(term in lowered for term in CREATION_TERMS)
            and not any(term in lowered for term in REPAIR_TERMS)
        ),
    }


def skill_scope(skill_text: str) -> dict[str, Any]:
    lowered = skill_text.casefold()
    actions = action_families(lowered)
    return {
        "formats": sorted(format_families(lowered)),
        "exclusive_formats": sorted(exclusive_formats(lowered)),
        "excluded_formats": sorted(excluded_formats(lowered)),
        "actions": sorted(actions),
        "multi_variant": requires_multi_variant(lowered),
        "repair_only": any(term in lowered for term in REPAIR_ONLY_TERMS),
    }


def compatibility(task: str, skill_text: str) -> tuple[bool, str | None]:
    """Return whether a skill's declared scope contradicts the task intent."""
    task_row = task_intent(task)
    skill_row = skill_scope(skill_text)

    if task_row["clean_creation"] and skill_row["repair_only"]:
        return False, "create-vs-repair"

    exclusive = set(skill_row["exclusive_formats"])
    if exclusive and task_row["formats"] and not (exclusive & set(task_row["formats"])):
        return False, "object-format-excluded"
    excluded = set(skill_row["excluded_formats"])
    if excluded and task_row["formats"] and (excluded & set(task_row["formats"])):
        return False, "object-format-excluded"

    if skill_row["multi_variant"] and not task_row["multi_variant"]:
        return False, "required-multi-variant-absent"

    if (
        skill_row["multi_variant"]
        and "publish" in skill_row["actions"]
        and "publish" not in task_row["actions"]
        and {"transform", "inspect"} & set(task_row["actions"])
    ):
        return False, "action-publish-vs-transform"

    return True, None
