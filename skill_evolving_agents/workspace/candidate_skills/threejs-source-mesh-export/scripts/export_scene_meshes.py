#!/usr/bin/env python3
"""Export part and link meshes from a native Three.js source module.

The producer is deliberately separate from the conformance checker: it executes
the task's ``.js``/``.mjs`` module in a controlled Node.js context, calls its
exported ``createScene()``, traverses the returned scene graph, resolves the
task-declared frame and units, composes the full parent chain and scene-root
transform, tessellates each mapped source primitive, and writes deterministic
OBJ files.  It never requires a hand-authored scene JSON and never reads an
exported mesh.

Exit codes: 0 all mapped meshes written (or, with --check, written and passing
the independent checker), 1 a write/output failure or checker failure, 2 the
export cannot be established (missing spec, frame, units, module,
createScene(), mapping, or an unsupported primitive).
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
from typing import Any

Vec = tuple[float, float, float]
Mat = list[list[float]]
Geometry = tuple[list[Vec], list[tuple[int, int, int]]]


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
    """Rotation matrix for a normalized [x, y, z, w] quaternion."""
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
    """Compose a node's local translation, rotation (quaternion or Euler), scale."""
    rotation = quaternion_matrix(node.get("quaternion")) \
        if node.get("quaternion") is not None else euler_xyz(vec3(node.get("rotation")))
    return matmul(translation(vec3(node.get("position"))),
                  matmul(rotation,
                         scaling(vec3(node.get("scale"), (1.0, 1.0, 1.0)))))


def transform(m: Mat, p: Vec) -> Vec:
    x, y, z = p
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


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


def primitive_args(primitive: str, raw: Any) -> dict[str, float]:
    if isinstance(raw, dict):
        out: dict[str, float] = {}
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
        w = args.get("width", 1.0)
        h = args.get("height", 1.0)
        d = args.get("depth", 1.0)
        hw, hh, hd = w / 2.0, h / 2.0, d / 2.0
        verts = [(-hw, -hh, -hd), (hw, -hh, -hd), (hw, hh, -hd), (-hw, hh, -hd),
                 (-hw, -hh, hd), (hw, -hh, hd), (hw, hh, hd), (-hw, hh, hd)]
        faces = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 4, 5), (0, 5, 1),
                 (3, 2, 6), (3, 6, 7), (0, 3, 7), (0, 7, 4), (1, 5, 6), (1, 6, 2)]
        return verts, faces
    if primitive == "plane":
        w = args.get("width", 1.0)
        h = args.get("height", 1.0)
        g = max(2, int(args.get("segments", 8)))
        verts = [((i / (g - 1) - 0.5) * w, 0.0, (j / (g - 1) - 0.5) * h)
                 for i in range(g) for j in range(g)]
        faces: list[tuple[int, int, int]] = []
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
        bottom_c = len(verts)
        verts.append((0.0, -h / 2.0, 0.0))
        top_c = len(verts)
        verts.append((0.0, h / 2.0, 0.0))
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


_NATIVE_BRIDGE = r"""
import { pathToFileURL } from "node:url";

const modulePath = process.env.NATIVE_SCENE_MODULE;
const mod = await import(pathToFileURL(modulePath).href);
const createScene = typeof mod.createScene === "function" ? mod.createScene
  : (mod.default && typeof mod.default.createScene === "function"
    ? mod.default.createScene : null);
if (!createScene) {
  throw new Error("module does not export createScene()");
}

const vector = (value, fallback) => {
  if (Array.isArray(value) && value.length === 3) {
    return value.map(Number);
  }
  if (value && typeof value === "object") {
    return [Number(value.x ?? fallback[0]), Number(value.y ?? fallback[1]),
            Number(value.z ?? fallback[2])];
  }
  return fallback.slice();
};

// Three.js Euler order XYZ -> quaternion, so Python never has to guess order.
const eulerQuaternion = (euler) => {
  const x = Number(euler.x ?? 0), y = Number(euler.y ?? 0), z = Number(euler.z ?? 0);
  const order = String(euler.order || "XYZ");
  if (order !== "XYZ") {
    throw new Error("only XYZ Euler order is supported; provide quaternion instead");
  }
  const c1 = Math.cos(x / 2), c2 = Math.cos(y / 2), c3 = Math.cos(z / 2);
  const s1 = Math.sin(x / 2), s2 = Math.sin(y / 2), s3 = Math.sin(z / 2);
  return [
    s1 * c2 * c3 + c1 * s2 * s3,
    c1 * s2 * c3 - s1 * c2 * s3,
    c1 * c2 * s3 + s1 * s2 * c3,
    c1 * c2 * c3 - s1 * s2 * s3,
  ];
};

const quaternion = (value) => {
  if (!value) return [0, 0, 0, 1];
  if (Array.isArray(value) && value.length === 4) return value.map(Number);
  if (Array.isArray(value) && value.length === 3) {
    return eulerQuaternion({ x: value[0], y: value[1], z: value[2], order: "XYZ" });
  }
  if (value.isQuaternion || ("w" in value && "x" in value)) {
    return [Number(value.x), Number(value.y), Number(value.z), Number(value.w)];
  }
  return eulerQuaternion(value);
};

const nodes = [];
const names = new Map();
let counter = 0;

const addNode = (object, parent) => {
  counter += 1;
  const base = String(object.name || object.id || `node_${counter}`);
  let name = base;
  while (names.has(name)) {
    name = `${base}_${counter}`;
    counter += 1;
  }
  names.set(name, true);
  const record = {
    name,
    parent,
    children: [],
    position: vector(object.position, [0, 0, 0]),
    quaternion: quaternion(object.quaternion || object.rotation),
    scale: vector(object.scale, [1, 1, 1]),
  };
  const geometry = object.geometry;
  const primitive = object.primitive || (geometry && geometry.type)
    || (geometry && geometry.constructor && geometry.constructor.name);
  if (primitive) {
    record.primitive = String(primitive).replace(/Geometry$/i, "").toLowerCase();
    const args = object.args || (geometry && geometry.parameters) || {};
    record.args = { ...args };
  }
  nodes.push(record);
  for (const child of object.children || []) {
    record.children.push(addNode(child, name));
  }
  return name;
};

const scene = await createScene();
if (!scene || typeof scene !== "object") {
  throw new Error("createScene() did not return a scene graph");
}

let root;
let top = [];
if (scene.geometry) {
  root = { name: String(scene.name || "Scene"), position: [0, 0, 0],
           quaternion: [0, 0, 0, 1], scale: [1, 1, 1] };
  addNode(scene, null);
  top = [nodes[nodes.length - 1].name];
} else {
  root = {
    name: String(scene.name || "Scene"),
    position: vector(scene.position, [0, 0, 0]),
    quaternion: quaternion(scene.quaternion || scene.rotation),
    scale: vector(scene.scale, [1, 1, 1]),
  };
  top = (scene.children || []).map((child) => addNode(child, null));
}

process.stdout.write(JSON.stringify({ root, top, nodes }));
"""


def load_native_scene(path: Path) -> dict[str, Any]:
    """Execute a native module's createScene() and return its local-node graph."""
    env = dict(os.environ)
    env["NATIVE_SCENE_MODULE"] = str(path.resolve())
    try:
        proc = subprocess.run(
            ["node", "--input-type=module", "--eval", _NATIVE_BRIDGE],
            capture_output=True, text=True, timeout=120, env=env, check=False)
    except FileNotFoundError as exc:
        raise ValueError("node executable is required to execute the native module") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("native module createScene() timed out") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown Node.js failure").strip()
        raise ValueError(f"createScene() execution failed: {detail[-800:]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"createScene() bridge returned invalid JSON: {exc}") from exc
    nodes: dict[str, Any] = {}
    for record in payload.get("nodes", []):
        if not isinstance(record, dict) or not record.get("name"):
            raise ValueError("native scene bridge returned a node without a name")
        nodes[str(record["name"])] = record
    if not nodes:
        raise ValueError("native module createScene() returned no mesh nodes")
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


def root_matrix(scene: dict[str, Any], nodes: dict[str, Any]) -> Mat:
    root = scene.get("root", {})
    if isinstance(root, str):
        return node_matrix(nodes, root, ())
    if not isinstance(root, dict):
        raise ValueError("scene root must be a node name or transform object")
    return local_matrix(root)


def collect_primitives(nodes: dict[str, Any], name: str,
                       stack: tuple[str, ...]) -> list[tuple[str, dict[str, Any]]]:
    if name in stack:
        raise ValueError(f"cycle in source scene at node {name!r}")
    node = nodes.get(name)
    if not isinstance(node, dict):
        raise ValueError(f"source scene has no node {name!r}")
    out: list[tuple[str, dict[str, Any]]] = []
    if "primitive" in node:
        out.append((name, node))
    for child in node.get("children", []) or []:
        out.extend(collect_primitives(nodes, str(child), stack + (name,)))
    return out


def write_obj(path: Path, geometry: Geometry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    verts, faces = geometry
    lines = ["# deterministic source-derived export"]
    # repr(float) is the shortest decimal that round-trips to the same value.
    lines.extend(f"v {p[0]!r} {p[1]!r} {p[2]!r}" for p in verts)
    lines.extend(f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export(spec_path: Path, out_root: Path,
           module_path: Path | None = None,
           manifest_path: Path | None = None) -> tuple[dict[str, Any], int]:
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "unverifiable", "error": f"cannot read spec: {exc}"}, 2
    source_value = spec.get("source")
    mapping = spec.get("mapping")
    frame_spec = spec.get("frame")
    units_spec = spec.get("units")
    tolerance = spec.get("tolerance")
    if (not source_value and module_path is None) \
            or not isinstance(mapping, dict) or not mapping:
        return {"status": "unverifiable",
                "error": "spec needs a native module and mapping"}, 2
    if not isinstance(frame_spec, dict) or not frame_spec.get("source_up") \
            or not frame_spec.get("artifact_up"):
        return {"status": "unverifiable", "error": "spec needs declared frame up axes"}, 2
    if not isinstance(units_spec, dict) or not isinstance(
            units_spec.get("source_to_artifact"), (int, float)):
        return {"status": "unverifiable", "error": "spec needs declared unit scale"}, 2
    if not isinstance(tolerance, (int, float)) or tolerance <= 0:
        return {"status": "unverifiable", "error": "spec needs a positive tolerance"}, 2
    unit_scale = float(units_spec["source_to_artifact"])
    if unit_scale <= 0:
        return {"status": "unverifiable", "error": "unit scale must be positive"}, 2

    if module_path is not None:
        source_path = module_path.resolve()
        if source_path.suffix.lower() not in (".js", ".mjs"):
            return {"status": "unverifiable",
                    "error": "--module must be a .js or .mjs native module"}, 2
    else:
        source_path = (spec_path.parent / str(source_value)).resolve()
    try:
        scene = load_scene(source_path)
        nodes = scene.get("nodes")
        if not isinstance(nodes, dict) or not nodes:
            raise ValueError("source is a mesh, not a scene graph with nodes")
        frame = frame_matrix(str(frame_spec["source_up"]),
                             str(frame_spec["artifact_up"]))
        root = root_matrix(scene, nodes)
        scene_scale = float(scene.get("unit_scale", 1.0))
        if scene_scale <= 0:
            raise ValueError("scene unit_scale must be positive")
        total_scale = unit_scale * scene_scale
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "unverifiable",
                "error": f"cannot read source scene: {exc}"}, 2

    prepared: list[tuple[str, Geometry]] = []
    for mesh_name, node_ref in mapping.items():
        node_name = node_ref if isinstance(node_ref, str) else node_ref.get("node") \
            if isinstance(node_ref, dict) else None
        if not node_name:
            return {"status": "unverifiable",
                    "error": f"mapping for {mesh_name!r} has no node"}, 2
        rel = Path(str(mesh_name))
        if rel.is_absolute() or ".." in rel.parts:
            return {"status": "unverifiable",
                    "error": f"mesh path must stay under the output root: {mesh_name!r}"}, 2
        verts: list[Vec] = []
        faces: list[tuple[int, int, int]] = []
        try:
            for owner, node in collect_primitives(nodes, str(node_name), ()):
                primitive = str(node["primitive"]).lower()
                if primitive.endswith("geometry"):
                    primitive = primitive[:-8]
                args = primitive_args(primitive, node.get("args"))
                geom = primitive_geometry(primitive, args)
                local = node_matrix(nodes, owner, ())
                matrix = matmul(root, local)
                offset = len(verts)
                verts.extend(transform(frame, transform(matrix, (
                    p[0] * total_scale, p[1] * total_scale, p[2] * total_scale)))
                    for p in geom[0])
                faces.extend((a + offset, b + offset, c + offset)
                             for a, b, c in geom[1])
            if not verts or not faces:
                raise ValueError(f"source node {node_name!r} produced no surface")
        except (ValueError, KeyError) as exc:
            return {"status": "unverifiable",
                    "error": f"cannot export {mesh_name!r}: {exc}"}, 2
        prepared.append((str(mesh_name), (verts, faces)))

    written = []
    try:
        for mesh_name, geometry in prepared:
            write_obj(out_root / mesh_name, geometry)
            written.append(mesh_name)
    except OSError as exc:
        return {"status": "fail", "error": f"cannot write mesh: {exc}",
                "written": written}, 1
    if manifest_path is not None:
        manifest = {
            "status": "produced",
            "source_module": str(source_path),
            "out": str(out_root),
            "meshes": written,
            "frame": {"source_up": str(frame_spec["source_up"]).upper(),
                      "artifact_up": str(frame_spec["artifact_up"]).upper()},
            "units": {"source_to_artifact": unit_scale,
                      "scene_unit_scale": scene_scale,
                      "effective_scale": total_scale},
            "nodes": [
                {key: node.get(key) for key in
                 ("name", "parent", "position", "quaternion", "scale",
                  "primitive", "args", "children")}
                for node in nodes.values()
            ],
        }
        try:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n",
                                     encoding="utf-8")
        except OSError as exc:
            return {"status": "fail", "error": f"cannot write manifest: {exc}",
                    "written": written}, 1
    return {
        "status": "pass",
        "source": str(source_path),
        "out": str(out_root),
        "frame": {"source_up": str(frame_spec["source_up"]).upper(),
                  "artifact_up": str(frame_spec["artifact_up"]).upper()},
        "units": {"source_to_artifact": unit_scale,
                  "scene_unit_scale": scene_scale,
                  "effective_scale": total_scale},
        "tolerance": float(tolerance),
        "meshes": written,
    }, 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute a native Three.js module and export its part meshes.")
    parser.add_argument("--module", type=Path,
                        help="native .js/.mjs module exporting createScene(); "
                             "defaults to the spec's source")
    parser.add_argument("--spec", required=True, type=Path,
                        help="task-derived JSON spec (source, mapping, frame, units)")
    parser.add_argument("--out", required=True, type=Path,
                        help="artifact root for the exported OBJ meshes")
    parser.add_argument("--manifest", type=Path,
                        help="optional output-only scene manifest (never an input)")
    parser.add_argument("--check", action="store_true",
                        help="run check_mesh_conformance.py over the written tree "
                             "in this same command and return its exit status")
    parser.add_argument("--report", type=Path,
                        help="checker report path used with --check")
    args = parser.parse_args()
    report, code = export(args.spec, args.out, args.module, args.manifest)
    print(json.dumps(report, indent=2))
    if code == 2:
        print(f"unverifiable: {report.get('error', 'missing export input')}",
              file=sys.stderr)
    elif code == 1:
        print(f"export failed: {report.get('error', 'write failure')}",
              file=sys.stderr)
    if code != 0 or not args.check:
        return code
    checker = Path(__file__).with_name("check_mesh_conformance.py")
    command = [sys.executable, str(checker), str(args.out),
               "--spec", str(args.spec)]
    if args.report is not None:
        command.extend(["--report", str(args.report)])
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
