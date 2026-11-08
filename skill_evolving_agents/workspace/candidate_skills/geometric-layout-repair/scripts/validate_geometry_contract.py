#!/usr/bin/env python3
"""Round-trip geometry-contract gate for repaired_layout.json and the DXF.

The consuming geometry contract is intentionally strict:

* JSON coordinate arrays are plan-view pairs with shape ``(N, 2)``.  A
  ``(N, 3)`` array is rejected before submission because the extra column is
  a different contract, not a harmless annotation.
* Every polygon and bbox ring is explicitly closed (last point equals first)
  and must be a valid shapely polygon.
* Every ``REPAIR-*`` DXF entity is reconstructed with ezdxf and cross-checked
  against the JSON geometry.

DXF vertices may be reconstructed as ``(N, 3)`` when elevation/OCS requires a
third component; that form is accepted only for DXF and is normalized to
plan-view coordinates for comparison.  Before any geometry reconstruction the
gate checks the required-output manifest: the layout, DXF, and every repeated
``--required-output`` path must exist and be non-empty.  Run with
``--self-test`` to exercise the manifest check, a malformed 3D-coordinate
fixture, and its corrected 2D counterpart.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import ezdxf
    from shapely.geometry import LineString, Polygon, box
    from shapely.validation import explain_validity
except ModuleNotFoundError as error:  # pragma: no cover - dependency guard
    print(
        f"error: missing required geometry library: {error.name}; "
        "install shapely and ezdxf before running this gate",
        file=sys.stderr,
    )
    raise SystemExit(2)

TOLERANCE = 1e-6
REQUIRED_LAYERS = {
    "REPAIR-ROOM",
    "REPAIR-DOOR",
    "REPAIR-WC",
    "REPAIR-LAV",
    "REPAIR-TUB",
    "REPAIR-GRABBAR",
}
POLYGON_KEYS = {
    "polygon",
    "polygons",
    "ring",
    "rings",
    "outline",
    "boundary",
    "shell",
    "exterior",
}
BBOX_KEYS = {"bbox", "bounding_box", "bounds", "extent"}
SEGMENT_KEYS = {"segment", "segments", "opening_segment", "line", "lines", "axis"}


@dataclass
class Geometry:
    element_id: str
    source: str
    kind: str
    points: list[tuple[float, ...]] = field(default_factory=list)
    center: tuple[float, ...] | None = None
    radius: float | None = None


@dataclass
class Violation:
    source: str
    element_id: str
    message: str

    def render(self) -> str:
        return f"{self.source}: element {self.element_id!r}: {self.message}"


class ContractError(ValueError):
    """A geometry element violates the consuming library contract."""


def _shape(points: list[tuple[float, ...]]) -> str:
    widths = {len(point) for point in points}
    if not widths:
        return "(0, 0)"
    if len(widths) == 1:
        return f"({len(points)}, {widths.pop()})"
    return f"({len(points)}, ragged)"


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _point(value: Any) -> tuple[float, ...] | None:
    if not isinstance(value, (list, tuple)):
        return None
    if len(value) not in (2, 3) or not all(_number(item) for item in value):
        return None
    return tuple(float(item) for item in value)


def _point_sequence(value: Any) -> list[tuple[float, ...]] | None:
    """Return a flat point sequence, accepting common JSON/GeoJSON wrappers."""
    if isinstance(value, dict):
        if all(key in value for key in ("minx", "miny", "maxx", "maxy")):
            return [
                (float(value["minx"]), float(value["miny"])),
                (float(value["maxx"]), float(value["maxy"])),
            ]
        for key in ("coordinates", "points", "ring", "exterior", "value"):
            if key in value:
                return _point_sequence(value[key])
        return None
    if not isinstance(value, (list, tuple)) or not value:
        return None
    if all(_number(item) for item in value):
        if len(value) in (2, 3):
            return [_point(value)]  # type: ignore[list-item]
        if len(value) % 2 == 0:
            return [
                (float(value[index]), float(value[index + 1]))
                for index in range(0, len(value), 2)
            ]
        return None
    points: list[tuple[float, ...]] = []
    for item in value:
        found = _point(item)
        if found is None:
            return None
        points.append(found)
    return points


def _rings(value: Any) -> list[list[tuple[float, ...]]] | None:
    """Return one or more rings from a polygon-like JSON value."""
    if isinstance(value, dict):
        if "coordinates" in value:
            return _rings(value["coordinates"])
        for key in ("exterior", "ring", "rings", "points", "value"):
            if key in value:
                return _rings(value[key])
        sequence = _point_sequence(value)
        return [sequence] if sequence else None
    if not isinstance(value, (list, tuple)) or not value:
        return None
    sequence = _point_sequence(value)
    if sequence is not None:
        return [sequence]
    rings: list[list[tuple[float, ...]]] = []
    for item in value:
        ring = _point_sequence(item)
        if ring is None:
            return None
        rings.append(ring)
    return rings or None


def _element_id(node: dict[str, Any], path: str) -> str:
    for key in ("id", "element_id", "fixture_id"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return path


def _check_json_shape(points: list[tuple[float, ...]], element_id: str) -> None:
    if any(len(point) != 2 for point in points):
        raise ContractError(
            "expected coordinate array shape (N, 2), got "
            f"{_shape(points)}; a 3-column (N, 3) array is not a valid "
            "repaired_layout.json coordinate array"
        )


def _closed(points: list[tuple[float, ...]]) -> bool:
    return len(points) > 1 and all(
        abs(first - second) <= TOLERANCE
        for first, second in zip(points[0], points[-1])
    )


def _validate_polygon(
    points: list[tuple[float, ...]], element_id: str, source: str
) -> None:
    if source.endswith(".json"):
        _check_json_shape(points, element_id)
    elif any(len(point) not in (2, 3) for point in points):
        raise ContractError(
            "expected coordinate array shape (N, 2) or (N, 3), got "
            f"{_shape(points)}"
        )
    if len(points) < 3:
        raise ContractError(
            "expected at least 3 vertices, got "
            f"{_shape(points)}"
        )
    if not _closed(points):
        raise ContractError(
            "expected an explicitly closed ring (first point equals last "
            f"point), got an open ring with shape {_shape(points)}"
        )
    if len(points) < 4:
        raise ContractError(
            "expected at least 3 distinct vertices plus a closing vertex, got "
            f"{_shape(points)}"
        )
    polygon = Polygon([point[:2] for point in points])
    if not polygon.is_valid:
        raise ContractError(
            "polygon is invalid (self-intersection or degenerate ring): "
            f"{explain_validity(polygon)}; shape {_shape(points)}"
        )


def _bbox_points(value: Any) -> list[tuple[float, ...]]:
    points = _point_sequence(value)
    if points is None:
        raise ContractError(
            "expected bbox coordinate array shape (2, 2) or (N, 2), got "
            "an unparseable value"
        )
    return points


def collect_json_geometry(document: Any) -> list[Geometry]:
    found: list[Geometry] = []
    source = "repaired_layout.json"

    def walk(node: Any, path: str, inherited_id: str | None = None) -> None:
        if isinstance(node, dict):
            element_id = _element_id(node, inherited_id or path or "root")
            center = node.get("center")
            diameter = node.get("diameter")
            radius = node.get("radius")
            if center is not None and (diameter is not None or radius is not None):
                found.append(
                    Geometry(
                        element_id=element_id,
                        source=source,
                        kind="circle",
                        center=tuple(center) if isinstance(center, (list, tuple)) else None,
                        radius=float(radius)
                        if radius is not None
                        else float(diameter) / 2.0,
                    )
                )
            for key, value in node.items():
                key_lower = key.casefold()
                child_path = f"{path}.{key}" if path else key
                child_id = _element_id(node, inherited_id or path or "root")
                if key_lower in BBOX_KEYS:
                    try:
                        bbox_points = _bbox_points(value)
                    except ContractError:
                        bbox_points = []
                    found.append(
                        Geometry(child_id, source, "bbox", points=bbox_points)
                    )
                elif key_lower in POLYGON_KEYS:
                    rings = _rings(value)
                    if rings is None:
                        found.append(
                            Geometry(
                                f"{child_id}.{key}",
                                source,
                                "polygon",
                                points=[],
                            )
                        )
                    else:
                        for index, ring in enumerate(rings):
                            suffix = f"[ring{index}]" if len(rings) > 1 else ""
                            found.append(
                                Geometry(
                                    f"{child_id}.{key}{suffix}",
                                    source,
                                    "polygon",
                                    points=ring,
                                )
                            )
                elif key_lower in SEGMENT_KEYS:
                    points = _point_sequence(value)
                    if points is not None and len(points) == 2:
                        found.append(
                            Geometry(
                                f"{child_id}.{key}",
                                source,
                                "segment",
                                points=points,
                            )
                        )
                    else:
                        found.append(
                            Geometry(
                                f"{child_id}.{key}",
                                source,
                                "segment",
                                points=points or [],
                            )
                        )
                elif key_lower in {"center", "diameter", "radius"} and center is not None:
                    continue
                else:
                    walk(value, child_path, child_id)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]", inherited_id)

    walk(document, "", None)
    return found


def _dxf_points(entity: Any) -> list[tuple[float, ...]]:
    entity_type = entity.dxftype()
    if entity_type == "LWPOLYLINE":
        return [(float(x), float(y)) for x, y in entity.get_points("xy")]
    if entity_type == "POLYLINE":
        return [
            (float(vertex.dxf.location.x), float(vertex.dxf.location.y), float(vertex.dxf.location.z))
            for vertex in entity.vertices
        ]
    return []


def collect_dxf_geometry(path: Path) -> list[Geometry]:
    try:
        document = ezdxf.readfile(path)
    except (OSError, ezdxf.DXFError) as error:
        raise ContractError(f"cannot read DXF: {error}") from error
    found: list[Geometry] = []
    sequence = 0
    for entity in document.modelspace():
        layer = str(entity.dxf.layer).upper()
        if not layer.startswith("REPAIR-"):
            continue
        sequence += 1
        entity_type = entity.dxftype()
        element_id = f"{layer}:{entity_type}#{sequence}"
        if entity_type in {"LWPOLYLINE", "POLYLINE"}:
            points = _dxf_points(entity)
            if entity_type == "LWPOLYLINE":
                closed_flag = bool(entity.closed)
            else:
                closed_flag = bool(entity.is_closed)
            if closed_flag and points and not _closed(points):
                points = [*points, points[0]]
            found.append(
                Geometry(element_id, path.name, "polygon", points=points)
            )
        elif entity_type == "LINE":
            found.append(
                Geometry(
                    element_id,
                    path.name,
                    "segment",
                    points=[
                        (
                            float(entity.dxf.start.x),
                            float(entity.dxf.start.y),
                        ),
                        (
                            float(entity.dxf.end.x),
                            float(entity.dxf.end.y),
                        ),
                    ],
                )
            )
        elif entity_type == "CIRCLE":
            found.append(
                Geometry(
                    element_id,
                    path.name,
                    "circle",
                    center=(
                        float(entity.dxf.center.x),
                        float(entity.dxf.center.y),
                    ),
                    radius=float(entity.dxf.radius),
                )
            )
    return found


def _ring_signature(points: list[tuple[float, ...]]) -> tuple[tuple[float, float], ...]:
    rounded = [(round(point[0], 6), round(point[1], 6)) for point in points]
    if len(rounded) > 1 and rounded[0] == rounded[-1]:
        rounded = rounded[:-1]
    if not rounded:
        return tuple()
    rotations = [rounded[index:] + rounded[:index] for index in range(len(rounded))]
    reversed_points = list(reversed(rounded))
    rotations += [
        reversed_points[index:] + reversed_points[:index]
        for index in range(len(reversed_points))
    ]
    return min(tuple(ring) for ring in rotations)


def _segment_signature(
    points: list[tuple[float, ...]],
) -> tuple[tuple[float, float], ...] | None:
    if len(points) != 2:
        return None
    left = (round(points[0][0], 6), round(points[0][1], 6))
    right = (round(points[1][0], 6), round(points[1][1], 6))
    return tuple(sorted((left, right)))


def _circle_signature(geometry: Geometry) -> tuple[float, float, float] | None:
    if geometry.center is None or geometry.radius is None:
        return None
    return (
        round(geometry.center[0], 6),
        round(geometry.center[1], 6),
        round(geometry.radius, 6),
    )


def validate_geometry(
    geometry: Geometry,
) -> None:
    if geometry.kind == "polygon":
        _validate_polygon(geometry.points, geometry.element_id, geometry.source)
    elif geometry.kind == "bbox":
        if geometry.source.endswith(".json"):
            _check_json_shape(geometry.points, geometry.element_id)
        if len(geometry.points) == 2:
            (x1, y1), (x2, y2) = geometry.points[0][:2], geometry.points[1][:2]
            if abs(x1 - x2) <= TOLERANCE or abs(y1 - y2) <= TOLERANCE:
                raise ContractError(
                    "bbox has zero width or height; expected two distinct "
                    f"opposite corners, got {_shape(geometry.points)}"
                )
            geometry.points = list(
                box(
                    min(x1, x2),
                    min(y1, y2),
                    max(x1, x2),
                    max(y1, y2),
                ).exterior.coords
            )
        _validate_polygon(geometry.points, geometry.element_id, geometry.source)
    elif geometry.kind == "segment":
        if len(geometry.points) != 2:
            raise ContractError(
                "expected segment coordinate array shape (2, 2), got "
                f"{_shape(geometry.points)}"
            )
        if geometry.source.endswith(".json"):
            _check_json_shape(geometry.points, geometry.element_id)
        if LineString([point[:2] for point in geometry.points]).length <= TOLERANCE:
            raise ContractError(
                "segment has zero length; expected two distinct endpoints, got "
                f"{_shape(geometry.points)}"
            )
    elif geometry.kind == "circle":
        if geometry.center is None or len(geometry.center) not in (2, 3):
            raise ContractError(
                "expected circle center shape (2,) or (3,), got "
                f"{_shape([geometry.center] if geometry.center else [])}"
            )
        if geometry.source.endswith(".json") and len(geometry.center) != 2:
            raise ContractError(
                "expected circle center shape (2,), got "
                f"{_shape([geometry.center])}"
            )
        if geometry.radius is None or geometry.radius <= TOLERANCE:
            raise ContractError("circle radius must be positive")
    else:  # pragma: no cover - internal guard
        raise ContractError(f"unknown geometry kind {geometry.kind!r}")


def validate_paths(layout_path: Path, dxf_path: Path) -> list[Violation]:
    violations: list[Violation] = []
    json_geometry: list[Geometry] | None = None
    dxf_geometry: list[Geometry] | None = None

    try:
        document = json.loads(layout_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        violations.append(
            Violation(
                "repaired_layout.json",
                "root",
                f"cannot read JSON: {error}",
            )
        )
    else:
        try:
            json_geometry = collect_json_geometry(document)
        except ContractError as error:
            violations.append(
                Violation("repaired_layout.json", "root", str(error))
            )
        else:
            if not json_geometry:
                violations.append(
                    Violation(
                        "repaired_layout.json",
                        "root",
                        "no polygon, bbox, segment, or turning-space geometry found",
                    )
                )
            else:
                for geometry in json_geometry:
                    try:
                        validate_geometry(geometry)
                    except ContractError as error:
                        violations.append(
                            Violation(
                                geometry.source,
                                geometry.element_id,
                                str(error),
                            )
                        )

    try:
        dxf_geometry = collect_dxf_geometry(dxf_path)
    except ContractError as error:
        violations.append(Violation(dxf_path.name, "root", str(error)))
    else:
        if not dxf_geometry:
            violations.append(
                Violation(
                    dxf_path.name,
                    "root",
                    "no REPAIR-* entities found",
                )
            )
        else:
            for geometry in dxf_geometry:
                try:
                    validate_geometry(geometry)
                except ContractError as error:
                    violations.append(
                        Violation(
                            geometry.source,
                            geometry.element_id,
                            str(error),
                        )
                    )

    if json_geometry is not None and dxf_geometry is not None:
        json_polygons = [
            geometry
            for geometry in json_geometry
            if geometry.kind in {"polygon", "bbox"}
        ]
        dxf_polygons = [
            geometry for geometry in dxf_geometry if geometry.kind == "polygon"
        ]
        dxf_rings = {
            _ring_signature(geometry.points): geometry for geometry in dxf_polygons
        }
        for geometry in json_polygons:
            signature = _ring_signature(geometry.points)
            if signature not in dxf_rings:
                violations.append(
                    Violation(
                        geometry.source,
                        geometry.element_id,
                        "round-trip mismatch: no closed REPAIR-* DXF polygon "
                        f"matches shape {_shape(geometry.points)}",
                    )
                )
        json_rings = {
            _ring_signature(geometry.points) for geometry in json_polygons
        }
        for geometry in dxf_polygons:
            if geometry.element_id.split(":", 1)[0] not in REQUIRED_LAYERS:
                continue
            if _ring_signature(geometry.points) not in json_rings:
                violations.append(
                    Violation(
                        geometry.source,
                        geometry.element_id,
                        "round-trip mismatch: required REPAIR-* DXF polygon "
                        f"has no matching JSON geometry (shape {_shape(geometry.points)})",
                    )
                )

        json_segments = {
            _segment_signature(geometry.points)
            for geometry in json_geometry
            if geometry.kind == "segment"
        }
        dxf_segments = {
            _segment_signature(geometry.points)
            for geometry in dxf_geometry
            if geometry.kind == "segment"
        }
        for geometry in json_geometry:
            if geometry.kind != "segment":
                continue
            if _segment_signature(geometry.points) not in dxf_segments:
                violations.append(
                    Violation(
                        geometry.source,
                        geometry.element_id,
                        "round-trip mismatch: no REPAIR-* DXF line matches "
                        f"segment shape {_shape(geometry.points)}",
                    )
                )
        for signature in dxf_segments - json_segments:
            if signature is None:
                continue
            violations.append(
                Violation(
                    dxf_path.name,
                    "REPAIR-* line",
                    "round-trip mismatch: DXF line has no matching JSON segment",
                )
            )

        json_circles = {
            _circle_signature(geometry)
            for geometry in json_geometry
            if geometry.kind == "circle"
        }
        dxf_circles = {
            _circle_signature(geometry)
            for geometry in dxf_geometry
            if geometry.kind == "circle"
        }
        for geometry in json_geometry:
            if geometry.kind != "circle":
                continue
            if _circle_signature(geometry) not in dxf_circles:
                violations.append(
                    Violation(
                        geometry.source,
                        geometry.element_id,
                        "round-trip mismatch: no REPAIR-* DXF CIRCLE matches "
                        "the JSON turning space",
                    )
                )
        for signature in dxf_circles - json_circles:
            if signature is None:
                continue
            violations.append(
                Violation(
                    dxf_path.name,
                    "REPAIR-* circle",
                    "round-trip mismatch: DXF circle has no matching JSON "
                    "turning space",
                )
            )

    return violations


def _write_fixture(directory: Path, three_dimensional: bool) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    room = [
        [0.0, 0.0, 0.0] if three_dimensional else [0.0, 0.0],
        [4.0, 0.0, 0.0] if three_dimensional else [4.0, 0.0],
        [4.0, 3.0, 0.0] if three_dimensional else [4.0, 3.0],
        [0.0, 3.0, 0.0] if three_dimensional else [0.0, 3.0],
        [0.0, 0.0, 0.0] if three_dimensional else [0.0, 0.0],
    ]
    layout = {
        "room": {"id": "ROOM-1", "polygon": room},
        "fixtures": [
            {
                "id": "WC-1",
                "type": "wc",
                "bbox": [[0.5, 0.5], [1.2, 1.5]],
            }
        ],
        "doors": [
            {
                "id": "D-1",
                "opening_segment": [[2.0, 0.0], [2.8, 0.0]],
            }
        ],
        "grab_bars": [
            {
                "id": "GB-1",
                "segment": [[0.6, 1.6], [1.2, 1.6]],
            }
        ],
        "turning_space": {
            "id": "TS-1",
            "center": [2.5, 1.5],
            "diameter": 1.5,
        },
    }
    layout_path = directory / "repaired_layout.json"
    layout_path.write_text(json.dumps(layout), encoding="utf-8")

    document = ezdxf.new("R2010")
    modelspace = document.modelspace()
    modelspace.add_lwpolyline(
        [(point[0], point[1]) for point in room],
        close=True,
        dxfattribs={"layer": "REPAIR-ROOM"},
    )
    modelspace.add_lwpolyline(
        [(0.5, 0.5), (1.2, 0.5), (1.2, 1.5), (0.5, 1.5)],
        close=True,
        dxfattribs={"layer": "REPAIR-WC"},
    )
    modelspace.add_line(
        (2.0, 0.0),
        (2.8, 0.0),
        dxfattribs={"layer": "REPAIR-DOOR"},
    )
    modelspace.add_line(
        (0.6, 1.6),
        (1.2, 1.6),
        dxfattribs={"layer": "REPAIR-GRABBAR"},
    )
    modelspace.add_circle(
        (2.5, 1.5),
        0.75,
        dxfattribs={"layer": "REPAIR-CLEARANCE"},
    )
    dxf_path = directory / "repaired_plan.dxf"
    document.saveas(dxf_path)
    return layout_path, dxf_path


def check_required_outputs(paths: list[Path]) -> list[str]:
    """Report required deliverables that are absent, not files, or empty.

    This manifest check runs before any geometry reconstruction so a run
    cannot spend another inspect-modify cycle while a required artifact is
    still unwritten or empty.  It does not parse files; parse and round-trip
    checks belong to :func:`validate_paths`.
    """
    problems: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            size = resolved.stat().st_size
        except OSError:
            problems.append(f"{resolved}: required output is missing")
            continue
        if not resolved.is_file():
            problems.append(f"{resolved}: required output is not a regular file")
        elif size <= 0:
            problems.append(f"{resolved}: required output is empty")
    return problems


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="geometry-contract-") as temporary:
        directory = Path(temporary)
        valid_layout, valid_dxf = _write_fixture(directory, three_dimensional=False)
        manifest_problems = check_required_outputs([valid_layout, valid_dxf])
        if manifest_problems:
            print(
                "self-test failed: complete fixture was reported missing or empty",
                file=sys.stderr,
            )
            for problem in manifest_problems:
                print(problem, file=sys.stderr)
            return 1
        missing_output = directory / "absent_artifact.json"
        empty_output = directory / "empty_artifact.dxf"
        empty_output.write_bytes(b"")
        manifest_problems = check_required_outputs(
            [missing_output, empty_output]
        )
        if len(manifest_problems) != 2 or "missing" not in manifest_problems[0] or "empty" not in manifest_problems[1]:
            print(
                "self-test failed: manifest did not report missing and empty outputs",
                file=sys.stderr,
            )
            for problem in manifest_problems:
                print(problem, file=sys.stderr)
            return 1
        valid = validate_paths(valid_layout, valid_dxf)
        if valid:
            print("self-test failed: corrected (N, 2) fixture was rejected", file=sys.stderr)
            for violation in valid:
                print(violation.render(), file=sys.stderr)
            return 1

        malformed_layout, malformed_dxf = _write_fixture(
            directory / "malformed", three_dimensional=True
        )
        malformed = validate_paths(malformed_layout, malformed_dxf)
        diagnostics = "\n".join(violation.render() for violation in malformed)
        if not malformed:
            print(
                "self-test failed: malformed (N, 3) fixture was accepted",
                file=sys.stderr,
            )
            return 1
        required = ("ROOM-1", "(N, 2)", "(5, 3)")
        missing = [value for value in required if value not in diagnostics]
        if missing:
            print(
                "self-test failed: diagnostic omitted " + ", ".join(missing),
                file=sys.stderr,
            )
            print(diagnostics, file=sys.stderr)
            return 1
    print("self-test passed: (N, 3) rejected with a precise diagnostic; (N, 2) accepted")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "layout",
        nargs="?",
        type=Path,
        default=Path("repaired_layout.json"),
        help="written repaired_layout.json",
    )
    parser.add_argument(
        "dxf",
        nargs="?",
        type=Path,
        default=Path("repaired_plan.dxf"),
        help="written repaired_plan.dxf",
    )
    parser.add_argument(
        "--required-output",
        action="append",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "additional required deliverable; repeat for each output. The "
            "layout and DXF arguments are always checked first"
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="exercise the malformed 3D and corrected 2D fixtures",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    manifest = [args.layout, args.dxf, *(args.required_output or [])]
    problems = check_required_outputs(manifest)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(
            "required-output manifest failed: write the missing or empty "
            "deliverables before further geometry inspection or repair",
            file=sys.stderr,
        )
        return 1
    violations = validate_paths(args.layout, args.dxf)
    if violations:
        for violation in violations:
            print(violation.render(), file=sys.stderr)
        print(
            "geometry contract failed: do not invoke the objective verifier "
            "or submit these outputs",
            file=sys.stderr,
        )
        return 1
    print(
        "geometry contract passed: JSON and REPAIR-* DXF geometry are "
        "round-trip consistent"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
