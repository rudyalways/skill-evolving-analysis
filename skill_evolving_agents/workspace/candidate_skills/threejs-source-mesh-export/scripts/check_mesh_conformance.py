#!/usr/bin/env python3
"""Independently check exported Three.js part meshes against source primitives.

The checker reads a task-derived JSON spec, executes the native ``.js``/``.mjs``
source module with its own Node.js bridge to obtain the primitive descriptors,
reconstructs every expected surface from those source primitives with its own
tessellation and transform code (box, sphere, cylinder, plane, or torus), and
compares each exported mesh with a symmetric surface Chamfer distance and
surface coverage.  It never imports the producer exporter and never derives the
expected surface from an exported mesh.

Exit codes: 0 all meshes pass, 1 one or more geometry violations, 2 the check
cannot be established (missing input, malformed spec, unsupported primitive, or
a non-independent reconstruction source).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

Vec = tuple[float, float, float]
Mat = list[list[float]]
Geometry = tuple[list[Vec], list[tuple[int, int, int]]]


# --------------------------------------------------------------------------- #
# Linear algebra
# --------------------------------------------------------------------------- #
def identity() -> Mat:
    return [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def matmul(a: Mat, b: Mat) -> Mat:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)]
            for i in range(4)]


def vec3(value: Any, default: Vec = (0.0, 0.0, 0.0)) -> Vec:
    if value is None:
        return default
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"expected a three-number vector, got {value!r}")
    return (float(value[0]), float(value[1]), float(value[2]))


def translation(p: Vec) -> Mat:
    m = identity()
    m[0][3], m[1][3], m[2][3] = p
    return m


def scaling(s: Vec) -> Mat:
    m = identity()
    m[0][0], m[1][1], m[2][2] = s
    return m


def euler_xyz(r: Vec) -> Mat:
    cx, sx = math.cos(r[0]), math.sin(r[0])
    cy, sy = math.cos(r[1]), math.sin(r[1])
    cz, sz = math.cos(r[2]), math.sin(r[2])
    rx = [[1, 0, 0, 0], [0, cx, -sx, 0], [0, sx, cx, 0], [0, 0, 0, 1]]
    ry = [[cy, 0, sy, 0], [0, 1, 0, 0], [-sy, 0, cy, 0], [0, 0, 0, 1]]
    rz = [[cz, -sz, 0, 0], [sz, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    # Three.js default Euler order XYZ: Rx * Ry * Rz for column vectors.
    return matmul(matmul(rx, ry), rz)


def quaternion_matrix(q: Vec | None) -> Mat:
    """Independent rotation-matrix reconstruction from [x, y, z, w]."""
    if q is None:
        return identity()
    x, y, z, w = (float(v) for v in q)
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm <= 0:
        return identity()
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0.0],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0.0],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def local_matrix(node: dict[str, Any]) -> Mat:
    rotation = quaternion_matrix(node.get("quaternion")) \
        if node.get("quaternion") is not None else euler_xyz(vec3(node.get("rotation")))
    return matmul(translation(vec3(node.get("position"))),
                  matmul(rotation,
                         scaling(vec3(node.get("scale"), (1.0, 1.0, 1.0)))))


def transform(m: Mat, p: Vec) -> Vec:
    x, y, z = p
    return (
        m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
        m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
        m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3],
    )


def centroid(points: list[Vec]) -> Vec:
    n = float(len(points))
    return (sum(p[0] for p in points) / n,
            sum(p[1] for p in points) / n,
            sum(p[2] for p in points) / n)


def bbox_diagonal(points: list[Vec]) -> float:
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    return math.dist(lo, hi)


# --------------------------------------------------------------------------- #
# Deterministic primitive tessellation (the independent expected surface)
# --------------------------------------------------------------------------- #
def primitive_args(primitive: str, raw: Any) -> dict[str, float]:
    if isinstance(raw, dict):
        out = {}
        for key, value in raw.items():
            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", str(key)).lower()
            out[snake] = float(value)
        return out
    values = [float(v) for v in (raw or [])]
    keys = {
        "box": ["width", "height", "depth"],
        "plane": ["width", "height"],
        "sphere": ["radius", "width_segments", "height_segments"],
        "cylinder": ["radius_top", "radius_bottom", "height", "radial_segments"],
        "torus": ["radius", "tube", "radial_segments", "tubular_segments"],
    }.get(primitive, [])
    return {k: v for k, v in zip(keys, values)}


def primitive_geometry(primitive: str, args: dict[str, float]) -> Geometry:
    """Build a triangle surface in the primitive's local frame."""
    if primitive == "box":
        w, h, d = args.get("width", 1.0), args.get("height", 1.0), args.get("depth", 1.0)
        hw, hh, hd = w / 2.0, h / 2.0, d / 2.0
        verts = [(-hw, -hh, -hd), (hw, -hh, -hd), (hw, hh, -hd), (-hw, hh, -hd),
                 (-hw, -hh, hd), (hw, -hh, hd), (hw, hh, hd), (-hw, hh, hd)]
        faces = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 4, 5), (0, 5, 1),
                 (3, 2, 6), (3, 6, 7), (0, 3, 7), (0, 7, 4), (1, 5, 6), (1, 6, 2)]
        return verts, faces
    if primitive == "plane":
        w, h = args.get("width", 1.0), args.get("height", 1.0)
        g = max(2, int(args.get("segments", 8)))
        verts = [((i / (g - 1) - 0.5) * w, 0.0, (j / (g - 1) - 0.5) * h)
                 for i in range(g) for j in range(g)]
        faces = []
        for i in range(g - 1):
            for j in range(g - 1):
                a = i * g + j
                b, c, d = a + 1, a + g, a + g + 1
                faces.extend([(a, c, d), (a, d, b)])
        return verts, faces
    if primitive == "sphere":
        r = args.get("radius", 1.0)
        nu = max(8, int(args.get("width_segments", 24)))
        nv = max(4, int(args.get("height_segments", 16)))
        verts = []
        for i in range(nv + 1):
            phi = math.pi * i / nv
            for j in range(nu):
                theta = 2.0 * math.pi * j / nu
                verts.append((r * math.sin(phi) * math.cos(theta),
                              r * math.cos(phi),
                              r * math.sin(phi) * math.sin(theta)))
        faces = []
        for i in range(nv):
            for j in range(nu):
                a = i * nu + j
                b = i * nu + (j + 1) % nu
                c = (i + 1) * nu + j
                d = (i + 1) * nu + (j + 1) % nu
                faces.extend([(a, c, d), (a, d, b)])
        return verts, faces
    if primitive == "cylinder":
        rt = args.get("radius_top", args.get("radius", 1.0))
        rb = args.get("radius_bottom", args.get("radius", rt))
        h = args.get("height", 1.0)
        n = max(8, int(args.get("radial_segments", 32)))
        verts = []
        for y, r in ((-h / 2.0, rb), (h / 2.0, rt)):
            for j in range(n):
                a = 2.0 * math.pi * j / n
                verts.append((r * math.cos(a), y, r * math.sin(a)))
        bottom_c = len(verts); verts.append((0.0, -h / 2.0, 0.0))
        top_c = len(verts); verts.append((0.0, h / 2.0, 0.0))
        faces = []
        for j in range(n):
            k = (j + 1) % n
            faces.extend([(j, k, n + j), (k, n + k, n + j),
                          (bottom_c, k, j), (top_c, n + j, n + k)])
        return verts, faces
    if primitive == "torus":
        r = args.get("radius", 1.0)
        tube = args.get("tube", 0.25)
        nu = max(8, int(args.get("radial_segments", 24)))
        nv = max(8, int(args.get("tubular_segments", 48)))
        verts = []
        for i in range(nu):
            u = 2.0 * math.pi * i / nu
            for j in range(nv):
                v = 2.0 * math.pi * j / nv
                verts.append(((r + tube * math.cos(v)) * math.cos(u),
                              tube * math.sin(v),
                              (r + tube * math.cos(v)) * math.sin(u)))
        faces = []
        for i in range(nu):
            for j in range(nv):
                a = i * nv + j
                b = i * nv + (j + 1) % nv
                c = ((i + 1) % nu) * nv + j
                d = ((i + 1) % nu) * nv + (j + 1) % nv
                faces.extend([(a, c, d), (a, d, b)])
        return verts, faces
    raise ValueError(f"unsupported source primitive {primitive!r}")


def transform_geometry(geom: Geometry, matrix: Mat, unit_scale: float,
                       frame: Mat) -> Geometry:
    verts = [transform(frame, transform(matrix, (p[0] * unit_scale,
                                                  p[1] * unit_scale,
                                                  p[2] * unit_scale)))
             for p in geom[0]]
    return verts, list(geom[1])


def merge_geometry(parts: list[Geometry]) -> Geometry:
    verts: list[Vec] = []
    faces: list[tuple[int, int, int]] = []
    for pv, pf in parts:
        offset = len(verts)
        verts.extend(pv)
        faces.extend((a + offset, b + offset, c + offset) for a, b, c in pf)
    return verts, faces


# --------------------------------------------------------------------------- #
# Source scene loading
# --------------------------------------------------------------------------- #
def _parse_js_object(text: str) -> dict[str, Any]:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(^|[^:])//.*?$", r"\1", text, flags=re.M)
    starts = [i for i in (text.find("export const SCENE"), text.find("const SCENE"),
                          text.find("module.exports")) if i >= 0]
    if not starts:
        raise ValueError("JavaScript source has no SCENE object")
    start = text.find("{", min(starts))
    if start < 0:
        raise ValueError("JavaScript source has no object literal")
    depth = 0
    in_string: str | None = None
    escaped = False
    end = -1
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_string:
                in_string = None
            continue
        if ch in ("'", '"'):
            in_string = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        raise ValueError("unterminated SCENE object literal")
    literal = text[start:end]
    literal = re.sub(r"'([^']*)'", r'"\1"', literal)
    literal = re.sub(r"([{,]\s*)([A-Za-z_$][\w$]*)\s*:", r'\1"\2":', literal)
    literal = re.sub(r",(\s*[}\]])", r"\1", literal)
    literal = re.sub(r"\bTrue\b", "true", literal)
    literal = re.sub(r"\bFalse\b", "false", literal)
    literal = re.sub(r"\bNone\b", "null", literal)
    return json.loads(literal)


# The checker's own module bridge.  It is intentionally not shared with the
# producer: only the native source module is common, while descriptor
# extraction, transform composition, and tessellation are separate code.
_CHECKER_BRIDGE = r"""
import { pathToFileURL } from "node:url";

const target = process.env.CHECKER_SOURCE_MODULE;
const namespace = await import(pathToFileURL(target).href);
const factory = namespace.createScene
  || (namespace.default && namespace.default.createScene);
if (typeof factory !== "function") {
  throw new Error("native source module does not export createScene()");
}

const asVector = (value, fallback) => {
  if (Array.isArray(value) && value.length === 3) return value.map(Number);
  if (value && typeof value === "object") {
    return [Number(value.x ?? fallback[0]), Number(value.y ?? fallback[1]),
            Number(value.z ?? fallback[2])];
  }
  return [...fallback];
};

const asQuaternion = (value) => {
  if (!value) return [0, 0, 0, 1];
  if (Array.isArray(value) && value.length === 4) return value.map(Number);
  if (Array.isArray(value) && value.length === 3) {
    return asQuaternion({ x: value[0], y: value[1], z: value[2], order: "XYZ" });
  }
  if ("w" in value && "x" in value && "y" in value && "z" in value) {
    return [Number(value.x), Number(value.y), Number(value.z), Number(value.w)];
  }
  const order = String(value.order || "XYZ");
  if (order !== "XYZ") {
    throw new Error("only XYZ Euler order or an explicit quaternion is supported");
  }
  const halfX = Number(value.x ?? 0) / 2;
  const halfY = Number(value.y ?? 0) / 2;
  const halfZ = Number(value.z ?? 0) / 2;
  const cx = Math.cos(halfX), sx = Math.sin(halfX);
  const cy = Math.cos(halfY), sy = Math.sin(halfY);
  const cz = Math.cos(halfZ), sz = Math.sin(halfZ);
  return [
    sx * cy * cz + cx * sy * sz,
    cx * sy * cz - sx * cy * sz,
    cx * cy * sz + sx * sy * cz,
    cx * cy * cz - sx * sy * sz,
  ];
};

const records = [];
const usedNames = new Set();
let sequence = 0;

function visit(object, parent) {
  sequence += 1;
  const stem = String(object.name || object.id || `object_${sequence}`);
  let label = stem;
  while (usedNames.has(label)) {
    sequence += 1;
    label = `${stem}_${sequence}`;
  }
  usedNames.add(label);
  const node = {
    name: label,
    parent,
    children: [],
    position: asVector(object.position, [0, 0, 0]),
    quaternion: asQuaternion(object.quaternion || object.rotation),
    scale: asVector(object.scale, [1, 1, 1]),
  };
  const geometry = object.geometry;
  const type = object.primitive || (geometry && geometry.type)
    || (geometry && geometry.constructor && geometry.constructor.name);
  node.type = type ? "Mesh" : String(object.type || "Group");
  if (type) {
    node.primitive = String(type).replace(/Geometry$/i, "").toLowerCase();
    node.args = { ...(object.args || (geometry && geometry.parameters) || {}) };
  }
  records.push(node);
  for (const child of object.children || []) {
    node.children.push(visit(child, label));
  }
  return label;
}

const returned = await factory();
if (!returned || typeof returned !== "object") {
  throw new Error("createScene() returned no scene graph");
}

let root;
let top;
if (returned.geometry) {
  root = { name: String(returned.name || "Scene"), position: [0, 0, 0],
           quaternion: [0, 0, 0, 1], scale: [1, 1, 1] };
  top = [visit(returned, null)];
} else {
  root = {
    name: String(returned.name || "Scene"),
    position: asVector(returned.position, [0, 0, 0]),
    quaternion: asQuaternion(returned.quaternion || returned.rotation),
    scale: asVector(returned.scale, [1, 1, 1]),
  };
  top = (returned.children || []).map((child) => visit(child, null));
}

process.stdout.write(JSON.stringify({ root, top, nodes: records }));
"""


def load_native_scene(path: Path) -> dict[str, Any]:
    """Execute createScene() with the checker's own bridge and local graph."""
    env = dict(os.environ)
    env["CHECKER_SOURCE_MODULE"] = str(path.resolve())
    try:
        proc = subprocess.run(
            ["node", "--input-type=module", "--eval", _CHECKER_BRIDGE],
            capture_output=True, text=True, timeout=120, env=env, check=False)
    except FileNotFoundError as exc:
        raise ValueError("node executable is required to execute the source module") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("source module createScene() timed out") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown Node.js failure").strip()
        raise ValueError(f"createScene() execution failed: {detail[-800:]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"native source bridge returned invalid JSON: {exc}") from exc
    nodes = {}
    for record in payload.get("nodes", []):
        if not isinstance(record, dict) or not record.get("name"):
            raise ValueError("native source bridge returned a node without a name")
        nodes[str(record["name"])] = record
    if not nodes:
        raise ValueError("createScene() returned no primitive nodes")
    return {
        "up_axis": "Y",
        "unit_scale": 1.0,
        "root": payload.get("root", {}),
        "nodes": nodes,
    }


def load_scene(path: Path) -> dict[str, Any]:
    if path.suffix.lower() in (".js", ".mjs"):
        return load_native_scene(path)
    if path.suffix.lower() == ".ts":
        raise ValueError("TypeScript source must be compiled to .js or .mjs first")
    return json.loads(path.read_text(encoding="utf-8"))


def reconstruction_error(spec: dict[str, Any], source_path: Path,
                         artifact_root: Path, mapping: dict[str, Any]) -> str | None:
    block = spec.get("reconstruction")
    if not isinstance(block, dict):
        return "spec has no reconstruction provenance"
    if block.get("independent_of_producer") is not True:
        return "reconstruction is not declared independent of the producer"
    method = str(block.get("method", "")).strip().lower()
    if not method or "source" not in method or any(
            token in method for token in
            ("producer", "exporter", "exported", "artifact", "identical", "copy",
             "self", "patched")):
        return f"reconstruction method {method!r} is not source-derived"
    if source_path.suffix.lower() == ".obj":
        return "reconstruction source is an exported mesh, not a source scene"
    source_resolved = source_path.resolve()
    for mesh_name in mapping:
        if (artifact_root / str(mesh_name)).resolve() == source_resolved:
            return f"reconstruction source is the produced mesh {mesh_name!r}"
    return None


def root_matrix(scene: dict[str, Any], nodes: dict[str, Any]) -> Mat:
    root = scene.get("root", {})
    if isinstance(root, str):
        return node_matrix(nodes, root, ())
    if not isinstance(root, dict):
        raise ValueError("scene root must be a node name or transform object")
    return local_matrix(root)


def node_matrix(nodes: dict[str, Any], name: str, stack: tuple[str, ...]) -> Mat:
    if name in stack:
        raise ValueError(f"cycle in source scene at node {name!r}")
    node = nodes.get(name)
    if not isinstance(node, dict):
        raise ValueError(f"source scene has no node {name!r}")
    local = local_matrix(node)
    parent = node.get("parent")
    if parent:
        local = matmul(node_matrix(nodes, str(parent), stack + (name,)), local)
    return local


def collect_nodes(nodes: dict[str, Any], name: str,
                  stack: tuple[str, ...]) -> Iterable[tuple[dict[str, Any], Mat]]:
    if name in stack:
        raise ValueError(f"cycle in source scene at node {name!r}")
    node = nodes.get(name)
    if not isinstance(node, dict):
        raise ValueError(f"source scene has no node {name!r}")
    local = node_matrix(nodes, name, ())
    yield node, local
    for child in node.get("children", []) or []:
        yield from collect_nodes(nodes, str(child), stack + (name,))


def frame_matrix(source_up: str, artifact_up: str) -> Mat:
    source_up = source_up.strip().upper()
    artifact_up = artifact_up.strip().upper()
    if source_up == artifact_up:
        return identity()
    if (source_up, artifact_up) == ("Y", "Z"):
        return [[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]]
    if (source_up, artifact_up) == ("Z", "Y"):
        return [[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]]
    raise ValueError(f"unsupported up-axis conversion {source_up} -> {artifact_up}")


def reconstruct(nodes: dict[str, Any], root: Mat, node_name: str,
                frame: Mat, unit_scale: float) -> Geometry:
    parts: list[Geometry] = []
    for node, local in collect_nodes(nodes, node_name, ()):
        if "primitive" not in node:
            continue
        primitive = str(node["primitive"]).lower()
        primitive = primitive[:-8] if primitive.endswith("geometry") else primitive
        args = primitive_args(primitive, node.get("args"))
        geom = primitive_geometry(primitive, args)
        parts.append(transform_geometry(geom, matmul(root, local), unit_scale, frame))
    if not parts:
        raise ValueError(f"source node {node_name!r} has no primitives")
    return merge_geometry(parts)


# --------------------------------------------------------------------------- #
# Exported mesh loading and surface sampling
# --------------------------------------------------------------------------- #
def _index(value: str, count: int) -> int:
    i = int(value.split("/")[0])
    return i - 1 if i > 0 else count + i


def load_obj(path: Path) -> Geometry:
    vertices: list[Vec] = []
    faces: list[tuple[int, int, int]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "v" and len(parts) >= 4:
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == "f" and len(parts) >= 4:
            idx = [_index(p, len(vertices)) for p in parts[1:]]
            for i in range(1, len(idx) - 1):
                faces.append((idx[0], idx[i], idx[i + 1]))
    return vertices, faces


def load_json_mesh(path: Path) -> Geometry:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_v = data.get("vertices", data.get("positions"))
    raw_f = data.get("faces", data.get("indices"))
    if not raw_v:
        raise ValueError("JSON mesh has no vertices")
    vertices = [(float(v[0]), float(v[1]), float(v[2])) for v in raw_v]
    faces: list[tuple[int, int, int]] = []
    if raw_f:
        if isinstance(raw_f[0], (list, tuple)):
            faces = [(int(f[0]), int(f[1]), int(f[2])) for f in raw_f]
        else:
            faces = [(int(raw_f[i]), int(raw_f[i + 1]), int(raw_f[i + 2]))
                     for i in range(0, len(raw_f) - 2, 3)]
    return vertices, faces


def sample_surface(geom: Geometry, budget: int) -> list[Vec]:
    vertices, faces = geom
    if not faces:
        return list(vertices)
    areas = []
    for a, b, c in faces:
        va, vb, vc = vertices[a], vertices[b], vertices[c]
        areas.append(0.5 * math.dist(
            (vb[0] - va[0], vb[1] - va[1], vb[2] - va[2]),
            (vc[0] - va[0], vc[1] - va[1], vc[2] - va[2])))
    total = sum(areas) or 1.0
    out = list(vertices)
    for (a, b, c), area in zip(faces, areas):
        k = max(1, int(round(area / total * budget)))
        va, vb, vc = vertices[a], vertices[b], vertices[c]
        for i in range(k):
            u = (i * 0.6180339887498949) % 1.0
            v = (i * 0.7548776662466927) % 1.0
            if u + v > 1.0:
                u, v = 1.0 - u, 1.0 - v
            w = 1.0 - u - v
            out.append((w * va[0] + u * vb[0] + v * vc[0],
                        w * va[1] + u * vb[1] + v * vc[1],
                        w * va[2] + u * vb[2] + v * vc[2]))
    return out


# --------------------------------------------------------------------------- #
# Exact point-to-triangle distance and bidirectional surface Chamfer
# --------------------------------------------------------------------------- #
def point_triangle_distance_sq(p: Vec, a: Vec, b: Vec, c: Vec) -> float:
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    ap = (p[0] - a[0], p[1] - a[1], p[2] - a[2])
    d1 = ab[0] * ap[0] + ab[1] * ap[1] + ab[2] * ap[2]
    d2 = ac[0] * ap[0] + ac[1] * ap[1] + ac[2] * ap[2]
    if d1 <= 0 and d2 <= 0:
        return (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2 + (p[2] - a[2]) ** 2
    bp = (p[0] - b[0], p[1] - b[1], p[2] - b[2])
    d3 = ab[0] * bp[0] + ab[1] * bp[1] + ab[2] * bp[2]
    d4 = ac[0] * bp[0] + ac[1] * bp[1] + ac[2] * bp[2]
    if d3 >= 0 and d4 <= d3:
        return (p[0] - b[0]) ** 2 + (p[1] - b[1]) ** 2 + (p[2] - b[2]) ** 2
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        denom = d1 - d3
        v = d1 / denom if denom else 0.0
        q = (a[0] + v * ab[0], a[1] + v * ab[1], a[2] + v * ab[2])
        return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
    cp = (p[0] - c[0], p[1] - c[1], p[2] - c[2])
    d5 = ab[0] * cp[0] + ab[1] * cp[1] + ab[2] * cp[2]
    d6 = ac[0] * cp[0] + ac[1] * cp[1] + ac[2] * cp[2]
    if d6 >= 0 and d5 <= d6:
        return (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        denom = d2 - d6
        w = d2 / denom if denom else 0.0
        q = (a[0] + w * ac[0], a[1] + w * ac[1], a[2] + w * ac[2])
        return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        denom = (d4 - d3) + (d5 - d6)
        w = (d4 - d3) / denom if denom else 0.0
        q = (b[0] + w * (c[0] - b[0]), b[1] + w * (c[1] - b[1]),
             b[2] + w * (c[2] - b[2]))
        return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
    denom = va + vb + vc
    if denom == 0:
        return (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2 + (p[2] - a[2]) ** 2
    v, w = vb / denom, vc / denom
    q = (a[0] + ab[0] * v + ac[0] * w, a[1] + ab[1] * v + ac[1] * w,
         a[2] + ab[2] * v + ac[2] * w)
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2


class TriangleIndex:
    def __init__(self, geom: Geometry) -> None:
        vertices, faces = geom
        self.triangles = [(vertices[a], vertices[b], vertices[c]) for a, b, c in faces]
        self.boxes = []
        for tri in self.triangles:
            lo = tuple(min(p[i] for p in tri) for i in range(3))
            hi = tuple(max(p[i] for p in tri) for i in range(3))
            self.boxes.append((lo, hi))

    def nearest(self, p: Vec) -> float:
        best = float("inf")
        px, py, pz = p
        for (a, b, c), (lo, hi) in zip(self.triangles, self.boxes):
            dx = lo[0] - px if px < lo[0] else (px - hi[0] if px > hi[0] else 0.0)
            dy = lo[1] - py if py < lo[1] else (py - hi[1] if py > hi[1] else 0.0)
            dz = lo[2] - pz if pz < lo[2] else (pz - hi[2] if pz > hi[2] else 0.0)
            if dx * dx + dy * dy + dz * dz >= best:
                continue
            d = point_triangle_distance_sq(p, a, b, c)
            if d < best:
                best = d
        return math.sqrt(best)


def surface_chamfer(expected_queries: list[Vec], actual_queries: list[Vec],
                    expected_geom: Geometry, actual_geom: Geometry,
                    tolerance: float) -> tuple[float, float]:
    actual_index = TriangleIndex(actual_geom)
    expected_index = TriangleIndex(expected_geom)
    forward = [actual_index.nearest(p) for p in expected_queries]
    backward = [expected_index.nearest(p) for p in actual_queries]
    chamfer = 0.5 * (sum(forward) / len(forward) + sum(backward) / len(backward))
    coverage = min(sum(d <= tolerance for d in forward) / len(forward),
                   sum(d <= tolerance for d in backward) / len(backward))
    return chamfer, coverage


def axis_rotations() -> list[list[list[float]]]:
    out: list[list[list[float]]] = []
    for perm in ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)):
        for signs in ((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)):
            m = [[0.0] * 3 for _ in range(3)]
            for row in range(3):
                m[row][perm[row]] = float(signs[row])
            if round(
                m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
            ) == 1:
                out.append(m)
    return out


AXIS_ROTATIONS = axis_rotations()
IDENTITY_3 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def transform_points(points: list[Vec], matrix: list[list[float]],
                     offset: Vec, scale: float = 1.0) -> list[Vec]:
    out = []
    for p in points:
        q = (p[0] * scale, p[1] * scale, p[2] * scale)
        out.append((
            matrix[0][0] * q[0] + matrix[0][1] * q[1] + matrix[0][2] * q[2] + offset[0],
            matrix[1][0] * q[0] + matrix[1][1] * q[1] + matrix[1][2] * q[2] + offset[1],
            matrix[2][0] * q[0] + matrix[2][1] * q[1] + matrix[2][2] * q[2] + offset[2],
        ))
    return out


def attribution(expected_geom: Geometry, actual_geom: Geometry,
                expected_queries: list[Vec], actual_queries: list[Vec],
                tolerance: float, min_coverage: float) -> str:
    actual_vertices, actual_faces = actual_geom
    stride = max(1, len(actual_queries) // 500)
    actual_probe = actual_queries[::stride]

    def passes(vertices: list[Vec], queries: list[Vec]) -> bool:
        geom = (vertices, actual_faces)
        c, cov = surface_chamfer(expected_queries[::stride], queries,
                                 expected_geom, geom, tolerance)
        return c <= tolerance and cov >= min_coverage

    def candidate(matrix: list[list[float]], offset: Vec,
                  scale: float) -> bool:
        vertices = transform_points(actual_vertices, matrix, offset, scale)
        queries = transform_points(actual_probe, matrix, offset, scale)
        return passes(vertices, queries)

    ec, ac = centroid(expected_queries), centroid(actual_queries)
    shift = (ec[0] - ac[0], ec[1] - ac[1], ec[2] - ac[2])
    if candidate(IDENTITY_3, shift, 1.0):
        return "placement"
    for rotation in AXIS_ROTATIONS:
        moved = transform_points(actual_queries, rotation, (0.0, 0.0, 0.0))
        mc = centroid(moved)
        offset = (ec[0] - mc[0], ec[1] - mc[1], ec[2] - mc[2])
        if candidate(rotation, offset, 1.0):
            return "frame"
    scale = bbox_diagonal(expected_queries) / max(bbox_diagonal(actual_queries), 1e-12)
    scaled = transform_points(actual_queries, IDENTITY_3, (0.0, 0.0, 0.0), scale)
    sc = centroid(scaled)
    if candidate(IDENTITY_3,
                 (ec[0] - sc[0], ec[1] - sc[1], ec[2] - sc[2]), scale):
        return "unit"
    for rotation in AXIS_ROTATIONS:
        moved = transform_points(actual_queries, rotation, (0.0, 0.0, 0.0), scale)
        mc = centroid(moved)
        offset = (ec[0] - mc[0], ec[1] - mc[1], ec[2] - mc[2])
        if candidate(rotation, offset, scale):
            return "frame+unit"
    return "shape"


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def load_mesh(path: Path) -> Geometry:
    if path.suffix.lower() == ".obj":
        return load_obj(path)
    if path.suffix.lower() == ".json":
        return load_json_mesh(path)
    raise ValueError(f"unsupported exported mesh format {path.suffix!r}")


def expected_manifest(spec: dict[str, Any], scene: dict[str, Any],
                      mapping: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Derive the expected part directories and link OBJs independently.

    A task-visible ``part_contract`` selects the Group-hierarchy rule: a part is
    a Group with direct primitive leaf children, and each leaf is one link OBJ
    named with the source object name.  Without that contract, the spec's
    mapping is the task-visible contract and its output paths provide both sets.
    The producer's manifest is never consulted.
    """
    contract = spec.get("part_contract")
    if isinstance(contract, dict):
        nodes = scene.get("nodes")
        if not isinstance(nodes, dict) or not nodes:
            return None, "part_contract requires a native scene graph"
        group_type = str(contract.get("group_type", "Group"))
        leaf_type = str(contract.get("primitive_leaf_type", "Mesh"))
        parts: dict[str, list[str]] = {}
        for name, node in nodes.items():
            if not isinstance(node, dict) or "primitive" in node:
                continue
            if str(node.get("type", "")) != group_type:
                continue
            leaf_names: list[str] = []
            for child_name in node.get("children", []) or []:
                child = nodes.get(str(child_name))
                if not isinstance(child, dict) or "primitive" not in child:
                    continue
                if str(child.get("type", "")) != leaf_type:
                    return None, (f"primitive child {child_name!r} of part {name!r} "
                                  f"is not a {leaf_type} leaf")
                if child.get("children"):
                    return None, (f"primitive child {child_name!r} of part {name!r} "
                                  "has children and is not a leaf")
                leaf_names.append(str(child_name))
            if leaf_names:
                if name in parts:
                    return None, f"duplicate part Group name {name!r}"
                parts[name] = sorted(f"{leaf_name}.obj" for leaf_name in leaf_names)
        if not parts:
            return None, ("part_contract found no Group with direct primitive "
                          "leaf children")
        links = {Path(part, link).as_posix()
                 for part, part_links in parts.items() for link in part_links}
        return {"parts": parts, "directories": sorted(parts),
                "links": sorted(links)}, None

    directories: set[str] = set()
    links: set[str] = set()
    for mesh_name in mapping:
        rel = Path(str(mesh_name))
        if rel.is_absolute() or ".." in rel.parts:
            return None, f"mapping has an unsafe mesh path {mesh_name!r}"
        links.add(rel.as_posix())
        if rel.parent != Path("."):
            directories.add(rel.parent.as_posix())
    if not links:
        return None, "spec has no task-derived part and link manifest"
    return {"parts": {}, "directories": sorted(directories),
            "links": sorted(links)}, None


def artifact_manifest(root: Path) -> dict[str, Any]:
    """Enumerate only what exists in the produced artifact tree."""
    directories: set[str] = set()
    links: set[str] = set()
    for entry in root.rglob("*"):
        rel = entry.relative_to(root).as_posix()
        if entry.is_dir():
            directories.add(rel)
        elif entry.suffix.lower() == ".obj":
            links.add(rel)
    return {"directories": sorted(directories), "links": sorted(links)}


def compare_manifest(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    missing_dirs = sorted(set(expected["directories"]) - set(actual["directories"]))
    extra_dirs = sorted(set(actual["directories"]) - set(expected["directories"]))
    missing_links = sorted(set(expected["links"]) - set(actual["links"]))
    extra_links = sorted(set(actual["links"]) - set(expected["links"]))
    renamed: list[dict[str, str]] = []
    missing_by_name: dict[str, list[str]] = {}
    for link in missing_links:
        missing_by_name.setdefault(Path(link).name, []).append(link)
    for link in extra_links:
        for expected_link in missing_by_name.get(Path(link).name, []):
            renamed.append({"expected": expected_link, "actual": link})
    return {
        "expected": expected,
        "actual": actual,
        "missing_directories": missing_dirs,
        "extra_directories": extra_dirs,
        "missing_links": missing_links,
        "extra_links": extra_links,
        "renamed": renamed,
        "status": "pass" if not any((missing_dirs, extra_dirs, missing_links,
                                     extra_links)) else "fail",
    }


def check(artifact_root: Path, spec_path: Path) -> tuple[dict[str, Any], int]:
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "unverifiable", "error": f"cannot read spec: {exc}"}, 2
    source_value = spec.get("source")
    mapping = spec.get("mapping", spec.get("parts"))
    part_contract = isinstance(spec.get("part_contract"), dict)
    if not source_value or ((not isinstance(mapping, dict) or not mapping)
                            and not part_contract):
        return {"status": "unverifiable",
                "error": "spec needs source and either mapping or part_contract"}, 2
    if not isinstance(mapping, dict):
        mapping = {}
    frame_spec = spec.get("frame")
    if not isinstance(frame_spec, dict) or not frame_spec.get("source_up") \
            or not frame_spec.get("artifact_up"):
        return {"status": "unverifiable", "error": "spec needs declared frame up axes"}, 2
    units = spec.get("units")
    if not isinstance(units, dict) or not isinstance(
            units.get("source_to_artifact"), (int, float)):
        return {"status": "unverifiable", "error": "spec needs a declared unit scale"}, 2
    tolerance = spec.get("tolerance")
    if not isinstance(tolerance, (int, float)) or tolerance <= 0:
        return {"status": "unverifiable", "error": "spec needs a positive tolerance"}, 2
    budget = max(200, int(spec.get("sampling_budget", 2000)))
    min_coverage = float(spec.get("min_coverage", 0.90))
    tolerance = float(tolerance)
    source_path = (spec_path.parent / str(source_value)).resolve()
    provenance = reconstruction_error(spec, source_path, artifact_root, mapping)
    if provenance:
        return {"status": "unverifiable", "error": provenance}, 2
    if float(units["source_to_artifact"]) <= 0:
        return {"status": "unverifiable", "error": "unit scale must be positive"}, 2
    try:
        scene = load_scene(source_path)
        nodes = scene.get("nodes")
        if not isinstance(nodes, dict) or not nodes:
            raise ValueError("source is a mesh, not a scene graph with nodes")
        source_up = str(frame_spec["source_up"])
        artifact_up = str(frame_spec["artifact_up"])
        frame = frame_matrix(source_up, artifact_up)
        unit_scale = float(units["source_to_artifact"])
        scene_scale = float(scene.get("unit_scale", 1.0))
        if scene_scale <= 0:
            raise ValueError("scene unit_scale must be positive")
        unit_scale *= scene_scale
        root = root_matrix(scene, nodes)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {"status": "unverifiable",
                "error": f"cannot reconstruct source scene: {exc}"}, 2

    expected, manifest_error = expected_manifest(spec, scene, mapping)
    if manifest_error or expected is None:
        return {"status": "unverifiable",
                "error": f"cannot derive task-derived manifest: {manifest_error}"}, 2
    manifest = compare_manifest(expected, artifact_manifest(artifact_root))
    if manifest["status"] != "pass":
        return {"status": "fail",
                "source": str(source_value),
                "tolerance": tolerance,
                "manifest": manifest,
                "checks": [],
                "violations": []}, 1
    if part_contract:
        # Geometry expectations come from the same derived hierarchy, not from
        # a hand-maintained mapping that could hide a renamed or missing part.
        mapping = {link: Path(link).stem for link in expected["links"]}

    records: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for mesh_name, node_ref in mapping.items():
        if isinstance(node_ref, str):
            node_name = node_ref
        elif isinstance(node_ref, dict):
            node_name = node_ref.get("node")
        else:
            node_name = None
        if not node_name:
            return {"status": "unverifiable",
                    "error": f"mapping for {mesh_name!r} has no node"}, 2
        mesh_tol = tolerance
        per_mesh = spec.get("tolerances", {}).get(mesh_name)
        if isinstance(per_mesh, (int, float)) and per_mesh > 0:
            mesh_tol = float(per_mesh)
        mesh_path = (artifact_root / mesh_name).resolve()
        try:
            actual_geom = load_mesh(mesh_path)
            if not actual_geom[0]:
                raise ValueError("mesh has no vertices")
            if not actual_geom[1]:
                raise ValueError("mesh has no triangle faces")
            expected_geom = reconstruct(nodes, root, str(node_name),
                                        frame, unit_scale)
            if not expected_geom[1]:
                raise ValueError("source primitive has no surface triangles")
            expected_queries = sample_surface(expected_geom, budget)
            actual_queries = sample_surface(actual_geom, budget)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            records.append({"mesh": mesh_name,
                            "mesh_path": mesh_name,
                            "metric": "chamfer",
                            "observed": None,
                            "tolerance": mesh_tol,
                            "threshold": mesh_tol,
                            "coverage": None,
                            "min_coverage": min_coverage,
                            "attribution": "unverifiable",
                            "status": "unverifiable",
                            "detail": str(exc)})
            continue
        observed, coverage = surface_chamfer(expected_queries, actual_queries,
                                             expected_geom, actual_geom, mesh_tol)
        cause = "none" if observed <= mesh_tol and coverage >= min_coverage else \
            attribution(expected_geom, actual_geom, expected_queries,
                        actual_queries, mesh_tol, min_coverage)
        passed = observed <= mesh_tol and coverage >= min_coverage
        record = {
            "mesh": mesh_name,
            "mesh_path": mesh_name,
            "metric": "chamfer",
            "observed": round(observed, 9),
            "tolerance": mesh_tol,
            "threshold": mesh_tol,
            "coverage": round(coverage, 6),
            "min_coverage": min_coverage,
            "attribution": "none" if passed else cause,
            "status": "pass" if passed else "fail",
        }
        records.append(record)
        if not passed:
            violations.append(record)

    unverifiable = [r for r in records if r["status"] == "unverifiable"]
    status = "unverifiable" if unverifiable else ("fail" if violations else "pass")
    reconstruction = spec.get("reconstruction")
    if not isinstance(reconstruction, dict):
        reconstruction = {}
    report = {
        "status": status,
        "source": str(source_value),
        "reference": {
            "source": str(source_value),
            "method": reconstruction.get("method"),
            "independent_of_producer": reconstruction.get("independent_of_producer"),
        },
        "frame": {"source_up": source_up, "artifact_up": artifact_up},
        "units": {"source_to_artifact": unit_scale},
        "tolerance": tolerance,
        "manifest": manifest,
        "checks": records,
        "violations": violations,
    }
    if unverifiable:
        report["error"] = "one or more meshes could not be checked"
        return report, 2
    return report, 1 if violations else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check exported part meshes against a Three.js source scene.")
    parser.add_argument("artifact_root", type=Path,
                        help="root containing the exported mesh files")
    parser.add_argument("--spec", required=True, type=Path,
                        help="task-derived JSON spec (source, mapping, frame, units, tolerance)")
    parser.add_argument("--report", type=Path,
                        help="optional path to write the structured JSON report")
    args = parser.parse_args()
    report, code = check(args.artifact_root, args.spec)
    text = json.dumps(report, indent=2, sort_keys=False)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    if report["status"] == "unverifiable":
        print(f"unverifiable: {report.get('error', 'missing independent input')}",
              file=sys.stderr)
    elif report["status"] == "fail":
        manifest = report.get("manifest")
        if manifest:
            for key in ("missing_directories", "extra_directories",
                        "missing_links", "extra_links"):
                for name in manifest.get(key, []):
                    print(f"manifest {key}: {name}", file=sys.stderr)
            for pair in manifest.get("renamed", []):
                print(f"manifest renamed: {pair['expected']} -> {pair['actual']}",
                      file=sys.stderr)
        for violation in report["violations"]:
            print(f"violation: {violation['mesh']} {violation['metric']}="
                  f"{violation['observed']} > {violation['tolerance']} "
                  f"({violation['attribution']})", file=sys.stderr)
        if report["violations"]:
            failing = ", ".join(str(v["mesh"]) for v in report["violations"])
            print(f"failed meshes ({len(report['violations'])}): {failing}",
                  file=sys.stderr)
    else:
        print(f"clean: {len(report['checks'])} part and link meshes within "
              f"source-derived tolerance {report['tolerance']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
