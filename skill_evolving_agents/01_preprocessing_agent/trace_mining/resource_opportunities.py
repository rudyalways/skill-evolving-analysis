"""Detect evidence-backed opportunities for reusable skill resources.

This detector intentionally has a high precision bias.  It recommends a script
only when an observed command sequence is deterministic, bounded, repeated, and
has explicit pacing and termination behavior.  Rejected candidates are retained
as audit decisions so thresholds can be tuned from labels later.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", re.IGNORECASE)
LONG_NUMBER = re.compile(r"\b\d{3,}\b")
SPACE = re.compile(r"\s+")
BOUNDED_LOOP = re.compile(
    r"\bfor\s+\w+\s+in\s+(?:\{?\d+(?:\.\.\d+)?\}?|(?:\d+\s+){2,}\d+)\s*;?\s*do\b",
    re.IGNORECASE,
)
UNBOUNDED_LOOP = re.compile(r"\b(?:while\s+(?:true|:)|for\s*\(\s*;;)", re.IGNORECASE)
PACING = re.compile(r"\b(?:sleep|backoff|retry[-_ ]?after|settimeout)\b", re.IGNORECASE)
ADAPTIVE_BACKOFF = re.compile(
    r"\b(?:backoff|retry[-_ ]?after)\b|sleep\s+[^;\n]*(?:\$\(\(|\*|attempt)",
    re.IGNORECASE,
)
TERMINATION = re.compile(
    r"\b(?:break|success|succeeded|failed|failure|crashed|removed|cancelled|canceled|complete[dt]?)\b",
    re.IGNORECASE,
)
MUTATION = re.compile(
    r"(?:^|[;&|]\s*)(?:rm|rmdir|drop|delete|destroy|terminate|kill)\b",
    re.IGNORECASE,
)
POLL_COMMANDS = (
    (re.compile(r"\brailway\s+deployment\s+list\b", re.IGNORECASE), "railway-deployment-status"),
    (re.compile(r"\bkubectl\s+(?:get|rollout\s+status)\b", re.IGNORECASE), "kubernetes-status"),
    (re.compile(r"\bgh\s+(?:run|pr)\s+(?:view|list|watch|checks)\b", re.IGNORECASE), "github-status"),
    (re.compile(r"\b(?:aws|gcloud|az)\b[^\n;]*(?:describe|status|list|get)\b", re.IGNORECASE), "cloud-status"),
)
DELEGATED_PROMPT = re.compile(
    r"\b(?:spawn_agent|create_thread)\b[\s\S]{0,1200}?\b(?:message|prompt)\s*:\s*([\"'])(?P<body>.+?)\1",
    re.IGNORECASE,
)
DELEGATED_MESSAGE = re.compile(
    r"\b(?:message|prompt)\s*[\"']?\s*:\s*([\"'])(?P<body>.+?)\1",
    re.IGNORECASE,
)
REFERENCE_READ = re.compile(
    r"\b(?:cat|sed\s+-n|rg)\b[^\n]{0,500}?(?P<path>(?:docs?|references?|schemas?|policies)/[A-Za-z0-9_./-]+)",
    re.IGNORECASE,
)
ASSET_REUSE = re.compile(
    r"(?:^|[;&|\n\"'])\s*(?:cp|copy|rsync)\s+"
    r"[^\n;&|]{0,300}?(?P<path>[A-Za-z0-9_./-]*(?:template|starter|scaffold)[A-Za-z0-9_./-]*)",
    re.IGNORECASE,
)
INLINE_ASSET = re.compile(
    r"\*\*\*\s+Add File:\s*(?P<path>[^\n]*(?:template|starter|scaffold)[^\n]*)\n"
    r"(?P<body>(?:\+[^\n]*(?:\n|$)){2,})",
    re.IGNORECASE,
)
ADD_FILE = re.compile(r"\*\*\*\s+Add File:\s*(?P<path>[^\n]+)", re.IGNORECASE)
UPDATE_FILE = re.compile(r"\*\*\*\s+Update File:\s*(?P<path>[^\n]+)", re.IGNORECASE)
EXECUTABLE_PATH = re.compile(r"/(?:scripts?|cli)/[^\s]+\.(?:py|sh|mjs|js|ts)$", re.IGNORECASE)
PIPELINE_ASSET_PATH = re.compile(r"/pipelines?/[^\s]+\.(?:json|ya?ml)$", re.IGNORECASE)
SCRIPT_VALIDATION = re.compile(
    r"(?:node\s+--check|py_compile|pytest|(?:^|\s)(?:bash|sh|python\d*|node)\s+)",
    re.IGNORECASE,
)
ASSET_VALIDATION = re.compile(r"\bpipeline\s+(?:list|validate|run|test)\b", re.IGNORECASE)


def _existing_script(
    workspace: Path, family: str, *, requires_adaptive_backoff: bool = False
) -> str | None:
    """Return an equivalent existing resource path using conservative markers."""
    marker = {
        "railway-deployment-status": re.compile(
            r"\brailway\s+deployment\s+list\b", re.IGNORECASE
        ),
        "kubernetes-status": re.compile(
            r"\bkubectl\s+(?:get|rollout\s+status)\b", re.IGNORECASE
        ),
        "github-status": re.compile(
            r"\bgh\s+(?:run|pr)\s+(?:view|list|watch|checks)\b", re.IGNORECASE
        ),
        "cloud-status": re.compile(
            r"\b(?:aws|gcloud|az)\b[^\n;]*(?:describe|status|list|get)\b",
            re.IGNORECASE,
        ),
    }.get(family)
    if marker is None:
        return None
    roots = (
        workspace / "candidate_skills",
        workspace / "target/to_be_improved_skills",
    )
    generic_status_runner = (
        re.compile(r"status[-_ ]command", re.IGNORECASE),
        re.compile(r"\b(?:poll|polling)\b", re.IGNORECASE),
        re.compile(r"\b(?:timeout|deadline)\b", re.IGNORECASE),
        re.compile(r"terminal", re.IGNORECASE),
    )
    for root in roots:
        for path in sorted(root.glob("*/scripts/**/*")) if root.is_dir() else []:
            if not path.is_file() or path.stat().st_size > 512_000:
                continue
            try:
                content = path.read_text(errors="replace")
            except OSError:
                continue
            if requires_adaptive_backoff and not ADAPTIVE_BACKOFF.search(content):
                continue
            if marker.search(content) and PACING.search(content) and TERMINATION.search(content):
                return path.relative_to(workspace).as_posix()
            if all(pattern.search(content) for pattern in generic_status_runner):
                return path.relative_to(workspace).as_posix()
    return None


def _fingerprint(text: str) -> tuple[str, str] | None:
    for pattern, family in POLL_COMMANDS:
        if pattern.search(text):
            flags = sorted(set(re.findall(r"--[a-z][a-z0-9-]*", text.casefold())))
            identity = json.dumps([family, flags], separators=(",", ":"))
            return family, hashlib.sha256(identity.encode()).hexdigest()[:24]
    return None


def _normalized_excerpt(text: str, maximum: int = 1000) -> str:
    text = UUID.sub("<id>", text)
    text = LONG_NUMBER.sub("<number>", text)
    text = SPACE.sub(" ", text).strip()
    return text[:maximum]


def _supporting_resource_candidate(
    text: str, tool: str = ""
) -> tuple[str, str, str] | None:
    """Return a conservative non-script resource candidate.

    The normalized key intentionally removes run-specific identifiers while
    retaining the reusable prompt or source path. These candidates still need
    repeated independent observations before they become findings.
    """
    delegated = DELEGATED_PROMPT.search(text)
    if delegated is None and tool.rsplit(".", 1)[-1] in {
        "spawn_agent",
        "create_thread",
    }:
        delegated = DELEGATED_MESSAGE.search(text)
    if delegated:
        body = _normalized_excerpt(delegated.group("body"), 800)
        if len(body.split()) >= 12:
            return "agents", "delegated-prompt", body
    reference = REFERENCE_READ.search(text)
    if reference:
        path = reference.group("path").rstrip(".,;:'\"")
        return "references", "repeated-knowledge-source", path.casefold()
    reuse = ASSET_REUSE.search(text)
    if reuse:
        path = reuse.group("path").rstrip(".,;:'\"")
        return "assets", "repeated-starter-reuse", path.casefold()
    asset = INLINE_ASSET.search(text)
    if asset:
        path = asset.group("path").rstrip(".,;:'\"")
        body = "\n".join(
            line[1:] for line in asset.group("body").splitlines()
        ).strip()
        normalized = _normalized_excerpt(f"{path}\n{body}", 4000)
        if len(body) >= 20:
            return "assets", "repeated-inline-starter", normalized
    return None


def _equivalent_supporting_resource(
    workspace: Path, resource: str, normalized: str
) -> str | None:
    """Find an authored resource that records the same reusable source/body."""
    roots = (
        workspace / "candidate_skills",
        workspace / "target/to_be_improved_skills",
    )
    needle = " ".join(normalized.casefold().split())
    needles = [needle]
    asset_source = ""
    asset_keys: set[str] = set()
    agent_terms: set[str] = set()
    if resource == "assets" and " " in needle:
        # Inline asset fingerprints include the destination path for identity,
        # while the authored asset file contains only the captured body.
        asset_source, asset_body = needle.split(" ", 1)
        needles.append(asset_body)
        asset_keys = set(
            re.findall(r"(?:^|\s)([a-z_][a-z0-9_-]*)\s*:", asset_body)
        )
    elif resource == "agents":
        stopwords = {
            "and", "changed", "concise", "exact", "file", "only",
            "paths", "return", "that", "the", "this", "with",
        }
        agent_terms = {
            term
            for term in re.findall(r"[a-z][a-z0-9_-]{3,}", needle)
            if term not in stopwords
        }
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob(f"*/{resource}/**/*")):
            if not path.is_file() or path.stat().st_size > 1_000_000:
                continue
            content = " ".join(_readable_resource_text(path).casefold().split())
            if any(candidate and candidate in content for candidate in needles):
                return path.relative_to(workspace).as_posix()
            if resource == "agents" and len(agent_terms) >= 8:
                content_terms = set(
                    re.findall(r"[a-z][a-z0-9_-]{3,}", content)
                )
                # Agent prompts are normally expanded into structured prompt
                # files, so byte containment is too brittle. Require a large
                # overlap across the prompt's discriminative terms; generic
                # delegation files will not meet both the term-count and ratio
                # guards.
                if len(agent_terms & content_terms) / len(agent_terms) >= 0.60:
                    return path.relative_to(workspace).as_posix()
            if resource == "assets" and asset_source and asset_keys:
                # Optimizers may add comments or adapt example values while
                # retaining the reusable artifact's contract. Treat a file at
                # the same declared resource path as equivalent only when it
                # still contains every captured structured key. This permits
                # convergence after value adaptation without hiding a later
                # trace that introduces a genuinely new field.
                resource_marker = "/assets/"
                relative = path.as_posix().casefold()
                if resource_marker in relative:
                    authored_source = "assets/" + relative.split(
                        resource_marker, 1
                    )[1]
                    content_keys = set(
                        re.findall(
                            r"(?:^|\s)([a-z_][a-z0-9_-]*)\s*:", content
                        )
                    )
                    if authored_source == asset_source and asset_keys <= content_keys:
                        return path.relative_to(workspace).as_posix()
    return None


def _readable_resource_text(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _decoded_arguments(value: str) -> str:
    """Decode the bounded JSON/JavaScript string escapes needed for patch mining."""
    return value.replace("\\r\\n", "\n").replace("\\n", "\n").replace('\\"', '"')


def _complete_added_file_body(arguments: str, match: re.Match[str]) -> str | None:
    """Return a complete apply_patch Add File body, never a truncated prefix.

    Tool evidence is deliberately bounded.  Capturing a partial configuration
    as though it were a reusable asset is worse than declaring the content
    unavailable, so a body qualifies only when a later patch marker proves the
    end of the file was observed and every intervening line is an added line.
    """
    remainder = arguments[match.end():]
    if remainder.startswith("\r\n"):
        remainder = remainder[2:]
    elif remainder.startswith("\n"):
        remainder = remainder[1:]
    lines = remainder.splitlines()
    body: list[str] = []
    complete = False
    for line in lines:
        if re.match(r"^\*\*\*\s+(?:Add|Update|Delete) File:", line, re.IGNORECASE) or re.match(
            r"^\*\*\*\s+End Patch\s*$", line, re.IGNORECASE
        ):
            complete = True
            break
        if not line.startswith("+"):
            return None
        body.append(line[1:])
    if not complete or not body:
        return None
    content = "\n".join(body)
    if len(content.encode()) > 256_000:
        return None
    return content + "\n"


def _authored_resource_lifecycle_findings(
    workspace: Path, output_root: Path, settings: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Find explicit create -> validate/reuse lifecycles in tool evidence.

    This complements repetition mining. A newly authored executable or pipeline
    template is strong evidence only when a later independent event validates,
    executes, updates, or consumes it successfully.
    """
    rows: list[dict[str, Any]] = []
    for path in sorted((output_root / "normalized/tool_evidence").glob("*.jsonl")):
        for line in path.read_text(errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                row["decoded_arguments"] = _decoded_arguments(str(row.get("arguments") or ""))
                row["turn_path"] = (
                    f"traces/derived/normalized/turns/{path.stem}.json"
                )
                rows.append(row)

    findings: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for created in rows:
        arguments = created["decoded_arguments"]
        for match in ADD_FILE.finditer(arguments):
            source_path = match.group("path").strip().rstrip(".,;:'\"")
            captured_body = _complete_added_file_body(arguments, match)
            resource = "scripts" if EXECUTABLE_PATH.search(source_path) else (
                "assets" if PIPELINE_ASSET_PATH.search(source_path) else ""
            )
            if not resource:
                continue
            trace_id = str(created.get("trace_id") or "")
            sequence = int(created.get("sequence") or 0)
            basename = Path(source_path).name
            stem = Path(source_path).stem.casefold()
            later = [
                row for row in rows
                if row.get("trace_id") == trace_id
                and int(row.get("sequence") or 0) > sequence
                and row.get("status") == "completed"
            ]
            validation = []
            updates = []
            for row in later:
                text = str(row.get("decoded_arguments") or "")
                result = str(row.get("result_preview") or "")
                if resource == "scripts":
                    if basename in text and SCRIPT_VALIDATION.search(text):
                        validation.append(row)
                    if basename in text and UPDATE_FILE.search(text):
                        updates.append(row)
                else:
                    family_word = "pipeline" if "pipeline" in source_path.casefold() else stem
                    if family_word in f"{text} {result}".casefold() and ASSET_VALIDATION.search(text):
                        validation.append(row)
            stages = 1 + bool(validation) + bool(updates)
            if resource == "assets" and validation:
                # A successful consumer is both validation and observed reuse.
                stages = 3
            if stages < 3:
                decisions.append({
                    "resource": resource,
                    "family": "authored-executable" if resource == "scripts" else "authored-pipeline-template",
                    "source_path": source_path,
                    "disposition": "rejected",
                    "reason_codes": ["incomplete-authored-resource-lifecycle"],
                    "lifecycle_stages": stages,
                })
                continue
            family = "authored-executable" if resource == "scripts" else "authored-pipeline-template"
            digest = hashlib.sha256(source_path.casefold().encode()).hexdigest()[:24]
            existing = _equivalent_supporting_resource(workspace, resource, basename.casefold())
            if existing:
                decisions.append({
                    "resource": resource, "family": family, "source_path": source_path,
                    "disposition": "suppressed", "reason_codes": ["equivalent-resource-exists"],
                    "equivalent_resource_path": existing,
                })
                continue
            evidence_rows = [created, validation[0], (updates or validation)[-1]]
            quote = " | ".join(
                _normalized_excerpt(
                    str(row.get("decoded_arguments") or ""), 550
                )
                for row in evidence_rows
            )
            evidence = [{
                "trace_id": trace_id,
                "turn_path": str(created.get("turn_path") or ""),
                "field": "tools.arguments",
                "quote": quote,
                "quote_sha256": hashlib.sha256(quote.encode()).hexdigest(),
            }]
            features: dict[str, Any] = {
                "candidate_source": "resource_opportunity",
                "resource": resource,
                "resource_decision": "use",
                "resource_family": family,
                "resource_fingerprint": digest,
                "resource_evidence_mode": "authored_lifecycle",
                "source_path": source_path,
                "occurrence_count": len(evidence_rows),
                "distinct_windows": 1,
                "distinct_lifecycle_stages": stages,
                "equivalent_resource_exists": False,
                "equivalent_resource_path": None,
                "false_positive_guards": [
                    "repeated-independent-invocations",
                    "explicit-resource-shape",
                    "stable-normalized-fingerprint",
                    "successful-post-authoring-validation",
                ],
            }
            if resource == "scripts":
                features["script_contract"] = {
                    "source": source_path,
                    "inputs": ["repository-local arguments and configuration"],
                    "output": "machine-readable command result",
                    "failure_behavior": "exit nonzero without publishing partial output",
                    "content_available": False,
                    "allowed_artifact": "a bounded representative helper derived from the validated executable contract",
                }
            else:
                features["asset_contract"] = {
                    "source": source_path,
                    "content": captured_body,
                    "content_available": captured_body is not None,
                    "content_digest_available": captured_body is not None,
                    "content_sha256": (
                        hashlib.sha256(captured_body.encode()).hexdigest()
                        if captured_body is not None else None
                    ),
                    "allowed_artifact": (
                        "the captured validated pipeline configuration, with only documented adaptation points"
                        if captured_body is not None
                        else "a reuse manifest documenting the observed pipeline path and validation contract; no placeholder template may be presented as captured content"
                    ),
                    "reuse": "instantiate and validate the pipeline template instead of regenerating the configuration",
                }
            identity = json.dumps(["authored-resource", trace_id, resource, digest], separators=(",", ":"))
            signal_id = "sig-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
            findings.append({
                "schema_version": 1, "signal_id": signal_id,
                "detector": f"resource-{resource}-opportunity", "detector_version": "2",
                "scope": "session", "session_id": trace_id.split(":")[1] if ":" in trace_id else trace_id,
                "trace_ids": [trace_id], "first_seen": "", "last_seen": "",
                "severity": "high", "confidence": 0.94, "score": 0.9,
                "routing": "skill_evolution", "features": features, "evidence": evidence,
            })
            decisions.append({
                "signal_id": signal_id, "resource": resource, "family": family,
                "source_path": source_path, "disposition": "emitted",
                "reason_codes": ["qualified-authored-resource-lifecycle"],
                "lifecycle_stages": stages, "confidence": 0.94,
            })
    return findings, decisions


def _supporting_resource_findings(
    workspace: Path,
    records: list[dict[str, Any]],
    settings: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    minimum = int(settings.get("min_supporting_resource_invocations", 3))
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    decisions: list[dict[str, Any]] = []
    for record in records:
        candidate = _supporting_resource_candidate(
            record["arguments"], str(record.get("tool") or "")
        )
        if candidate is None:
            continue
        resource, family, normalized = candidate
        digest = hashlib.sha256(normalized.encode()).hexdigest()[:24]
        groups[(record["session_id"], resource, family, digest)].append(
            {**record, "resource": resource, "family": family, "normalized": normalized}
        )
    findings: list[dict[str, Any]] = []
    for (session_id, resource, family, digest), matches in sorted(groups.items()):
        traces = sorted({str(row["trace_id"]) for row in matches})
        if len(matches) < minimum or len(traces) < 2:
            decisions.append(
                {
                    "resource": resource,
                    "family": family,
                    "fingerprint": digest,
                    "disposition": "rejected",
                    "reason_codes": ["insufficient-independent-invocations"],
                    "invocations": len(matches),
                    "distinct_traces": len(traces),
                }
            )
            continue
        existing_path = _equivalent_supporting_resource(
            workspace, resource, matches[0]["normalized"]
        )
        if existing_path is not None:
            decisions.append(
                {
                    "resource": resource,
                    "family": family,
                    "fingerprint": digest,
                    "disposition": "suppressed",
                    "reason_codes": ["equivalent-resource-exists"],
                    "invocations": len(matches),
                    "distinct_traces": len(traces),
                    "equivalent_resource_path": existing_path,
                }
            )
            continue
        confidence = min(0.96, 0.78 + 0.03 * min(len(matches), 4) + 0.02 * min(len(traces), 3))
        identity = json.dumps(
            ["supporting-resource", session_id, resource, family, digest],
            separators=(",", ":"),
        )
        signal_id = "sig-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        excerpts = []
        seen: set[str] = set()
        for row in matches:
            if row["trace_id"] in seen:
                continue
            seen.add(row["trace_id"])
            quote = _normalized_excerpt(row["arguments"], 900)
            excerpts.append(
                {
                    "trace_id": row["trace_id"],
                    "turn_path": row["turn_path"],
                    "field": "tools.arguments",
                    "quote": quote,
                    "quote_sha256": hashlib.sha256(quote.encode()).hexdigest(),
                }
            )
        features: dict[str, Any] = {
            "candidate_source": "resource_opportunity",
            "resource": resource,
            "resource_decision": "use",
            "resource_family": family,
            "resource_fingerprint": digest,
            "occurrence_count": len(matches),
            "distinct_windows": len(traces),
            "equivalent_resource_exists": existing_path is not None,
            "equivalent_resource_path": existing_path,
            "false_positive_guards": [
                "repeated-independent-invocations",
                "explicit-resource-shape",
                "stable-normalized-fingerprint",
            ],
        }
        if resource == "agents":
            features["agent_contract"] = {
                "prompt": matches[0]["normalized"],
                "output": "bounded delegated result returned to the calling workflow",
            }
        elif resource == "references":
            features["reference_contract"] = {
                "source": matches[0]["normalized"],
                "read_when": "before the conditional workflow that repeatedly retrieves this knowledge",
                "content_available": False,
                "content_digest_available": False,
                "allowed_artifact": "navigational index with a runtime freshness check",
            }
        else:
            normalized = matches[0]["normalized"]
            captured_inline = family == "repeated-inline-starter"
            features["asset_contract"] = {
                "source": normalized.split(" ", 1)[0],
                "content": normalized if captured_inline else None,
                "content_available": captured_inline,
                "allowed_artifact": (
                    "captured reusable starter artifact"
                    if captured_inline
                    else "reuse manifest documenting the observed starter path and safe adaptation contract"
                ),
                "reuse": "copy or adapt the observed starter artifact instead of regenerating it",
            }
        findings.append(
            {
                "schema_version": 1,
                "signal_id": signal_id,
                "detector": f"resource-{resource}-opportunity",
                "detector_version": "1",
                "scope": "session",
                "session_id": session_id,
                "trace_ids": traces,
                "first_seen": "",
                "last_seen": "",
                "severity": "medium",
                "confidence": round(confidence, 6),
                "score": round(min(1.0, len(matches) / 5), 6),
                "routing": "skill_evolution",
                "features": features,
                "evidence": excerpts[: int(settings.get("max_evidence_records", 5))],
            }
        )
        decisions.append(
            {
                "signal_id": signal_id,
                "resource": resource,
                "family": family,
                "fingerprint": digest,
                "disposition": "emitted",
                "reason_codes": [f"qualified-{resource}-opportunity"],
                "invocations": len(matches),
                "distinct_traces": len(traces),
                "confidence": round(confidence, 6),
            }
        )
    return findings, decisions


def _loop_bound(text: str) -> int | None:
    match = BOUNDED_LOOP.search(text)
    if not match:
        return None
    source = match.group(0)
    range_match = re.search(r"(\d+)\.\.(\d+)", source)
    if range_match:
        return abs(int(range_match.group(2)) - int(range_match.group(1))) + 1
    values = [int(value) for value in re.findall(r"\b\d+\b", source)]
    return len(values) if len(values) >= 3 else None


def analyze(
    workspace: Path, output_root: Path, config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    settings = config.get("resource_opportunities") or {}
    if not settings.get("enabled", True):
        return [], []
    minimum_invocations = int(settings.get("min_invocations", 3))
    minimum_loop_iterations = int(settings.get("min_loop_iterations", 3))
    minimum_confidence = float(settings.get("min_confidence", 0.82))
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    decisions: list[dict[str, Any]] = []
    supporting_records: list[dict[str, Any]] = []

    for path in sorted((output_root / "normalized/task_trajectories").glob("*.json")):
        trajectory = json.loads(path.read_text())
        for event in trajectory.get("events") or []:
            arguments = str(event.get("arguments_preview") or "")
            supporting_records.append(
                {
                    "trace_id": trajectory["trace_id"],
                    "session_id": trajectory["session_id"],
                    "turn_path": (trajectory.get("provenance") or {}).get("turn_path"),
                    "status": event.get("status"),
                    "tool": event.get("tool"),
                    "arguments": arguments,
                }
            )
            fingerprint = _fingerprint(arguments)
            if fingerprint is None or not (
                BOUNDED_LOOP.search(arguments) or UNBOUNDED_LOOP.search(arguments)
            ):
                continue
            family, digest = fingerprint
            reasons: list[str] = []
            bound = _loop_bound(arguments)
            if bound is None or bound < minimum_loop_iterations:
                reasons.append("loop-not-provably-bounded")
            if UNBOUNDED_LOOP.search(arguments):
                reasons.append("unbounded-loop")
            if not PACING.search(arguments):
                reasons.append("missing-pacing-or-backoff")
            if not TERMINATION.search(arguments):
                reasons.append("missing-terminal-condition")
            if MUTATION.search(arguments):
                reasons.append("destructive-command")
            record = {
                "trace_id": trajectory["trace_id"],
                "session_id": trajectory["session_id"],
                "turn_path": (trajectory.get("provenance") or {}).get("turn_path"),
                "sequence": event.get("sequence"),
                "status": event.get("status"),
                "family": family,
                "fingerprint": digest,
                "loop_bound": bound,
                "excerpt": _normalized_excerpt(arguments),
                "timestamp": "",
            }
            if reasons:
                decisions.append({**record, "disposition": "rejected", "reason_codes": reasons})
                continue
            groups[(trajectory["session_id"], family, digest)].append(record)

    findings: list[dict[str, Any]] = []
    for (session_id, family, digest), records in sorted(groups.items()):
        invocations = len(records)
        distinct_traces = sorted({record["trace_id"] for record in records})
        total_iterations = sum(int(record["loop_bound"] or 0) for record in records)
        if invocations < minimum_invocations:
            for record in records:
                decisions.append(
                    {**record, "disposition": "rejected", "reason_codes": ["insufficient-independent-invocations"]}
                )
            continue
        completed = sum(record["status"] == "completed" for record in records)
        success_rate = completed / invocations
        requires_adaptive_backoff = any(
            ADAPTIVE_BACKOFF.search(record["excerpt"]) for record in records
        )
        existing = _existing_script(
            workspace,
            family,
            requires_adaptive_backoff=requires_adaptive_backoff,
        )
        if existing:
            decisions.append(
                {
                    "family": family,
                    "fingerprint": digest,
                    "disposition": "rejected",
                    "reason_codes": ["equivalent-existing-script"],
                    "existing_resource": existing,
                    "invocations": invocations,
                }
            )
            continue
        confidence = min(
            0.98,
            0.68
            + min(invocations, 8) * 0.025
            + min(len(distinct_traces), 4) * 0.025
            + success_rate * 0.05,
        )
        if confidence < minimum_confidence:
            for record in records:
                decisions.append(
                    {**record, "disposition": "rejected", "reason_codes": ["below-confidence-threshold"]}
                )
            continue
        identity = json.dumps(["resource-script", session_id, family, digest], separators=(",", ":"))
        signal_id = "sig-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        excerpts = []
        seen_evidence_traces: set[str] = set()
        for record in records:
            if record["trace_id"] in seen_evidence_traces:
                continue
            if len(excerpts) >= int(settings.get("max_evidence_records", 5)):
                break
            seen_evidence_traces.add(record["trace_id"])
            quote = record["excerpt"]
            excerpts.append(
                {
                    "trace_id": record["trace_id"],
                    "turn_path": record["turn_path"],
                    "field": "tools.arguments",
                    "quote": quote,
                    "quote_sha256": hashlib.sha256(quote.encode()).hexdigest(),
                }
            )
        finding = {
            "schema_version": 1,
            "signal_id": signal_id,
            "detector": "resource-script-opportunity",
            "detector_version": "1",
            "scope": "session",
            "session_id": session_id,
            "trace_ids": distinct_traces,
            "first_seen": "",
            "last_seen": "",
            "severity": "high" if invocations >= 5 else "medium",
            "confidence": round(confidence, 6),
            "score": round(min(1.0, total_iterations / 40), 6),
            "routing": "skill_evolution",
            "features": {
                "candidate_source": "resource_opportunity",
                "resource": "scripts",
                "resource_decision": "use",
                "resource_family": family,
                "resource_fingerprint": digest,
                "occurrence_count": invocations,
                "distinct_windows": len(distinct_traces),
                "estimated_repetitions": total_iterations,
                "execution_success_rate": round(success_rate, 6),
                "false_positive_guards": [
                    "bounded-loop",
                    "explicit-pacing",
                    "terminal-condition",
                    "non-destructive-command",
                    "repeated-independent-invocations",
                ],
                "required_capabilities": {
                    "adaptive_backoff": requires_adaptive_backoff,
                },
                "script_contract": {
                    "inputs": ["service", "environment", "deployment_id", "timeout", "poll_interval"],
                    "output": "terminal deployment status and machine-readable exit result",
                    "failure_behavior": (
                        "honor adaptive backoff and stop on timeout, command failure, or terminal failure state"
                        if requires_adaptive_backoff
                        else "stop on timeout, command failure, or terminal failure state"
                    ),
                    "fixture": "mock status sequence BUILDING, BUILDING, SUCCESS",
                },
            },
            "evidence": excerpts,
        }
        findings.append(finding)
        decisions.append(
            {
                "signal_id": signal_id,
                "family": family,
                "fingerprint": digest,
                "disposition": "emitted",
                "reason_codes": ["qualified-script-opportunity"],
                "invocations": invocations,
                "distinct_traces": len(distinct_traces),
                "estimated_repetitions": total_iterations,
                "confidence": round(confidence, 6),
            }
        )
    supporting_findings, supporting_decisions = _supporting_resource_findings(
        workspace, supporting_records, settings
    )
    lifecycle_findings, lifecycle_decisions = _authored_resource_lifecycle_findings(
        workspace, output_root, settings
    )
    return (
        findings + supporting_findings + lifecycle_findings,
        decisions + supporting_decisions + lifecycle_decisions,
    )
