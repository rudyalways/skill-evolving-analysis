#!/usr/bin/env python3
"""Deterministic architectural-DXF extraction and plan-view turning-space solver.

The helper consumes one DXF, a semantic layer schema, one or more output JSON
schemas, and plan-view rules.  It emits normalized layer, room, door, fixture,
grab-bar, and bounded turning-space-candidate geometry as one machine-readable
JSON document.  It never writes a partial document: the output is validated
against every supplied schema and then published atomically.

Supported DXF entity types are LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE, and
SPLINE.  An unsupported entity on a semantic layer is a single terminal
failure that names the entity type, layer, handle, and unsupported geometry.

A harness-style task root is extracted with the bundled adapter,
``python3 scripts/extract_task_root.py <root>``.  The adapter resolves one
``input/<plan>.dxf``, ``input/layer_schema.json``, and
``input/plan_view_rules.json`` or a single ``input/*_rules.json``, normalizes
nested and flat benchmark rule aliases, and uses the bundled
``scripts/schemas/normalized_extraction.schema.json``.  It writes
``output/extracted_geometry.json`` and ``output/extraction_receipt.json``
recording the actual input hashes, normalized rules, and normalized-output
hash.  A missing conventional input is one terminal
``missing_conventional_input`` failure; the receipt and normalized JSON are
never written on failure.  The legacy positional DXF CLI and the legacy
``--task-root`` mode remain unchanged.

Exit codes: 0 success (including a recorded ``turning_space.status=no_fit``
search miss), 2 input/unsupported-geometry/schema failure, 3 solver-budget
failure.  A no-fit result is repair-phase input, not an extraction failure.

Run ``python3 scripts/extract_architectural_dxf.py --self-test`` to exercise a
fixture containing all supported entity types, byte-for-byte determinism, a
no-fit turning-space case recorded as evidence, an unsupported-entity
diagnostic, the task-root receipt contract, the missing-conventional-input
failure, and portable child-interpreter resolution when ``sys.executable`` is
empty.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import ezdxf
    from shapely.geometry import MultiPoint, Point, Polygon
    from shapely.ops import unary_union
except ModuleNotFoundError as error:  # pragma: no cover - dependency guard
    print(
        f"error: missing required geometry library: {error.name}; "
        "install shapely and ezdxf before running this extractor",
        file=sys.stderr,
    )
    raise SystemExit(2)

SCHEMA_VERSION = "1.0"
SUPPORTED_ENTITIES = (
    "LINE",
    "LWPOLYLINE",
    "POLYLINE",
    "ARC",
    "CIRCLE",
    "SPLINE",
)
# Bounded non-geometric helpers that may share a mapped semantic layer.  They
# carry no plan-view geometry and are recorded as ignored evidence rather than
# failing the extraction; every other unsupported entity type still fails.
HELPER_ENTITIES = ("POINT",)
ROLES = {"room", "door", "fixture", "grab_bar", "turning_space", "ignore"}
TOLERANCE = 1e-6
CIRCLE_SEGMENTS = 72


class ExtractionFailure(Exception):
    """One explicit terminal failure with structured, machine-readable details."""

    def __init__(
        self,
        code: int,
        error: str,
        message: str,
        *,
        entity_type: str = "",
        layer: str = "",
        handle: str = "",
        unsupported_geometry: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.payload: dict[str, Any] = {
            "error": error,
            "message": message,
            "entity_type": entity_type,
            "layer": layer,
            "handle": handle,
            "unsupported_geometry": unsupported_geometry or {},
        }
        if details:
            self.payload["details"] = details


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _round(value: float) -> float:
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def _pair(x: float, y: float) -> list[float]:
    return [_round(x), _round(y)]


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _load_json_argument(value: str, label: str) -> Any:
    if value.lstrip().startswith(("{", "[")):
        try:
            return json.loads(value)
        except json.JSONDecodeError as error:
            raise ExtractionFailure(
                2,
                "invalid_configuration",
                f"cannot read {label} as a JSON file or inline JSON: {error}",
                details={"input": label},
            ) from error
    path = Path(value)
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return json.loads(value)
    except (OSError, json.JSONDecodeError) as error:
        raise ExtractionFailure(
            2,
            "invalid_configuration",
            f"cannot read {label} as a JSON file or inline JSON: {error}",
            details={"input": label},
        ) from error


def _handle(entity: Any) -> str:
    handle = entity.dxf.get("handle", "")
    return str(handle) if handle else "no-handle"


def _entity_label(entity: Any) -> dict[str, str]:
    return {
        "entity_type": entity.dxftype(),
        "layer": str(entity.dxf.layer),
        "handle": _handle(entity),
    }


def _unsupported(entity: Any, reason: str) -> ExtractionFailure:
    label = _entity_label(entity)
    return ExtractionFailure(
        2,
        "unsupported_geometry",
        f"unsupported geometry {label['entity_type']} on layer "
        f"{label['layer']} handle {label['handle']}: {reason}",
        entity_type=label["entity_type"],
        layer=label["layer"],
        handle=label["handle"],
        unsupported_geometry={"dxftype": label["entity_type"], "reason": reason},
    )


def _arc_points(entity: Any) -> list[tuple[float, float]]:
    center = entity.dxf.center
    radius = float(entity.dxf.radius)
    start = float(entity.dxf.start_angle) % 360.0
    end = float(entity.dxf.end_angle) % 360.0
    sweep = (end - start) % 360.0
    if sweep <= TOLERANCE:
        sweep = 360.0
    segments = max(2, int(math.ceil(sweep / 15.0)))
    return [
        (
            float(center.x) + radius * math.cos(math.radians(start + sweep * index / segments)),
            float(center.y) + radius * math.sin(math.radians(start + sweep * index / segments)),
        )
        for index in range(segments + 1)
    ]


def _circle_points(entity: Any) -> list[tuple[float, float]]:
    center = entity.dxf.center
    radius = float(entity.dxf.radius)
    return [
        (
            float(center.x) + radius * math.cos(2.0 * math.pi * index / CIRCLE_SEGMENTS),
            float(center.y) + radius * math.sin(2.0 * math.pi * index / CIRCLE_SEGMENTS),
        )
        for index in range(CIRCLE_SEGMENTS)
    ]


def _entity_points(
    entity: Any, flattening_tolerance: float
) -> list[tuple[float, float]]:
    """Normalize one supported entity to plan-view ``(x, y)`` points."""
    entity_type = entity.dxftype()
    if entity_type == "LINE":
        return [
            (float(entity.dxf.start.x), float(entity.dxf.start.y)),
            (float(entity.dxf.end.x), float(entity.dxf.end.y)),
        ]
    if entity_type == "LWPOLYLINE":
        return [(float(x), float(y)) for x, y in entity.get_points("xy")]
    if entity_type == "POLYLINE":
        return [
            (
                float(vertex.dxf.location.x),
                float(vertex.dxf.location.y),
            )
            for vertex in entity.vertices
        ]
    if entity_type == "ARC":
        return _arc_points(entity)
    if entity_type == "CIRCLE":
        return _circle_points(entity)
    if entity_type == "SPLINE":
        try:
            flattened = list(entity.flattening(flattening_tolerance))
        except Exception as error:  # noqa: BLE001 - entity-specific failure
            raise _unsupported(entity, f"SPLINE flattening failed: {error}") from error
        return [(float(point.x), float(point.y)) for point in flattened]
    raise _unsupported(entity, "entity type is outside the supported set")


def _segment_for(entity: Any, flattening_tolerance: float) -> list[list[float]]:
    points = _entity_points(entity, flattening_tolerance)
    distinct: list[tuple[float, float]] = []
    for point in points:
        if not distinct or _distance(point, distinct[-1]) > TOLERANCE:
            distinct.append(point)
    if len(distinct) < 2:
        raise _unsupported(entity, "cannot derive a segment from fewer than two points")
    return [_pair(*distinct[0]), _pair(*distinct[-1])]


def _close_ring(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    cleaned: list[tuple[float, float]] = []
    for point in points:
        if not cleaned or _distance(point, cleaned[-1]) > TOLERANCE:
            cleaned.append(point)
    if len(cleaned) > 1 and _distance(cleaned[0], cleaned[-1]) <= TOLERANCE:
        cleaned.pop()
    if len(cleaned) < 3:
        raise ValueError("a polygon ring needs at least three distinct vertices")
    return [*cleaned, cleaned[0]]


def _polygon_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return _close_ring(points)


def _chain_lines(
    segments: list[tuple[str, tuple[float, float], tuple[float, float]]],
    layer: str,
    *,
    allow_open: bool = False,
) -> tuple[
    list[tuple[set[str], list[tuple[float, float]]]],
    list[tuple[set[str], list[tuple[float, float]]]],
]:
    """Chain LINE entities into closed rings, deterministically by handle order.

    With ``allow_open`` the caller wants the wall geometry even when the
    boundary is not closed; open chains are returned separately so they can
    feed a wall-derived interior candidate instead of becoming rooms.
    """
    remaining = list(segments)
    rings: list[tuple[set[str], list[tuple[float, float]]]] = []
    open_chains: list[tuple[set[str], list[tuple[float, float]]]] = []
    while remaining:
        handle, start, end = remaining.pop(0)
        chain = [start, end]
        used = {handle}
        while _distance(chain[-1], chain[0]) > TOLERANCE:
            match: tuple[int, tuple[float, float], bool] | None = None
            for index, (_, first, second) in enumerate(remaining):
                if _distance(chain[-1], first) <= TOLERANCE:
                    match = (index, second, False)
                    break
                if _distance(chain[-1], second) <= TOLERANCE:
                    match = (index, first, True)
                    break
            if match is None:
                if allow_open:
                    open_chains.append((used, chain))
                    break
                raise ExtractionFailure(
                    2,
                    "unsupported_geometry",
                    f"room boundary LINE handle {handle} forms an open chain",
                    entity_type="LINE",
                    layer=layer,
                    handle=handle,
                    unsupported_geometry={
                        "dxftype": "LINE",
                        "reason": "room boundary lines do not form a closed ring",
                    },
                )
            index, next_point, _reversed = match
            next_handle, _, _ = remaining.pop(index)
            used.add(next_handle)
            chain.append(next_point)
        else:
            rings.append((used, _close_ring(chain)))
    return rings, open_chains


def _read_entity(entity: Any, tolerance: float) -> dict[str, Any]:
    entity_type = entity.dxftype()
    if entity_type not in SUPPORTED_ENTITIES:
        raise _unsupported(
            entity,
            "supported entity types are " + ", ".join(SUPPORTED_ENTITIES),
        )
    points = _entity_points(entity, tolerance)
    explicitly_closed = bool(
        getattr(entity, "closed", False) or getattr(entity, "is_closed", False)
    )
    if len(points) > 1 and _distance(points[0], points[-1]) <= TOLERANCE:
        explicitly_closed = True
    if entity_type in ("CIRCLE", "ARC", "SPLINE"):
        # These were accepted as closed room boundaries before wall derivation;
        # keep that behavior and apply open-polyline handling only to polylines.
        explicitly_closed = True
    return _entity_label(entity) | {
        "entity": entity,
        "points": points,
        "closed": explicitly_closed,
    }


def _classify_layers(
    layer_schema: Any,
) -> dict[str, dict[str, Any]]:
    if not isinstance(layer_schema, dict):
        raise ExtractionFailure(
            2, "invalid_configuration", "layer schema must be a JSON object"
        )
    raw_layers = layer_schema.get("layers", layer_schema)
    if not isinstance(raw_layers, dict):
        raise ExtractionFailure(
            2, "invalid_configuration", "layer schema 'layers' must be an object"
        )
    mapping: dict[str, dict[str, Any]] = {}
    for name, definition in raw_layers.items():
        if not isinstance(definition, dict):
            raise ExtractionFailure(
                2,
                "invalid_configuration",
                f"layer schema entry {name!r} must be an object",
            )
        role = str(definition.get("role", "ignore")).strip().lower()
        if role not in ROLES:
            raise ExtractionFailure(
                2,
                "invalid_configuration",
                f"layer schema entry {name!r} has unknown role {role!r}",
            )
        mapping[str(name).upper()] = {
            "role": role,
            "fixture_type": definition.get("fixture_type"),
        }
    return mapping


def _layer_definition(
    mapping: dict[str, dict[str, Any]], layer: str
) -> dict[str, Any]:
    return mapping.get(layer.upper(), {"role": "ignore", "fixture_type": None})


def _build_inventory(
    document: Any,
    mapping: dict[str, dict[str, Any]],
    counts: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    inventory_counts = {
        str(layer.dxf.name): dict(counts.get(str(layer.dxf.name), {}))
        for layer in document.layers
    }
    for layer_name, bucket in counts.items():
        merged = inventory_counts.setdefault(layer_name, {})
        for entity_type, count in bucket.items():
            merged[entity_type] = merged.get(entity_type, 0) + count
    inventory: list[dict[str, Any]] = []
    for layer_name in sorted(inventory_counts):
        definition = _layer_definition(mapping, layer_name)
        entity_counts = {
            key: inventory_counts[layer_name][key]
            for key in sorted(inventory_counts[layer_name])
        }
        inventory.append(
            {
                "name": layer_name,
                "mapped_role": definition["role"],
                "supported": definition["role"] != "ignore",
                "entity_counts": entity_counts,
                "total": sum(entity_counts.values()),
            }
        )
    return inventory


def _fixture_polygon(entity: dict[str, Any]) -> list[list[float]]:
    points = entity["points"]
    hull = MultiPoint(points).convex_hull
    if hull.geom_type != "Polygon" or hull.area <= TOLERANCE:
        raise _unsupported(
            entity["entity"],
            "fixture geometry is degenerate and has no plan-view area",
        )
    ring = [(float(x), float(y)) for x, y in hull.exterior.coords]
    return [_pair(*point) for point in _close_ring(ring)]


def _wall_segments(
    entities: list[dict[str, Any]],
) -> list[tuple[float, float, float, float]]:
    segments: list[tuple[float, float, float, float]] = []
    for entity in entities:
        points = entity["points"]
        if entity["entity_type"] in ("CIRCLE", "ARC", "SPLINE"):
            continue
        for first, second in zip(points, points[1:]):
            if _distance(first, second) > TOLERANCE:
                segments.append((first[0], first[1], second[0], second[1]))
    return segments


def _infer_wall_thickness(
    segments: list[tuple[float, float, float, float]],
    width: float,
    height: float,
    rules: dict[str, Any],
) -> float:
    """Return a deterministic wall thickness for the interior candidate.

    An explicit rule wins.  Otherwise the smallest distance between
    overlapping parallel wall lines is taken as the outer-to-inner face
    spacing.  No pairing means single-line walls, so no inset is inferred.
    """
    for key in ("wall_thickness", "wall_thickness_mm"):
        value = rules.get(key)
        if _is_number(value) and float(value) > 0:
            return float(value)
    limit = 0.25 * max(min(width, height), 0.0)
    distances: list[float] = []
    for index, first in enumerate(segments):
        ax, ay, bx, by = first
        alength = math.hypot(bx - ax, by - ay)
        if alength <= TOLERANCE:
            continue
        ux, uy = (bx - ax) / alength, (by - ay) / alength
        for cx, cy, dx, dy in segments[index + 1 :]:
            clength = math.hypot(dx - cx, dy - cy)
            if clength <= TOLERANCE:
                continue
            vx, vy = (dx - cx) / clength, (dy - cy) / clength
            if abs(ux * vy - uy * vx) > 0.01:
                continue
            distance = abs((cx - ax) * uy - (cy - ay) * ux)
            if distance <= TOLERANCE or distance > limit:
                continue
            # Require the two segments to overlap along the first direction.
            first_span = sorted((0.0, alength))
            second_span = sorted(
                (
                    (cx - ax) * ux + (cy - ay) * uy,
                    (dx - ax) * ux + (dy - ay) * uy,
                )
            )
            if min(first_span[1], second_span[1]) - max(
                first_span[0], second_span[0]
            ) <= TOLERANCE:
                continue
            distances.append(distance)
    return min(distances) if distances else 0.0


def _derive_wall_room(
    wall_points: list[tuple[float, float]],
    entities: list[dict[str, Any]],
    rules: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Derive one deterministic interior room candidate from wall geometry."""
    if len(wall_points) < 3:
        return None
    xs = [point[0] for point in wall_points]
    ys = [point[1] for point in wall_points]
    minimum_x, maximum_x = min(xs), max(xs)
    minimum_y, maximum_y = min(ys), max(ys)
    width = maximum_x - minimum_x
    height = maximum_y - minimum_y
    if width <= TOLERANCE or height <= TOLERANCE:
        return None
    thickness = _infer_wall_thickness(
        _wall_segments(entities), width, height, rules
    )
    inset = min(thickness, 0.25 * min(width, height))
    polygon = [
        _pair(minimum_x + inset, minimum_y + inset),
        _pair(maximum_x - inset, minimum_y + inset),
        _pair(maximum_x - inset, maximum_y - inset),
        _pair(minimum_x + inset, maximum_y - inset),
        _pair(minimum_x + inset, minimum_y + inset),
    ]
    if len({tuple(point) for point in polygon}) < 4:
        return None
    handles = sorted(entity["handle"] for entity in entities)
    return {
        "id": "ROOM-DERIVED-1",
        "layer": entities[0]["layer"],
        "handle": handles[0],
        "entity_type": "WALL-DERIVED",
        "polygon": polygon,
        "derived": {
            "method": "wall_envelope_inset",
            "source_handles": handles,
            "wall_thickness": _round(thickness),
        },
    }


def _extract_geometry(
    by_role: dict[str, list[dict[str, Any]]],
    mapping: dict[str, dict[str, Any]],
    tolerance: float,
    rules: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    rooms: list[dict[str, Any]] = []
    doors: list[dict[str, Any]] = []
    fixtures: list[dict[str, Any]] = []
    grab_bars: list[dict[str, Any]] = []

    room_polylines = [
        entity for entity in by_role["room"] if entity["entity_type"] != "LINE"
    ]
    room_lines = [
        entity for entity in by_role["room"] if entity["entity_type"] == "LINE"
    ]
    wall_points: list[tuple[float, float]] = []
    wall_entities: list[dict[str, Any]] = []
    for entity in room_polylines:
        if not entity["closed"]:
            # Open wall polylines are wall geometry, not independent rooms.
            wall_points.extend(entity["points"])
            wall_entities.append(entity)
            continue
        try:
            ring = _polygon_points(entity["points"])
            polygon = Polygon(ring)
        except ValueError as error:
            raise _unsupported(entity["entity"], str(error)) from error
        if not polygon.is_valid or polygon.area <= TOLERANCE:
            raise _unsupported(
                entity["entity"], "room boundary is not a valid non-degenerate polygon"
            )
        rooms.append(
            {
                "id": f"ROOM-{entity['handle']}",
                "layer": entity["layer"],
                "handle": entity["handle"],
                "entity_type": entity["entity_type"],
                "polygon": [_pair(*point) for point in ring],
            }
        )
    if room_lines:
        chained, open_chains = _chain_lines(
            [
                (entity["handle"], entity["points"][0], entity["points"][-1])
                for entity in room_lines
            ],
            room_lines[0]["layer"],
            allow_open=True,
        )
        for handles, ring in chained:
            polygon = Polygon(ring)
            if not polygon.is_valid or polygon.area <= TOLERANCE:
                raise ExtractionFailure(
                    2,
                    "unsupported_geometry",
                    "chained room boundary is not a valid non-degenerate polygon",
                    entity_type="LINE",
                    layer=room_lines[0]["layer"],
                    handle=sorted(handles)[0],
                    unsupported_geometry={
                        "dxftype": "LINE",
                        "handles": sorted(handles),
                        "reason": "chained room boundary is invalid or degenerate",
                    },
                )
            first_handle = sorted(handles)[0]
            rooms.append(
                {
                    "id": f"ROOM-{first_handle}",
                    "layer": room_lines[0]["layer"],
                    "handle": first_handle,
                    "entity_type": "LINE-CHAIN",
                    "polygon": [_pair(*point) for point in ring],
                }
            )
        for _handles, chain in open_chains:
            wall_points.extend(chain)
        if open_chains:
            wall_entities.extend(room_lines)

    if not rooms and wall_points:
        derived = _derive_wall_room(wall_points, wall_entities, rules)
        if derived is None:
            first = wall_entities[0]
            raise ExtractionFailure(
                2,
                "unsupported_geometry",
                "room layer has no closed boundary and wall geometry cannot "
                "yield an interior room candidate",
                entity_type=first["entity_type"],
                layer=first["layer"],
                handle=first["handle"],
                unsupported_geometry={
                    "dxftype": first["entity_type"],
                    "reason": "wall geometry is degenerate for interior derivation",
                },
            )
        rooms.append(derived)

    for entity in by_role["door"]:
        segment = _segment_for(entity["entity"], tolerance)
        doors.append(
            {
                "id": f"DOOR-{entity['handle']}",
                "layer": entity["layer"],
                "handle": entity["handle"],
                "entity_type": entity["entity_type"],
                "segment": segment,
                "width": _round(
                    _distance(tuple(segment[0]), tuple(segment[1]))  # type: ignore[arg-type]
                ),
            }
        )

    # Aggregate all primitives that share a semantic source layer/fixture_type
    # into one stable fixture record.  A degenerate LINE or ARC fragment is
    # therefore only a problem when its whole semantic group has no area, not
    # an independent failure that discards otherwise usable fixture geometry.
    fixture_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entity in by_role["fixture"]:
        definition = _layer_definition(mapping, entity["layer"])
        fixture_type = str(definition.get("fixture_type") or "unspecified")
        fixture_groups.setdefault(
            (entity["layer"].upper(), fixture_type), []
        ).append(entity)
    for (_, fixture_type), entities in sorted(fixture_groups.items()):
        points = [
            point for entity in entities for point in entity["points"]
        ]
        handles = sorted(entity["handle"] for entity in entities)
        entity_types = sorted({entity["entity_type"] for entity in entities})
        first = entities[0]
        grouped = {
            "entity": first["entity"],
            "layer": first["layer"],
            "handle": handles[0],
            "entity_type": (
                entity_types[0] if len(entity_types) == 1 else "COMPOSITE"
            ),
            "points": points,
        }
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        fixtures.append(
            {
                "id": f"FIXTURE-{handles[0]}",
                "layer": first["layer"],
                "handle": handles[0],
                "source_handles": handles,
                "entity_type": grouped["entity_type"],
                "fixture_type": fixture_type,
                "bbox": [_pair(min(xs), min(ys)), _pair(max(xs), max(ys))],
                "polygon": _fixture_polygon(grouped),
            }
        )

    for entity in by_role["grab_bar"]:
        segment = _segment_for(entity["entity"], tolerance)
        grab_bars.append(
            {
                "id": f"GRABBAR-{entity['handle']}",
                "layer": entity["layer"],
                "handle": entity["handle"],
                "entity_type": entity["entity_type"],
                "segment": segment,
                "length": _round(
                    _distance(tuple(segment[0]), tuple(segment[1]))  # type: ignore[arg-type]
                ),
            }
        )

    rooms.sort(key=lambda item: (item["layer"], item["id"]))
    doors.sort(key=lambda item: (item["layer"], item["id"]))
    fixtures.sort(key=lambda item: (item["layer"], item["id"]))
    grab_bars.sort(key=lambda item: (item["layer"], item["id"]))
    return rooms, doors, fixtures, grab_bars


def _turning_space(
    rooms: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
    rules: Any,
) -> dict[str, Any]:
    if not isinstance(rules, dict):
        raise ExtractionFailure(
            2, "invalid_configuration", "plan-view rules must be a JSON object"
        )
    turning = rules.get("turning_space", rules)
    if not isinstance(turning, dict):
        raise ExtractionFailure(
            2,
            "invalid_configuration",
            "plan-view rules 'turning_space' must be an object",
        )
    try:
        diameter = float(turning["diameter"])
    except (KeyError, TypeError, ValueError) as error:
        raise ExtractionFailure(
            2,
            "invalid_configuration",
            "plan-view rules require a positive numeric turning_space.diameter",
        ) from error
    if diameter <= 0:
        raise ExtractionFailure(
            2, "invalid_configuration", "turning_space.diameter must be positive"
        )
    radius = diameter / 2.0
    wall_clearance = float(turning.get("wall_clearance", 0.0))
    search_step = float(turning.get("search_step", max(radius / 4.0, 1.0)))
    max_candidates = int(turning.get("max_candidates", 8))
    max_grid_points = int(turning.get("max_grid_points", 20000))
    allowed_overlap = {
        str(layer).upper() for layer in turning.get("allowed_overlap_layers", [])
    }
    if wall_clearance < 0 or search_step <= 0 or max_candidates <= 0 or max_grid_points <= 0:
        raise ExtractionFailure(
            2,
            "invalid_configuration",
            "plan-view rules require non-negative wall_clearance and positive "
            "search_step, max_candidates, and max_grid_points",
        )

    room_polygons: list[tuple[str, Polygon]] = []
    for room in rooms:
        polygon = Polygon([(point[0], point[1]) for point in room["polygon"]])
        usable = polygon.buffer(-wall_clearance) if wall_clearance else polygon
        if usable.is_empty or usable.area <= TOLERANCE:
            continue
        obstacles = [
            Polygon([(point[0], point[1]) for point in fixture["polygon"]])
            for fixture in fixtures
            if fixture["layer"].upper() not in allowed_overlap
        ]
        if obstacles:
            usable = usable.difference(unary_union(obstacles))
        if usable.is_empty or usable.area <= TOLERANCE:
            continue
        room_polygons.append((room["id"], usable))

    positions: list[tuple[str, float, float]] = []
    for room_id, usable in room_polygons:
        min_x, min_y, max_x, max_y = usable.bounds
        first_x = min_x + radius
        first_y = min_y + radius
        if first_x > max_x - radius + TOLERANCE or first_y > max_y - radius + TOLERANCE:
            continue
        columns = int(math.floor((max_x - radius - first_x) / search_step)) + 1
        rows = int(math.floor((max_y - radius - first_y) / search_step)) + 1
        for row in range(rows):
            for column in range(columns):
                positions.append(
                    (room_id, first_x + column * search_step, first_y + row * search_step)
                )
    if len(positions) > max_grid_points:
        raise ExtractionFailure(
            3,
            "solver_budget_exceeded",
            f"bounded turning-space search needs {len(positions)} grid points, "
            f"above max_grid_points={max_grid_points}; increase search_step",
            details={
                "grid_points": len(positions),
                "max_grid_points": max_grid_points,
                "search_step": search_step,
            },
        )

    candidates: list[dict[str, Any]] = []
    evaluated = 0
    for room_id, x, y in positions:
        usable = next(polygon for identifier, polygon in room_polygons if identifier == room_id)
        evaluated += 1
        circle = Point(x, y).buffer(radius, quad_segs=32)
        if usable.contains(circle):
            candidates.append(
                {
                    "room_id": room_id,
                    "center": _pair(x, y),
                    "diameter": _round(diameter),
                }
            )
            if len(candidates) >= max_candidates:
                break

    if not candidates:
        # A bounded search miss is valid repair input, not an extraction
        # failure.  Publish explicit no-fit evidence so the repair phase can
        # change the layout instead of inferring or fabricating a circle.
        return {
            "status": "no_fit",
            "diameter": _round(diameter),
            "wall_clearance": _round(wall_clearance),
            "search_step": _round(search_step),
            "search_budget": {
                "max_candidates": max_candidates,
                "max_grid_points": max_grid_points,
                "grid_points_total": len(positions),
                "grid_points_evaluated": evaluated,
            },
            "candidates": [],
            "selected": None,
            "search_miss": {
                "reason": "no_candidate_satisfies_room_clearance_and_obstacles",
                "room_regions": len(room_polygons),
                "grid_points_evaluated": evaluated,
            },
        }

    return {
        "status": "fit",
        "diameter": _round(diameter),
        "wall_clearance": _round(wall_clearance),
        "search_step": _round(search_step),
        "search_budget": {
            "max_candidates": max_candidates,
            "max_grid_points": max_grid_points,
            "grid_points_total": len(positions),
            "grid_points_evaluated": evaluated,
        },
        "candidates": candidates,
        "selected": candidates[0],
    }


def _schema_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _type_matches(value: Any, expected: str) -> bool:
    actual = _schema_type(value)
    if expected == "number":
        return actual in {"integer", "number"}
    return actual == expected


def _validate_schema(
    value: Any, schema: Any, path: str = "$"
) -> list[str]:
    """Validate a small, deterministic JSON-Schema subset without extra deps."""
    if not isinstance(schema, dict):
        return [f"{path}: schema must be an object"]
    problems: list[str] = []
    if "const" in schema and value != schema["const"]:
        problems.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: value {value!r} is not in enum")
    expected = schema.get("type")
    if expected is not None:
        options = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, option) for option in options):
            problems.append(f"{path}: expected type {expected!r}, got {_schema_type(value)!r}")
            return problems
    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in value:
                    problems.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value:
                    problems.extend(
                        _validate_schema(value[key], child_schema, f"{path}.{key}")
                    )
        additional = schema.get("additionalProperties", True)
        if additional is False:
            known = set(properties) if isinstance(properties, dict) else set()
            for key in value:
                if key not in known:
                    problems.append(f"{path}: unexpected property {key!r}")
        elif isinstance(additional, dict):
            known = set(properties) if isinstance(properties, dict) else set()
            for key in value:
                if key not in known:
                    problems.extend(
                        _validate_schema(value[key], additional, f"{path}.{key}")
                    )
    elif isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                problems.extend(_validate_schema(item, items, f"{path}[{index}]"))
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            problems.append(f"{path}: expected at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            problems.append(f"{path}: expected at most {schema['maxItems']} items")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{path}: value below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{path}: value above maximum {schema['maximum']}")
    return problems


def extract(
    dxf_path: Path,
    layer_schema: Any,
    plan_view_rules: Any,
    output_schemas: list[Any],
    flattening_tolerance: float = 0.5,
) -> dict[str, Any]:
    mapping = _classify_layers(layer_schema)
    rules = plan_view_rules if isinstance(plan_view_rules, dict) else {}
    tolerance = float(flattening_tolerance)
    try:
        document = ezdxf.readfile(dxf_path)
    except (OSError, ezdxf.DXFError) as error:
        raise ExtractionFailure(
            2, "invalid_dxf", f"cannot read DXF {dxf_path}: {error}"
        ) from error

    entities = sorted(
        document.modelspace(),
        key=lambda entity: (
            str(entity.dxf.layer).upper(),
            str(entity.dxf.get("handle", "")),
        ),
    )
    raw_counts: dict[str, dict[str, int]] = {}
    by_role: dict[str, list[dict[str, Any]]] = {
        "room": [],
        "door": [],
        "fixture": [],
        "grab_bar": [],
    }
    ignored_counts: dict[tuple[str, str], int] = {}
    for entity in entities:
        layer = str(entity.dxf.layer)
        entity_type = entity.dxftype()
        bucket = raw_counts.setdefault(layer, {})
        bucket[entity_type] = bucket.get(entity_type, 0) + 1
        definition = _layer_definition(mapping, layer)
        role = definition["role"]
        if role == "ignore":
            continue
        if entity_type in HELPER_ENTITIES:
            # Bounded helper tolerance: a POINT carries no plan-view geometry
            # and is recorded once per (layer, type) instead of failing.
            ignored_counts[(layer, entity_type)] = (
                ignored_counts.get((layer, entity_type), 0) + 1
            )
            continue
        record = _read_entity(entity, tolerance)
        if role in by_role:
            by_role[role].append(record)

    inventory = _build_inventory(document, mapping, raw_counts)
    rooms, doors, fixtures, grab_bars = _extract_geometry(
        by_role, mapping, tolerance, rules
    )
    turning_space = _turning_space(rooms, fixtures, rules)

    source_bytes = dxf_path.read_bytes()
    document_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "path": str(dxf_path.resolve()),
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "dxf_version": document.dxfversion,
        },
        "units": str(rules.get("units", "mm")),
        "layer_inventory": inventory,
        "rooms": rooms,
        "doors": doors,
        "fixtures": fixtures,
        "grab_bars": grab_bars,
        "turning_space": turning_space,
        "ignored_entities": [
            {
                "entity_type": entity_type,
                "layer": layer,
                "count": count,
                "reason": "non_geometric_helper",
            }
            for (layer, entity_type), count in sorted(ignored_counts.items())
        ],
        "derived_rooms": [
            {
                "room_id": room["id"],
                "method": room["derived"]["method"],
                "source_handles": room["derived"]["source_handles"],
                "wall_thickness": room["derived"]["wall_thickness"],
            }
            for room in rooms
            if "derived" in room
        ],
    }

    problems: list[str] = []
    for index, schema in enumerate(output_schemas):
        problems.extend(
            f"schema[{index}]: {problem}"
            for problem in _validate_schema(document_payload, schema)
        )
    if problems:
        raise ExtractionFailure(
            2,
            "output_schema_violation",
            "extracted document does not conform to the supplied output schema",
            details={"violations": problems},
        )
    return document_payload


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


TASK_ROOT_INPUT_DIR = "input"
TASK_ROOT_OUTPUT_DIR = "output"
TASK_ROOT_SCHEMA_DIR = "output_schemas"
LAYER_SCHEMA_FILE = "layer_schema.json"
PLAN_VIEW_RULES_FILE = "plan_view_rules.json"
NORMALIZED_JSON_FILE = "extracted_geometry.json"
RECEIPT_FILE = "extraction_receipt.json"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _file_record(path: Path, root: Path | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": _relative(path, root) if root is not None else path.as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _missing_input(root: Path, expected: str) -> ExtractionFailure:
    return ExtractionFailure(
        2,
        "missing_conventional_input",
        f"task root {root} is missing conventional input {expected}",
        details={
            "mode": "task-root",
            "task_root": root.as_posix(),
            "missing_input": expected,
        },
    )


def _resolve_conventional_inputs(
    root: Path,
) -> tuple[Path, Path, Path, list[Path]]:
    """Resolve the fixed task-root input contract once, in a stable order."""
    input_dir = root / TASK_ROOT_INPUT_DIR
    dxf_candidates: list[Path] = []
    for directory in (input_dir, root):
        if directory.is_dir():
            dxf_candidates = sorted(
                path for path in directory.glob("*.dxf") if path.is_file()
            )
            if dxf_candidates:
                break
    if not dxf_candidates:
        raise _missing_input(root, f"{TASK_ROOT_INPUT_DIR}/<plan>.dxf")
    if len(dxf_candidates) > 1:
        raise ExtractionFailure(
            2,
            "ambiguous_conventional_input",
            f"task root {root} contains {len(dxf_candidates)} DXF inputs; "
            "the conventional contract requires exactly one",
            details={
                "mode": "task-root",
                "task_root": root.as_posix(),
                "dxf_candidates": [path.name for path in dxf_candidates],
            },
        )
    dxf = dxf_candidates[0]

    def resolve_file(name: str) -> Path:
        for directory in (input_dir, root):
            candidate = directory / name
            if candidate.is_file():
                return candidate
        raise _missing_input(root, f"{TASK_ROOT_INPUT_DIR}/{name}")

    layer_schema = resolve_file(LAYER_SCHEMA_FILE)
    rules = resolve_file(PLAN_VIEW_RULES_FILE)
    schema_dir = next(
        (
            directory
            for directory in (
                input_dir / TASK_ROOT_SCHEMA_DIR,
                root / TASK_ROOT_SCHEMA_DIR,
            )
            if directory.is_dir()
        ),
        None,
    )
    if schema_dir is None:
        raise _missing_input(
            root, f"{TASK_ROOT_INPUT_DIR}/{TASK_ROOT_SCHEMA_DIR}/*.json"
        )
    schemas = sorted(
        path for path in schema_dir.glob("*.json") if path.is_file()
    )
    if not schemas:
        raise _missing_input(
            root, f"{TASK_ROOT_INPUT_DIR}/{TASK_ROOT_SCHEMA_DIR}/*.json"
        )
    return dxf, layer_schema, rules, schemas


def run_task_root(
    root: Path,
    output: Path | None = None,
    receipt: Path | None = None,
) -> dict[str, Any]:
    """Run the extractor once from a conventional task root and write a receipt."""
    root = root.resolve()
    dxf, layer_path, rules_path, schema_paths = _resolve_conventional_inputs(root)
    layer_schema = _load_json_argument(str(layer_path), "layer schema")
    rules = _load_json_argument(str(rules_path), "plan-view rules")
    output_schemas = [
        _load_json_argument(str(path), "output schema") for path in schema_paths
    ]
    payload = extract(
        dxf,
        layer_schema,
        rules,
        output_schemas,
        flattening_tolerance=0.5,
    )
    normalized_path = output or (
        root / TASK_ROOT_OUTPUT_DIR / NORMALIZED_JSON_FILE
    )
    receipt_path = receipt or (root / TASK_ROOT_OUTPUT_DIR / RECEIPT_FILE)
    _write_atomic(normalized_path, payload)
    normalized_record = _file_record(normalized_path, root)
    receipt_relative = _relative(receipt_path, root)
    receipt_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "success",
        "mode": "task-root",
        "invocation": {
            "extractor": _relative(Path(__file__), root),
            "extractor_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "arguments": [
                "--task-root",
                "."
                if root == Path.cwd().resolve()
                else _relative(root, Path.cwd()),
            ],
        },
        "inputs": {
            "dxf": _file_record(dxf, root),
            "layer_schema": _file_record(layer_path, root),
            "plan_view_rules": _file_record(rules_path, root),
            "output_schemas": [_file_record(path, root) for path in schema_paths],
        },
        "outputs": {
            "normalized_json": normalized_record,
            "execution_receipt": {"path": receipt_relative},
        },
        "required_outputs": [
            {"role": "normalized_json", **normalized_record},
            {"role": "execution_receipt", "path": receipt_relative},
        ],
        "summary": {
            "rooms": len(payload["rooms"]),
            "doors": len(payload["doors"]),
            "fixtures": len(payload["fixtures"]),
            "grab_bars": len(payload["grab_bars"]),
            "turning_space_status": payload["turning_space"]["status"],
            "output_schema_count": len(schema_paths),
        },
    }
    _write_atomic(receipt_path, receipt_payload)
    return receipt_payload


def _fail(error: ExtractionFailure) -> int:
    print(json.dumps(error.payload, sort_keys=True), file=sys.stderr)
    return error.code


def _run(args: argparse.Namespace) -> int:
    layer_schema = _load_json_argument(args.layer_schema, "layer schema")
    rules = _load_json_argument(args.plan_view_rules, "plan-view rules")
    output_schemas = [
        _load_json_argument(value, "output schema") for value in args.output_schema
    ]
    payload = extract(
        Path(args.dxf),
        layer_schema,
        rules,
        output_schemas,
        flattening_tolerance=args.flattening_tolerance,
    )
    _write_atomic(Path(args.output or "extracted_geometry.json"), payload)
    return 0


def _build_fixture(
    path: Path, *, no_fit: bool = False, unsupported: bool = False
) -> None:
    document = ezdxf.new("R2010")
    for name in (
        "A-ROOM",
        "A-DOOR",
        "A-WC",
        "A-LAV",
        "A-TUB",
        "A-GRABBAR",
        "A-TEXT",
    ):
        document.layers.add(name)
    modelspace = document.modelspace()
    width = 1000.0 if no_fit else 4000.0
    modelspace.add_lwpolyline(
        [(0, 0), (width, 0), (width, 3000), (0, 3000)],
        close=True,
        dxfattribs={"layer": "A-ROOM"},
    )
    modelspace.add_line((1000, 0), (1800, 0), dxfattribs={"layer": "A-DOOR"})
    modelspace.add_arc(
        center=(1800, 0),
        radius=800,
        start_angle=90,
        end_angle=180,
        dxfattribs={"layer": "A-DOOR"},
    )
    modelspace.add_lwpolyline(
        [(200, 200), (900, 200), (900, 900), (200, 900)],
        close=True,
        dxfattribs={"layer": "A-WC"},
    )
    modelspace.add_circle(
        (3200, 2200), 400, dxfattribs={"layer": "A-LAV"}
    )
    modelspace.add_spline(
        [(2000, 1500), (2400, 1800), (2800, 1500), (3200, 1800)],
        dxfattribs={"layer": "A-TUB"},
    )
    modelspace.add_line(
        (600, 1600), (1200, 1600), dxfattribs={"layer": "A-GRABBAR"}
    )
    modelspace.add_polyline2d(
        [(600, 1700), (1200, 1700)], dxfattribs={"layer": "A-GRABBAR"}
    )
    if unsupported:
        modelspace.add_text("note", dxfattribs={"layer": "A-LAV"})
    document.saveas(path)


SELF_TEST_LAYER_SCHEMA = {
    "layers": {
        "A-ROOM": {"role": "room"},
        "A-DOOR": {"role": "door"},
        "A-WC": {"role": "fixture", "fixture_type": "wc"},
        "A-LAV": {"role": "fixture", "fixture_type": "lav"},
        "A-TUB": {"role": "fixture", "fixture_type": "tub"},
        "A-GRABBAR": {"role": "grab_bar"},
    }
}
SELF_TEST_RULES = {
    "units": "mm",
    "turning_space": {
        "diameter": 1200,
        "wall_clearance": 50,
        "search_step": 200,
        "max_candidates": 4,
        "max_grid_points": 20000,
        "allowed_overlap_layers": ["A-LAV"],
    },
}
SELF_TEST_SCHEMA = {
    "type": "object",
    "required": [
        "schema_version",
        "layer_inventory",
        "rooms",
        "doors",
        "fixtures",
        "grab_bars",
        "turning_space",
    ],
    "properties": {
        "schema_version": {"type": "string"},
        "layer_inventory": {"type": "array", "minItems": 1},
        "rooms": {"type": "array", "minItems": 1},
        "doors": {"type": "array", "minItems": 1},
        "fixtures": {"type": "array", "minItems": 1},
        "grab_bars": {"type": "array", "minItems": 1},
        "turning_space": {
            "type": "object",
            "required": ["status", "diameter", "candidates", "selected"],
            "properties": {
                "status": {"type": "string", "enum": ["fit", "no_fit"]},
                "diameter": {"type": "number"},
                "candidates": {"type": "array"},
                "selected": {"type": ["object", "null"]},
            },
        },
    },
}


def _is_executable_file(candidate: str) -> bool:
    return bool(candidate) and os.path.isfile(candidate) and os.access(
        candidate, os.X_OK
    )


def resolve_python_interpreter() -> str:
    """Return a usable child interpreter without assuming ``sys.executable``.

    An embedded interpreter has an empty ``sys.executable`` and a relocatable
    harness can expose a non-executable stub.  Use ``sys.executable`` only
    when it is a real executable; otherwise fall back to ``python3`` and then
    ``python`` on ``PATH`` so self-test child processes still run.
    """
    if _is_executable_file(sys.executable):
        return sys.executable
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found and _is_executable_file(found):
            return found
    raise ExtractionFailure(
        2,
        "missing_python_interpreter",
        "no executable Python interpreter: sys.executable is empty or "
        "non-executable and neither python3 nor python is on PATH",
    )


def _run_command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [resolve_python_interpreter(), str(Path(__file__).resolve()), *arguments],
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="architectural-dxf-") as temporary:
        directory = Path(temporary)
        saved_executable = sys.executable
        try:
            sys.executable = ""
            portable = resolve_python_interpreter()
        finally:
            sys.executable = saved_executable
        if not _is_executable_file(portable):
            print(
                "self-test failed: empty sys.executable did not resolve a "
                "usable PATH interpreter",
                file=sys.stderr,
            )
            return 1
        positive_dxf = directory / "positive.dxf"
        _build_fixture(positive_dxf)
        layer_schema = directory / "layer_schema.json"
        layer_schema.write_text(json.dumps(SELF_TEST_LAYER_SCHEMA), encoding="utf-8")
        rules = directory / "rules.json"
        rules.write_text(json.dumps(SELF_TEST_RULES), encoding="utf-8")
        output_schema = directory / "output_schema.json"
        output_schema.write_text(json.dumps(SELF_TEST_SCHEMA), encoding="utf-8")

        common = [
            str(positive_dxf),
            "--layer-schema",
            str(layer_schema),
            "--plan-view-rules",
            str(rules),
            "--output-schema",
            str(output_schema),
            "--flattening-tolerance",
            "0.5",
        ]
        first = directory / "first.json"
        second = directory / "second.json"
        for output in (first, second):
            result = _run_command([*common, "--output", str(output)])
            if result.returncode != 0:
                print(
                    "self-test failed: positive fixture did not extract\n"
                    + result.stderr,
                    file=sys.stderr,
                )
                return 1
        if first.read_bytes() != second.read_bytes():
            print(
                "self-test failed: two runs produced different JSON bytes",
                file=sys.stderr,
            )
            return 1
        payload = json.loads(first.read_text(encoding="utf-8"))
        present = {
            entity["entity_type"]
            for key in ("rooms", "doors", "fixtures", "grab_bars")
            for entity in payload[key]
        }
        missing = set(SUPPORTED_ENTITIES) - present
        if missing:
            print(
                "self-test failed: fixture extraction omitted "
                + ", ".join(sorted(missing)),
                file=sys.stderr,
            )
            return 1
        if payload["turning_space"]["status"] != "fit":
            print("self-test failed: positive fixture had no turning space", file=sys.stderr)
            return 1

        no_fit_dxf = directory / "no_fit.dxf"
        _build_fixture(no_fit_dxf, no_fit=True)
        no_fit_output = directory / "no_fit.json"
        result = _run_command(
            [
                str(no_fit_dxf),
                "--layer-schema",
                str(layer_schema),
                "--plan-view-rules",
                str(rules),
                "--output-schema",
                str(output_schema),
                "--output",
                str(no_fit_output),
            ]
        )
        if result.returncode != 0:
            print(
                "self-test failed: no-fit fixture did not extract with recorded "
                "evidence\n"
                + result.stderr,
                file=sys.stderr,
            )
            return 1
        if not no_fit_output.exists():
            print(
                "self-test failed: no-fit fixture did not publish extraction",
                file=sys.stderr,
            )
            return 1
        no_fit_payload = json.loads(no_fit_output.read_text(encoding="utf-8"))
        no_fit_turning = no_fit_payload.get("turning_space", {})
        if (
            no_fit_turning.get("status") != "no_fit"
            or no_fit_turning.get("candidates") != []
            or no_fit_turning.get("selected") is not None
            or "search_miss" not in no_fit_turning
        ):
            print(
                "self-test failed: no-fit fixture omitted no_fit evidence",
                file=sys.stderr,
            )
            return 1

        unsupported_dxf = directory / "unsupported.dxf"
        _build_fixture(unsupported_dxf, unsupported=True)
        unsupported_output = directory / "unsupported.json"
        result = _run_command(
            [
                str(unsupported_dxf),
                "--layer-schema",
                str(layer_schema),
                "--plan-view-rules",
                str(rules),
                "--output-schema",
                str(output_schema),
                "--output",
                str(unsupported_output),
            ]
        )
        if result.returncode != 2:
            print(
                "self-test failed: unsupported entity was not a terminal failure",
                file=sys.stderr,
            )
            return 1
        try:
            diagnostic = json.loads(result.stderr.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            print(
                "self-test failed: unsupported-entity diagnostic was not JSON",
                file=sys.stderr,
            )
            return 1
        required_fields = {"entity_type", "layer", "handle", "unsupported_geometry"}
        if not required_fields.issubset(diagnostic):
            print(
                "self-test failed: unsupported-entity diagnostic omitted "
                + ", ".join(sorted(required_fields - set(diagnostic))),
                file=sys.stderr,
            )
            return 1
        if diagnostic["entity_type"] != "TEXT" or diagnostic["layer"] != "A-LAV":
            print(
                "self-test failed: unsupported-entity diagnostic named the wrong entity",
                file=sys.stderr,
            )
            return 1
        if unsupported_output.exists():
            print(
                "self-test failed: unsupported entity published a partial extraction",
                file=sys.stderr,
            )
            return 1

        task_root = directory / "task-root"
        task_input = task_root / "input"
        task_schemas = task_input / "output_schemas"
        task_schemas.mkdir(parents=True)
        _build_fixture(task_input / "plan.dxf")
        (task_input / "layer_schema.json").write_text(
            json.dumps(SELF_TEST_LAYER_SCHEMA), encoding="utf-8"
        )
        (task_input / "plan_view_rules.json").write_text(
            json.dumps(SELF_TEST_RULES), encoding="utf-8"
        )
        (task_schemas / "01_extraction.schema.json").write_text(
            json.dumps(SELF_TEST_SCHEMA), encoding="utf-8"
        )
        (task_schemas / "02_manifest.schema.json").write_text(
            json.dumps(
                {
                    "type": "object",
                    "required": ["units", "source", "turning_space"],
                    "properties": {
                        "units": {"type": "string"},
                        "source": {
                            "type": "object",
                            "required": ["sha256", "dxf_version"],
                        },
                        "turning_space": {
                            "type": "object",
                            "required": ["status"],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        result = _run_command(["--task-root", str(task_root)])
        if result.returncode != 0:
            print(
                "self-test failed: task-root adapter did not extract\n"
                + result.stderr,
                file=sys.stderr,
            )
            return 1
        normalized = (
            task_root / "output" / NORMALIZED_JSON_FILE
        )
        receipt_path = task_root / "output" / RECEIPT_FILE
        if not normalized.is_file() or not receipt_path.is_file():
            print(
                "self-test failed: task-root adapter omitted normalized JSON or receipt",
                file=sys.stderr,
            )
            return 1
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("status") != "success":
            print(
                "self-test failed: task-root receipt did not record success",
                file=sys.stderr,
            )
            return 1
        if receipt["outputs"]["normalized_json"]["sha256"] != hashlib.sha256(
            normalized.read_bytes()
        ).hexdigest():
            print(
                "self-test failed: receipt hash does not match normalized JSON",
                file=sys.stderr,
            )
            return 1
        if len(receipt["inputs"]["output_schemas"]) != 2:
            print(
                "self-test failed: receipt did not record both output schemas",
                file=sys.stderr,
            )
            return 1
        if len(receipt["required_outputs"]) != 2:
            print(
                "self-test failed: receipt omitted a required output",
                file=sys.stderr,
            )
            return 1

        missing_root = directory / "task-root-missing"
        missing_root.mkdir()
        result = _run_command(["--task-root", str(missing_root)])
        if (
            result.returncode != 2
            or "missing_conventional_input" not in result.stderr
        ):
            print(
                "self-test failed: missing conventional input did not fail once",
                file=sys.stderr,
            )
            return 1
        if (missing_root / "output").exists():
            print(
                "self-test failed: missing conventional input published output",
                file=sys.stderr,
            )
            return 1

    print(
        "self-test passed: LINE/POLYLINE/ARC/CIRCLE/SPLINE extracted, output "
        "deterministic, no-fit recorded as status=no_fit evidence, unsupported "
        "TEXT named layer/handle/geometry with exit 2, task-root receipt hashes "
        "matched, missing conventional input failed once without output, and "
        "the child interpreter resolved from PATH with an empty sys.executable"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dxf", nargs="?", help="architectural DXF to extract")
    parser.add_argument(
        "--layer-schema",
        help="JSON file or inline JSON mapping layer names to semantic roles",
    )
    parser.add_argument(
        "--output-schema",
        action="append",
        default=[],
        help="JSON Schema file or inline JSON; repeat for multiple schemas",
    )
    parser.add_argument(
        "--plan-view-rules",
        help="JSON file or inline JSON with turning-space diameter and solver bounds",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="normalized geometry JSON path (default: extracted_geometry.json)",
    )
    parser.add_argument(
        "--task-root",
        "--auto",
        dest="task_root",
        help=(
            "resolve conventional input/<plan>.dxf, input/layer_schema.json, "
            "input/plan_view_rules.json, input/output_schemas/*.json and "
            "write output/extracted_geometry.json plus an execution receipt"
        ),
    )
    parser.add_argument(
        "--receipt",
        help="execution receipt path (default: output/extraction_receipt.json)",
    )
    parser.add_argument(
        "--flattening-tolerance",
        type=float,
        default=0.5,
        help="curve flattening distance in drawing units",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "run the built-in positive, no-fit, unsupported-entity, task-root, "
            "and missing-input fixtures"
        ),
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.task_root is not None:
        if args.dxf or args.layer_schema or args.plan_view_rules or args.output_schema:
            parser.error(
                "--task-root cannot be combined with DXF or explicit input arguments"
            )
        try:
            run_task_root(
                Path(args.task_root),
                output=Path(args.output) if args.output else None,
                receipt=Path(args.receipt) if args.receipt else None,
            )
            return 0
        except ExtractionFailure as error:
            return _fail(error)
    if args.dxf is None and not (
        args.layer_schema or args.plan_view_rules or args.output_schema
    ):
        try:
            run_task_root(
                Path.cwd(),
                output=Path(args.output) if args.output else None,
                receipt=Path(args.receipt) if args.receipt else None,
            )
            return 0
        except ExtractionFailure as error:
            return _fail(error)
    missing = [
        flag
        for flag, value in (
            ("dxf", args.dxf),
            ("--layer-schema", args.layer_schema),
            ("--plan-view-rules", args.plan_view_rules),
            ("--output-schema", args.output_schema),
        )
        if not value
    ]
    if missing:
        parser.error("missing required input(s): " + ", ".join(missing))
    try:
        return _run(args)
    except ExtractionFailure as error:
        return _fail(error)


if __name__ == "__main__":
    raise SystemExit(main())
