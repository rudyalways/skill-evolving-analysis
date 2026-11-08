#!/usr/bin/env node
/**
 * Independent source-native OBJ checker.
 *
 * Usage:
 *   node scripts/check_native_export.mjs --config <native_export_spec.json> \
 *     --artifact <artifact.obj> [--json <report.json>]
 *
 * The checker executes the configured clean .js/.mjs module itself, calls its
 * createScene() export, and rebuilds each expected mesh from the live
 * geometry.attributes.position and geometry.index buffers in its own code.
 * Indexed geometry is expanded to non-indexed triangles for comparison.  The
 * checker never imports the producer and never reads geometry.parameters or a
 * producer manifest as its expectation.
 */

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import path from "node:path";
import process from "node:process";

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

const asVector = (value, fallback = [0, 0, 0]) => {
  if (Array.isArray(value) && value.length === 3) return value.map(Number);
  if (value && typeof value === "object") {
    return [Number(value.x ?? fallback[0]), Number(value.y ?? fallback[1]),
            Number(value.z ?? fallback[2])];
  }
  return [...fallback];
};

const eulerMatrix = (value) => {
  const r = asVector(value);
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

const localMatrix = (node) => {
  if (node.matrix && node.matrix.elements && node.matrixAutoUpdate === false) {
    return elementsToMatrix(node.matrix.elements);
  }
  const rotation = node.quaternion
    ? quaternionMatrix(node.quaternion)
    : eulerMatrix(node.rotation);
  return matmul(translation(asVector(node.position)),
                matmul(rotation, scaling(asVector(node.scale, [1, 1, 1]))));
};

const elementsToMatrix = (e) => [
  [e[0], e[4], e[8], e[12]],
  [e[1], e[5], e[9], e[13]],
  [e[2], e[6], e[10], e[14]],
  [e[3], e[7], e[11], e[15]],
];

const transform = (m, p) => [
  m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + m[0][3],
  m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + m[1][3],
  m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + m[2][3],
];

const arrayOf = (attribute) => {
  const array = attribute && (attribute.array ?? attribute);
  if (!array || typeof array.length !== "number") {
    throw new Error("unsupported geometry attribute");
  }
  return array;
};

const sourceTriangles = (geometry, world) => {
  const position = geometry.attributes && geometry.attributes.position;
  if (!position) throw new Error("mesh has no geometry.attributes.position");
  const source = arrayOf(position);
  const index = geometry.index;
  const indices = [];
  if (index) {
    const values = arrayOf(index);
    for (let i = 0; i < values.length; i += 1) indices.push(Number(values[i]));
  } else {
    for (let i = 0; i < source.length / 3; i += 1) indices.push(i);
  }
  const triangles = [];
  for (let i = 0; i + 2 < indices.length; i += 3) {
    const triangle = [];
    for (const vertexIndex of [indices[i], indices[i + 1], indices[i + 2]]) {
      const offset = vertexIndex * 3;
      triangle.push(transform(world,
        [source[offset], source[offset + 1], source[offset + 2]]));
    }
    triangles.push(triangle);
  }
  return {
    triangles,
    sourceIndexCount: index ? arrayOf(index).length : 0,
    sourceVertexCount: source.length / 3,
  };
};

const walkExpected = (scene) => {
  const expected = new Map();
  const walk = (node, parentWorld, names, isRoot) => {
    if (!node || typeof node !== "object") return;
    const world = node.matrixWorld && node.matrixWorld.elements
      ? elementsToMatrix(node.matrixWorld.elements)
      : matmul(parentWorld, localMatrix(node));
    const nextNames = isRoot ? [] : [...names, String(node.name || "")];
    if (node.geometry && node.geometry.attributes && node.geometry.attributes.position) {
      const label = nextNames.filter(Boolean).join("/");
      if (!label) throw new Error("mesh without a name path");
      const data = sourceTriangles(node.geometry, world);
      expected.set(label, { ...data, indexed: Boolean(node.geometry.index) });
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
      current = objects.get(name) || { name, faces: [] };
      objects.set(name, current);
    } else if (keyword === "v") {
      vertices.push(rest.slice(0, 3).map(Number));
    } else if (keyword === "f") {
      if (!current) throw new Error("OBJ face before an object declaration");
      if (rest.length !== 3) throw new Error(`${current.name}: non-triangle face`);
      current.faces.push(rest.map((token) => {
        const index = Number(token.split("/")[0]);
        if (!Number.isInteger(index) || index === 0) {
          throw new Error(`${current.name}: unsupported face vertex reference ${token}`);
        }
        return index > 0 ? index - 1 : vertices.length + index;
      }));
    }
  }
  for (const object of objects.values()) {
    object.triangles = object.faces.map((face) => face.map((index) => {
      const vertex = vertices[index];
      if (!vertex) throw new Error(`${object.name}: face index out of range`);
      return vertex;
    }));
  }
  return objects;
};

const centroid = (triangles) => {
  const sum = [0, 0, 0];
  let count = 0;
  for (const triangle of triangles) {
    for (const point of triangle) {
      sum[0] += point[0];
      sum[1] += point[1];
      sum[2] += point[2];
      count += 1;
    }
  }
  return count ? sum.map((value) => value / count) : [0, 0, 0];
};

const pairDistance = (expected, actual) => {
  let observed = 0;
  const length = Math.max(expected.length, actual.length);
  for (let i = 0; i < length; i += 1) {
    const a = expected[i];
    const b = actual[i];
    if (!a || !b) return 1e9;
    for (let j = 0; j < 3; j += 1) {
      observed = Math.max(observed, Math.hypot(
        a[j][0] - b[j][0], a[j][1] - b[j][1], a[j][2] - b[j][2]));
    }
  }
  return observed;
};

// Full-precision gate: fixed-decimal serialization rounds coordinates even when
// every triangle still lands inside a loose surface tolerance.
const coordinateDistance = (expected, actual) => {
  let observed = 0;
  const length = Math.max(expected.length, actual.length);
  for (let i = 0; i < length; i += 1) {
    const a = expected[i];
    const b = actual[i];
    if (!a || !b) return Number.POSITIVE_INFINITY;
    for (let j = 0; j < 3; j += 1) {
      for (let c = 0; c < 3; c += 1) {
        observed = Math.max(observed, Math.abs(a[j][c] - b[j][c]));
      }
    }
  }
  return observed;
};

const translatedDistance = (expected, actual) => {
  const shift = centroid(actual).map((value, i) => value - centroid(expected)[i]);
  const moved = actual.map((triangle) => triangle.map((point) => [
    point[0] - shift[0], point[1] - shift[1], point[2] - shift[2],
  ]));
  return pairDistance(expected, moved);
};

const parseArgs = (argv) => {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith("--")) throw new Error(`unexpected argument: ${key}`);
    const value = argv[i + 1];
    if (value === undefined || value.startsWith("--")) {
      throw new Error(`missing value for ${key}`);
    }
    args[key.slice(2)] = value;
    i += 1;
  }
  return args;
};

const run = async () => {
  const args = parseArgs(process.argv.slice(2));
  if (!args.config || !args.artifact) {
    throw new Error("usage: check_native_export.mjs --config <spec.json> --artifact <artifact.obj> [--json <report.json>]");
  }
  const configPath = path.resolve(args.config);
  const config = JSON.parse(await readFile(configPath, "utf8"));
  const moduleSpec = args.module || config.source_module;
  if (!moduleSpec) throw new Error(`${args.config}: source_module is required`);
  const modulePath = path.resolve(path.dirname(configPath), moduleSpec);
  const tolerance = Number(config.tolerance);
  if (!Number.isFinite(tolerance) || tolerance < 0) {
    throw new Error(`${args.config}: tolerance must be a nonnegative number`);
  }
  const precisionTolerance = Number(config.coordinate_tolerance ?? 1e-12);
  if (!Number.isFinite(precisionTolerance) || precisionTolerance < 0) {
    throw new Error(`${args.config}: coordinate_tolerance must be a nonnegative number`);
  }

  const namespace = await import(pathToFileURL(modulePath).href);
  const createScene = namespace.createScene
    || (namespace.default && namespace.default.createScene);
  if (typeof createScene !== "function") {
    throw new Error(`${moduleSpec}: missing createScene() export`);
  }
  const scene = await createScene();
  if (!scene || typeof scene !== "object") {
    throw new Error(`${moduleSpec}: createScene() returned no scene`);
  }
  const expected = walkExpected(scene);
  if (!expected.size) throw new Error(`${moduleSpec}: createScene() returned no meshes`);

  const artifactPath = path.resolve(args.artifact);
  const actual = parseObj(await readFile(artifactPath, "utf8"));

  const records = [];
  const violations = [];
  const names = new Set([...expected.keys(), ...actual.keys()]);
  for (const name of [...names].sort()) {
    const want = expected.get(name);
    const got = actual.get(name);
    if (!want || !got) {
      const record = {
        mesh: name,
        metric: "native_position_index",
        observed: 1e9,
        tolerance,
        attribution: "shape",
        status: "fail",
        reason: want ? "missing mesh in artifact" : "unexpected mesh in artifact",
      };
      records.push(record);
      violations.push(record);
      continue;
    }
    const observed = pairDistance(want.triangles, got.triangles);
    const coordinateError = coordinateDistance(want.triangles, got.triangles);
    const withinTolerance = observed <= tolerance;
    const fullPrecision = coordinateError <= precisionTolerance;
    const pass = withinTolerance && fullPrecision;
    const record = {
      mesh: name,
      metric: "native_position_index",
      observed,
      tolerance,
      coordinate_error: coordinateError,
      coordinate_tolerance: precisionTolerance,
      attribution: pass ? "none"
        : (fullPrecision && translatedDistance(want.triangles, got.triangles) <= tolerance
          ? "placement" : "shape"),
      status: pass ? "pass" : "fail",
      precision_status: fullPrecision ? "pass" : "fail",
      indexed: want.indexed,
      source_index_count: want.sourceIndexCount,
      source_vertex_count: want.sourceVertexCount,
      output_triangle_count: got.triangles.length,
      expected_triangle_count: want.triangles.length,
    };
    records.push(record);
    if (!pass) violations.push(record);
  }

  const report = {
    source_module: moduleSpec,
    artifact: args.artifact,
    tolerance,
    status: violations.length ? "fail" : "pass",
    coordinate_tolerance: precisionTolerance,
    meshes: records,
    violations,
  };
  if (args.json) {
    const reportPath = path.resolve(args.json);
    await mkdir(path.dirname(reportPath), { recursive: true });
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  }

  for (const violation of violations) {
    process.stderr.write(
      `mesh ${violation.mesh}: observed ${violation.observed} ` +
      `tolerance ${violation.tolerance} attribution ${violation.attribution} ` +
      `coordinate_error ${violation.coordinate_error} ` +
      `status ${violation.status}\n`);
  }
  process.stdout.write(`${JSON.stringify(report)}\n`);
  process.exit(violations.length ? 1 : 0);
};

run().catch((error) => {
  process.stderr.write(`unverifiable: ${error.message}\n`);
  process.exit(2);
});
