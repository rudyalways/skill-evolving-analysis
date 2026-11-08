#!/usr/bin/env python3
"""Config-driven conformance preflight for a complete JSON or JSONL artifact.

The validator is deliberately generic: every expected value, bound, unit
factor, group order, and separation threshold is read from a task-derived
constraint spec. It hard-codes no benchmark paths, answers, or unit tables.

Exit codes: 0 clean, 1 violations or unverifiable constraints, 2 spec/artifact
error.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

INVARIANT_CLASSES = {
    "equality",
    "numeric_range",
    "calibration",
    "independent_recompute",
    "field_encoding",
    "structural",
    "domain_membership",
    "graph_structure",
    "companion_artifact",
    "geometry_conformance",
    "unverifiable",
}
METAMORPHIC_KINDS = {"positive", "bounds", "representation", "round_trip"}
GEOMETRY_PRIMITIVES = {"box", "sphere", "cylinder", "plane"}
GEOMETRY_METRICS = {"max_nearest", "chamfer"}
GEOMETRY_FRAMES = {"scene_root", "part_local"}
GEOMETRY_REJECTED_SOURCE_KINDS = {
    "submitted_export",
    "producer_output",
    "manifest",
    "exporter_intermediate",
    "same_pipeline",
}
GEOMETRY_REJECTED_EVIDENCE = {
    "export_path",
    "producer_reconstruction",
    "self_comparison",
    "counts",
    "file_counts",
    "mesh_counts",
    "triangle_equality",
    "all_checks_passed",
}
GEOMETRY_MESH_SUFFIXES = {".obj", ".ply", ".stl", ".gltf", ".glb", ".fbx"}
GEOMETRY_PRODUCER_PATH_TOKEN = re.compile(
    r"(?:^|[\\/_.-])(manifest|producer|exporter|export|intermediate|submitted|submission)"
    r"(?:[\\/_.-]|$)",
    re.IGNORECASE,
)
GEOMETRY_SELF_REFERENTIAL_TOKEN = re.compile(
    r"\b(producer|exporter|submitted|submission|manifest|intermediate|"
    r"self[-_ ]?referential|same[-_ ](?:primitive|transform|code|path|builder|exporter)|"
    r"shared[-_ ]?(?:primitive|coordinates?|transform|code|path)|expected[-_ ]coordinates?)\b",
    re.IGNORECASE,
)


def geometry_acceptance_tolerance(invariant: dict[str, Any]) -> Any:
    """Return the task-derived acceptance tolerance, never a looser local default.

    ``acceptance_tolerance`` is the contract value. Legacy specs may carry only
    ``tolerance``; it is accepted as a fallback so earlier fixtures keep working,
    but when both are present the task-stated value wins.
    """
    if "acceptance_tolerance" in invariant:
        return invariant.get("acceptance_tolerance")
    return invariant.get("tolerance")


def geometry_independence_reason(provenance: dict[str, Any]) -> str | None:
    """Fail closed when the expected surface reuses the producer's path.

    A reconstruction is independent only when it records a separate source reader
    and transform path. Reusing the producer's primitive decomposition, expected
    coordinates, or transform code makes the comparison self-referential even
    when it records provenance strings.
    """
    if provenance.get("self_referential") is True:
        return "expected surface is declared self-referential, so it cannot prove independence"
    evidence = provenance.get("independence_evidence")
    if isinstance(evidence, dict):
        if evidence.get("independent_of_exporter") is not True:
            return (
                "independence evidence does not establish a second derivation path; "
                "record independent_of_exporter: true with a separate reader and transform_path"
            )
        if evidence.get("self_referential") is True:
            return "independence evidence declares the producer's own reconstruction"
        reader = evidence.get("reader")
        transform_path = evidence.get("transform_path")
        if not isinstance(reader, str) or not reader.strip():
            return "independence evidence has no separate source reader"
        if not isinstance(transform_path, str) or not transform_path.strip():
            return "independence evidence has no separate transform path"
        values = [("reader", reader), ("transform_path", transform_path)]
    elif isinstance(evidence, str):
        if not evidence.strip():
            return "independence evidence is empty"
        values = [("independence_evidence", evidence)]
    else:
        reader = provenance.get("reader")
        transform_path = provenance.get("transform_path")
        if not isinstance(reader, str) or not reader.strip():
            return (
                "independence evidence is absent; record a separate reader and "
                "transform_path or an independence_evidence object"
            )
        if not isinstance(transform_path, str) or not transform_path.strip():
            return (
                "independence evidence is incomplete; record a separate transform_path "
                "that does not reuse the producer's primitive or transform code"
            )
        values = [("reader", reader), ("transform_path", transform_path)]
    for label, value in values:
        if GEOMETRY_SELF_REFERENTIAL_TOKEN.search(value):
            return (
                f"independence evidence {label} names the producer, exporter, submitted "
                "artifact, or the same primitive/transform path, so the expected surface "
                "is self-referential and cannot establish equivalence"
            )
    return None


class SpecError(ValueError):
    """Raised when the constraint spec itself cannot be used."""


class ArtifactError(ValueError):
    """Raised when the artifact cannot be read or located."""


def resolve_path(record: Any, path: str | None) -> Any:
    """Resolve a dotted path against one record. Missing keys yield MISSING."""
    if path in (None, "", "."):
        return record
    current = record
    for part in str(path).split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return MISSING
    return current


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "MISSING"


MISSING = _Missing()


def jsonable(value: Any) -> Any:
    """Make a resolved value safe for JSON output."""
    if value is MISSING:
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    return repr(value)


def load_artifact(path: Path, records_path: str | None, fmt: str) -> list[Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactError(f"cannot read artifact {path}: {exc}") from exc

    chosen = fmt
    if chosen == "auto":
        chosen = "jsonl" if path.suffix.lower() in {".jsonl", ".ndjson"} else "json"
        if chosen == "json":
            try:
                json.loads(text)
            except json.JSONDecodeError:
                chosen = "jsonl"

    if chosen == "jsonl":
        records = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ArtifactError(f"artifact line {line_number} is not valid JSON: {exc}") from exc
        if not records:
            raise ArtifactError("artifact contains no records")
        return records

    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"artifact is not valid JSON: {exc}") from exc

    if isinstance(document, list):
        records = document
    elif isinstance(document, dict):
        key = records_path or "records"
        if key not in document:
            raise ArtifactError(
                f"artifact has no records array at {key!r}; set records_path in the spec"
            )
        records = document[key]
    else:
        raise ArtifactError("artifact root must be an object or array")

    if not isinstance(records, list) or not records:
        raise ArtifactError("artifact records must be a non-empty array")
    return records


def record_locator(record: Any, index: int, path: str | None) -> str:
    value = resolve_path(record, path) if path else MISSING
    if value is MISSING or value is None:
        return f"record[{index}]"
    return str(value)


def load_json_document(path: Path) -> Any:
    """Read the complete JSON artifact for object-path selection."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactError(f"cannot read artifact {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"artifact is not valid JSON: {exc}") from exc


def object_records(
    invariant: dict[str, Any],
    records: list[Any],
    artifact: Path,
    spec: dict[str, Any],
) -> list[Any]:
    """Select the artifact object collection a structural or domain rule applies to."""
    objects_path = invariant.get("objects_path")
    records_path = spec.get("records_path")
    if not objects_path:
        return records
    if records_path and str(objects_path) == str(records_path):
        return records
    if not records_path and str(objects_path) in {"records", "."}:
        return records
    document = load_json_document(artifact)
    objects = resolve_path(document, str(objects_path))
    if objects is MISSING:
        raise ArtifactError(
            f"artifact has no objects at {objects_path!r}; set objects_path on the invariant"
        )
    if not isinstance(objects, list) or not objects:
        raise ArtifactError(f"objects at {objects_path!r} must be a non-empty array")
    return objects


def field_encoding_fields(invariant: dict[str, Any]) -> list[str]:
    """Return every field touched by a field_encoding invariant, in spec order."""
    ordered: list[str] = []
    for key in ("field", "fields", "nullable", "non_nullable", "require_present"):
        value = invariant.get(key)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item in (None, ""):
                continue
            text = str(item)
            if text not in ordered:
                ordered.append(text)
    return ordered


def spec_problem(invariant: dict[str, Any]) -> str | None:
    kind = invariant.get("class")
    if kind not in INVARIANT_CLASSES:
        return f"unknown invariant class {kind!r}"
    if kind == "unverifiable":
        return invariant.get("reason") or "constraint is marked unverifiable"
    if not str(invariant.get("expected_source") or "").strip():
        return "expected_source is absent; expected value cannot be traced to the task"
    if kind == "equality":
        has_literal = "expected" in invariant
        has_pair = bool(invariant.get("expected_field"))
        if not has_literal and not has_pair:
            return "equality invariant needs expected or expected_field"
    if kind == "numeric_range":
        if not invariant.get("field"):
            return "numeric_range invariant needs field"
        if "min" not in invariant and "max" not in invariant:
            return "numeric_range invariant needs min or max"
        unit = invariant.get("unit")
        if unit is not None and not isinstance(unit, dict):
            return "unit must be an object with factor and optional offset"
    if kind == "calibration":
        if not invariant.get("confidence") or not invariant.get("group_by"):
            return "calibration invariant needs confidence and group_by"
        order = invariant.get("order")
        if not isinstance(order, list) or len(order) < 2:
            return "calibration invariant needs an order list with at least two groups"
        if "min_separation" not in invariant:
            return "calibration invariant needs min_separation"
    if kind == "field_encoding":
        fields = field_encoding_fields(invariant)
        if not fields:
            return "field_encoding invariant needs field, fields, nullable, or non_nullable"
        sentinels = invariant.get("forbidden_sentinels")
        if sentinels is not None:
            if not isinstance(sentinels, list):
                return "forbidden_sentinels must be a list of strings"
            if any(not isinstance(sentinel, str) for sentinel in sentinels):
                return "forbidden_sentinels must be a list of strings"
        for key in ("nullable", "non_nullable", "require_present"):
            values = invariant.get(key)
            if values is not None and not isinstance(values, list):
                return f"{key} must be a list of field names"
        if not invariant.get("nullable") and not invariant.get("non_nullable") \
                and not invariant.get("forbidden_sentinels"):
            return "field_encoding invariant needs nullable, non_nullable, or forbidden_sentinels"
    if kind == "structural":
        rules = (
            "required_fields",
            "non_empty_list_fields",
            "allowed_aggregations",
            "required_cache_fields",
            "cache_sources",
        )
        if not any(invariant.get(key) not in (None, "", []) for key in rules):
            return "structural invariant needs at least one declared object rule"
        for key in rules:
            values = invariant.get(key)
            if values is None:
                continue
            if not isinstance(values, list) or not values:
                return f"{key} must be a non-empty list"
            if any(not isinstance(item, str) or not item.strip() for item in values):
                return f"{key} must contain non-empty field names or values"
        for key in ("cache_field", "aggregation_field"):
            value = invariant.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                return f"{key} must be a non-empty field name"
        if invariant.get("allowed_aggregations") and not invariant.get("aggregation_field"):
            return "allowed_aggregations requires aggregation_field"
        if (invariant.get("cache_sources") or invariant.get("required_cache_fields")) \
                and not invariant.get("cache_field"):
            return "cache rules require cache_field"
        if invariant.get("case_sensitive") is not None and not isinstance(invariant.get("case_sensitive"), bool):
            return "case_sensitive must be a boolean"
    if kind == "domain_membership":
        fields = invariant.get("fields") or invariant.get("field")
        if isinstance(fields, str):
            fields = [fields]
        if not isinstance(fields, list) or not fields or any(not isinstance(item, str) or not item.strip() for item in fields):
            return "domain_membership invariant needs field or a non-empty fields list"
        allowed = invariant.get("allowed")
        allowed_by_field = invariant.get("allowed_by_field") or {}
        if allowed is None and not allowed_by_field:
            return "domain_membership invariant needs allowed or allowed_by_field"
        if allowed is not None:
            if not isinstance(allowed, list) or not allowed:
                return "allowed must be a non-empty list"
            if any(not isinstance(item, (str, int, float, bool)) or isinstance(item, (list, dict)) for item in allowed):
                return "allowed must contain scalar category values"
        if not isinstance(allowed_by_field, dict):
            return "allowed_by_field must be an object mapping field names to allowed lists"
        if allowed is None:
            uncovered = [name for name in fields if name not in allowed_by_field]
            if uncovered:
                return f"allowed_by_field is missing domains for fields {uncovered}"
        for name, values in allowed_by_field.items():
            if not isinstance(values, list) or not values:
                return f"allowed_by_field[{name!r}] must be a non-empty list"
            if any(isinstance(item, (list, dict)) for item in values):
                return f"allowed_by_field[{name!r}] must contain scalar category values"
        if invariant.get("case_sensitive") is not None and not isinstance(invariant.get("case_sensitive"), bool):
            return "case_sensitive must be a boolean"
        if invariant.get("allow_null") is not None and not isinstance(invariant.get("allow_null"), bool):
            return "allow_null must be a boolean"
    if kind == "graph_structure":
        if not str(invariant.get("entry_node") or "").strip():
            return "graph_structure invariant needs a declared entry_node"
        for key in ("nodes_path", "edges_path", "node_id_field", "edge_source_field", "edge_target_field"):
            value = invariant.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                return f"{key} must be a non-empty path or field name"
        terminal = invariant.get("terminal_nodes")
        if terminal is not None:
            if not isinstance(terminal, list):
                return "terminal_nodes must be a list"
            if any(item is None or isinstance(item, (list, dict)) for item in terminal):
                return "terminal_nodes must contain scalar node ids"
    if kind == "companion_artifact":
        deliverable = invariant.get("deliverable_path")
        if not isinstance(deliverable, str) or not deliverable.strip():
            return "companion_artifact invariant needs a deliverable_path"
        fmt = invariant.get("format", "auto")
        if fmt not in {"auto", "dot", "svg", "html", "json"}:
            return f"unsupported companion format {fmt!r}"
        for key in (
            "source_nodes_path",
            "source_id_field",
            "source_type_field",
            "node_id_attribute",
            "nodes_path",
            "id_field",
        ):
            value = invariant.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                return f"{key} must be a non-empty path or field name"
        encodings = invariant.get("encodings")
        if encodings is None and invariant.get("encoding") is not None:
            encodings = [invariant.get("encoding")]
        if not isinstance(encodings, list) or not encodings:
            return "companion_artifact invariant needs encoding or a non-empty encodings list"
        for entry in encodings:
            if not isinstance(entry, dict):
                return "each companion encoding must be an object"
            attribute = entry.get("attribute")
            if not isinstance(attribute, str) or not attribute.strip():
                return "each companion encoding needs an attribute"
            mapping = entry.get("mapping")
            if not isinstance(mapping, dict) or not mapping:
                return "each companion encoding needs a non-empty mapping from node type to encoding"
            if any(isinstance(value, (list, dict)) for value in mapping.values()):
                return "companion mapping values must be scalar encodings"
    if kind == "geometry_conformance":
        deliverable = invariant.get("deliverable_path") or invariant.get("mesh_path")
        if not isinstance(deliverable, str) or not deliverable.strip():
            return "geometry_conformance invariant needs a deliverable_path"
        tolerance = numeric(geometry_acceptance_tolerance(invariant))
        if tolerance is None or tolerance < 0:
            return (
                "geometry_conformance invariant needs a non-negative numeric "
                "acceptance_tolerance from the task contract; a local default is not sufficient"
            )
        metric = str(invariant.get("metric") or "max_nearest")
        if metric not in GEOMETRY_METRICS:
            return f"unsupported geometry metric {metric!r}"
        source = invariant.get("source")
        if not isinstance(source, dict):
            return "geometry_conformance needs an independent source scene; expected geometry cannot be derived"
        if (
            source.get("mesh_path")
            or source.get("expected_mesh_path")
            or source.get("path")
            or source.get("export_path")
            or source.get("link_mesh_path")
            or source.get("part_mesh_path")
        ):
            return (
                "expected geometry must be reconstructed from source primitive parameters, "
                "not loaded from an exported, part, or link mesh path"
            )
        if invariant.get("exact_union") is True:
            return (
                "exact_union is producer self-consistency (per-mesh vertex or triangle union); "
                "it cannot satisfy geometry_conformance without an independent source comparison"
            )
        evidence = str(invariant.get("evidence") or "").strip().lower()
        if evidence in GEOMETRY_REJECTED_EVIDENCE or invariant.get("self_consistency_only"):
            return (
                "export-path self-consistency (counts, exact unions, triangle deltas, producer "
                "reconstruction, or link meshes mirroring part meshes) is structural-only and "
                "cannot satisfy geometry_conformance"
            )
        export_checks = invariant.get("export_path_checks")
        if export_checks is not None:
            if not isinstance(export_checks, dict):
                return "export_path_checks must be an object with a pairs list"
            pairs = export_checks.get("pairs")
            if not isinstance(pairs, list) or not pairs:
                return "export_path_checks needs a non-empty pairs list"
            for index, pair in enumerate(pairs):
                if not isinstance(pair, dict):
                    return f"export_path_checks pair[{index}] must be an object"
                for key in ("part_path", "link_path"):
                    value = pair.get(key)
                    if not isinstance(value, str) or not value.strip():
                        return f"export_path_checks pair[{index}] needs {key}"
        has_inline = isinstance(source.get("primitives"), list) and bool(source.get("primitives"))
        has_scene = isinstance(source.get("scene_path"), str) and bool(source.get("scene_path").strip())
        if not has_inline and not has_scene:
            return "geometry_conformance needs source primitives or a source scene_path to derive expected geometry"
        primitives = source.get("primitives") if has_inline else []
        for index, primitive in enumerate(primitives):
            if not isinstance(primitive, dict):
                return f"source primitive[{index}] must be an object"
            if primitive.get("type") not in GEOMETRY_PRIMITIVES:
                return f"unsupported source primitive type {primitive.get('type')!r}"
        mapping = invariant.get("mesh_to_source")
        if mapping is not None and not isinstance(mapping, dict):
            return "mesh_to_source must be an object mapping mesh names to source primitive ids"
        unit = invariant.get("unit_conversion")
        if unit is not None and not isinstance(unit, dict):
            return "unit_conversion must be an object with factor and optional offset"
        frame = invariant.get("frame_transform")
        if frame is not None and not isinstance(frame, (dict, list)):
            return "frame_transform must be a matrix or a transform object"
        provenance = invariant.get("provenance")
        if provenance is not None:
            if not isinstance(provenance, dict) or not provenance:
                return "provenance must be an object recording the expected-surface source"
            for key in ("source_scene_path", "frame", "units", "derivation"):
                value = provenance.get(key)
                if not isinstance(value, str) or not value.strip():
                    return f"provenance needs a non-empty {key}"
            if provenance.get("frame") not in GEOMETRY_FRAMES:
                return f"provenance frame must be scene_root or part_local, not {provenance.get('frame')!r}"
            if provenance.get("source_kind") in GEOMETRY_REJECTED_SOURCE_KINDS:
                return (
                    "provenance source_kind points at the producer's export or manifest; "
                    "expected geometry must come from the task source scene"
                )
        mesh_provenance = invariant.get("mesh_provenance")
        if mesh_provenance is not None and not isinstance(mesh_provenance, dict):
            return "mesh_provenance must be an object mapping mesh names to provenance overrides"
        sample_count = invariant.get("sample_count", 512)
        if not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count < 1:
            return "sample_count must be a positive integer"
    if kind == "independent_recompute":
        field = str(invariant.get("field") or "")
        if not field:
            return "independent_recompute invariant needs field"
        if invariant.get("self_referential") or invariant.get("use_submitted_output"):
            return "self-referential oracle: expected value comes from the producer or its submitted output"
        if str(invariant.get("expected_field") or "") == field:
            return f"self-referential oracle: expected_field is the submitted field {field!r}"
        if str(invariant.get("oracle_field") or "") == field:
            return f"self-referential oracle: oracle_field is the submitted field {field!r}"
        oracle_path = invariant.get("oracle_path")
        producer_path = invariant.get("producer_path")
        if oracle_path and producer_path and str(oracle_path) == str(producer_path):
            return "self-referential oracle: oracle_path is the producer's own code path"
        metamorphic = invariant.get("metamorphic")
        if not oracle_path and not metamorphic:
            return "no independent oracle: supply oracle_path or a metamorphic relation list"
        if metamorphic is not None:
            if not isinstance(metamorphic, list) or not metamorphic:
                return "metamorphic must be a non-empty list of relation objects"
            for relation in metamorphic:
                if not isinstance(relation, dict):
                    return "metamorphic relation must be an object"
                if relation.get("kind") not in METAMORPHIC_KINDS:
                    return f"unknown metamorphic relation kind {relation.get('kind')!r}"
    return None


def numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def equal_values(left: Any, right: Any, tolerance: float) -> bool:
    left_number, right_number = numeric(left), numeric(right)
    if left_number is not None and right_number is not None:
        return abs(left_number - right_number) <= tolerance
    return left == right


def add_violation(
    violations: list[dict[str, Any]],
    invariant: dict[str, Any],
    *,
    locator: str,
    field: str,
    observed: Any,
    expected: Any,
    diagnosis: str,
    oracle_path: str | None = None,
    metamorphic_relation: str | None = None,
    observed_delta: float | None = None,
    deliverable: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    entry = {
        "invariant_id": str(invariant.get("id")),
        "invariant_class": invariant.get("class"),
        "locator": locator,
        "field": field,
        "observed": jsonable(observed),
        "expected": expected,
        "diagnosis": diagnosis,
    }
    if oracle_path is not None:
        entry["oracle_path"] = oracle_path
    if metamorphic_relation is not None:
        entry["metamorphic_relation"] = metamorphic_relation
    if observed_delta is not None:
        entry["observed_delta"] = observed_delta
    if deliverable is not None:
        entry["deliverable"] = deliverable
    if extra:
        entry.update({key: jsonable(value) for key, value in extra.items()})
    violations.append(entry)


def load_oracle(path_text: str, base_dir: Path) -> Any:
    """Load a task-derived oracle module and return its recompute callable."""
    path = Path(path_text)
    if not path.is_absolute():
        path = base_dir / path
    if not path.is_file():
        raise SpecError(f"oracle module not found: {path}")
    module_spec = importlib.util.spec_from_file_location(
        f"preflight_oracle_{abs(hash(str(path.resolve())))}", path
    )
    if module_spec is None or module_spec.loader is None:
        raise SpecError(f"oracle module cannot be loaded: {path}")
    module = importlib.util.module_from_spec(module_spec)
    try:
        module_spec.loader.exec_module(module)
    except Exception as exc:  # oracle code is task-derived, so surface its failure
        raise SpecError(f"oracle module {path} failed to import: {exc}") from exc
    recompute = getattr(module, "recompute", None)
    if not callable(recompute):
        raise SpecError(f"oracle module {path} must define a callable recompute(record)")
    return recompute


def check_equality(
    invariant: dict[str, Any],
    records: list[Any],
    violations: list[dict[str, Any]],
) -> tuple[int, int]:
    field = str(invariant.get("field") or "")
    tolerance = float(invariant.get("tolerance", 0) or 0)
    passed = failed = 0
    for index, record in enumerate(records):
        locator = record_locator(record, index, invariant.get("record_locator"))
        observed = resolve_path(record, field)
        if "expected_field" in invariant:
            expected = resolve_path(record, invariant.get("expected_field"))
            source = f"record field {invariant.get('expected_field')}"
        else:
            expected = invariant.get("expected")
            source = str(invariant.get("expected_source"))
        if observed is MISSING:
            failed += 1
            add_violation(
                violations,
                invariant,
                locator=locator,
                field=field,
                observed=None,
                expected=f"value at {field} matching {source}",
                diagnosis=f"field {field!r} is missing from the record",
            )
            continue
        if expected is MISSING:
            failed += 1
            add_violation(
                violations,
                invariant,
                locator=locator,
                field=field,
                observed=observed,
                expected=f"expected field {invariant.get('expected_field')} to exist",
                diagnosis="paired expected field is missing, so equality cannot hold",
            )
            continue
        if equal_values(observed, expected, tolerance):
            passed += 1
        else:
            failed += 1
            add_violation(
                violations,
                invariant,
                locator=locator,
                field=field,
                observed=observed,
                expected=f"exactly {jsonable(expected)} from {source}",
                diagnosis=f"observed {jsonable(observed)!r} differs from expected {jsonable(expected)!r}",
            )
    return passed, failed


def check_numeric_range(
    invariant: dict[str, Any],
    records: list[Any],
    violations: list[dict[str, Any]],
) -> tuple[int, int]:
    field = str(invariant.get("field") or "")
    lower = numeric(invariant.get("min"))
    upper = numeric(invariant.get("max"))
    unit = invariant.get("unit") or {}
    factor = float(unit.get("factor", 1))
    offset = float(unit.get("offset", 0))
    passed = failed = 0
    bounds = []
    if lower is not None:
        bounds.append(f">= {lower:g}")
    if upper is not None:
        bounds.append(f"<= {upper:g}")
    expected_rule = "value in [" + ", ".join(bounds) + "]"
    if unit:
        expected_rule += f" after conversion {unit.get('from')} -> {unit.get('to')} (factor {factor:g}, offset {offset:g})"

    for index, record in enumerate(records):
        locator = record_locator(record, index, invariant.get("record_locator"))
        raw = resolve_path(record, field)
        value = numeric(raw)
        if value is None:
            failed += 1
            add_violation(
                violations,
                invariant,
                locator=locator,
                field=field,
                observed=raw,
                expected=expected_rule,
                diagnosis=f"field {field!r} is missing or not a finite number",
            )
            continue
        converted = value * factor + offset
        below = lower is not None and converted < lower
        above = upper is not None and converted > upper
        if below or above:
            failed += 1
            add_violation(
                violations,
                invariant,
                locator=locator,
                field=field,
                observed={"raw": raw, "converted": converted, "unit": unit.get("to")},
                expected=expected_rule,
                diagnosis=f"converted value {converted:g} falls outside the allowed range",
            )
        else:
            passed += 1
    return passed, failed


def check_calibration(
    invariant: dict[str, Any],
    records: list[Any],
    violations: list[dict[str, Any]],
    unverifiable: list[dict[str, Any]],
) -> tuple[int, int]:
    confidence_field = str(invariant.get("confidence") or "")
    group_field = str(invariant.get("group_by") or "")
    order = [str(group) for group in invariant.get("order") or []]
    minimum = float(invariant.get("min_separation"))
    groups: dict[str, list[float]] = {group: [] for group in order}
    unknown: list[str] = []

    for index, record in enumerate(records):
        locator = record_locator(record, index, invariant.get("record_locator"))
        group_value = resolve_path(record, group_field)
        confidence = numeric(resolve_path(record, confidence_field))
        if group_value is MISSING or confidence is None:
            add_violation(
                violations,
                invariant,
                locator=locator,
                field=f"{group_field}/{confidence_field}",
                observed={"group": jsonable(group_value), "confidence": jsonable(resolve_path(record, confidence_field))},
                expected=f"group from {group_field} and finite confidence from {confidence_field}",
                diagnosis="record cannot participate in calibration because grouping or confidence is missing",
            )
            continue
        group_key = str(group_value)
        if group_key not in groups:
            unknown.append(f"{locator}:{group_key}")
            continue
        groups[group_key].append(confidence)

    if unknown:
        unverifiable.append(
            {
                "invariant_id": str(invariant.get("id")),
                "reason": "records use groups outside the spec order: " + ", ".join(sorted(unknown)),
            }
        )

    passed = failed = 0
    means: list[tuple[str, float]] = []
    for group in order:
        values = groups[group]
        if not values:
            unverifiable.append(
                {
                    "invariant_id": str(invariant.get("id")),
                    "reason": f"group {group!r} has no records, so its separation cannot be verified",
                }
            )
            continue
        means.append((group, sum(values) / len(values)))

    mean_by_group = dict(means)
    for previous, following in zip(order, order[1:]):
        if previous not in mean_by_group or following not in mean_by_group:
            continue
        gap = mean_by_group[following] - mean_by_group[previous]
        if gap + 1e-12 < minimum:
            failed += 1
            add_violation(
                violations,
                invariant,
                locator=f"group:{previous}->{following}",
                field=confidence_field,
                observed={"lower_mean": mean_by_group[previous], "higher_mean": mean_by_group[following], "separation": gap},
                expected=f"mean separation >= {minimum:g} in order {order}",
                diagnosis=f"confidence separation {gap:.6g} is below the required {minimum:g}",
            )
        else:
            passed += 1
    return passed, failed


def check_field_encoding(
    invariant: dict[str, Any],
    records: list[Any],
    violations: list[dict[str, Any]],
) -> tuple[int, int]:
    """Check per-field nullability and forbidden-sentinel rules from the spec."""
    fields = field_encoding_fields(invariant)
    nullable = {str(item) for item in invariant.get("nullable") or []}
    non_nullable = {str(item) for item in invariant.get("non_nullable") or []}
    require_present = {str(item) for item in invariant.get("require_present") or []}
    sentinels = [str(item) for item in invariant.get("forbidden_sentinels") or []]
    passed = failed = 0

    for index, record in enumerate(records):
        locator = record_locator(record, index, invariant.get("record_locator"))
        for field in fields:
            observed = resolve_path(record, field)
            must_exist = field in require_present
            allows_null = field in nullable and field not in non_nullable
            sentinel = (
                isinstance(observed, str)
                and observed in sentinels
            )

            if observed is MISSING:
                if must_exist:
                    failed += 1
                    required = "JSON null for a missing value" if allows_null else "a non-null value"
                    add_violation(
                        violations,
                        invariant,
                        locator=locator,
                        field=field,
                        observed=None,
                        expected=f"field present as {required}",
                        diagnosis=f"field {field!r} is absent; encode a declared missing value as JSON null",
                    )
                else:
                    passed += 1
                continue

            if sentinel:
                failed += 1
                if allows_null:
                    expected = f"JSON null for a missing {field}; forbidden sentinel {observed!r}"
                else:
                    expected = f"a value other than forbidden sentinel {observed!r}"
                add_violation(
                    violations,
                    invariant,
                    locator=locator,
                    field=field,
                    observed=observed,
                    expected=expected,
                    diagnosis=(
                        f"field {field!r} uses forbidden sentinel {observed!r}; "
                        "encode a declared missing value as JSON null"
                        if allows_null
                        else f"field {field!r} uses forbidden sentinel {observed!r}"
                    ),
                )
                continue

            if observed is None:
                if allows_null:
                    passed += 1
                else:
                    failed += 1
                    add_violation(
                        violations,
                        invariant,
                        locator=locator,
                        field=field,
                        observed=None,
                        expected=f"a non-null value for {field}",
                        diagnosis=f"field {field!r} is null but the contract does not declare it nullable",
                    )
                continue

            passed += 1
    return passed, failed


def non_empty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def check_structural(
    invariant: dict[str, Any],
    objects: list[Any],
    violations: list[dict[str, Any]],
) -> tuple[int, int]:
    """Check required object fields, aggregation mode, and pivot cache coverage."""
    required_fields = [str(item) for item in invariant.get("required_fields") or []]
    list_fields = [str(item) for item in invariant.get("non_empty_list_fields") or []]
    aggregation_field = str(invariant.get("aggregation_field") or "aggregation")
    allowed_aggregations = [item for item in invariant.get("allowed_aggregations") or []]
    cache_field = str(invariant.get("cache_field") or "")
    required_cache_fields = [str(item) for item in invariant.get("required_cache_fields") or []]
    cache_sources = [str(item) for item in invariant.get("cache_sources") or []]
    case_sensitive = bool(invariant.get("case_sensitive", True))
    passed = failed = 0

    def fail(
        locator: str, field: str, observed: Any, expected: Any, diagnosis: str
    ) -> None:
        nonlocal failed
        failed += 1
        add_violation(
            violations,
            invariant,
            locator=locator,
            field=field,
            observed=observed,
            expected=expected,
            diagnosis=diagnosis,
        )

    for index, obj in enumerate(objects):
        locator = record_locator(obj, index, invariant.get("record_locator") or invariant.get("object_locator"))
        for field in required_fields:
            observed = resolve_path(obj, field)
            if observed is MISSING or observed is None:
                fail(
                    locator,
                    field,
                    None,
                    f"required field {field!r} present with a value",
                    f"required object field {field!r} is missing or null",
                )
            else:
                passed += 1

        for field in list_fields:
            observed = resolve_path(obj, field)
            if non_empty_string_list(observed):
                passed += 1
            else:
                fail(
                    locator,
                    field,
                    observed,
                    f"non-empty list of field names for {field!r}",
                    f"{field!r} is not a non-empty list of field names",
                )

        if allowed_aggregations:
            observed = resolve_path(obj, aggregation_field)
            if observed is MISSING or not isinstance(observed, str):
                fail(
                    locator,
                    aggregation_field,
                    None if observed is MISSING else observed,
                    f"aggregation mode in {allowed_aggregations}",
                    f"aggregation field {aggregation_field!r} is missing or not a string",
                )
            else:
                probe = observed if case_sensitive else observed.casefold()
                allowed_probe = [
                    item if case_sensitive else str(item).casefold()
                    for item in allowed_aggregations
                ]
                if probe in allowed_probe:
                    passed += 1
                else:
                    fail(
                        locator,
                        aggregation_field,
                        observed,
                        f"aggregation mode in {allowed_aggregations}",
                        f"aggregation mode {observed!r} is outside the task-declared set",
                    )

        if cache_field:
            cache = resolve_path(obj, cache_field)
            if not non_empty_string_list(cache):
                fail(
                    locator,
                    cache_field,
                    cache,
                    f"non-empty cache field list at {cache_field!r}",
                    f"pivot cache field list {cache_field!r} is missing or empty",
                )
                continue
            for field in required_cache_fields:
                if field in cache:
                    passed += 1
                else:
                    fail(
                        locator,
                        cache_field,
                        cache,
                        f"cache includes required field {field!r}",
                        f"pivot cache is missing required field {field!r}",
                    )
            for source in cache_sources:
                values = resolve_path(obj, source)
                if not isinstance(values, list):
                    fail(
                        locator,
                        source,
                        values,
                        f"a list of fields at {source!r}",
                        f"cache source {source!r} is missing or not a list",
                    )
                    continue
                missing = [item for item in values if item not in cache]
                if missing:
                    fail(
                        locator,
                        cache_field,
                        cache,
                        f"cache includes every field from {source!r}: {missing}",
                        f"pivot cache is missing field(s) {missing} used by {source!r}",
                    )
                else:
                    passed += 1
    return passed, failed


def domain_value_key(value: Any, case_sensitive: bool) -> Any:
    if isinstance(value, str) and not case_sensitive:
        return value.casefold()
    return value


def check_domain_membership(
    invariant: dict[str, Any],
    objects: list[Any],
    violations: list[dict[str, Any]],
) -> tuple[int, int]:
    """Check categorical values against task-declared allowed domains."""
    raw_fields = invariant.get("fields") or invariant.get("field")
    fields = [raw_fields] if isinstance(raw_fields, str) else list(raw_fields or [])
    shared_allowed = invariant.get("allowed")
    allowed_by_field = invariant.get("allowed_by_field") or {}
    case_sensitive = bool(invariant.get("case_sensitive", True))
    allow_null = bool(invariant.get("allow_null", False))
    passed = failed = 0

    for index, obj in enumerate(objects):
        locator = record_locator(obj, index, invariant.get("record_locator") or invariant.get("object_locator"))
        for field in fields:
            allowed = allowed_by_field.get(field, shared_allowed)
            if not isinstance(allowed, list) or not allowed:
                continue
            allowed_keys = [domain_value_key(item, case_sensitive) for item in allowed]
            observed = resolve_path(obj, field)
            if observed is MISSING:
                failed += 1
                add_violation(
                    violations,
                    invariant,
                    locator=locator,
                    field=field,
                    observed=None,
                    expected=f"value in allowed domain {allowed}",
                    diagnosis=f"categorical field {field!r} is missing",
                )
                continue
            values = observed if isinstance(observed, list) else [observed]
            for value in values:
                if value is None and allow_null:
                    passed += 1
                    continue
                if domain_value_key(value, case_sensitive) in allowed_keys:
                    passed += 1
                else:
                    failed += 1
                    add_violation(
                        violations,
                        invariant,
                        locator=locator,
                        field=field,
                        observed=value,
                        expected=f"value in allowed domain {allowed}",
                        diagnosis=f"category {value!r} in {field!r} is outside the task-declared domain",
                    )
            if not values:
                failed += 1
                add_violation(
                    violations,
                    invariant,
                    locator=locator,
                    field=field,
                    observed=observed,
                    expected=f"value in allowed domain {allowed}",
                    diagnosis=f"categorical field {field!r} is empty",
                )
    return passed, failed


def check_independent_recompute(
    invariant: dict[str, Any],
    records: list[Any],
    violations: list[dict[str, Any]],
    base_dir: Path,
) -> tuple[int, int]:
    field = str(invariant.get("field") or "")
    tolerance = float(invariant.get("tolerance", 0) or 0)
    oracle_path = invariant.get("oracle_path")
    metamorphic = invariant.get("metamorphic") or []
    oracle = load_oracle(str(oracle_path), base_dir) if oracle_path else None
    passed = failed = 0

    for index, record in enumerate(records):
        locator = record_locator(record, index, invariant.get("record_locator"))
        observed = numeric(resolve_path(record, field))
        if observed is None:
            failed += 1
            add_violation(
                violations,
                invariant,
                locator=locator,
                field=field,
                observed=resolve_path(record, field),
                expected="a finite numeric derived value",
                diagnosis=f"field {field!r} is missing or not a finite number",
            )
            continue

        relation_failures: list[dict[str, Any]] = []

        if oracle is not None:
            try:
                expected_raw = oracle(record)
            except Exception as exc:
                raise SpecError(f"oracle {oracle_path} failed on {locator}: {exc}") from exc
            expected = numeric(expected_raw)
            if expected is None:
                raise SpecError(f"oracle {oracle_path} returned a non-numeric value on {locator}")
            delta = observed - expected
            if abs(delta) > tolerance:
                relation_failures.append(
                    {
                        "expected": expected_raw,
                        "oracle_path": str(oracle_path),
                        "observed_delta": delta,
                        "diagnosis": (
                            f"independent recomputation differs from submitted {field!r} "
                            f"by {delta:.6g} (tolerance {tolerance:g})"
                        ),
                    }
                )

        for relation in metamorphic:
            kind = str(relation.get("kind"))
            relation_tolerance = float(relation.get("tolerance", tolerance) or 0)
            expected: Any = None
            delta: float | None = None
            failure = None

            if kind == "positive":
                allow_zero = bool(relation.get("allow_zero", False))
                ok = observed >= 0 if allow_zero else observed > 0
                expected = ">= 0" if allow_zero else "> 0"
                if not ok:
                    failure = f"derived value {observed:g} is not {'nonnegative' if allow_zero else 'positive'}"
            elif kind == "bounds":
                lower = numeric(relation.get("min"))
                upper = numeric(relation.get("max"))
                bounds = []
                if lower is not None:
                    bounds.append(f">= {lower:g}")
                if upper is not None:
                    bounds.append(f"<= {upper:g}")
                expected = "value in [" + ", ".join(bounds) + "]"
                if (lower is not None and observed < lower) or (upper is not None and observed > upper):
                    failure = f"derived value {observed:g} is outside the plausible bounds"
            elif kind in {"representation", "round_trip"}:
                source_field = str(relation.get("other_field") or relation.get("source_field") or "")
                source = numeric(resolve_path(record, source_field))
                if source is None:
                    expected = f"finite numeric source at {source_field}"
                    failure = f"source field {source_field!r} is missing or not numeric"
                else:
                    factor = float(relation.get("factor", 1))
                    offset = float(relation.get("offset", 0))
                    expected = source * factor + offset
                    delta = observed - expected
                    if abs(delta) > relation_tolerance:
                        failure = (
                            f"derived value {observed:g} disagrees with {source_field} under "
                            f"factor {factor:g} and offset {offset:g} by {delta:.6g}"
                        )

            if failure is not None:
                relation_failures.append(
                    {
                        "expected": expected,
                        "metamorphic_relation": f"{kind}:{relation.get('other_field') or relation.get('source_field') or 'value'}",
                        "observed_delta": delta,
                        "diagnosis": failure,
                    }
                )

        if relation_failures:
            failed += 1
            for item in relation_failures:
                add_violation(
                    violations,
                    invariant,
                    locator=locator,
                    field=field,
                    observed=observed,
                    expected=item["expected"],
                    diagnosis=item["diagnosis"],
                    oracle_path=item.get("oracle_path"),
                    metamorphic_relation=item.get("metamorphic_relation"),
                    observed_delta=item.get("observed_delta"),
                )
        else:
            passed += 1
    return passed, failed


def companion_encodings(invariant: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every declared semantic-encoding assertion for a companion."""
    encodings = invariant.get("encodings")
    if encodings is None:
        encodings = [invariant.get("encoding")]
    return [entry for entry in encodings if isinstance(entry, dict)]


def parse_dot_nodes(text: str) -> dict[str, dict[str, Any]]:
    """Parse node declarations and their attribute maps from a DOT subset.

    This intentionally handles the portable node-statement form
    ``id [key=value, ...]`` and ignores edge statements, graph defaults, and
    subgraph wrappers. A declaration without attributes still yields a node so
    a missing encoding is observable rather than invisible.
    """
    nodes: dict[str, dict[str, Any]] = {}
    declaration = re.compile(
        r'(?P<ident>"(?:[^"\\]|\\.)*"|[A-Za-z_][A-Za-z0-9_.:-]*)'
        r'\s*\[(?P<attrs>[^\]]*)\]'
    )
    for match in declaration.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        prefix = text[line_start:match.start()]
        if "->" in prefix or "--" in prefix:
            continue
        ident = match.group("ident").strip('"')
        if ident.lower() in {"graph", "digraph", "node", "edge", "subgraph", "strict"}:
            continue
        attrs: dict[str, Any] = {}
        for pair in re.finditer(
            r'([A-Za-z_][A-Za-z0-9_.:-]*)\s*=\s*("(?:[^"\\]|\\.)*"|[^,\s\]]+)',
            match.group("attrs"),
        ):
            key = pair.group(1)
            value = pair.group(2).strip('"')
            attrs[key] = value
        nodes.setdefault(ident, {}).update(attrs)
    return nodes


def parse_svg_nodes(text: str) -> dict[str, dict[str, Any]]:
    """Parse SVG elements carrying an id or data-node-id into attribute maps."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ArtifactError(f"companion SVG is not well-formed XML: {exc}") from exc
    nodes: dict[str, dict[str, Any]] = {}
    for element in root.iter():
        node_id = element.get("data-node-id") or element.get("id")
        if not node_id:
            continue
        nodes[node_id] = {key: value for key, value in element.attrib.items()}
    return nodes


class _HtmlNodeParser(HTMLParser):
    """Collect elements carrying an id or data-node-id from an HTML rendering."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: dict[str, dict[str, Any]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value for key, value in attrs if value is not None}
        node_id = attributes.get("data-node-id") or attributes.get("id")
        if node_id:
            self.nodes[node_id] = attributes

    handle_startendtag = handle_starttag


def parse_html_nodes(text: str) -> dict[str, dict[str, Any]]:
    """Parse an HTML rendering's tagged elements into attribute maps."""
    parser = _HtmlNodeParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # html.parser is lenient; surface rare failures
        raise ArtifactError(f"companion HTML cannot be parsed: {exc}") from exc
    return parser.nodes


def parse_json_nodes(text: str, nodes_path: str, id_field: str) -> dict[str, dict[str, Any]]:
    """Parse a JSON companion's node collection into id-to-object maps."""
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"companion JSON is not valid: {exc}") from exc
    collection = resolve_path(document, nodes_path)
    if not isinstance(collection, list) or not collection:
        raise ArtifactError(f"companion JSON has no node collection at {nodes_path!r}")
    nodes: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(collection):
        node_id = resolve_path(item, id_field) if isinstance(item, dict) else MISSING
        if node_id is MISSING or node_id is None or isinstance(node_id, (list, dict)):
            raise ArtifactError(f"companion node[{index}] has no scalar id at {id_field!r}")
        nodes[str(node_id)] = item
    return nodes


def companion_attribute(node: dict[str, Any], attribute: str) -> Any:
    """Look up an encoding attribute, tolerating dotted paths and data- prefixes."""
    observed = resolve_path(node, attribute)
    if observed is not MISSING:
        return observed
    for candidate in (f"data-{attribute}", "data-" + attribute.replace(".", "-"),
                      "data_" + attribute.replace(".", "_")):
        if candidate in node:
            return node[candidate]
    return MISSING


def check_companion_artifact(
    invariant: dict[str, Any],
    artifact: Path,
    violations: list[dict[str, Any]],
    unverifiable: list[dict[str, Any]],
    base_dir: Path,
) -> tuple[int, int]:
    """Check that a companion deliverable encodes each declared semantic distinction.

    The companion is a separate rendered representation (DOT, SVG, or JSON
    node map). The task-derived encoding contract maps each source node type to
    the attribute value the rendering must carry. The check parses the
    companion, requires the declared path to exist, and compares the observed
    encoding per declared node; existence or byte size alone never passes.
    """
    invariant_id = str(invariant.get("id"))
    deliverable = str(invariant.get("deliverable_path"))
    path = Path(deliverable)
    if not path.is_absolute():
        path = base_dir / path
    if not path.is_file():
        add_violation(
            violations,
            invariant,
            locator=deliverable,
            field="deliverable_path",
            observed="absent",
            expected=f"companion deliverable present at declared path {deliverable!r}",
            diagnosis=f"declared companion deliverable {deliverable!r} does not exist",
            deliverable=deliverable,
        )
        return 0, 1

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        add_violation(
            violations,
            invariant,
            locator=deliverable,
            field="deliverable_path",
            observed="unreadable",
            expected=f"readable companion deliverable at {deliverable!r}",
            diagnosis=f"declared companion deliverable {deliverable!r} cannot be read: {exc}",
            deliverable=deliverable,
        )
        return 0, 1

    fmt = str(invariant.get("format") or "auto")
    if fmt == "auto":
        suffix = path.suffix.lower()
        fmt = {".dot": "dot", ".gv": "dot", ".svg": "svg", ".html": "html",
                   ".htm": "html", ".json": "json"}.get(suffix, "dot")

    try:
        if fmt == "dot":
            companion_nodes = parse_dot_nodes(text)
        elif fmt == "svg":
            companion_nodes = parse_svg_nodes(text)
        elif fmt == "html":
            companion_nodes = parse_html_nodes(text)
        else:
            companion_nodes = parse_json_nodes(
                text,
                str(invariant.get("nodes_path") or "nodes"),
                str(invariant.get("id_field") or "id"),
            )
    except ArtifactError as exc:
        add_violation(
            violations,
            invariant,
            locator=deliverable,
            field="deliverable_path",
            observed="unparseable",
            expected=f"parseable {fmt} companion deliverable",
            diagnosis=f"companion deliverable {deliverable!r} cannot be parsed: {exc}",
            deliverable=deliverable,
        )
        return 0, 1

    if not companion_nodes:
        add_violation(
            violations,
            invariant,
            locator=deliverable,
            field="nodes",
            observed="no node declarations",
            expected="the companion exposes at least one encoded node",
            diagnosis=f"companion deliverable {deliverable!r} parses but exposes no nodes",
            deliverable=deliverable,
        )
        return 0, 1

    document = load_json_document(artifact)
    source_nodes = resolve_path(document, str(invariant.get("source_nodes_path") or "nodes"))
    if not isinstance(source_nodes, list) or not source_nodes:
        unverifiable.append(
            {
                "invariant_id": invariant_id,
                "reason": "source artifact exposes no node collection for the companion encoding contract",
            }
        )
        return 0, 0

    source_id_field = str(invariant.get("source_id_field") or "id")
    source_type_field = str(invariant.get("source_type_field") or "type")
    node_id_attribute = str(invariant.get("node_id_attribute") or "id")
    encodings = companion_encodings(invariant)
    passed = failed = 0

    for index, node in enumerate(source_nodes):
        node_id = resolve_path(node, source_id_field) if isinstance(node, dict) else MISSING
        node_type = resolve_path(node, source_type_field) if isinstance(node, dict) else MISSING
        if node_id is MISSING or node_id is None or isinstance(node_id, (list, dict)):
            unverifiable.append(
                {
                    "invariant_id": invariant_id,
                    "reason": f"source node[{index}] has no scalar {source_id_field!r} id",
                }
            )
            return passed, failed
        locator = str(node_id)
        if node_type is MISSING or node_type is None:
            failed += 1
            add_violation(
                violations,
                invariant,
                locator=locator,
                field=source_type_field,
                observed=None,
                expected=f"a task-declared {source_type_field!r} for every node",
                diagnosis=f"source node {locator!r} has no type, so its companion encoding cannot be checked",
                deliverable=deliverable,
            )
            continue

        rendered = companion_nodes.get(locator)
        if rendered is MISSING or rendered is None:
            failed += 1
            add_violation(
                violations,
                invariant,
                locator=locator,
                field=node_id_attribute,
                observed="absent",
                expected=f"companion node {locator!r} present in {deliverable!r}",
                diagnosis=f"companion deliverable {deliverable!r} omits source node {locator!r}",
                deliverable=deliverable,
            )
            continue

        type_key = str(node_type)
        for encoding in encodings:
            attribute = str(encoding.get("attribute"))
            mapping = {str(key): value for key, value in (encoding.get("mapping") or {}).items()}
            if type_key not in mapping:
                unverifiable.append(
                    {
                        "invariant_id": invariant_id,
                        "reason": (
                            f"no declared {attribute!r} encoding for node type {type_key!r}; "
                            "the encoding contract is incomplete"
                        ),
                    }
                )
                continue
            expected = mapping[type_key]
            observed = companion_attribute(rendered, attribute)
            if observed is MISSING or observed is None:
                failed += 1
                add_violation(
                    violations,
                    invariant,
                    locator=locator,
                    field=attribute,
                    observed="absent",
                    expected=f"{attribute}={expected!r} for node type {type_key!r}",
                    diagnosis=(
                        f"companion {deliverable!r} node {locator!r} of type {type_key!r} "
                        f"has no {attribute!r} encoding"
                    ),
                    deliverable=deliverable,
                )
            elif str(observed) == str(expected):
                passed += 1
            else:
                failed += 1
                add_violation(
                    violations,
                    invariant,
                    locator=locator,
                    field=attribute,
                    observed=observed,
                    expected=f"{attribute}={expected!r} for node type {type_key!r}",
                    diagnosis=(
                        f"companion {deliverable!r} node {locator!r} of type {type_key!r} "
                        f"encodes {attribute}={observed!r}, not {expected!r}"
                    ),
                    deliverable=deliverable,
                )
    return passed, failed


def check_graph_structure(
    invariant: dict[str, Any],
    artifact: Path,
    violations: list[dict[str, Any]],
    unverifiable: list[dict[str, Any]],
) -> tuple[int, int]:
    """Check entry-node reachability and non-terminal edge-target existence.

    Every node must be reachable over directed edges from the declared entry
    node. Every edge target must be a node unless it is a declared terminal
    node. Multiple inbound paths to a terminal node are legitimate and are
    never flagged.
    """
    invariant_id = str(invariant.get("id"))
    document = load_json_document(artifact)
    objects_path = invariant.get("objects_path")
    graph = resolve_path(document, str(objects_path)) if objects_path else document
    if graph is MISSING or not isinstance(graph, dict):
        unverifiable.append(
            {
                "invariant_id": invariant_id,
                "reason": f"graph object at {objects_path!r} is missing or not an object",
            }
        )
        return 0, 0

    nodes_path = str(invariant.get("nodes_path") or "nodes")
    edges_path = str(invariant.get("edges_path") or "edges")
    nodes = resolve_path(graph, nodes_path)
    edges = resolve_path(graph, edges_path)
    if not isinstance(nodes, list) or not nodes:
        unverifiable.append(
            {
                "invariant_id": invariant_id,
                "reason": f"graph node collection at {nodes_path!r} is missing or not a non-empty array",
            }
        )
        return 0, 0
    if not isinstance(edges, list):
        unverifiable.append(
            {
                "invariant_id": invariant_id,
                "reason": f"graph edge collection at {edges_path!r} is missing or not an array",
            }
        )
        return 0, 0

    node_id_field = str(invariant.get("node_id_field") or "id")
    source_field = str(invariant.get("edge_source_field") or "source")
    target_field = str(invariant.get("edge_target_field") or "target")

    node_ids: dict[str, Any] = {}
    for index, node in enumerate(nodes):
        node_id = resolve_path(node, node_id_field) if isinstance(node, dict) else MISSING
        if node_id is MISSING or node_id is None or isinstance(node_id, (list, dict)):
            unverifiable.append(
                {
                    "invariant_id": invariant_id,
                    "reason": f"node[{index}] does not expose a scalar {node_id_field!r} id",
                }
            )
            return 0, 0
        node_ids[str(node_id)] = node_id

    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            unverifiable.append(
                {
                    "invariant_id": invariant_id,
                    "reason": f"edge[{index}] is not an object",
                }
            )
            return 0, 0
        source = resolve_path(edge, source_field)
        target = resolve_path(edge, target_field)
        if source is MISSING or source is None or isinstance(source, (list, dict)) \
                or target is MISSING or target is None or isinstance(target, (list, dict)):
            unverifiable.append(
                {
                    "invariant_id": invariant_id,
                    "reason": f"edge[{index}] does not expose scalar {source_field!r} and {target_field!r} endpoints",
                }
            )
            return 0, 0

    entry = invariant.get("entry_node")
    entry_key = str(entry)
    terminal_keys = {str(item) for item in invariant.get("terminal_nodes") or []}
    passed = failed = 0

    if entry_key not in node_ids:
        failed += 1
        add_violation(
            violations,
            invariant,
            locator=entry_key,
            field=node_id_field,
            observed=entry,
            expected=f"declared entry node {entry!r} present in {nodes_path!r}",
            diagnosis=f"declared entry node {entry!r} is not a node, so reachability cannot start",
        )
        return passed, failed

    adjacency: dict[str, list[str]] = {key: [] for key in node_ids}
    for edge in edges:
        source = resolve_path(edge, source_field)
        target = resolve_path(edge, target_field)
        source_key = str(source)
        target_key = str(target)
        if target_key not in node_ids and target_key not in terminal_keys:
            failed += 1
            add_violation(
                violations,
                invariant,
                locator=source_key,
                field=target_field,
                observed=target,
                expected="edge target exists as a node or is a declared terminal node",
                diagnosis=(
                    f"edge from {source!r} targets {target!r}, which is neither a node "
                    f"nor a declared terminal node {sorted(terminal_keys)}"
                ),
            )
        else:
            passed += 1
        if source_key in adjacency:
            adjacency[source_key].append(target_key)

    reachable = {entry_key}
    pending = [entry_key]
    while pending:
        current = pending.pop()
        for following in adjacency.get(current, []):
            if following not in reachable:
                reachable.add(following)
                pending.append(following)

    for node_key, node_id in node_ids.items():
        if node_key in reachable:
            passed += 1
        else:
            failed += 1
            add_violation(
                violations,
                invariant,
                locator=str(node_id),
                field="node",
                observed=node_id,
                expected=f"reachable from declared entry node {entry!r}",
                diagnosis=f"node {node_id!r} is unreachable from declared entry node {entry!r}",
            )
    return passed, failed


def _geometry_vector(value: Any, default: list[float]) -> list[float]:
    if value is None:
        return list(default)
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("expected a three-number vector")
    return [float(item) for item in value]


def _geometry_scale_rotate_translate(
    vertices: list[list[float]],
    scale: list[float],
    rotation_deg: list[float],
    translation: list[float],
) -> list[list[float]]:
    rx, ry, rz = [math.radians(value) for value in rotation_deg]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    # Rz * Ry * Rx, applied after per-axis scale and before translation.
    transform = [
        [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
        [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
        [-sy, cy * sx, cy * cx],
    ]
    moved: list[list[float]] = []
    for vertex in vertices:
        scaled = [vertex[0] * scale[0], vertex[1] * scale[1], vertex[2] * scale[2]]
        moved.append(
            [
                sum(transform[row][column] * scaled[column] for column in range(3)) + translation[row]
                for row in range(3)
            ]
        )
    return moved


def _geometry_build_primitive(primitive: dict[str, Any]) -> tuple[list[list[float]], list[list[int]]]:
    kind = primitive.get("type")
    if kind == "box":
        sx, sy, sz = _geometry_vector(primitive.get("size") or primitive.get("dimensions"), [1.0, 1.0, 1.0])
        x, y, z = sx / 2.0, sy / 2.0, sz / 2.0
        vertices = [
            [-x, -y, -z], [x, -y, -z], [x, y, -z], [-x, y, -z],
            [-x, -y, z], [x, -y, z], [x, y, z], [-x, y, z],
        ]
        faces = [
            [4, 5, 6], [4, 6, 7], [1, 0, 3], [1, 3, 2],
            [0, 4, 7], [0, 7, 3], [5, 1, 2], [5, 2, 6],
            [3, 7, 6], [3, 6, 2], [0, 1, 5], [0, 5, 4],
        ]
    elif kind == "sphere":
        radius = float(primitive.get("radius", 1.0))
        segments = int(primitive.get("segments", 16))
        rings = int(primitive.get("rings", 8))
        if radius <= 0 or segments < 3 or rings < 2:
            raise ValueError("sphere needs positive radius, at least 3 segments, and at least 2 rings")
        vertices = []
        for ring in range(rings + 1):
            theta = math.pi * ring / rings
            ring_radius = radius * math.sin(theta)
            height = radius * math.cos(theta)
            for segment in range(segments):
                phi = 2.0 * math.pi * segment / segments
                vertices.append([ring_radius * math.cos(phi), height, ring_radius * math.sin(phi)])
        faces = []
        for ring in range(rings):
            for segment in range(segments):
                following = (segment + 1) % segments
                lower = ring * segments + segment
                lower_next = ring * segments + following
                upper = (ring + 1) * segments + segment
                upper_next = (ring + 1) * segments + following
                if ring != 0:
                    faces.append([lower, lower_next, upper_next])
                if ring != rings - 1:
                    faces.append([lower, upper_next, upper])
    elif kind == "cylinder":
        radius = float(primitive.get("radius", 1.0))
        height = float(primitive.get("height", 1.0))
        segments = int(primitive.get("segments", 16))
        if radius <= 0 or height <= 0 or segments < 3:
            raise ValueError("cylinder needs positive radius and height and at least 3 segments")
        half = height / 2.0
        vertices = []
        for level in (-half, half):
            for segment in range(segments):
                phi = 2.0 * math.pi * segment / segments
                vertices.append([radius * math.cos(phi), level, radius * math.sin(phi)])
        bottom_center = len(vertices)
        vertices.append([0.0, -half, 0.0])
        top_center = len(vertices)
        vertices.append([0.0, half, 0.0])
        faces = []
        for segment in range(segments):
            following = (segment + 1) % segments
            bottom, bottom_next = segment, following
            top, top_next = segments + segment, segments + following
            faces.append([bottom, bottom_next, top_next])
            faces.append([bottom, top_next, top])
            faces.append([bottom_center, bottom_next, bottom])
            faces.append([top_center, top, top_next])
    elif kind == "plane":
        width = float(primitive.get("width", 1.0))
        depth = float(primitive.get("depth", 1.0))
        if width <= 0 or depth <= 0:
            raise ValueError("plane needs positive width and depth")
        x, z = width / 2.0, depth / 2.0
        vertices = [[-x, 0.0, -z], [x, 0.0, -z], [x, 0.0, z], [-x, 0.0, z]]
        faces = [[0, 1, 2], [0, 2, 3]]
    else:
        raise ValueError(f"unsupported source primitive type {kind!r}")

    scale = _geometry_vector(primitive.get("scale"), [1.0, 1.0, 1.0])
    rotation = _geometry_vector(primitive.get("rotation_euler_deg"), [0.0, 0.0, 0.0])
    position = _geometry_vector(primitive.get("position"), [0.0, 0.0, 0.0])
    return _geometry_scale_rotate_translate(vertices, scale, rotation, position), faces


def _geometry_source_primitives(
    invariant: dict[str, Any], base_dir: Path
) -> tuple[list[dict[str, Any]] | None, str | None, str | None]:
    source = invariant.get("source") or {}
    inline = source.get("primitives")
    if isinstance(inline, list) and inline:
        return inline, "inline source primitives", None
    scene_path = source.get("scene_path")
    if not isinstance(scene_path, str) or not scene_path.strip():
        return None, None, "geometry invariant has no source scene or source primitives"
    path = Path(scene_path)
    if not path.is_absolute():
        path = base_dir / path
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, None, f"source scene {scene_path!r} cannot be read: {exc}"
    primitives = document.get("primitives") if isinstance(document, dict) else None
    if not isinstance(primitives, list) or not primitives:
        return None, None, f"source scene {scene_path!r} exposes no primitive list"
    return primitives, scene_path, None


def _geometry_triangulate(polygon: list[int]) -> list[list[int]]:
    if len(polygon) < 3:
        return []
    return [[polygon[0], polygon[index], polygon[index + 1]] for index in range(1, len(polygon) - 1)]


def _geometry_parse_obj(path: Path) -> list[dict[str, Any]]:
    vertices: list[list[float]] = []
    normal_declarations = 0
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    current: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        tag = parts[0]
        if tag == "v" and len(parts) >= 4:
            vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif tag == "vn":
            normal_declarations += 1
        elif tag in {"o", "g"}:
            name = " ".join(parts[1:]).strip() or path.stem
            if name not in groups:
                groups[name] = {"faces": [], "normal_indices": set()}
                order.append(name)
            current = name
        elif tag == "f":
            if current is None:
                current = path.stem
                groups[current] = {"faces": [], "normal_indices": set()}
                order.append(current)
            polygon: list[int] = []
            for token in parts[1:]:
                pieces = token.split("/")
                if not pieces[0]:
                    continue
                index = int(pieces[0])
                polygon.append(index - 1 if index > 0 else len(vertices) + index)
                if len(pieces) >= 3 and pieces[2]:
                    groups[current]["normal_indices"].add(int(pieces[2]))
            groups[current]["faces"].extend(_geometry_triangulate(polygon))

    meshes = []
    for name in order:
        group = groups[name]
        meshes.append(
            {
                "name": name,
                "vertices": [list(vertex) for vertex in vertices],
                "faces": group["faces"],
                "normals": len(group["normal_indices"]) or normal_declarations,
            }
        )
    return meshes


def _geometry_parse_json_mesh_file(path: Path) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(document, dict) and isinstance(document.get("meshes"), list):
        entries = document["meshes"]
    elif isinstance(document, dict) and "vertices" in document and "faces" in document:
        entries = [document]
    else:
        raise ArtifactError("mesh JSON must expose a meshes array or a single vertices/faces object")
    meshes = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ArtifactError(f"mesh[{index}] is not an object")
        raw_vertices = entry.get("vertices")
        if not isinstance(raw_vertices, list) or not raw_vertices:
            raise ArtifactError(f"mesh[{index}] has no vertices array")
        vertices = []
        for vertex in raw_vertices:
            vertices.append(_geometry_vector(vertex, [0.0, 0.0, 0.0]))
        raw_faces = entry.get("faces")
        if not isinstance(raw_faces, list):
            raise ArtifactError(f"mesh[{index}] has no faces array")
        faces: list[list[int]] = []
        normal_indices: set[int] = set()
        for face in raw_faces:
            if not isinstance(face, list) or not face:
                continue
            polygon = []
            for token in face:
                if isinstance(token, list):
                    token = token[0] if token else None
                if token is None:
                    continue
                polygon.append(int(token))
            faces.extend(_geometry_triangulate(polygon))
            if len(face) >= 3 and isinstance(face[2], int):
                normal_indices.add(face[2])
        normals = entry.get("normals")
        normal_count = len(normals) if isinstance(normals, list) else int(entry.get("normal_count", 0) or 0)
        meshes.append(
            {
                "name": str(entry.get("name") or f"mesh[{index}]"),
                "vertices": vertices,
                "faces": faces,
                "normals": len(normal_indices) or normal_count,
            }
        )
    return meshes


def _geometry_load_meshes(path: Path, fmt: str) -> list[dict[str, Any]]:
    chosen = fmt
    if chosen == "auto":
        chosen = "json" if path.suffix.lower() == ".json" else "obj"
    if chosen == "json":
        return _geometry_parse_json_mesh_file(path)
    return _geometry_parse_obj(path)


def _geometry_apply_unit(vertices: list[list[float]], unit: dict[str, Any]) -> list[list[float]]:
    factor = float(unit.get("factor", 1.0))
    offset = float(unit.get("offset", 0.0))
    return [[component * factor + offset for component in vertex] for vertex in vertices]


def _geometry_apply_frame(vertices: list[list[float]], frame: Any) -> list[list[float]]:
    if not frame:
        return vertices
    if isinstance(frame, dict) and "matrix" in frame:
        frame = frame.get("matrix")
    elif isinstance(frame, dict):
        scale = _geometry_vector(frame.get("scale"), [1.0, 1.0, 1.0])
        rotation = _geometry_vector(frame.get("rotation_euler_deg"), [0.0, 0.0, 0.0])
        translation = _geometry_vector(frame.get("translation"), [0.0, 0.0, 0.0])
        return _geometry_scale_rotate_translate(vertices, scale, rotation, translation)
    matrix = frame
    if not isinstance(matrix, list) or len(matrix) not in {3, 4}:
        raise ValueError("frame_transform matrix must have three or four rows")
    rows = matrix[:3]
    if any(not isinstance(row, list) or len(row) not in {3, 4} for row in rows):
        raise ValueError("each frame_transform row must have three or four columns")
    moved = []
    for vertex in vertices:
        source = [vertex[0], vertex[1], vertex[2], 1.0]
        moved.append(
            [
                sum(float(rows[row][column]) * source[column] for column in range(3))
                + (float(rows[row][3]) if len(rows[row]) == 4 else 0.0)
                for row in range(3)
            ]
        )
    return moved


def _geometry_face_is_degenerate(vertices: list[list[float]], face: list[int]) -> bool:
    if len(set(face)) < 3:
        return True
    try:
        a, b, c = (vertices[index] for index in face)
    except IndexError:
        return True
    ab = [b[index] - a[index] for index in range(3)]
    ac = [c[index] - a[index] for index in range(3)]
    cross = [
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    ]
    return 0.5 * math.sqrt(sum(component * component for component in cross)) <= 1e-12


def _geometry_finalize(mesh: dict[str, Any], unit: dict[str, Any], frame: Any) -> dict[str, Any]:
    vertices = _geometry_apply_unit(mesh["vertices"], unit or {})
    vertices = _geometry_apply_frame(vertices, frame)
    valid_faces = []
    degenerate = 0
    for face in mesh["faces"]:
        if _geometry_face_is_degenerate(vertices, face):
            degenerate += 1
        else:
            valid_faces.append(face)
    return {
        "name": mesh["name"],
        "vertices": vertices,
        "faces": valid_faces,
        "normals": mesh.get("normals", 0),
        "degenerate_faces": degenerate,
    }


def _geometry_triangle_area(a: list[float], b: list[float], c: list[float]) -> float:
    ab = [b[index] - a[index] for index in range(3)]
    ac = [c[index] - a[index] for index in range(3)]
    cross = [
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    ]
    return 0.5 * math.sqrt(sum(component * component for component in cross))


def _geometry_surface_samples(mesh: dict[str, Any], budget: int) -> list[list[float]]:
    vertices = mesh["vertices"]
    triangles = []
    total_area = 0.0
    for face in mesh["faces"]:
        try:
            a, b, c = (vertices[index] for index in face)
        except IndexError:
            continue
        area = _geometry_triangle_area(a, b, c)
        if area > 1e-12:
            triangles.append((a, b, c, area))
            total_area += area
    if not triangles or total_area <= 0:
        return []
    samples: list[list[float]] = []
    for a, b, c, area in triangles:
        samples.append(a)
        samples.append(b)
        samples.append(c)
        samples.append([(a[i] + b[i]) / 2.0 for i in range(3)])
        samples.append([(b[i] + c[i]) / 2.0 for i in range(3)])
        samples.append([(c[i] + a[i]) / 2.0 for i in range(3)])
        samples.append([(a[i] + b[i] + c[i]) / 3.0 for i in range(3)])
        count = max(1, int(round(budget * area / total_area)))
        for index in range(count):
            u = ((index + 0.5) * 0.6180339887498949) % 1.0
            v = ((index + 0.5) * 0.7548776662466927) % 1.0
            if u + v > 1.0:
                u, v = 1.0 - u, 1.0 - v
            samples.append(
                [
                    a[0] + u * (b[0] - a[0]) + v * (c[0] - a[0]),
                    a[1] + u * (b[1] - a[1]) + v * (c[1] - a[1]),
                    a[2] + u * (b[2] - a[2]) + v * (c[2] - a[2]),
                ]
            )
    return samples


def _geometry_point_triangle_distance_sq(
    point: list[float], a: list[float], b: list[float], c: list[float]
) -> float:
    ab = [b[index] - a[index] for index in range(3)]
    ac = [c[index] - a[index] for index in range(3)]
    ap = [point[index] - a[index] for index in range(3)]
    d1 = sum(ab[index] * ap[index] for index in range(3))
    d2 = sum(ac[index] * ap[index] for index in range(3))
    if d1 <= 0.0 and d2 <= 0.0:
        closest = a
    else:
        bp = [point[index] - b[index] for index in range(3)]
        d3 = sum(ab[index] * bp[index] for index in range(3))
        d4 = sum(ac[index] * bp[index] for index in range(3))
        if d3 >= 0.0 and d4 <= d3:
            closest = b
        else:
            vc = d1 * d4 - d3 * d2
            if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
                denominator = d1 - d3
                v = d1 / denominator if denominator else 0.0
                closest = [a[index] + v * ab[index] for index in range(3)]
            else:
                cp = [point[index] - c[index] for index in range(3)]
                d5 = sum(ab[index] * cp[index] for index in range(3))
                d6 = sum(ac[index] * cp[index] for index in range(3))
                if d6 >= 0.0 and d5 <= d6:
                    closest = c
                else:
                    vb = d5 * d2 - d1 * d6
                    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
                        denominator = d2 - d6
                        w = d2 / denominator if denominator else 0.0
                        closest = [a[index] + w * ac[index] for index in range(3)]
                    else:
                        va = d3 * d6 - d5 * d4
                        if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
                            denominator = (d4 - d3) + (d5 - d6)
                            w = (d4 - d3) / denominator if denominator else 0.0
                            closest = [b[index] + w * (c[index] - b[index]) for index in range(3)]
                        else:
                            denominator = va + vb + vc
                            if denominator == 0.0:
                                closest = a
                            else:
                                v = vb / denominator
                                w = vc / denominator
                                closest = [
                                    a[index] + ab[index] * v + ac[index] * w for index in range(3)
                                ]
    delta = [point[index] - closest[index] for index in range(3)]
    return sum(component * component for component in delta)


def _geometry_nearest_distances(
    points: list[list[float]], mesh: dict[str, Any]
) -> list[float]:
    vertices = mesh["vertices"]
    triangles = []
    for face in mesh["faces"]:
        try:
            triangles.append(tuple(vertices[index] for index in face))
        except IndexError:
            continue
    if not points or not triangles:
        return []
    distances = []
    for point in points:
        best = min(
            _geometry_point_triangle_distance_sq(point, a, b, c) for a, b, c in triangles
        )
        distances.append(math.sqrt(best))
    return distances


def _geometry_compare(
    submitted: dict[str, Any], expected: dict[str, Any], metric: str, sample_count: int
) -> dict[str, float] | None:
    submitted_samples = _geometry_surface_samples(submitted, sample_count)
    expected_samples = _geometry_surface_samples(expected, sample_count)
    forward = _geometry_nearest_distances(submitted_samples, expected)
    reverse = _geometry_nearest_distances(expected_samples, submitted)
    if not forward or not reverse:
        return None
    maximum = max(max(forward), max(reverse))
    chamfer = (sum(forward) / len(forward) + sum(reverse) / len(reverse)) / 2.0
    return {"max_nearest": maximum, "chamfer": chamfer, "metric_value": maximum if metric == "max_nearest" else chamfer}


def _geometry_counts(mesh: dict[str, Any]) -> dict[str, int]:
    return {
        "vertices": len(mesh["vertices"]),
        "faces": len(mesh["faces"]),
        "normals": int(mesh.get("normals", 0)),
        "degenerate_faces": int(mesh.get("degenerate_faces", 0)),
    }


def _geometry_mesh_by_name(path: Path, fmt: str, name: str | None) -> dict[str, Any]:
    meshes = _geometry_load_meshes(path, fmt)
    if not meshes:
        raise ValueError("no mesh objects")
    for mesh in meshes:
        if name and str(mesh.get("name")) == name:
            return mesh
    if len(meshes) == 1:
        return meshes[0]
    raise ValueError(f"no mesh named {name!r}")


def _geometry_export_path_checks(
    invariant: dict[str, Any], base_dir: Path
) -> list[dict[str, Any]]:
    """Record export-path agreement as structural-only evidence.

    Matching counts, a near-zero triangle delta, or link meshes that mirror
    part meshes describe the exporter's own consistency. They are reported for
    diagnosis but never counted as a geometry_conformance pass.
    """
    declared = invariant.get("export_path_checks")
    if not isinstance(declared, dict):
        return []
    results: list[dict[str, Any]] = []
    fmt = str(invariant.get("format") or "auto")
    unit = invariant.get("unit_conversion") or {}
    frame = invariant.get("frame_transform")
    sample_count = min(int(invariant.get("sample_count", 512)), 8192)
    for pair in declared.get("pairs") or []:
        part_text = str(pair.get("part_path"))
        link_text = str(pair.get("link_path"))
        entry: dict[str, Any] = {
            "part_path": part_text,
            "link_path": link_text,
            "part_mesh": pair.get("part_mesh"),
            "link_mesh": pair.get("link_mesh"),
            "status": "structural_only",
            "limitation": (
                "export-path self-consistency is structural evidence only; it cannot "
                "satisfy geometry_conformance without an independent source-scene surface"
            ),
        }
        try:
            part_path = Path(part_text)
            if not part_path.is_absolute():
                part_path = base_dir / part_path
            link_path = Path(link_text)
            if not link_path.is_absolute():
                link_path = base_dir / link_path
            part = _geometry_mesh_by_name(part_path, fmt, pair.get("part_mesh"))
            link = _geometry_mesh_by_name(link_path, fmt, pair.get("link_mesh"))
            part = _geometry_finalize(part, unit, frame)
            link = _geometry_finalize(link, unit, frame)
        except (ArtifactError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            entry["reason"] = f"export-path pair cannot be compared: {exc}"
            results.append(entry)
            continue
        part_counts = _geometry_counts(part)
        link_counts = _geometry_counts(link)
        entry["part_counts"] = part_counts
        entry["link_counts"] = link_counts
        entry["vertex_counts_match"] = part_counts["vertices"] == link_counts["vertices"]
        entry["face_counts_match"] = part_counts["faces"] == link_counts["faces"]
        comparison = _geometry_compare(link, part, "max_nearest", sample_count)
        if comparison is None:
            entry["triangle_delta"] = None
            entry["reason"] = "export-path pair has no measurable surface"
        else:
            entry["triangle_delta"] = comparison["max_nearest"]
            entry["triangle_delta_within_zero"] = comparison["max_nearest"] <= 1e-9
        results.append(entry)
    return results


def _geometry_producer_path_reason(
    source_path: str,
    deliverable: str,
    invariant: dict[str, Any],
    base_dir: Path,
) -> str | None:
    """Reject producer-owned paths that merely present themselves as a scene.

    A manifest, exporter intermediate, or mesh file can carry a primitive list
    and a matching provenance string while still being producer output. The
    independence gate cannot establish a separate source from such a path, so
    it fails closed instead of trusting a self-declared source_kind.
    """
    expected_path = Path(source_path)
    if not expected_path.is_absolute():
        expected_path = base_dir / expected_path
    resolved = expected_path.resolve()
    try:
        relative = resolved.relative_to(base_dir.resolve()).as_posix().casefold()
    except ValueError:
        relative = expected_path.name.casefold()
    if GEOMETRY_PRODUCER_PATH_TOKEN.search(relative):
        return (
            f"provenance source_scene_path {source_path!r} names a manifest, export, "
            "intermediate, or producer-owned path, so expected geometry cannot be "
            "shown to be independent of the submitted export"
        )
    if expected_path.suffix.casefold() in GEOMETRY_MESH_SUFFIXES:
        return (
            f"provenance source_scene_path {source_path!r} is a mesh or export format, "
            "not a task source scene, so expected geometry is producer-owned"
        )
    checks = invariant.get("export_path_checks")
    pairs = checks.get("pairs") if isinstance(checks, dict) else None
    for pair in pairs if isinstance(pairs, list) else []:
        if not isinstance(pair, dict):
            continue
        for key in ("part_path", "link_path"):
            value = pair.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = base_dir / candidate
            if candidate.resolve() == resolved:
                return (
                    f"provenance source_scene_path {source_path!r} is one of the "
                    "declared part/link exports, so the expected surface is loaded "
                    "from the submitted export path"
                )
    return None


def geometry_provenance(
    invariant: dict[str, Any],
    mesh_name: str,
    deliverable: str,
    base_dir: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve and gate one expected mesh's source and frame provenance.

    A comparison may start only when the expected surface records where it came
    from and in which frame it was reconstructed. The submitted export, its
    manifest, and any producer-owned path are rejected as expected sources.
    """
    provenance = invariant.get("provenance")
    if not isinstance(provenance, dict) or not provenance:
        return None, (
            f"mesh {mesh_name!r} has no expected-surface provenance; record "
            "source_scene_path, frame, units, and derivation before comparing geometry"
        )
    overrides = invariant.get("mesh_provenance") or {}
    override = overrides.get(mesh_name) if isinstance(overrides, dict) else None
    if override is not None and not isinstance(override, dict):
        return None, f"mesh_provenance[{mesh_name!r}] must be an object"
    merged = dict(provenance)
    if override:
        merged.update(override)

    source_path = merged.get("source_scene_path")
    if not isinstance(source_path, str) or not source_path.strip():
        return None, f"mesh {mesh_name!r} provenance has no source_scene_path"
    frame = merged.get("frame")
    if frame not in GEOMETRY_FRAMES:
        return None, (
            f"mesh {mesh_name!r} provenance frame must be scene_root or part_local, "
            f"not {frame!r}"
        )
    units = merged.get("units")
    if not isinstance(units, str) or not units.strip():
        return None, f"mesh {mesh_name!r} provenance has no units"
    derivation = merged.get("derivation")
    if not isinstance(derivation, str) or not derivation.strip():
        return None, f"mesh {mesh_name!r} provenance has no derivation step"
    if merged.get("source_kind") in GEOMETRY_REJECTED_SOURCE_KINDS:
        return None, (
            f"mesh {mesh_name!r} expected surface comes from the producer's export "
            "or manifest instead of the task source scene"
        )
    rejected = _geometry_producer_path_reason(source_path, deliverable, invariant, base_dir)
    if rejected is not None:
        return None, f"mesh {mesh_name!r} {rejected}"

    self_referential = geometry_independence_reason(merged)
    if self_referential is not None:
        return None, f"mesh {mesh_name!r} {self_referential}"

    source = invariant.get("source") if isinstance(invariant.get("source"), dict) else {}
    declared_scene = source.get("scene_path")
    if declared_scene is not None and str(declared_scene) != str(source_path):
        return None, (
            f"mesh {mesh_name!r} provenance source_scene_path {source_path!r} "
            f"does not match the declared source scene {declared_scene!r}"
        )
    declared_units = source.get("units")
    if declared_units is not None and str(declared_units) != str(units):
        return None, (
            f"mesh {mesh_name!r} provenance units {units!r} do not match the "
            f"declared source units {declared_units!r}"
        )

    deliverable_path = Path(deliverable)
    if not deliverable_path.is_absolute():
        deliverable_path = base_dir / deliverable_path
    expected_path = Path(source_path)
    if not expected_path.is_absolute():
        expected_path = base_dir / expected_path
    if expected_path.resolve() == deliverable_path.resolve():
        return None, (
            f"mesh {mesh_name!r} expected surface is loaded from the submitted export "
            "itself, so independence cannot be established"
        )

    record = {
        "source_scene_path": source_path,
        "frame": frame,
        "units": units,
        "derivation": derivation,
    }
    for key in ("reader", "transform_path"):
        value = merged.get(key)
        if isinstance(value, str) and value.strip():
            record[key] = value
    return record, None


def _geometry_centroid(mesh: dict[str, Any], budget: int) -> list[float] | None:
    samples = _geometry_surface_samples(mesh, budget)
    if not samples:
        return None
    count = float(len(samples))
    return [
        sum(point[axis] for point in samples) / count
        for axis in range(3)
    ]


def _geometry_shift(mesh: dict[str, Any], delta: list[float]) -> dict[str, Any]:
    shifted = dict(mesh)
    shifted["vertices"] = [
        [vertex[axis] - delta[axis] for axis in range(3)]
        for vertex in mesh.get("vertices") or []
    ]
    return shifted


def _geometry_classify_displacement(
    submitted: dict[str, Any],
    expected: dict[str, Any],
    metric: str,
    tolerance: float,
    sample_count: int,
) -> tuple[str, float | None]:
    """Separate a rigid frame/placement offset from a shape difference.

    Center both surfaces on their own sample centroids and compare again. A
    displaced copy of the right shape becomes equivalent after centering, while
    a genuinely different shape remains outside tolerance.
    """
    submitted_centroid = _geometry_centroid(submitted, sample_count)
    expected_centroid = _geometry_centroid(expected, sample_count)
    if submitted_centroid is None or expected_centroid is None:
        return "shape", None
    centered_submitted = _geometry_shift(submitted, submitted_centroid)
    centered_expected = _geometry_shift(expected, expected_centroid)
    centered = _geometry_compare(centered_submitted, centered_expected, metric, sample_count)
    if centered is None:
        return "shape", None
    # Use the symmetric mean (Chamfer) after centering so a deterministic rigid
    # offset is not misread as a shape difference by sampling density alone.
    centered_delta = centered["chamfer"]
    if centered_delta <= tolerance + 1e-9:
        return "frame_or_placement", centered_delta
    return "shape", centered_delta


def _check_geometry(
    invariant: dict[str, Any],
    violations: list[dict[str, Any]],
    unverifiable: list[dict[str, Any]],
    base_dir: Path,
) -> tuple[int, int, list[dict[str, Any]], list[dict[str, Any]]]:
    """Compare exported meshes with independently reconstructed source geometry."""
    invariant_id = str(invariant.get("id"))
    deliverable = str(invariant.get("deliverable_path") or invariant.get("mesh_path"))
    path = Path(deliverable)
    if not path.is_absolute():
        path = base_dir / path
    consistency = _geometry_export_path_checks(invariant, base_dir)
    entries: list[dict[str, Any]] = []
    if not path.is_file():
        add_violation(
            violations,
            invariant,
            locator=deliverable,
            field="deliverable_path",
            observed="absent",
            expected=f"exported mesh deliverable present at declared path {deliverable!r}",
            diagnosis=f"declared mesh deliverable {deliverable!r} does not exist",
            deliverable=deliverable,
        )
        return 0, 1, entries, consistency

    try:
        meshes = _geometry_load_meshes(path, str(invariant.get("format") or "auto"))
    except (ArtifactError, OSError, ValueError, json.JSONDecodeError) as exc:
        add_violation(
            violations,
            invariant,
            locator=deliverable,
            field="deliverable_path",
            observed="unparseable",
            expected="a parseable OBJ or JSON mesh with vertices and faces",
            diagnosis=f"mesh deliverable {deliverable!r} cannot be parsed: {exc}",
            deliverable=deliverable,
        )
        return 0, 1, entries, consistency

    if not meshes:
        add_violation(
            violations,
            invariant,
            locator=deliverable,
            field="meshes",
            observed="no mesh objects",
            expected="at least one named mesh in the exported deliverable",
            diagnosis=f"mesh deliverable {deliverable!r} exposes no mesh objects",
            deliverable=deliverable,
        )
        return 0, 1, entries, consistency

    if invariant.get("provenance") is None:
        reason = (
            "expected-surface provenance is absent; record source_scene_path, frame, "
            "units, and derivation for every expected mesh"
        )
        unverifiable.append({"invariant_id": invariant_id, "reason": reason})
        for mesh in meshes:
            entries.append(
                {
                    "deliverable": deliverable,
                    "mesh": mesh.get("name"),
                    "source_geometry": None,
                    "metric": str(invariant.get("metric") or "max_nearest"),
                    "tolerance": float(geometry_acceptance_tolerance(invariant) or 0),
                    "observed_delta": None,
                    "counts": _geometry_counts(mesh),
                    "status": "unverifiable",
                    "provenance": None,
                }
            )
        return 0, 0, entries, consistency

    primitives, source_label, reason = _geometry_source_primitives(invariant, base_dir)
    if reason is not None or not primitives:
        unverifiable.append({"invariant_id": invariant_id, "reason": reason or "source geometry is unavailable"})
        for mesh in meshes:
            entries.append(
                {
                    "deliverable": deliverable,
                    "mesh": mesh.get("name"),
                    "source_geometry": None,
                    "metric": str(invariant.get("metric") or "max_nearest"),
                    "tolerance": float(geometry_acceptance_tolerance(invariant) or 0),
                    "observed_delta": None,
                    "counts": _geometry_counts(mesh),
                    "status": "unverifiable",
                }
            )
        return 0, 0, entries, consistency

    primitive_by_id: dict[str, dict[str, Any]] = {}
    source_types: dict[str, str] = {}
    for index, primitive in enumerate(primitives):
        if not isinstance(primitive, dict):
            unverifiable.append(
                {
                    "invariant_id": invariant_id,
                    "reason": f"source primitive[{index}] is not an object; source geometry cannot be reconstructed",
                }
            )
            continue
        primitive_id = str(primitive.get("id") or f"primitive[{index}]")
        primitive_by_id[primitive_id] = primitive
        source_types[primitive_id] = str(primitive.get("type"))

    unit = invariant.get("unit_conversion") or {}
    frame = invariant.get("frame_transform")
    try:
        normalized = [_geometry_finalize(mesh, unit, frame) for mesh in meshes]
    except (ValueError, TypeError) as exc:
        unverifiable.append(
            {"invariant_id": invariant_id, "reason": f"mesh frame normalization cannot be applied: {exc}"}
        )
        return 0, 0, entries, consistency

    mapping = invariant.get("mesh_to_source")
    if not isinstance(mapping, dict):
        mapping = {}
    metric = str(invariant.get("metric") or "max_nearest")
    tolerance = float(geometry_acceptance_tolerance(invariant) or 0)
    sample_count = min(int(invariant.get("sample_count", 512)), 8192)
    passed = failed = 0

    for mesh in normalized:
        mesh_name = str(mesh.get("name"))
        provenance, provenance_reason = geometry_provenance(
            invariant, mesh_name, deliverable, base_dir
        )
        if provenance_reason is not None or provenance is None:
            unverifiable.append(
                {
                    "invariant_id": invariant_id,
                    "reason": provenance_reason or "expected-surface provenance is unverifiable",
                }
            )
            entries.append(
                {
                    "deliverable": deliverable,
                    "mesh": mesh_name,
                    "source_geometry": None,
                    "metric": metric,
                    "tolerance": tolerance,
                    "observed_delta": None,
                    "counts": _geometry_counts(mesh),
                    "status": "unverifiable",
                    "attribution": "missing_oracle_independence",
                    "provenance": None,
                }
            )
            continue

        source_ids = mapping.get(mesh_name)
        if source_ids is None and len(primitives) == 1:
            source_ids = [str(primitives[0].get("id") or "primitive[0]")]
        if isinstance(source_ids, str):
            source_ids = [source_ids]
        if not isinstance(source_ids, list) or not source_ids:
            unverifiable.append(
                {
                    "invariant_id": invariant_id,
                    "reason": f"mesh {mesh_name!r} has no mesh_to_source mapping to a source primitive",
                }
            )
            entries.append(
                {
                    "deliverable": deliverable,
                    "mesh": mesh_name,
                    "source_geometry": None,
                    "metric": metric,
                    "tolerance": tolerance,
                    "observed_delta": None,
                    "counts": _geometry_counts(mesh),
                    "status": "unverifiable",
                }
            )
            continue

        missing = [str(source_id) for source_id in source_ids if str(source_id) not in primitive_by_id]
        if missing:
            unverifiable.append(
                {
                    "invariant_id": invariant_id,
                    "reason": f"mesh {mesh_name!r} maps to unknown source primitive(s) {missing}",
                }
            )
            entries.append(
                {
                    "deliverable": deliverable,
                    "mesh": mesh_name,
                    "source_geometry": None,
                    "metric": metric,
                    "tolerance": tolerance,
                    "observed_delta": None,
                    "counts": _geometry_counts(mesh),
                    "status": "unverifiable",
                }
            )
            continue

        expected_vertices: list[list[float]] = []
        expected_faces: list[list[int]] = []
        labels = []
        build_error: str | None = None
        for source_id in source_ids:
            primitive = primitive_by_id[str(source_id)]
            if provenance["frame"] == "part_local":
                primitive = dict(primitive)
                primitive["position"] = [0.0, 0.0, 0.0]
            try:
                vertices, faces = _geometry_build_primitive(primitive)
            except (ValueError, KeyError, TypeError) as exc:
                build_error = (
                    f"source primitive {source_id!r} cannot be reconstructed in "
                    f"{provenance['frame']} frame: {exc}"
                )
                break
            offset = len(expected_vertices)
            expected_vertices.extend([list(vertex) for vertex in vertices])
            expected_faces.extend(
                [[index + offset for index in face] for face in faces]
            )
            labels.append(f"{source_id}:{source_types.get(str(source_id), 'primitive')}")
        if build_error is not None:
            unverifiable.append({"invariant_id": invariant_id, "reason": build_error})
            entries.append(
                {
                    "deliverable": deliverable,
                    "mesh": mesh_name,
                    "source_geometry": None,
                    "metric": metric,
                    "tolerance": tolerance,
                    "observed_delta": None,
                    "counts": _geometry_counts(mesh),
                    "status": "unverifiable",
                    "provenance": provenance,
                }
            )
            continue
        expected = {
            "name": "+".join(str(source_id) for source_id in source_ids),
            "vertices": expected_vertices,
            "faces": expected_faces,
            "normals": 0,
            "degenerate_faces": 0,
        }
        comparison = _geometry_compare(mesh, expected, metric, sample_count)
        if comparison is None:
            unverifiable.append(
                {
                    "invariant_id": invariant_id,
                    "reason": f"mesh {mesh_name!r} or its source geometry has no measurable surface",
                }
            )
            entries.append(
                {
                    "deliverable": deliverable,
                    "mesh": mesh_name,
                    "source_geometry": ", ".join(labels),
                    "metric": metric,
                    "tolerance": tolerance,
                    "observed_delta": None,
                    "counts": _geometry_counts(mesh),
                    "status": "unverifiable",
                }
            )
            continue

        observed_delta = comparison["metric_value"]
        status = "pass" if observed_delta <= tolerance + 1e-9 else "fail"
        if status == "pass":
            displacement_class, centered_delta = "within_tolerance", 0.0
        else:
            displacement_class, centered_delta = _geometry_classify_displacement(
                mesh, expected, metric, tolerance, sample_count
            )
        entry = {
            "deliverable": deliverable,
            "mesh": mesh_name,
            "source_geometry": ", ".join(labels),
            "metric": metric,
            "tolerance": tolerance,
            "observed_delta": observed_delta,
            "max_nearest": comparison["max_nearest"],
            "chamfer": comparison["chamfer"],
            "displacement_class": displacement_class,
            "attribution": "placement" if displacement_class == "frame_or_placement" else "shape",
            "centered_delta": centered_delta,
            "frame": provenance["frame"],
            "units": provenance["units"],
            "derivation": provenance["derivation"],
            "provenance": provenance,
            "counts": _geometry_counts(mesh),
            "source_counts": _geometry_counts(expected),
            "status": status,
        }
        entries.append(entry)
        if status == "pass":
            passed += 1
        else:
            failed += 1
            add_violation(
                violations,
                invariant,
                locator=mesh_name,
                field="chamfer",
                observed={
                    "deliverable": deliverable,
                    "mesh": mesh_name,
                    "observed_delta": observed_delta,
                    "tolerance": tolerance,
                    "max_nearest": comparison["max_nearest"],
                    "chamfer": comparison["chamfer"],
                    "displacement_class": displacement_class,
                    "centered_delta": centered_delta,
                    "counts": _geometry_counts(mesh),
                },
                expected=(
                    f"chamfer within task-stated tolerance {tolerance:g} of independently "
                    f"reconstructed source geometry {', '.join(labels)} in "
                    f"{provenance['frame']} frame"
                ),
                diagnosis=(
                    f"mesh {mesh_name!r} in {deliverable!r} deviates from independently "
                    f"reconstructed source geometry {labels} by Chamfer "
                    f"{comparison['chamfer']:.6g} and {metric} {observed_delta:.6g}, "
                    f"exceeding the stated tolerance {tolerance:g}; classified as "
                    f"{displacement_class} displacement in {provenance['frame']} frame, "
                    "and structural counts do not prove equivalence"
                ),
                observed_delta=observed_delta,
                deliverable=deliverable,
                extra={
                    "chamfer": comparison["chamfer"],
                    "max_nearest": comparison["max_nearest"],
                    "displacement_class": displacement_class,
                    "attribution": "placement" if displacement_class == "frame_or_placement" else "shape",
                    "centered_delta": centered_delta,
                    "frame": provenance["frame"],
                    "units": provenance["units"],
                    "source_scene_path": provenance["source_scene_path"],
                    "derivation": provenance["derivation"],
                    "artifact_path": str(path),
                },
            )

    return passed, failed, entries, consistency


def check_geometry(
    invariant: dict[str, Any],
    violations: list[dict[str, Any]],
    unverifiable: list[dict[str, Any]],
    base_dir: Path,
) -> tuple[int, int, list[dict[str, Any]], list[dict[str, Any]]]:
    """Annotate per-mesh results with the artifact and source-scene paths."""
    passed, failed, entries, consistency = _check_geometry(
        invariant, violations, unverifiable, base_dir
    )
    deliverable = str(invariant.get("deliverable_path") or invariant.get("mesh_path"))
    artifact_path = Path(deliverable)
    if not artifact_path.is_absolute():
        artifact_path = base_dir / artifact_path
    source = invariant.get("source") or {}
    provenance = invariant.get("provenance") if isinstance(invariant.get("provenance"), dict) else {}
    source_path = provenance.get("source_scene_path")
    source_path = source_path or (source.get("scene_path") if isinstance(source, dict) else None)
    source_path = source_path or "inline source primitives"
    for entry in entries:
        entry.setdefault("artifact_path", str(artifact_path))
        entry.setdefault("source_scene_path", source_path)
        entry.setdefault(
            "evidence",
            "independent_source_reconstruction"
            if entry.get("status") != "unverifiable"
            else "unverifiable",
        )
        if "provenance" not in entry:
            entry["provenance"] = provenance or None
    for record in violations:
        if record.get("invariant_class") == "geometry_conformance":
            record.setdefault("artifact_path", str(artifact_path))
            record.setdefault("source_scene_path", source_path)
            if provenance:
                record.setdefault("frame", provenance.get("frame"))
                record.setdefault("units", provenance.get("units"))
                record.setdefault("derivation", provenance.get("derivation"))
    return passed, failed, entries, consistency


def run(
    artifact: Path, spec_path: Path, fmt: str, artifact_root: Path | None = None
) -> tuple[dict[str, Any], int]:
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return error_report(artifact, None, f"cannot read constraint spec {spec_path}: {exc}"), 2

    if not isinstance(spec, dict) or not isinstance(spec.get("invariants"), list):
        return error_report(artifact, spec, "constraint spec must be an object with an invariants array"), 2

    records_path = spec.get("records_path")
    if not records_path:
        for candidate in spec["invariants"]:
            if not isinstance(candidate, dict) or candidate.get("class") not in {
                "structural",
                "domain_membership",
            }:
                continue
            if candidate.get("objects_path"):
                records_path = candidate["objects_path"]
                spec["records_path"] = records_path
                break

    document_only = not records_path and any(
        isinstance(candidate, dict)
        and candidate.get("class") in {"graph_structure", "companion_artifact", "geometry_conformance"}
        for candidate in spec["invariants"]
    )
    geometry_root = artifact_root if artifact_root is not None else spec_path.parent
    try:
        if document_only and artifact.is_dir():
            records = []
        elif document_only:
            records = [load_json_document(artifact)]
        else:
            records = load_artifact(artifact, records_path, fmt)
    except ArtifactError as exc:
        return error_report(artifact, spec, str(exc)), 2

    violations: list[dict[str, Any]] = []
    unverifiable: list[dict[str, Any]] = []
    invariant_reports: list[dict[str, Any]] = []
    geometry_entries: list[dict[str, Any]] = []
    export_path_checks: list[dict[str, Any]] = []
    has_geometry = any(
        isinstance(candidate, dict) and candidate.get("class") == "geometry_conformance"
        for candidate in spec["invariants"]
    )

    for invariant in spec["invariants"]:
        if not isinstance(invariant, dict):
            unverifiable.append({"invariant_id": None, "reason": "invariant entry is not an object"})
            continue
        invariant_id = str(invariant.get("id") or f"invariant[{len(invariant_reports)}]")
        invariant["id"] = invariant_id
        kind = invariant.get("class")
        reported_unverifiable = len(unverifiable)
        problem = spec_problem(invariant)

        if problem or kind == "unverifiable":
            unverifiable.append({"invariant_id": invariant_id, "reason": problem or "constraint is marked unverifiable"})
            invariant_reports.append(
                {"id": invariant_id, "class": kind, "pass_count": 0, "fail_count": 0, "status": "unverifiable"}
            )
            continue

        if kind == "equality":
            passed, failed = check_equality(invariant, records, violations)
        elif kind == "numeric_range":
            passed, failed = check_numeric_range(invariant, records, violations)
        elif kind == "calibration":
            passed, failed = check_calibration(invariant, records, violations, unverifiable)
        elif kind == "field_encoding":
            passed, failed = check_field_encoding(invariant, records, violations)
        elif kind in {"structural", "domain_membership"}:
            try:
                objects = object_records(invariant, records, artifact, spec)
            except ArtifactError as exc:
                return error_report(artifact, spec, str(exc)), 2
            if kind == "structural":
                passed, failed = check_structural(invariant, objects, violations)
            else:
                passed, failed = check_domain_membership(invariant, objects, violations)
        elif kind == "graph_structure":
            try:
                passed, failed = check_graph_structure(invariant, artifact, violations, unverifiable)
            except ArtifactError as exc:
                return error_report(artifact, spec, str(exc)), 2
        elif kind == "companion_artifact":
            try:
                passed, failed = check_companion_artifact(
                    invariant, artifact, violations, unverifiable, spec_path.parent
                )
            except ArtifactError as exc:
                return error_report(artifact, spec, str(exc)), 2
        elif kind == "geometry_conformance":
            passed, failed, entries, consistency = check_geometry(
                invariant, violations, unverifiable, geometry_root
            )
            geometry_entries.extend(entries)
            export_path_checks.extend(consistency)
        else:
            try:
                passed, failed = check_independent_recompute(
                    invariant, records, violations, spec_path.parent
                )
            except SpecError as exc:
                return error_report(artifact, spec, str(exc)), 2

        new_unverifiable = len(unverifiable) - reported_unverifiable
        status = "fail" if failed or new_unverifiable else "pass"
        invariant_reports.append(
            {
                "id": invariant_id,
                "class": kind,
                "pass_count": passed,
                "fail_count": failed,
                "status": status,
            }
        )

    total_passed = sum(item["pass_count"] for item in invariant_reports)
    total_failed = sum(item["fail_count"] for item in invariant_reports)
    clean = total_failed == 0 and not unverifiable
    report = {
        "status": "clean" if clean else "violations",
        "artifact_path": str(artifact),
        "spec_revision": spec.get("spec_revision"),
        "counts": {
            "records": len(records),
            "invariants": len(invariant_reports),
            "passed": total_passed,
            "violations": total_failed,
            "unverifiable": len(unverifiable),
        },
        "invariants": invariant_reports,
        "violations": violations,
        "unverifiable": unverifiable,
    }
    if has_geometry:
        report["geometry"] = geometry_entries
        report["export_path_checks"] = export_path_checks
    return report, 0 if clean else 1


def error_report(artifact: Path, spec: Any, message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "artifact_path": str(artifact),
        "spec_revision": spec.get("spec_revision") if isinstance(spec, dict) else None,
        "counts": {"records": 0, "invariants": 0, "passed": 0, "violations": 0, "unverifiable": 0},
        "invariants": [],
        "violations": [],
        "unverifiable": [],
        "error": message,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a config-driven conformance preflight over a complete artifact.")
    parser.add_argument(
        "artifact",
        type=Path,
        nargs="?",
        help="Path to the complete JSON or JSONL artifact, or the artifact root with --artifact-root",
    )
    parser.add_argument("--spec", required=True, type=Path, help="Path to the task-derived constraint spec")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        help="Directory containing exported deliverables and the task-derived source scene; "
        "resolves relative deliverable and scene paths independently of the exporter",
    )
    parser.add_argument("--format", choices=("auto", "json", "jsonl"), default="auto", help="Artifact format")
    parser.add_argument("--report", type=Path, help="Optional path to also write the JSON report")
    parser.add_argument("--quiet", action="store_true", help="Suppress the stdout report")
    args = parser.parse_args(list(argv) if argv is not None else None)

    artifact_root = args.artifact_root
    artifact = args.artifact or artifact_root
    if artifact is None:
        parser.error("provide an artifact path or --artifact-root")
    if artifact_root is not None and not artifact_root.is_dir():
        parser.error(f"--artifact-root {artifact_root} is not a directory")

    report, code = run(artifact, args.spec, args.format, artifact_root)
    payload = json.dumps(report, indent=2, sort_keys=False)
    if not args.quiet:
        print(payload)
        counts = report["counts"]
        print(
            f"preflight: {report['status']} | records={counts['records']} "
            f"violations={counts['violations']} unverifiable={counts['unverifiable']} "
            f"exit={code}",
            file=sys.stderr,
        )
    if args.report:
        try:
            args.report.write_text(payload + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"preflight: cannot write report {args.report}: {exc}", file=sys.stderr)
            return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
