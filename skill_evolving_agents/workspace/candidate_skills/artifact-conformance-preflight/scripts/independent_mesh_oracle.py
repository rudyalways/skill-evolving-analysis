#!/usr/bin/env python3
"""Independent source-scene mesh oracle.

Recompute expected primitive assembly and world transforms from the task source
scene without using the exporter, its manifest, an intermediate mesh, or the
submitted artifact as the expectation.  Compare every mapped exported mesh
against that oracle and fail closed on primitive-assembly, hierarchy, or
transform defects.

Standard library only.  The transformation path here composes 4x4 matrices;
it deliberately does not reuse the preflight or exporter per-vertex formulas.

Usage:
    python3 scripts/independent_mesh_oracle.py SOURCE_SCENE ARTIFACT \
        --spec SPEC.json [--report REPORT.json]

Exit codes: 0 clean, 1 violation or unverifiable constraint, 2 input error.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

EPS = 1e-9
SUPPORTED_PRIMITIVES = {"box", "sphere", "cylinder", "plane"}
SELF_REFERENTIAL_TOKEN = re.compile(
    r"\b(producer|exporter|submitted|submission|manifest|intermediate|"
    r"self[-_ ]?referential|same[-_ ](?:primitive|transform|code|path|builder|exporter)|"
    r"shared[-_ ]?(?:primitive|coordinates?|transform|code|path)|expected[-_ ]coordinates?)\b",
    re.IGNORECASE,
)


def _acceptance_tolerance(spec: Dict[str, Any]) -> Any:
    """Return the task-derived threshold; a looser local tolerance never wins."""
    if "acceptance_tolerance" in spec:
        return spec.get("acceptance_tolerance")
    return spec.get("tolerance")


def _independence_evidence(spec: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Validate that the oracle path is separate from the producer's code path."""
    candidate = spec.get("independence_evidence")
    if candidate is None:
        oracle = spec.get("oracle")
        if isinstance(oracle, dict):
            candidate = oracle
    if candidate is None:
        provenance = spec.get("provenance")
        if isinstance(provenance, dict):
            candidate = provenance
    if isinstance(candidate, dict):
        if candidate.get("self_referential") is True:
            return None, "oracle is declared self-referential and cannot prove geometry independence"
        if candidate.get("independent_of_exporter") is not True:
            return None, (
                "independence evidence does not establish a second derivation path; "
                "record independent_of_exporter: true with a separate reader and transform_path"
            )
        reader = candidate.get("reader")
        transform_path = candidate.get("transform_path")
        if not isinstance(reader, str) or not reader.strip():
            return None, "independence evidence has no separate source reader"
        if not isinstance(transform_path, str) or not transform_path.strip():
            return None, "independence evidence has no separate transform path"
        for label, value in (("reader", reader), ("transform_path", transform_path)):
            if SELF_REFERENTIAL_TOKEN.search(value):
                return None, (
                    f"independence evidence {label} names the producer, exporter, submitted "
                    "artifact, or the same primitive/transform path, so the oracle is self-referential"
                )
        return {"reader": reader, "transform_path": transform_path, "independent_of_exporter": True}, None
    if isinstance(candidate, str) and candidate.strip():
        if SELF_REFERENTIAL_TOKEN.search(candidate):
            return None, "independence evidence names the producer or the same derivation path"
        return {"evidence": candidate, "independent_of_exporter": True}, None
    return None, (
        "independence evidence is absent; record a separate reader and transform_path "
        "with independent_of_exporter: true"
    )


def _unverifiable_report(
    source_scene: Path,
    artifact: Path,
    spec: Dict[str, Any],
    reason: str,
    tolerance: Any,
) -> Dict[str, Any]:
    return {
        "status": "violations",
        "source_scene": str(source_scene),
        "artifact": str(artifact),
        "spec_revision": spec.get("spec_revision"),
        "tolerance": tolerance,
        "metric": str(spec.get("metric", "max_nearest")),
        "oracle": {
            "method": "independent source-scene primitive assembly and world-transform recomputation",
            "reader": "direct source-scene JSON primitive and node reader",
            "transform_path": "4x4 matrix composition applied to source primitives, then parent node chain",
            "independent_of_exporter": False,
            "frame": "scene_root",
        },
        "counts": {"meshes": 0, "mapped_primitives": 0, "source_primitives": 0, "passed": 0, "violations": 0, "unverifiable": 1},
        "meshes": [],
        "violations": [],
        "unverifiable": [{"invariant_class": "geometry_conformance", "reason": reason}],
    }


class OracleError(Exception):
    """The source scene, artifact, or tolerance spec cannot be interpreted."""


# ---------------------------------------------------------------------------
# Matrix and vector helpers (independent composition path)
# ---------------------------------------------------------------------------


def _vec(value: Any, default: Sequence[float]) -> List[float]:
    if value is None:
        return [float(item) for item in default]
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise OracleError("expected a three-number vector")
    return [float(item) for item in value]


def _mat_identity() -> List[List[float]]:
    return [[1.0 if row == column else 0.0 for column in range(4)] for row in range(4)]


def _mat_mul(left: List[List[float]], right: List[List[float]]) -> List[List[float]]:
    return [
        [sum(left[row][k] * right[k][column] for k in range(4)) for column in range(4)]
        for row in range(4)
    ]


def _mat_apply(matrix: List[List[float]], point: Sequence[float]) -> List[float]:
    source = [float(point[0]), float(point[1]), float(point[2]), 1.0]
    return [
        sum(matrix[row][column] * source[column] for column in range(4))
        for row in range(3)
    ]


def _rot_x(angle: float) -> List[List[float]]:
    cosine, sine = math.cos(angle), math.sin(angle)
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, cosine, -sine, 0.0],
        [0.0, sine, cosine, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _rot_y(angle: float) -> List[List[float]]:
    cosine, sine = math.cos(angle), math.sin(angle)
    return [
        [cosine, 0.0, sine, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [-sine, 0.0, cosine, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _rot_z(angle: float) -> List[List[float]]:
    cosine, sine = math.cos(angle), math.sin(angle)
    return [
        [cosine, -sine, 0.0, 0.0],
        [sine, cosine, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _trs_matrix(
    position: Sequence[float],
    rotation_euler_deg: Sequence[float],
    scale: Sequence[float],
) -> List[List[float]]:
    """Build T * Rz * Ry * Rx * S using 4x4 matrix composition."""
    rx, ry, rz = [math.radians(float(value)) for value in rotation_euler_deg]
    rotation = _mat_mul(_mat_mul(_rot_z(rz), _rot_y(ry)), _rot_x(rx))
    scale_matrix = _mat_identity()
    for index in range(3):
        scale_matrix[index][index] = float(scale[index])
    translation = _mat_identity()
    translation[0][3] = float(position[0])
    translation[1][3] = float(position[1])
    translation[2][3] = float(position[2])
    return _mat_mul(translation, _mat_mul(rotation, scale_matrix))


def _matrix_from_value(value: Any) -> List[List[float]]:
    if isinstance(value, list) and len(value) == 16 and all(isinstance(item, (int, float)) for item in value):
        # glTF-style column-major 4x4.
        return [[float(value[column * 4 + row]) for column in range(4)] for row in range(4)]
    if isinstance(value, list) and len(value) in {3, 4}:
        rows = value[:3]
        if all(isinstance(row, list) and len(row) in {3, 4} for row in rows):
            matrix = _mat_identity()
            for row in range(3):
                for column in range(3):
                    matrix[row][column] = float(rows[row][column])
                if len(rows[row]) == 4:
                    matrix[row][3] = float(rows[row][3])
            return matrix
    raise OracleError("matrix must be 16 column-major values or a 3/4-row matrix")


# ---------------------------------------------------------------------------
# Source-scene reading
# ---------------------------------------------------------------------------


def _node_table(document: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = document.get("nodes") or document.get("objects") or []
    if isinstance(raw, dict):
        table: Dict[str, Dict[str, Any]] = {}
        for node_id, node in raw.items():
            if not isinstance(node, dict):
                raise OracleError(f"node {node_id!r} must be an object")
            entry = dict(node)
            entry.setdefault("id", str(node_id))
            table[str(node_id)] = entry
        return table
    if isinstance(raw, list):
        table = {}
        for index, node in enumerate(raw):
            if not isinstance(node, dict):
                raise OracleError(f"node[{index}] must be an object")
            node_id = node.get("id")
            if node_id is None:
                raise OracleError(f"node[{index}] has no id")
            table[str(node_id)] = node
        return table
    raise OracleError("scene nodes must be an array or object")


def _node_world(
    node_id: Optional[str],
    nodes: Dict[str, Dict[str, Any]],
    cache: Dict[str, List[List[float]]],
    stack: Tuple[str, ...] = (),
) -> List[List[float]]:
    if not node_id:
        return _mat_identity()
    node_id = str(node_id)
    if node_id in cache:
        return cache[node_id]
    if node_id in stack:
        raise OracleError(f"scene node cycle at {node_id!r}")
    node = nodes.get(node_id)
    if node is None:
        raise OracleError(f"scene node {node_id!r} is not declared")
    if "matrix" in node:
        local = _matrix_from_value(node.get("matrix"))
    else:
        local = _trs_matrix(
            _vec(node.get("position"), [0.0, 0.0, 0.0]),
            _vec(node.get("rotation_euler_deg"), [0.0, 0.0, 0.0]),
            _vec(node.get("scale"), [1.0, 1.0, 1.0]),
        )
    parent = node.get("parent")
    world = _mat_mul(_node_world(str(parent) if parent else None, nodes, cache, stack + (node_id,)), local)
    cache[node_id] = world
    return world


def _primitive_local_matrix(primitive: Dict[str, Any]) -> List[List[float]]:
    if "matrix" in primitive:
        return _matrix_from_value(primitive.get("matrix"))
    return _trs_matrix(
        _vec(primitive.get("position"), [0.0, 0.0, 0.0]),
        _vec(primitive.get("rotation_euler_deg"), [0.0, 0.0, 0.0]),
        _vec(primitive.get("scale"), [1.0, 1.0, 1.0]),
    )


def _primitive_chain(primitive: Dict[str, Any], nodes: Dict[str, Dict[str, Any]]) -> List[str]:
    chain: List[str] = []
    node_id = primitive.get("node") or primitive.get("parent")
    while node_id:
        node_id = str(node_id)
        if node_id in chain:
            raise OracleError(f"scene node cycle at {node_id!r}")
        chain.append(node_id)
        node = nodes.get(node_id)
        if node is None:
            raise OracleError(f"scene node {node_id!r} is not declared")
        node_id = node.get("parent")
    return chain


def _base_primitive(primitive: Dict[str, Any]) -> Tuple[List[List[float]], List[List[int]]]:
    kind = primitive.get("type")
    if kind == "box":
        sx, sy, sz = _vec(primitive.get("size") or primitive.get("dimensions"), [1.0, 1.0, 1.0])
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
        return vertices, faces
    if kind == "sphere":
        radius = float(primitive.get("radius", 1.0))
        segments = int(primitive.get("segments", 16))
        rings = int(primitive.get("rings", 8))
        if radius <= 0 or segments < 3 or rings < 2:
            raise OracleError("sphere needs positive radius, at least 3 segments, and at least 2 rings")
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
        return vertices, faces
    if kind == "cylinder":
        radius = float(primitive.get("radius", 1.0))
        height = float(primitive.get("height", 1.0))
        segments = int(primitive.get("segments", 16))
        if radius <= 0 or height <= 0 or segments < 3:
            raise OracleError("cylinder needs positive radius, height, and at least 3 segments")
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
        return vertices, faces
    if kind == "plane":
        width = float(primitive.get("width", 1.0))
        depth = float(primitive.get("depth", 1.0))
        if width <= 0 or depth <= 0:
            raise OracleError("plane needs positive width and depth")
        x, z = width / 2.0, depth / 2.0
        vertices = [[-x, 0.0, -z], [x, 0.0, -z], [x, 0.0, z], [-x, 0.0, z]]
        faces = [[0, 1, 2], [0, 2, 3]]
        return vertices, faces
    raise OracleError(f"unsupported source primitive type {kind!r}")


def _build_source_primitive(
    primitive: Dict[str, Any],
    nodes: Dict[str, Dict[str, Any]],
    node_cache: Dict[str, List[List[float]]],
    ignore_parents: bool = False,
) -> Dict[str, Any]:
    vertices, faces = _base_primitive(primitive)
    world = _mat_identity() if ignore_parents else _node_world(
        str(primitive.get("node") or primitive.get("parent")) if (primitive.get("node") or primitive.get("parent")) else None,
        nodes,
        node_cache,
    )
    local = _primitive_local_matrix(primitive)
    matrix = _mat_mul(world, local)
    moved = [_mat_apply(matrix, vertex) for vertex in vertices]
    return {
        "name": str(primitive.get("id") or primitive.get("name") or "primitive"),
        "vertices": moved,
        "faces": [list(face) for face in faces],
    }


# ---------------------------------------------------------------------------
# Surface sampling and distance
# ---------------------------------------------------------------------------


def _triangles(mesh: Dict[str, Any]) -> List[Tuple[List[float], List[float], List[float]]]:
    vertices = mesh.get("vertices", [])
    triangles = []
    for face in mesh.get("faces", []):
        if not isinstance(face, list) or len(face) < 3:
            continue
        for index in range(1, len(face) - 1):
            try:
                a, b, c = vertices[face[0]], vertices[face[index]], vertices[face[index + 1]]
            except (IndexError, TypeError):
                continue
            triangles.append((a, b, c))
    return triangles


def _triangle_area(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
    ab = [b[index] - a[index] for index in range(3)]
    ac = [c[index] - a[index] for index in range(3)]
    cross = [
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    ]
    return 0.5 * math.sqrt(sum(component * component for component in cross))


def _surface_samples(mesh: Dict[str, Any], budget: int) -> List[List[float]]:
    triangles = _triangles(mesh)
    if not triangles:
        return []
    per_triangle = max(7, budget // max(1, len(triangles)))
    samples: List[List[float]] = []
    golden, silver = 0.6180339887498949, 0.4142135623730950
    for triangle_index, (a, b, c) in enumerate(triangles):
        samples.extend([list(a), list(b), list(c)])
        samples.append([(a[i] + b[i]) / 2.0 for i in range(3)])
        samples.append([(b[i] + c[i]) / 2.0 for i in range(3)])
        samples.append([(c[i] + a[i]) / 2.0 for i in range(3)])
        samples.append([(a[i] + b[i] + c[i]) / 3.0 for i in range(3)])
        for step in range(per_triangle):
            u = (step * golden + triangle_index * silver) % 1.0
            v = (step * silver + triangle_index * golden) % 1.0
            if u + v > 1.0:
                u, v = 1.0 - u, 1.0 - v
            samples.append([a[i] + u * (b[i] - a[i]) + v * (c[i] - a[i]) for i in range(3)])
    if len(samples) > budget * 3:
        stride = max(1, len(samples) // (budget * 3))
        samples = samples[::stride]
    return samples


def _point_triangle_distance_sq(point: Sequence[float], a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
    ab = [b[i] - a[i] for i in range(3)]
    ac = [c[i] - a[i] for i in range(3)]
    ap = [point[i] - a[i] for i in range(3)]
    d1 = sum(ab[i] * ap[i] for i in range(3))
    d2 = sum(ac[i] * ap[i] for i in range(3))
    if d1 <= 0 and d2 <= 0:
        return sum(ap[i] * ap[i] for i in range(3))
    bp = [point[i] - b[i] for i in range(3)]
    d3 = sum(ab[i] * bp[i] for i in range(3))
    d4 = sum(ac[i] * bp[i] for i in range(3))
    if d3 >= 0 and d4 <= d3:
        return sum(bp[i] * bp[i] for i in range(3))
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        denominator = d1 - d3
        if abs(denominator) <= EPS:
            return sum(ap[i] * ap[i] for i in range(3))
        v = d1 / denominator
        closest = [a[i] + v * ab[i] for i in range(3)]
        return sum((point[i] - closest[i]) ** 2 for i in range(3))
    cp = [point[i] - c[i] for i in range(3)]
    d5 = sum(ab[i] * cp[i] for i in range(3))
    d6 = sum(ac[i] * cp[i] for i in range(3))
    if d6 >= 0 and d5 <= d6:
        return sum(cp[i] * cp[i] for i in range(3))
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        denominator = d2 - d6
        if abs(denominator) <= EPS:
            return sum(ap[i] * ap[i] for i in range(3))
        w = d2 / denominator
        closest = [a[i] + w * ac[i] for i in range(3)]
        return sum((point[i] - closest[i]) ** 2 for i in range(3))
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        denominator = (d4 - d3) + (d5 - d6)
        if abs(denominator) <= EPS:
            return sum(bp[i] * bp[i] for i in range(3))
        w = (d4 - d3) / denominator
        closest = [b[i] + w * (c[i] - b[i]) for i in range(3)]
        return sum((point[i] - closest[i]) ** 2 for i in range(3))
    denominator = va + vb + vc
    if abs(denominator) <= EPS:
        return min(
            sum(ap[i] * ap[i] for i in range(3)),
            sum(bp[i] * bp[i] for i in range(3)),
            sum(cp[i] * cp[i] for i in range(3)),
        )
    v = vb / denominator
    w = vc / denominator
    closest = [a[i] + ab[i] * v + ac[i] * w for i in range(3)]
    return sum((point[i] - closest[i]) ** 2 for i in range(3))


def _nearest_distances(points: Sequence[Sequence[float]], mesh: Dict[str, Any], tolerance: float) -> Tuple[List[float], float]:
    triangles = _triangles(mesh)
    if not triangles or not points:
        return [], 0.0
    tile = max(0.0, float(tolerance))
    distances = []
    for point in points:
        best = float("inf")
        for a, b, c in triangles:
            # Cheap lower bound on the point-to-AABB-of-triangle distance.
            if tile > 0.0:
                near = 0.0
                for axis in range(3):
                    low = min(a[axis], b[axis], c[axis])
                    high = max(a[axis], b[axis], c[axis])
                    gap = max(low - point[axis], 0.0, point[axis] - high)
                    near += gap * gap
                if near > best:
                    continue
            distance_sq = _point_triangle_distance_sq(point, a, b, c)
            if distance_sq < best:
                best = distance_sq
        distances.append(math.sqrt(best))
    return distances, 0.0


def _mesh_stats(mesh: Dict[str, Any]) -> Dict[str, Any]:
    triangles = _triangles(mesh)
    used = set()
    for face in mesh.get("faces", []):
        for index in face:
            if isinstance(index, int):
                used.add(index)
    points = [mesh["vertices"][index] for index in sorted(used) if 0 <= index < len(mesh.get("vertices", []))]
    if not points:
        points = [vertex for vertex in mesh.get("vertices", [])]
    if not points:
        raise OracleError("surface has no vertices")
    minimum = [min(point[i] for point in points) for i in range(3)]
    maximum = [max(point[i] for point in points) for i in range(3)]
    size = [maximum[i] - minimum[i] for i in range(3)]
    area = 0.0
    weighted = [0.0, 0.0, 0.0]
    for a, b, c in triangles:
        triangle_area = _triangle_area(a, b, c)
        area += triangle_area
        for i in range(3):
            weighted[i] += triangle_area * (a[i] + b[i] + c[i]) / 3.0
    centroid = [weighted[i] / area for i in range(3)] if area > EPS else [
        sum(point[i] for point in points) / len(points) for i in range(3)
    ]
    return {
        "vertex_count": len(mesh.get("vertices", [])),
        "triangle_count": len(mesh.get("faces", [])),
        "bounds": {
            "min": [round(value, 6) for value in minimum],
            "max": [round(value, 6) for value in maximum],
            "size": [round(value, 6) for value in size],
            "center": [round((minimum[i] + maximum[i]) / 2.0, 6) for i in range(3)],
        },
        "centroid": [round(value, 6) for value in centroid],
    }


def _components(mesh: Dict[str, Any]) -> List[Dict[str, Any]]:
    vertices = mesh.get("vertices", [])
    faces = [face for face in mesh.get("faces", []) if isinstance(face, list) and len(face) >= 3]
    if not faces:
        return []
    parent = list(range(len(vertices)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    canonical: Dict[Tuple[int, int, int], int] = {}
    for face in faces:
        indices = [int(index) for index in face if isinstance(index, int)]
        for index in indices:
            if not 0 <= index < len(vertices):
                continue
            key = tuple(round(vertices[index][axis], 6) for axis in range(3))
            if key in canonical:
                union(index, canonical[key])
            else:
                canonical[key] = index
        for index in indices[1:]:
            if 0 <= indices[0] < len(vertices) and 0 <= index < len(vertices):
                union(indices[0], index)
    groups: Dict[int, List[List[int]]] = {}
    for face in faces:
        indices = [int(index) for index in face if isinstance(index, int) and 0 <= index < len(vertices)]
        if not indices:
            continue
        root = find(indices[0])
        groups.setdefault(root, []).append(face)
    components = []
    for root, component_faces in sorted(groups.items()):
        components.append({"name": f"component-{root}", "vertices": vertices, "faces": component_faces})
    return components


# ---------------------------------------------------------------------------
# Artifact readers
# ---------------------------------------------------------------------------


def _obj_faces(parts: Sequence[str], vertex_count: int) -> List[int]:
    polygon = []
    for token in parts:
        piece = token.split("/")[0]
        if not piece:
            continue
        index = int(piece)
        polygon.append(index - 1 if index > 0 else vertex_count + index)
    return polygon


def _read_obj_groups(path: Path) -> List[Dict[str, Any]]:
    vertices: List[List[float]] = []
    groups: Dict[str, List[List[int]]] = {}
    order: List[str] = []

    def start(name: str) -> None:
        if name not in groups:
            groups[name] = []
            order.append(name)

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        tag = parts[0]
        if tag == "v" and len(parts) >= 4:
            vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
        elif tag in {"o", "g"}:
            start(" ".join(parts[1:]).strip() or path.stem)
        elif tag == "f":
            if not order:
                start(path.stem)
            polygon = _obj_faces(parts[1:], len(vertices))
            if len(polygon) >= 3:
                for index in range(1, len(polygon) - 1):
                    groups[order[-1]].append([polygon[0], polygon[index], polygon[index + 1]])
    return [
        {"name": name, "vertices": [list(vertex) for vertex in vertices], "faces": faces, "format": "obj"}
        for name, faces in ((name, groups[name]) for name in order)
        if faces
    ]


def _read_glb(path: Path) -> List[Dict[str, Any]]:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"glTF":
        raise OracleError(f"{path} is not a GLB file")
    offset = 12
    json_document: Optional[Dict[str, Any]] = None
    binary = b""
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "little")
        chunk_type = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        offset += 8 + length
        if chunk_type[:4] == b"JSON":
            json_document = json.loads(payload.rstrip(b" \t\r\n\x00").decode("utf-8"))
        elif chunk_type[:4] == b"BIN\x00":
            binary = payload
    if json_document is None:
        raise OracleError(f"{path} has no JSON chunk")
    document = json_document
    accessors = document.get("accessors") or []
    buffer_views = document.get("bufferViews") or []
    component_format = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
    type_width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

    def read_accessor(index: int) -> List[Any]:
        accessor = accessors[index]
        view = buffer_views[accessor["bufferView"]]
        start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
        count = int(accessor["count"])
        width = type_width[accessor["type"]]
        fmt, size = component_format[int(accessor["componentType"])]
        stride = int(view.get("byteStride", width * size))
        values = []
        for item in range(count):
            base = start + item * stride
            values.append([
                struct.unpack_from("<" + fmt, binary, base + component * size)[0]
                for component in range(width)
            ])
        return values

    nodes = document.get("nodes") or []
    meshes = document.get("meshes") or []
    scene_nodes = (document.get("scenes") or [{}])[int(document.get("scene", 0) or 0)].get("nodes", []) if document.get("scenes") else list(range(len(nodes)))
    world_cache: Dict[int, List[List[float]]] = {}

    def node_matrix(index: int) -> List[List[float]]:
        if index in world_cache:
            return world_cache[index]
        node = nodes[index]
        if "matrix" in node:
            local = _matrix_from_value(node["matrix"])
        else:
            local = _trs_matrix(
                _vec(node.get("translation"), [0.0, 0.0, 0.0]),
                _vec(node.get("rotation_euler_deg"), [0.0, 0.0, 0.0]),
                _vec(node.get("scale"), [1.0, 1.0, 1.0]),
            )
        if "rotation" in node and len(node["rotation"]) == 4 and "matrix" not in node and "rotation_euler_deg" not in node:
            x, y, z, w = [float(value) for value in node["rotation"]]
            rotation = [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0.0],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0.0],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
            scale = _mat_identity()
            for axis in range(3):
                scale[axis][axis] = float(_vec(node.get("scale"), [1.0, 1.0, 1.0])[axis])
            translation = _mat_identity()
            for axis in range(3):
                translation[axis][3] = float(_vec(node.get("translation"), [0.0, 0.0, 0.0])[axis])
            local = _mat_mul(translation, _mat_mul(rotation, scale))
        parent = node.get("_parent")
        world = _mat_mul(node_matrix(parent) if parent is not None else _mat_identity(), local)
        world_cache[index] = world
        return world

    for parent_index, node in enumerate(nodes):
        for child in node.get("children", []) or []:
            nodes[int(child)]["_parent"] = parent_index

    records: List[Dict[str, Any]] = []
    def visit(index: int, prefix: str) -> None:
        node = nodes[index]
        name = str(node.get("name") or f"node-{index}")
        label = f"{prefix}/{name}" if prefix else name
        if "mesh" in node:
            mesh_index = int(node["mesh"])
            matrix = node_matrix(index)
            mesh_name = str(meshes[mesh_index].get("name") or name)
            vertices: List[List[float]] = []
            faces: List[List[int]] = []
            for primitive in meshes[mesh_index].get("primitives", []) or []:
                if int(primitive.get("mode", 4)) != 4:
                    continue
                position_accessor = (primitive.get("attributes") or {}).get("POSITION")
                if position_accessor is None:
                    continue
                positions = read_accessor(int(position_accessor))
                base = len(vertices)
                vertices.extend([_mat_apply(matrix, position) for position in positions])
                index_accessor = primitive.get("indices")
                if index_accessor is None:
                    indices = list(range(len(positions)))
                else:
                    indices = [int(item[0]) for item in read_accessor(int(index_accessor))]
                for start in range(0, len(indices) - 2, 3):
                    faces.append([base + indices[start], base + indices[start + 1], base + indices[start + 2]])
            if vertices and faces:
                records.append({"name": mesh_name, "path_name": label, "vertices": vertices, "faces": faces, "format": "glb"})
        for child in node.get("children", []) or []:
            visit(int(child), label)

    for index in scene_nodes:
        visit(int(index), "")
    if not records:
        for index, node in enumerate(nodes):
            if "mesh" in node:
                visit(index, "")
    return records


def _load_mesh_records(artifact: Path) -> List[Dict[str, Any]]:
    if not artifact.exists():
        raise OracleError(f"artifact {artifact} does not exist")
    if artifact.is_dir():
        records = []
        for path in sorted(item for item in artifact.rglob("*") if item.is_file()):
            if path.suffix.lower() == ".obj":
                groups = _read_obj_groups(path)
                if groups:
                    vertices = groups[0]["vertices"]
                    faces = [face for group in groups for face in group["faces"]]
                    relative = path.relative_to(artifact).as_posix()
                    records.append({"name": path.stem, "path": relative, "vertices": vertices, "faces": faces, "format": "obj"})
            elif path.suffix.lower() == ".glb":
                for record in _read_glb(path):
                    record["path"] = path.relative_to(artifact).as_posix()
                    records.append(record)
        if not records:
            raise OracleError(f"artifact {artifact} contains no OBJ or GLB meshes")
        return records
    if artifact.suffix.lower() == ".glb":
        return _read_glb(artifact)
    if artifact.suffix.lower() == ".obj":
        groups = _read_obj_groups(artifact)
        if not groups:
            raise OracleError(f"artifact {artifact} contains no OBJ mesh")
        if len(groups) == 1:
            return groups
        return groups
    raise OracleError(f"unsupported artifact suffix {artifact.suffix!r}; use .obj or .glb")


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def _mapping_value(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, dict) and isinstance(value.get("primitives"), list):
        return [str(item) for item in value["primitives"]]
    raise OracleError("mesh_to_source values must be a primitive id, a list of ids, or {primitives: [...]}")


def _bbox_match(expected: Dict[str, Any], observed: Dict[str, Any], tolerance: float) -> bool:
    return all(abs(expected["bounds"]["size"][axis] - observed["bounds"]["size"][axis]) <= max(tolerance, 0.02 * max(1.0, expected["bounds"]["size"][axis])) for axis in range(3))


def _transform_payload(
    expected: Dict[str, Any],
    observed: Dict[str, Any],
    primitive: Dict[str, Any],
) -> Dict[str, Any]:
    delta = [round(observed["centroid"][axis] - expected["centroid"][axis], 6) for axis in range(3)]
    ratio = [
        round(observed["bounds"]["size"][axis] / expected["bounds"]["size"][axis], 6)
        if abs(expected["bounds"]["size"][axis]) > EPS else None
        for axis in range(3)
    ]
    return {
        "expected": {
            "position": primitive.get("position", [0.0, 0.0, 0.0]),
            "rotation_euler_deg": primitive.get("rotation_euler_deg", [0.0, 0.0, 0.0]),
            "scale": primitive.get("scale", [1.0, 1.0, 1.0]),
            "node": primitive.get("node") or primitive.get("parent"),
            "parent_chain": [str(item) for item in (primitive.get("_chain") or [])],
            "centroid": expected["centroid"],
            "bounds": expected["bounds"],
            "triangle_count": expected["triangle_count"],
        },
        "observed": {
            "centroid": observed["centroid"],
            "bounds": observed["bounds"],
            "triangle_count": observed["triangle_count"],
        },
        "translation_delta": delta,
        "size_ratio": ratio,
    }


def _classify_deformation(expected: Dict[str, Any], observed: Dict[str, Any], tolerance: float) -> str:
    delta = math.sqrt(sum((observed["centroid"][axis] - expected["centroid"][axis]) ** 2 for axis in range(3)))
    if delta > tolerance and _bbox_match(expected, observed, tolerance):
        return "transform_translation"
    if delta <= tolerance and not _bbox_match(expected, observed, tolerance):
        ratios = [
            observed["bounds"]["size"][axis] / expected["bounds"]["size"][axis]
            for axis in range(3)
            if abs(expected["bounds"]["size"][axis]) > EPS
        ]
        if ratios and max(ratios) - min(ratios) <= 0.2:
            return "transform_scale"
        expected_volume = expected["bounds"]["size"][0] * expected["bounds"]["size"][1] * expected["bounds"]["size"][2]
        observed_volume = observed["bounds"]["size"][0] * observed["bounds"]["size"][1] * observed["bounds"]["size"][2]
        volume_ratio = observed_volume / expected_volume if expected_volume > EPS else 1.0
        if 0.7 <= volume_ratio <= 1.4:
            return "transform_rotation"
        return "transform_rotation_or_scale"
    if delta > tolerance:
        return "transform_composite"
    return "shape_mismatch"


def _compare_mapping(
    key: str,
    primitive_ids: List[str],
    record: Dict[str, Any],
    primitives: Dict[str, Dict[str, Any]],
    nodes: Dict[str, Dict[str, Any]],
    node_cache: Dict[str, List[List[float]]],
    spec: Dict[str, Any],
    tolerance: float,
    sample_count: int,
    unit: Dict[str, Any],
    frame: Any,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    violations: List[Dict[str, Any]] = []
    artifact_path = str(record.get("path") or record.get("name") or key)
    actual_vertices = []
    factor = float(unit.get("factor", 1.0))
    offset = float(unit.get("offset", 0.0))
    for vertex in record["vertices"]:
        converted = [vertex[axis] * factor + offset for axis in range(3)]
        actual_vertices.append(_mat_apply(_frame_matrix(frame), converted) if frame else converted)
    actual = {"vertices": actual_vertices, "faces": record["faces"]}
    actual_stats = _mesh_stats(actual)
    components = _components(actual)
    component_stats = []
    component_samples = []
    for component in components:
        component_stats.append(_mesh_stats(component))
        component_samples.append(_surface_samples(component, sample_count))
    matched_component_indices: set[int] = set()
    used_component_indices: set[int] = set()
    primitive_entries = []

    expected_meshes = []
    for primitive_id in primitive_ids:
        primitive = primitives.get(primitive_id)
        if primitive is None:
            violations.append({
                "code": "unverifiable_mapping",
                "invariant_class": "geometry_conformance",
                "mesh": key,
                "artifact_path": artifact_path,
                "primitive": primitive_id,
                "field": "mesh_to_source",
                "expected": "a primitive declared by the task source scene",
                "observed": "no such primitive",
                "tolerance": tolerance,
                "diagnosis": f"mesh {key!r} maps to undeclared source primitive {primitive_id!r}",
            })
            continue
        expected_mesh = _build_source_primitive(primitive, nodes, node_cache)
        expected_mesh["name"] = primitive_id
        expected_meshes.append(expected_mesh)
        expected_stats = _mesh_stats(expected_mesh)
        samples = _surface_samples(expected_mesh, sample_count)
        distances, _ = _nearest_distances(samples, actual, tolerance)
        if not distances:
            violations.append({
                "code": "unverifiable_source",
                "invariant_class": "geometry_conformance",
                "mesh": key,
                "artifact_path": artifact_path,
                "primitive": primitive_id,
                "field": "surface",
                "expected": "a measurable reconstructed source primitive",
                "observed": "no measurable surface",
                "tolerance": tolerance,
                "diagnosis": f"primitive {primitive_id!r} has no measurable surface",
            })
            continue
        mean_distance = sum(distances) / len(distances)
        max_distance = max(distances)
        coverage = sum(1 for distance in distances if distance <= tolerance) / len(distances)
        candidate_indices = []
        for component_index, component in enumerate(components):
            component_distances, _ = _nearest_distances(samples, component, tolerance)
            if component_distances and max(component_distances) <= tolerance:
                candidate_indices.append(component_index)
        if candidate_indices:
            matched_component_indices.update(candidate_indices)
            used_component_indices.update(candidate_indices)
            duplicate_indices = candidate_indices + [
                index for index in range(len(components))
                if index not in candidate_indices and _bbox_match(expected_stats, component_stats[index], tolerance)
            ]
            if len(duplicate_indices) > 1:
                used_component_indices.update(duplicate_indices)
                duplicate_stats = component_stats[duplicate_indices[-1]]
                violations.append({
                    "code": "primitive_duplication",
                    "invariant_class": "geometry_conformance",
                    "mesh": key,
                    "artifact_path": artifact_path,
                    "primitive": primitive_id,
                    "field": "primitive_assembly",
                    "expected": f"exactly one exported instance of source primitive {primitive_id!r}",
                    "observed": f"{len(duplicate_indices)} exported instances have that primitive's placement and shape",
                    "tolerance": tolerance,
                    "observed_delta": 0.0,
                    "coverage": round(coverage, 6),
                    "transform": _transform_payload(expected_stats, duplicate_stats, primitive),
                    "diagnosis": f"mesh {key!r} duplicates source primitive {primitive_id!r}",
                })
            primitive_entries.append({
                "id": primitive_id,
                "status": "pass" if len(candidate_indices) == 1 else "fail",
                "expected": expected_stats,
                "observed": component_stats[candidate_indices[0]],
                "observed_delta": round(max_distance, 6),
                "coverage": round(coverage, 6),
            })
            continue

        best_index = None
        best_mean = float("inf")
        for component_index, samples_for_component in enumerate(component_samples):
            component_distances, _ = _nearest_distances(samples, components[component_index], tolerance)
            if component_distances and sum(component_distances) / len(component_distances) < best_mean:
                best_mean = sum(component_distances) / len(component_distances)
                best_index = component_index
        local_variant = None
        if primitive.get("node") or primitive.get("parent"):
            local_variant = _build_source_primitive(primitive, nodes, node_cache, ignore_parents=True)
        local_match = False
        if local_variant is not None:
            local_distances, _ = _nearest_distances(_surface_samples(local_variant, sample_count), actual, tolerance)
            local_match = bool(local_distances) and max(local_distances) <= tolerance

        available = [index for index in range(len(components)) if index not in matched_component_indices]
        if not available or best_index is None:
            code = "primitive_omission"
            diagnosis = f"mesh {key!r} omits source primitive {primitive_id!r}"
        elif local_match:
            code = "mis_parented"
            diagnosis = (
                f"mesh {key!r} matches the local primitive surface for {primitive_id!r} "
                "but not its source-scene world transform; parent transforms were not applied"
            )
        else:
            code = _classify_deformation(expected_stats, component_stats[best_index], tolerance)
            diagnosis = (
                f"mesh {key!r} does not match source primitive {primitive_id!r} at tolerance {tolerance}; "
                f"expected centroid {expected_stats['centroid']} size {expected_stats['bounds']['size']}, "
                f"observed centroid {component_stats[best_index]['centroid']} size {component_stats[best_index]['bounds']['size']}"
            )
        if best_index is not None:
            used_component_indices.add(best_index)
        primitive_entries.append({
            "id": primitive_id,
            "status": "fail",
            "code": code,
            "expected": expected_stats,
            "observed": component_stats[best_index] if best_index is not None else None,
            "observed_delta": round(max_distance, 6),
            "coverage": round(coverage, 6),
        })
        if code == "primitive_omission":
            payload = {"expected": {
                "position": primitive.get("position", [0.0, 0.0, 0.0]),
                "rotation_euler_deg": primitive.get("rotation_euler_deg", [0.0, 0.0, 0.0]),
                "scale": primitive.get("scale", [1.0, 1.0, 1.0]),
                "node": primitive.get("node") or primitive.get("parent"),
                "centroid": expected_stats["centroid"],
                "bounds": expected_stats["bounds"],
            }, "observed": {"status": "absent", "centroid": None, "bounds": None, "triangle_count": 0}}
        else:
            payload = _transform_payload(
                expected_stats,
                component_stats[best_index] if best_index is not None else {"centroid": [0.0, 0.0, 0.0], "bounds": {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0], "size": [0.0, 0.0, 0.0], "center": [0.0, 0.0, 0.0]}, "triangle_count": 0},
                primitive,
            )
        violations.append({
            "code": code,
            "invariant_class": "geometry_conformance",
            "mesh": key,
            "artifact_path": artifact_path,
            "primitive": primitive_id,
            "field": "world_transform" if code != "primitive_omission" else "primitive_assembly",
            "expected": f"source-scene primitive {primitive_id!r} assembled at its world transform within {tolerance}",
            "observed": "absent from the exported assembly" if code == "primitive_omission" else f"max nearest deviation {round(max_distance, 6)}",
            "observed_delta": round(max_distance, 6),
            "tolerance": tolerance,
            "coverage": round(coverage, 6),
            "transform": payload,
            "diagnosis": diagnosis,
        })

    extra_components = [index for index in range(len(components)) if index not in used_component_indices and index not in matched_component_indices]
    for component_index in extra_components:
        stats = component_stats[component_index]
        violations.append({
            "code": "unexpected_primitive",
            "invariant_class": "geometry_conformance",
            "mesh": key,
            "artifact_path": artifact_path,
            "primitive": None,
            "field": "primitive_assembly",
            "expected": "only the source-scene primitives named in mesh_to_source",
            "observed": {"centroid": stats["centroid"], "bounds": stats["bounds"], "triangle_count": stats["triangle_count"]},
            "tolerance": tolerance,
            "observed_delta": None,
            "diagnosis": f"mesh {key!r} contains an extra connected component not present in the mapped source assembly",
        })

    expected_combined = {"vertices": [], "faces": []}
    vertex_offset = 0
    for expected_mesh in expected_meshes:
        expected_combined["vertices"].extend(expected_mesh["vertices"])
        expected_combined["faces"].extend([[index + vertex_offset for index in face] for face in expected_mesh["faces"]])
        vertex_offset += len(expected_mesh["vertices"])
    if expected_combined["faces"]:
        expected_stats = _mesh_stats(expected_combined)
        expected_distances, _ = _nearest_distances(_surface_samples(expected_combined, sample_count), actual, tolerance)
        actual_distances, _ = _nearest_distances(_surface_samples(actual, sample_count), expected_combined, tolerance)
        max_nearest = max(max(expected_distances or [0.0]), max(actual_distances or [0.0]))
    else:
        expected_stats = {"vertex_count": 0, "triangle_count": 0, "bounds": {"min": [0, 0, 0], "max": [0, 0, 0], "size": [0, 0, 0], "center": [0, 0, 0]}, "centroid": [0, 0, 0]}
        max_nearest = 0.0
    mesh_status = "fail" if violations else "pass"
    entry = {
        "mesh": key,
        "artifact_path": artifact_path,
        "status": mesh_status,
        "source_primitives": primitive_ids,
        "expected": expected_stats,
        "observed": actual_stats,
        "expected_triangle_count": expected_stats["triangle_count"],
        "observed_triangle_count": actual_stats["triangle_count"],
        "triangle_delta": actual_stats["triangle_count"] - expected_stats["triangle_count"],
        "observed_delta": round(max_nearest, 6),
        "tolerance": tolerance,
        "primitives": primitive_entries,
    }
    return entry, violations


def _frame_matrix(frame: Any) -> Optional[List[List[float]]]:
    if not frame:
        return None
    if isinstance(frame, dict) and "matrix" in frame:
        return _matrix_from_value(frame.get("matrix"))
    if isinstance(frame, dict):
        return _trs_matrix(
            _vec(frame.get("translation"), [0.0, 0.0, 0.0]),
            _vec(frame.get("rotation_euler_deg"), [0.0, 0.0, 0.0]),
            _vec(frame.get("scale"), [1.0, 1.0, 1.0]),
        )
    return _matrix_from_value(frame)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _load_scene(path: Path) -> Dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OracleError(f"source scene {path} cannot be read: {exc}")
    if not isinstance(document, dict):
        raise OracleError("source scene must be a JSON object")
    primitives = document.get("primitives")
    if not isinstance(primitives, list) or not primitives:
        raise OracleError("source scene exposes no primitive list")
    table = {}
    for index, primitive in enumerate(primitives):
        if not isinstance(primitive, dict):
            raise OracleError(f"source primitive[{index}] must be an object")
        primitive_id = primitive.get("id") or primitive.get("name")
        if primitive_id is None:
            raise OracleError(f"source primitive[{index}] has no id")
        if primitive.get("type") not in SUPPORTED_PRIMITIVES:
            raise OracleError(f"unsupported source primitive type {primitive.get('type')!r}")
        entry = dict(primitive)
        entry["id"] = str(primitive_id)
        entry["_chain"] = _primitive_chain(entry, _node_table(document))
        table[str(primitive_id)] = entry
    return {"document": document, "primitives": table}


def run(source_scene: Path, artifact: Path, spec_path: Path) -> Dict[str, Any]:
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OracleError(f"tolerance spec {spec_path} cannot be read: {exc}")
    if not isinstance(spec, dict):
        raise OracleError("tolerance spec must be a JSON object")
    tolerance = _acceptance_tolerance(spec)
    if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) or tolerance < 0:
        return _unverifiable_report(
            source_scene,
            artifact,
            spec,
            "task-stated acceptance_tolerance is absent or non-numeric; a local default cannot substitute",
            tolerance,
        )
    tolerance = float(tolerance)
    independence, independence_reason = _independence_evidence(spec)
    if independence_reason is not None or independence is None:
        return _unverifiable_report(
            source_scene,
            artifact,
            spec,
            independence_reason or "oracle independence is unverifiable",
            tolerance,
        )
    sample_count = int(spec.get("sample_count", 512) or 512)
    if sample_count < 16:
        raise OracleError("sample_count must be at least 16")
    scene = _load_scene(source_scene)
    document = scene["document"]
    primitives = scene["primitives"]
    nodes = _node_table(document)
    node_cache: Dict[str, List[List[float]]] = {}
    units = str(document.get("units") or "")
    if spec.get("units") and units and str(spec.get("units")) != units:
        raise OracleError(f"spec units {spec.get('units')!r} disagree with source scene units {units!r}")
    unit = spec.get("unit_conversion") or {"factor": 1.0, "offset": 0.0}
    frame = spec.get("frame_transform")
    try:
        records = _load_mesh_records(artifact)
    except OSError as exc:
        raise OracleError(f"artifact {artifact} cannot be read: {exc}")
    mapping = spec.get("mesh_to_source")
    if not isinstance(mapping, dict) or not mapping:
        if len(records) == 1 and len(primitives) == 1:
            mapping = {next(iter(primitives)): next(iter(primitives))}
        else:
            raise OracleError("tolerance spec needs a mesh_to_source mapping")
    records_by_path = {record.get("path"): record for record in records if record.get("path")}
    records_by_name: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        records_by_name.setdefault(str(record.get("name")), []).append(record)
    violations: List[Dict[str, Any]] = []
    unverifiable: List[Dict[str, Any]] = []
    meshes = []
    used_records: set[int] = set()
    for key, value in mapping.items():
        try:
            primitive_ids = _mapping_value(value)
        except OracleError as exc:
            unverifiable.append({"mesh": key, "reason": str(exc), "invariant_class": "geometry_conformance"})
            continue
        record = records_by_path.get(key)
        if record is None and key in records_by_name and len(records_by_name[key]) == 1:
            record = records_by_name[key][0]
        if record is None and len(records) == 1 and key in {records[0].get("name"), records[0].get("path"), artifact.name, artifact.stem}:
            record = records[0]
        if record is None:
            violations.append({
                "code": "mesh_missing",
                "invariant_class": "geometry_conformance",
                "mesh": key,
                "artifact_path": key,
                "primitive": None,
                "field": "artifact_path",
                "expected": "the declared exported mesh in the task artifact",
                "observed": "absent",
                "tolerance": tolerance,
                "diagnosis": f"declared exported mesh {key!r} is missing from {artifact}",
            })
            continue
        used_records.add(id(record))
        entry, mesh_violations = _compare_mapping(
            key, primitive_ids, record, primitives, nodes, node_cache,
            spec, tolerance, sample_count, unit, frame,
        )
        meshes.append(entry)
        violations.extend(mesh_violations)
    for record in records:
        if id(record) in used_records:
            continue
        violations.append({
            "code": "unmapped_export",
            "invariant_class": "geometry_conformance",
            "mesh": record.get("name"),
            "artifact_path": record.get("path") or record.get("name"),
            "primitive": None,
            "field": "mesh_to_source",
            "expected": "every exported mesh mapped to source primitives from the task scene",
            "observed": "no mapping entry",
            "tolerance": tolerance,
            "diagnosis": "exported mesh has no source mapping and cannot be passed",
        })
    mapped_ids = set()
    for value in mapping.values():
        try:
            mapped_ids.update(_mapping_value(value))
        except OracleError:
            pass
    for primitive_id in sorted(set(primitives) - mapped_ids):
        violations.append({
            "code": "primitive_omission",
            "invariant_class": "geometry_conformance",
            "mesh": None,
            "artifact_path": None,
            "primitive": primitive_id,
            "field": "primitive_assembly",
            "expected": f"source-scene primitive {primitive_id!r} present in the exported assembly",
            "observed": "not mapped to any exported mesh",
            "tolerance": tolerance,
            "diagnosis": f"source primitive {primitive_id!r} has no exported counterpart",
        })
    for item in violations:
        code = str(item.get("code") or "")
        if code in {
            "primitive_omission", "primitive_duplication", "unexpected_primitive",
            "mesh_missing", "unmapped_export",
        }:
            attribution = "assembly"
        elif code == "mis_parented" or code.startswith("transform_"):
            attribution = "transform"
        elif code == "shape_mismatch":
            attribution = "shape"
        else:
            attribution = "unverifiable"
        item.setdefault("attribution", attribution)
    for item in unverifiable:
        item.setdefault("attribution", "missing_oracle_independence")
    status = "clean" if not violations and not unverifiable else "violations"
    return {
        "status": status,
        "source_scene": str(source_scene),
        "artifact": str(artifact),
        "spec_revision": spec.get("spec_revision"),
        "units": units,
        "tolerance": tolerance,
        "metric": str(spec.get("metric", "max_nearest")),
        "oracle": {
            "method": "independent source-scene primitive assembly and world-transform recomputation",
            "reader": "direct source-scene JSON primitive and node reader",
            "transform_path": "4x4 matrix composition T * Rz * Ry * Rx * S applied to source primitive vertices, then parent node chain; exporter, manifest, intermediate mesh, and submitted mesh are not read as expectations",
            "independent_of_exporter": True,
            "independence_evidence": independence,
            "frame": "scene_root",
        },
        "counts": {
            "meshes": len(meshes),
            "mapped_primitives": len(mapped_ids),
            "source_primitives": len(primitives),
            "passed": sum(1 for mesh in meshes if mesh["status"] == "pass"),
            "violations": len(violations),
            "unverifiable": len(unverifiable),
        },
        "meshes": meshes,
        "violations": violations,
        "unverifiable": unverifiable,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Independently recompute source-scene mesh geometry and compare an exported artifact.")
    parser.add_argument("source_scene", type=Path, help="task source scene JSON with primitives and optional node hierarchy")
    parser.add_argument("artifact", type=Path, help="exported OBJ/GLB file or artifact root directory")
    parser.add_argument("--spec", required=True, type=Path, help="tolerance spec JSON with mesh_to_source")
    parser.add_argument("--report", type=Path, help="optional path for the JSON report")
    args = parser.parse_args(argv)
    try:
        report = run(args.source_scene, args.artifact, args.spec)
    except (OracleError, OSError, ValueError, KeyError, IndexError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        return 2
    rendered = json.dumps(report, indent=2)
    if args.report:
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "clean" else 1


if __name__ == "__main__":
    sys.exit(main())
