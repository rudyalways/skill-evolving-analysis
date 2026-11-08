#!/usr/bin/env node
/**
 * Independent preflight for artifacts written by export_native_scene.mjs.
 *
 * Usage:
 *   node scripts/check_native_scene.mjs --module <scene.js|scene.mjs> \
 *     --root <artifact-directory> [--tolerance 1e-12] [--json <report.json>]
 *
 * The checker executes createScene() itself, derives every expected vertex
 * from the live position/index buffers, applies the composed world transform
 * and the Blender Z-up -90 degree X frame transfer in its own code, and
 * compares the complete OBJ by object and vertex.  It never imports the
 * producer and never treats manifest.json or a reference exporter as its
 * expectation.
 */

import { readFile, writeFile, mkdir } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import path from "node:path";
import process from "node:process";

const FRAME_ROTATION = [-90, 0, 0];

class CheckError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

const identity = () => [
  [1, 0, 0, 0],
  [0, 1, 0, 0],
  [0, 0, 1, 0],
  [0, 0, 0, 1],
];
const matmul = (a, b) => a.map((row, i) =>
  row.map((_, j) => [0, 1, 2, 3].reduce((sum, k) => sum + a[i][k] * b[k][j], 0)));
const translation = (p) => {
  const m = identity();
  m[0][3] = Number(p[0]);
  m[1][3] = Number(p[1]);
  m[2][3] = Number(p[2]);
  return m;
};
const scaling = (s) => {
  const m = identity();
  m[0][0] = Number(s[0]);
  m[1][1] = Number(s[1]);
  m[2][2] = Number(s[2]);
  return m;
};
const vec3 = (value, fallback = [0, 0, 0]) => {
  if (Array.isArray(value) && value.length === 3) return value.map(Number);
  if (value && typeof value === "object") {
    return [Number(value.x ?? fallback[0]), Number(value.y ?? fallback[1]),
            Number(value.z ?? fallback[2])];
  }
  return [...fallback];
};
const eulerXYZ = (value) => {
  const r = vec3(value);
  const [cx, sx] = [Math.cos(r[0]), Math.sin(r[0])];
  const [cy, sy] = [Math.cos(r[1]), Math.sin(r[1])];
  const [cz, sz] = [Math.cos(r[2]), Math.sin(r[2])];
  const rx = [[1, 0, 0, 0], [0, cx, -sx, 0], [0, sx, cx, 0], [0, 0, 0, 1]];
  const ry = [[cy, 0, sy, 0], [0, 1, 0, 0], [-sy, 0, cy, 0], [0, 0, 0, 1]];
  const rz = [[cz, -sz, 0, 0], [sz, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]];
  return matmul(matmul(rx, ry), rz);
};
const quaternionMatrix = (q) => {
  if (!q) return identity();
  let [x, y, z, w] = (Array.isArray(q) ? q : [q.x, q.y, q.z, q.w]).map(Number);
  const norm = Math.hypot(x, y, z, w);
  if (!norm) return identity();
  [x, y, z, w] = [x / norm, y / norm, z / norm, w / norm];
  return [
    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
    [0, 0, 0, 1],
  ];
};
const elementsToMatrix = (e) => [
  [e[0], e[4], e[8], e[12]],
  [e[1], e[5], e[9], e[13]],
  [e[2], e[6], e[10], e[14]],
  [e[3], e[7], e[11], e[15]],
];
const localMatrix = (node) => {
  if (node.matrix && node.matrix.elements && node.matrixAutoUpdate === false) {
    return elementsToMatrix(node.matrix.elements);
  }
  const rotation = node.quaternion
    ? quaternionMatrix(node.quaternion)
    : eulerXYZ(node.rotation);
  return matmul(translation(vec3(node.position)),
                matmul(rotation, scaling(vec3(node.scale, [1, 1, 1]))));
};
const transformPoint = (m, p) => [
  m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + m[0][3],
  m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + m[1][3],
  m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + m[2][3],
];
const framePoint = (p) => [p[0], p[2], -p[1]];
const otherFrames = {
  "identity-frame": (p) => [p[0], p[1], p[2]],
  "plus90-x": (p) => [p[0], -p[2], p[1]],
  "180-x": (p) => [p[0], -p[1], -p[2]],
};

const arrayOf = (attribute) => {
  const values = attribute && (attribute.array ?? attribute);
  if (!values || typeof values.length !== "number") {
    throw new CheckError("UNSUPPORTED_ATTRIBUTE", "attribute is not an array-like buffer");
  }
  return values;
};

const sourceVertices = (geometry, world) => {
  const position = geometry.attributes && geometry.attributes.position;
  if (!position) throw new CheckError("MISSING_POSITION", "mesh has no position buffer");
  const source = arrayOf(position);
  if (Number(position.itemSize || 3) !== 3 || source.length % 3 !== 0) {
    throw new CheckError("UNSUPPORTED_POSITION", "position is not a 3-component buffer");
  }
  const index = geometry.index;
  const order = [];
  if (index) {
    const values = arrayOf(index);
    for (let i = 0; i < values.length; i += 1) order.push(Number(values[i]));
  } else {
    for (let i = 0; i < source.length / 3; i += 1) order.push(i);
  }
  const vertices = order.map((vertexIndex) => {
    const offset = vertexIndex * 3;
    return transformPoint(world, [source[offset], source[offset + 1], source[offset + 2]]);
  });
  return {
    vertices,
    indexed: Boolean(index),
    sourceArrayType: source.constructor?.name || "Array",
    float32Positions: source instanceof Float32Array,
    sourceVertexCount: source.length / 3,
    sourceIndexCount: index ? arrayOf(index).length : 0,
    triangles: vertices.length / 3,
    expansion: index ? "toNonIndexed" : "native-non-indexed",
  };
};

const instanceMatrices = (node, label) => {
  const matrix = node.instanceMatrix;
  const array = matrix && (matrix.array ?? matrix);
  const count = Number(node.count ?? (array && typeof array.length === "number" ? array.length / 16 : 0));
  if (!array || typeof array.length !== "number" || !Number.isInteger(count) || count < 1
      || array.length < count * 16) {
    throw new CheckError("UNSUPPORTED_INSTANCING",
      `${label}: instanced mesh has no readable instanceMatrix with count instances`);
  }
  const matrices = [];
  for (let instance = 0; instance < count; instance += 1) {
    const slice = Array.from(array.slice(instance * 16, instance * 16 + 16), Number);
    if (slice.some((value) => !Number.isFinite(value))) {
      throw new CheckError("UNSUPPORTED_INSTANCING",
        `${label}: instance ${instance} has a non-finite instanceMatrix`);
    }
    matrices.push(elementsToMatrix(slice));
  }
  return matrices;
};

const collectExpected = (scene) => {
  const expected = new Map();
  const walk = (node, parentWorld, names, isRoot) => {
    if (!node || typeof node !== "object") return;
    const world = node.matrixWorld && node.matrixWorld.elements
      ? elementsToMatrix(node.matrixWorld.elements)
      : matmul(parentWorld, localMatrix(node));
    const nextNames = isRoot ? [] : [...names, String(node.name || "")];
    if (node.geometry && node.geometry.attributes && node.geometry.attributes.position) {
      const baseLabel = nextNames.filter(Boolean).join("/");
      if (!baseLabel) throw new CheckError("UNNAMED_MESH", "mesh without a name path");
      const instanced = Boolean(node.isInstancedMesh || node.instanceMatrix);
      if (instanced) {
        const matrices = instanceMatrices(node, baseLabel);
        matrices.forEach((matrix, instance) => {
          const label = `${baseLabel}#instance_${instance}`;
          if (expected.has(label)) {
            throw new CheckError("DUPLICATE_MESH", `${label}: duplicate source mesh name`);
          }
          expected.set(label, {
            ...sourceVertices(node.geometry, matmul(world, matrix)),
            hierarchy: [...nextNames.slice(0, -1)],
            worldTransform: matmul(world, matrix),
            instanced: true,
            instance,
          });
        });
      } else {
        if (expected.has(baseLabel)) {
          throw new CheckError("DUPLICATE_MESH", `${baseLabel}: duplicate source mesh name`);
        }
        expected.set(baseLabel, {
          ...sourceVertices(node.geometry, world),
          hierarchy: [...nextNames.slice(0, -1)],
          worldTransform: world,
          instanced: false,
          instance: null,
        });
      }
    }
    for (const child of node.children || []) walk(child, world, nextNames, false);
  };
  walk(scene, identity(), [], true);
  return expected;
};

const parseObj = (text) => {
  const vertices = [];
  const objects = new Map();
  let current = null;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const [keyword, ...rest] = line.split(/\s+/);
    if (keyword === "o" || keyword === "g") {
      const name = rest.join(" ");
      if (!objects.has(name)) {
        objects.set(name, { name, vertices: [], faces: [], vertexStart: vertices.length });
      }
      current = objects.get(name);
      objects.set(name, current);
    } else if (keyword === "v") {
      const vertex = rest.slice(0, 3).map(Number);
      vertices.push(vertex);
      if (current) current.vertices.push(vertex);
    } else if (keyword === "f") {
      if (!current) throw new CheckError("BAD_OBJ", "face before an object declaration");
      if (rest.length !== 3) throw new CheckError("BAD_OBJ", `${current.name}: non-triangle face`);
      current.faces.push(rest.map((token) => {
        const oneBased = Number(token.split("/")[0]);
        if (!Number.isInteger(oneBased) || oneBased === 0) {
          throw new CheckError("BAD_OBJ", `${current.name}: bad face reference ${token}`);
        }
        return oneBased - 1;
      }));
    }
  }
  for (const object of objects.values()) {
    object.triangles = object.faces.map((face) => face.map((index) => {
      if (!vertices[index]) throw new CheckError("BAD_OBJ", `${object.name}: face index out of range`);
      return vertices[index];
    }));
  }
  return { objects, vertexCount: vertices.length, faceCount: [...objects.values()]
    .reduce((sum, object) => sum + object.faces.length, 0) };
};

const bounds = (points) => {
  if (!points.length) return null;
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const point of points) {
    for (let i = 0; i < 3; i += 1) {
      min[i] = Math.min(min[i], point[i]);
      max[i] = Math.max(max[i], point[i]);
    }
  }
  return { min, max };
};

const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

const matches = (actual, candidate, tolerance) =>
  distance(actual, candidate) <= tolerance;

const compareMesh = (name, expected, actual, tolerance) => {
  const framed = expected.vertices.map(framePoint);
  const record = {
    mesh: name,
    status: "pass",
    hierarchy: expected.hierarchy,
    world_transform: expected.worldTransform,
    instanced: expected.instanced,
    instance: expected.instance,
    indexed: expected.indexed,
    expansion: expected.expansion,
    source_array_type: expected.sourceArrayType,
    float32_positions: expected.float32Positions,
    source_vertex_count: expected.sourceVertexCount,
    source_index_count: expected.sourceIndexCount,
    expected_vertex_count: expected.vertices.length,
    actual_vertex_count: actual ? actual.vertices.length : 0,
    expected_triangle_count: expected.triangles,
    actual_triangle_count: actual ? actual.triangles.length : 0,
    non_indexed_output: Boolean(actual
      && actual.vertices.length === expected.vertices.length),
    face_winding: "pass",
    component_order: "pass",
    round_trip_precision: "pass",
    coordinate_tolerance: tolerance,
    coordinate_error: 0,
    max_position_delta: 0,
    expected_bounds: bounds(framed),
    actual_bounds: actual ? bounds(actual.vertices) : null,
    violations: [],
  };
  if (!actual) {
    record.status = "fail";
    record.violations.push({ code: "missing_mesh", mesh: name, message: `missing OBJ object ${name}` });
    return record;
  }
  if (actual.triangles.length !== expected.triangles) {
    record.status = "fail";
    record.violations.push({
      code: "triangle_count",
      mesh: name,
      expected: expected.triangles,
      actual: actual.triangles.length,
    });
  }
  if (actual.vertices.length !== expected.vertices.length) {
    record.status = "fail";
    record.violations.push({
      code: "vertex_count",
      mesh: name,
      expected: expected.vertices.length,
      actual: actual.vertices.length,
    });
  }
  // Structural expansion check: every OBJ face must be a triangle over the
  // consecutive non-indexed vertices for its triangle slot, in source order.
  if (actual.triangles.length === expected.triangles) {
    for (let t = 0; t < expected.triangles; t += 1) {
      const face = actual.faces?.[t];
      if (!face) break;
      for (let corner = 0; corner < 3; corner += 1) {
        if (face[corner] - actual.vertexStart !== t * 3 + corner) {
          record.face_winding = "fail";
          record.status = "fail";
          record.violations.push({
            code: "face_topology",
            mesh: name,
            triangle: t,
            corner,
            expected_vertex: t * 3 + corner,
            actual_vertex: face[corner] - actual.vertexStart,
            message: "face does not reference consecutive triangle-expanded vertices; indexed output or reordered winding",
          });
          t = expected.triangles;
          break;
        }
      }
    }
  }
  const count = Math.min(actual.vertices.length, framed.length);
  let worst = { error: 0, index: -1 };
  let firstFailures = [];
  for (let i = 0; i < count; i += 1) {
    const observed = distance(actual.vertices[i], framed[i]);
    if (observed > worst.error) worst = { error: observed, index: i };
    if (observed > tolerance) {
      firstFailures.push({ index: i, error: observed });
      record.status = "fail";
      if (firstFailures.length >= 20) break;
    }
  }
  record.coordinate_error = worst.error;
  record.max_position_delta = worst.error;
  let componentMismatch = false;
  for (let i = 0; i < count; i += 1) {
    for (let axis = 0; axis < 3; axis += 1) {
      if (Math.abs(actual.vertices[i][axis] - framed[i][axis]) > tolerance) {
        componentMismatch = true;
        break;
      }
    }
    if (componentMismatch) break;
  }
  if (componentMismatch) record.component_order = "fail";
  if (record.status === "fail" && worst.error > tolerance) {
    record.round_trip_precision = "fail";
    let attribution = "position";
    for (const [label, transform] of Object.entries(otherFrames)) {
      const candidate = expected.vertices.map(transform);
      if (actual.vertices.length === candidate.length
          && actual.vertices.every((vertex, i) => matches(vertex, candidate[i], tolerance))) {
        attribution = "frame";
        record.detected_frame = label;
        break;
      }
    }
    record.violations.push({
      code: "coordinate_round_trip",
      mesh: name,
      attribution,
      tolerance,
      coordinate_error: worst.error,
      first_mismatch_vertex_index: worst.index,
      first_mismatch_vertex: worst.index >= 0 ? {
        expected: framed[worst.index],
        actual: actual.vertices[worst.index],
      } : null,
      failing_vertex_indices: firstFailures.map((v) => v.index),
      failing_deltas: firstFailures.slice(0, 5),
    });
  }
  // Face/vertex order: the OBJ must preserve expanded triangle order, so each
  // face must reference the actual vertices that equal the matching expansion.
  const localIndex = new Map();
  actual.vertices.forEach((vertex, index) => {
    const key = `${vertex[0]},${vertex[1]},${vertex[2]}`;
    if (!localIndex.has(key)) localIndex.set(key, []);
    localIndex.get(key).push(index);
  });
  if (actual.triangles.length === expected.triangles) {
    for (let t = 0; t < expected.triangles; t += 1) {
      for (let corner = 0; corner < 3; corner += 1) {
        const wanted = framed[t * 3 + corner];
        const got = actual.triangles[t][corner];
        if (!got || distance(got, wanted) > tolerance) {
          record.status = "fail";
          record.violations.push({
            code: "triangle_order",
            mesh: name,
            triangle: t,
            corner,
            expected: wanted,
            actual: got || null,
            tolerance,
            message: "triangle-expanded face order or winding differs from the source index order",
          });
          t = expected.triangles;
          break;
        }
      }
    }
  }
  return record;
};

const run = async () => {
  const args = {};
  for (let i = 0; i < process.argv.length; i += 1) {
    if (i < 2) continue;
    const key = process.argv[i];
    if (!key.startsWith("--")) continue;
    const value = process.argv[i + 1];
    if (value === undefined || value.startsWith("--")) {
      throw new CheckError("BAD_ARGUMENT", `missing value for ${key}`);
    }
    args[key.slice(2)] = value;
    i += 1;
  }
  if (!args.module || !args.root) {
    throw new CheckError("BAD_ARGUMENT",
      "usage: check_native_scene.mjs --module <scene.js|scene.mjs> --root <artifact-directory> [--tolerance 1e-12]");
  }
  const tolerance = args.tolerance === undefined ? 1e-12 : Number(args.tolerance);
  if (!Number.isFinite(tolerance) || tolerance < 0) {
    throw new CheckError("BAD_ARGUMENT", "tolerance must be a non-negative number");
  }
  const root = path.resolve(args.root);
  let namespace;
  try {
    namespace = await import(pathToFileURL(path.resolve(args.module)).href);
  } catch (error) {
    throw new CheckError("UNVERIFIABLE_SOURCE", `${args.module}: cannot load module: ${error.message}`);
  }
  const createScene = namespace.createScene
    || (namespace.default && namespace.default.createScene);
  if (typeof createScene !== "function") {
    throw new CheckError("UNVERIFIABLE_SOURCE", `${args.module}: missing createScene() export`);
  }
  const scene = await createScene();
  if (!scene || typeof scene !== "object") {
    throw new CheckError("UNVERIFIABLE_SOURCE", `${args.module}: createScene() returned no scene`);
  }
  const expected = collectExpected(scene);
  if (!expected.size) {
    throw new CheckError("UNVERIFIABLE_SOURCE", `${args.module}: createScene() returned no positioned meshes`);
  }

  let manifest;
  let objText;
  try {
    manifest = JSON.parse(await readFile(path.join(root, "manifest.json"), "utf8"));
    objText = await readFile(path.join(root, manifest.artifact || "scene.obj"), "utf8");
  } catch (error) {
    return reportResult({
      status: "unverifiable",
      error: `complete artifact set is missing: ${error.message}`,
      artifact_root: root,
    }, 2, args.json);
  }
  const obj = parseObj(objText);
  const expectedNames = new Set(expected.keys());
  const actualNames = new Set(obj.objects.keys());
  const missing = [...expectedNames].filter((name) => !actualNames.has(name));
  const extra = [...actualNames].filter((name) => !expectedNames.has(name));
  const manifestProblems = [];
  if (manifest.status !== "produced") manifestProblems.push("status");
  if (Number(manifest.mesh_count) !== expected.size) manifestProblems.push("mesh_count");
  if (!Array.isArray(manifest.meshes)) manifestProblems.push("mesh records");
  if (manifest.frame?.rotation_degrees_xyz?.join(",") !== FRAME_ROTATION.join(",")) {
    manifestProblems.push("frame rotation");
  }
  if (Number(manifest.vertex_count) !== obj.vertexCount) manifestProblems.push("vertex_count");
  if (Number(manifest.triangle_count) !== obj.faceCount) manifestProblems.push("triangle_count");

  const checks = [...expected.entries()].map(([name, data]) =>
    compareMesh(name, data, obj.objects.get(name), tolerance));
  const failures = checks.filter((check) => check.status !== "pass");
  const pass = !missing.length && !extra.length && !manifestProblems.length && !failures.length;
  const result = {
    status: pass ? "pass" : "fail",
    probe: "native-scene-compatibility",
    artifact_root: root,
    source_module: args.module,
    frame: {
      name: "blender-z-up",
      rotation_degrees_xyz: FRAME_ROTATION,
    },
    coordinate_tolerance: tolerance,
    expected_meshes: [...expectedNames],
    actual_meshes: [...actualNames],
    missing_meshes: missing,
    extra_meshes: extra,
    manifest_problems: manifestProblems,
    failures: [
      ...missing.map((mesh) => ({ code: "missing_mesh", mesh })),
      ...extra.map((mesh) => ({ code: "extra_mesh", mesh })),
      ...manifestProblems.map((problem) => ({ code: "manifest", detail: problem })),
      ...failures.flatMap((check) => check.violations
        .map((violation) => ({ ...violation, mesh: check.mesh }))),
    ],
    checks,
  };
  return reportResult(result, pass ? 0 : 1, args.json);
};

const reportResult = async (result, code, jsonPath) => {
  const text = `${JSON.stringify(result, null, 2)}\n`;
  if (jsonPath) {
    await mkdir(path.dirname(path.resolve(jsonPath)), { recursive: true });
    await writeFile(path.resolve(jsonPath), text, "utf8");
  }
  (code === 0 ? process.stdout : process.stderr).write(text);
  process.exitCode = code;
};

run().catch((error) => {
  const result = {
    status: error.code && error.code.startsWith("UNVERIFIABLE") ? "unverifiable" : "fail",
    code: error.code || "CHECK_FAILED",
    message: error.message,
  };
  process.stderr.write(`${JSON.stringify(result, null, 2)}\n`);
  process.exitCode = result.status === "unverifiable" ? 2 : 1;
});
