#!/usr/bin/env node
/**
 * Independent name-set and coordinate-precision preflight for the default
 * source-native part/link tree.
 *
 * Usage:
 *   node scripts/check_part_meshes.mjs --module <scene.js|scene.mjs> \
 *     --root <artifact-root> [--coordinate-tolerance <number>] [--report <json>]
 *
 * The checker reloads the native module itself, calls createScene(), derives
 * the expected part directories, part mesh OBJs, and link OBJs from the source
 * Group structure, and recomputes every expected triangle from the live
 * geometry.attributes.position and geometry.index buffers under the same
 * toNonIndexed()/OBJExporter face semantics as the producer.  It then enumerates
 * the complete produced tree and compares:
 *
 *   part_meshes/<Group name>/<Mesh name>.obj
 *   links/<Group name>.obj
 *
 * It reports every missing part directory, extra part directory, missing or
 * extra part mesh, missing or extra link OBJ, and every inexact coordinate with
 * the concrete path.  Directory existence alone never passes.
 *
 * Exit codes: 0 exact name sets and coordinates, 1 mismatch, 2 unverifiable.
 */

import { mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
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
    : eulerMatrix(node.rotation);
  return matmul(translation(asVector(node.position)),
                matmul(rotation, scaling(asVector(node.scale, [1, 1, 1]))));
};

const transform = (m, p) => [
  m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + m[0][3],
  m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + m[1][3],
  m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + m[2][3],
];

const arrayOf = (attribute) => {
  const array = attribute && (attribute.array ?? attribute);
  if (!array || typeof array.length !== "number") {
    throw new Error("unsupported geometry attribute; expected an array-like buffer");
  }
  return array;
};

const isMesh = (node) => Boolean(node && node.geometry
  && node.geometry.attributes && node.geometry.attributes.position);

const isGroup = (node) => Boolean(node && !isMesh(node)
  && (node.isGroup || node.type === "Group" || Array.isArray(node.children)));

const safeName = (name, kind) => {
  const value = String(name ?? "");
  if (!value || value === "." || value === ".." || value.includes("/")
      || value.includes("\\") || value.includes("\0")) {
    throw new Error(`${kind} has no safe source object name: ${JSON.stringify(name)}`);
  }
  return value;
};

/**
 * Independent expansion of the live position/index buffers.  It never calls
 * the producer and never reads geometry.parameters or a normalized scene.
 */
const expandedPositions = (geometry) => {
  let source = geometry;
  if (geometry.index && typeof geometry.toNonIndexed === "function") {
    source = geometry.toNonIndexed();
  }
  const position = source.attributes && source.attributes.position;
  if (!position) throw new Error("mesh has no geometry.attributes.position");
  const values = arrayOf(position);
  const indices = [];
  if (source.index) {
    const raw = arrayOf(source.index);
    for (let i = 0; i < raw.length; i += 1) indices.push(Number(raw[i]));
  } else {
    for (let i = 0; i < values.length / 3; i += 1) indices.push(i);
  }
  if (indices.length % 3 !== 0) {
    throw new Error("source index count is not a multiple of three");
  }
  const positions = [];
  for (const index of indices) {
    const offset = index * 3;
    if (!Number.isInteger(index) || offset + 2 >= values.length) {
      throw new Error(`source index ${index} is out of range for the position buffer`);
    }
    const p = [Number(values[offset]), Number(values[offset + 1]),
               Number(values[offset + 2])];
    if (!p.every(Number.isFinite)) {
      throw new Error(`mesh has a non-finite position at vertex ${index}`);
    }
    positions.push(p);
  }
  return positions;
};

const deriveExpected = (scene) => {
  const parts = new Map();
  const ungrouped = [];

  const visit = (node, parentWorld, containingPart) => {
    if (!node || typeof node !== "object") return;
    const world = matmul(parentWorld, localMatrix(node));
    if (isMesh(node)) {
      if ((node.children || []).length) {
        throw new Error(`primitive ${JSON.stringify(node.name)} is not a leaf`);
      }
      if (!containingPart) {
        ungrouped.push(String(node.name || "<unnamed>"));
        return;
      }
      const meshName = safeName(node.name, "primitive Mesh");
      if (containingPart.meshes.has(meshName)) {
        throw new Error(`duplicate primitive Mesh name ${JSON.stringify(meshName)} `
          + `in part ${JSON.stringify(containingPart.name)}; naming is ambiguous`);
      }
      containingPart.meshes.set(meshName, { node, world });
      return;
    }
    if (!isGroup(node)) return;

    const directMeshes = (node.children || []).filter(isMesh);
    let ownPart = containingPart;
    if (directMeshes.length) {
      const partName = safeName(node.name, "part Group");
      if (parts.has(partName)) {
        throw new Error(`duplicate part Group name ${JSON.stringify(partName)}; `
          + "naming is ambiguous and must be disambiguated at the source");
      }
      ownPart = { name: partName, meshes: new Map(), node };
      parts.set(partName, ownPart);
    }
    for (const child of node.children || []) {
      visit(child, world, ownPart);
    }
  };

  visit(scene, identity(), null);
  if (ungrouped.length) {
    throw new Error(`primitive leaves outside a part Group: ${ungrouped.join(", ")}`);
  }
  if (!parts.size) {
    throw new Error("createScene() hierarchy has no Group with direct primitive Mesh children");
  }
  return parts;
};

const triangleMap = (parts) => {
  const meshTriangles = new Map();
  const linkTriangles = new Map();
  for (const [partName, part] of parts) {
    const combined = [];
    for (const [meshName, mesh] of part.meshes) {
      const positions = expandedPositions(mesh.node.geometry);
      const triangles = [];
      for (let i = 0; i < positions.length; i += 3) {
        triangles.push(positions.slice(i, i + 3).map((p) => transform(mesh.world, p)));
      }
      meshTriangles.set(`${partName}/${meshName}`, triangles);
      combined.push(...triangles);
    }
    linkTriangles.set(partName, combined);
  }
  return { meshTriangles, linkTriangles };
};

const parseObj = (text, label) => {
  const vertices = [];
  const faces = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const [keyword, ...rest] = line.split(/\s+/);
    if (keyword === "v") {
      if (rest.length < 3) throw new Error(`${label}: malformed vertex record`);
      const point = rest.slice(0, 3).map(Number);
      if (!point.every(Number.isFinite)) {
        throw new Error(`${label}: non-finite vertex coordinate`);
      }
      vertices.push(point);
    } else if (keyword === "f") {
      if (rest.length !== 3) {
        throw new Error(`${label}: non-triangle face with ${rest.length} vertices; `
          + "indexed geometry must be expanded with toNonIndexed semantics");
      }
      const indices = rest.map((token) => {
        const rawIndex = Number(token.split("/")[0]);
        if (!Number.isInteger(rawIndex) || rawIndex === 0) {
          throw new Error(`${label}: unsupported face reference ${token}`);
        }
        return rawIndex > 0 ? rawIndex - 1 : vertices.length + rawIndex;
      });
      faces.push(indices);
    }
  }
  const triangles = faces.map((face) => face.map((index) => {
    const vertex = vertices[index];
    if (!vertex) throw new Error(`${label}: face index out of range`);
    return vertex;
  }));
  return { vertices, faces, triangles };
};

const compareTriangles = (expected, actual) => {
  let maxError = 0;
  let first = null;
  const count = Math.max(expected.length, actual.length);
  for (let t = 0; t < count; t += 1) {
    const want = expected[t];
    const got = actual[t];
    if (!want || !got) {
      if (!first) {
        first = { triangle: t, reason: want ? "missing triangle" : "extra triangle" };
      }
      maxError = Number.POSITIVE_INFINITY;
      continue;
    }
    for (let corner = 0; corner < 3; corner += 1) {
      for (let component = 0; component < 3; component += 1) {
        const error = Math.abs(want[corner][component] - got[corner][component]);
        if (error > maxError) maxError = error;
        if (error > 0 && !first) {
          first = {
            triangle: t,
            corner,
            component,
            expected: want[corner][component],
            actual: got[corner][component],
            error,
          };
        }
      }
    }
  }
  return { maxError, first };
};

const relativeTo = (root, target) => {
  const rel = path.relative(root, target);
  return rel.split(path.sep).join("/");
};

const listTree = async (root) => {
  const files = [];
  const directories = [];
  const walk = async (dir) => {
    const entries = await readdir(dir, { withFileTypes: true });
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        directories.push(relativeTo(root, full));
        await walk(full);
      } else if (entry.isFile()) {
        files.push(relativeTo(root, full));
      }
    }
  };
  await walk(root);
  return { files, directories };
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
  if (!args.module || !args.root) {
    throw new Error("usage: check_part_meshes.mjs --module <scene.js|scene.mjs> --root <artifact-root>");
  }
  if (!/\.(?:js|mjs)$/i.test(args.module)) {
    throw new Error("--module must be a .js or .mjs native module");
  }
  const coordinateTolerance = Number(args["coordinate-tolerance"] ?? 1e-12);
  if (!Number.isFinite(coordinateTolerance) || coordinateTolerance < 0) {
    throw new Error("--coordinate-tolerance must be a nonnegative number");
  }

  const modulePath = path.resolve(args.module);
  const root = path.resolve(args.root);
  const rootStat = await stat(root).catch(() => null);
  if (!rootStat || !rootStat.isDirectory()) {
    throw new Error(`${args.root}: artifact root does not exist or is not a directory`);
  }

  const namespace = await import(pathToFileURL(modulePath).href);
  const createScene = typeof namespace.createScene === "function"
    ? namespace.createScene
    : namespace.default && namespace.default.createScene;
  if (typeof createScene !== "function") {
    throw new Error(`${args.module}: missing createScene() export`);
  }
  const scene = await createScene();
  if (!scene || typeof scene !== "object") {
    throw new Error(`${args.module}: createScene() returned no scene`);
  }

  const parts = deriveExpected(scene);
  const { meshTriangles, linkTriangles } = triangleMap(parts);
  const expectedParts = [...parts.keys()].sort();
  const expectedMeshes = [...meshTriangles.keys()].sort();
  const expectedLinks = [...linkTriangles.keys()].sort();
  const expectedMeshFiles = expectedMeshes.map((name) => `${name}.obj`);

  const tree = await listTree(root);
  const actualPartDirs = new Set();
  const actualMeshFiles = [];
  const actualLinkFiles = [];
  const unexpectedObj = [];

  for (const file of tree.files) {
    if (!file.toLowerCase().endsWith(".obj")) continue;
    const segments = file.split("/");
    if (segments[0] === "part_meshes" && segments.length === 3) {
      actualPartDirs.add(segments[1]);
      actualMeshFiles.push(`${segments[1]}/${segments[2]}`);
    } else if (segments[0] === "links" && segments.length === 2) {
      actualLinkFiles.push(segments[1]);
    } else {
      unexpectedObj.push(file);
    }
  }
  for (const directory of tree.directories) {
    const segments = directory.split("/");
    if (segments[0] === "part_meshes" && segments.length === 2) {
      actualPartDirs.add(segments[1]);
    }
  }

  const actualMeshSet = new Set(actualMeshFiles);
  const actualLinkSet = new Set(actualLinkFiles);
  const missingParts = expectedParts.filter((name) => !actualPartDirs.has(name));
  const extraParts = [...actualPartDirs].filter((name) => !expectedParts.includes(name)).sort();
  const missingMeshes = expectedMeshFiles.filter((name) => !actualMeshSet.has(name));
  const extraMeshes = [...actualMeshSet].filter((name) => !expectedMeshFiles.includes(name)).sort();
  const missingLinks = expectedLinks
    .map((name) => `${name}.obj`)
    .filter((name) => !actualLinkSet.has(name));
  const extraLinks = [...actualLinkSet].filter((name) =>
    !expectedLinks.includes(name.replace(/\.obj$/i, ""))).sort();

  const violations = [];
  for (const name of missingParts) {
    violations.push({ kind: "missing_part_directory", path: `part_meshes/${name}` });
  }
  for (const name of extraParts) {
    violations.push({ kind: "extra_part_directory", path: `part_meshes/${name}` });
  }
  for (const name of missingMeshes) {
    violations.push({ kind: "missing_part_mesh", path: `part_meshes/${name}` });
  }
  for (const name of extraMeshes) {
    violations.push({ kind: "extra_part_mesh", path: `part_meshes/${name}` });
  }
  for (const name of missingLinks) {
    violations.push({ kind: "missing_link_obj", path: `links/${name}` });
  }
  for (const name of extraLinks) {
    violations.push({ kind: "extra_link_obj", path: `links/${name}` });
  }
  for (const name of unexpectedObj) {
    violations.push({ kind: "unexpected_obj", path: name });
  }

  const meshRecords = [];
  for (const [key, expected] of meshTriangles) {
    const rel = `part_meshes/${key}.obj`;
    if (!actualMeshSet.has(`${key}.obj`)) continue;
    try {
      const actual = parseObj(await readFile(path.join(root, ...rel.split("/")), "utf8"), rel);
      const { maxError, first } = compareTriangles(expected, actual.triangles);
      const pass = maxError <= coordinateTolerance;
      const record = {
        path: rel,
        expected_triangle_count: expected.length,
        actual_triangle_count: actual.triangles.length,
        coordinate_error: maxError,
        coordinate_tolerance: coordinateTolerance,
        first_mismatch: first,
        status: pass ? "pass" : "inexact",
      };
      meshRecords.push(record);
      if (!pass) {
        violations.push({
          kind: "inexact_part_mesh_coordinate",
          path: rel,
          coordinate_error: maxError,
          coordinate_tolerance: coordinateTolerance,
          first_mismatch: first,
        });
      }
    } catch (error) {
      meshRecords.push({ path: rel, status: "unverifiable", detail: error.message });
      violations.push({ kind: "unreadable_part_mesh", path: rel, detail: error.message });
    }
  }

  const linkRecords = [];
  for (const [partName, expected] of linkTriangles) {
    const rel = `links/${partName}.obj`;
    if (!actualLinkSet.has(`${partName}.obj`)) continue;
    try {
      const actual = parseObj(await readFile(path.join(root, ...rel.split("/")), "utf8"), rel);
      const { maxError, first } = compareTriangles(expected, actual.triangles);
      const pass = maxError <= coordinateTolerance;
      const record = {
        path: rel,
        expected_triangle_count: expected.length,
        actual_triangle_count: actual.triangles.length,
        coordinate_error: maxError,
        coordinate_tolerance: coordinateTolerance,
        first_mismatch: first,
        status: pass ? "pass" : "inexact",
      };
      linkRecords.push(record);
      if (!pass) {
        violations.push({
          kind: "inexact_link_coordinate",
          path: rel,
          coordinate_error: maxError,
          coordinate_tolerance: coordinateTolerance,
          first_mismatch: first,
        });
      }
    } catch (error) {
      linkRecords.push({ path: rel, status: "unverifiable", detail: error.message });
      violations.push({ kind: "unreadable_link_obj", path: rel, detail: error.message });
    }
  }

  const status = violations.length ? "fail" : "pass";
  const report = {
    status,
    source_module: modulePath,
    artifact_root: root,
    coordinate_tolerance: coordinateTolerance,
    expected: {
      part_directories: expectedParts,
      part_meshes: expectedMeshFiles,
      link_objs: expectedLinks.map((name) => `${name}.obj`),
    },
    actual: {
      part_directories: [...actualPartDirs].sort(),
      part_meshes: [...actualMeshSet].sort(),
      link_objs: [...actualLinkSet].sort(),
    },
    missing: { parts: missingParts, meshes: missingMeshes, links: missingLinks },
    extra: { parts: extraParts, meshes: extraMeshes, links: extraLinks,
             unexpected_obj: unexpectedObj },
    meshes: meshRecords,
    links: linkRecords,
    violations,
  };

  if (args.report) {
    const reportPath = path.resolve(args.report);
    await mkdir(path.dirname(reportPath), { recursive: true });
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  }

  for (const violation of violations) {
    if (violation.kind.startsWith("inexact")) {
      process.stderr.write(
        `${violation.kind}: ${violation.path} coordinate_error ` +
        `${violation.coordinate_error} > ${violation.coordinate_tolerance} ` +
        `first ${JSON.stringify(violation.first_mismatch)}\n`);
    } else {
      process.stderr.write(`${violation.kind}: ${violation.path}` +
        (violation.detail ? ` (${violation.detail})` : "") + "\n");
    }
  }
  process.stdout.write(`${JSON.stringify(report)}\n`);
  process.exit(status === "pass" ? 0 : 1);
};

run().catch((error) => {
  process.stderr.write(`unverifiable: ${error.message}\n`);
  process.exit(2);
});
