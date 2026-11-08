#!/usr/bin/env node
/**
 * One-command native Three.js scene producer.
 *
 * Usage:
 *   node scripts/export_native_scene.mjs --module <scene.js|scene.mjs> \
 *     --out <artifact-directory> [--name scene.obj]
 *
 * The only scene input is an executable .js/.mjs module exporting
 * createScene().  The command calls it, walks the returned scene, expands
 * indexed geometry with toNonIndexed() (or an equivalent), applies the
 * composed world transform and the Blender Z-up frame transfer
 * (rotation of -90 degrees about X), and writes the requested OBJ plus
 * manifest.json.  No normalized intermediate scene is read or written.
 */

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import path from "node:path";
import process from "node:process";

const FRAME = {
  name: "blender-z-up",
  source_up: "Y",
  artifact_up: "Z",
  rotation_degrees_xyz: [-90, 0, 0],
};

class ProducerError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

const fail = (code, message, details) => {
  throw new ProducerError(code, message, details);
};

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

const normalMatrix = (m) => {
  const a = m[0][0], b = m[0][1], c = m[0][2];
  const d = m[1][0], e = m[1][1], f = m[1][2];
  const g = m[2][0], h = m[2][1], i = m[2][2];
  const det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
  if (!det) return [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  const inv = 1 / det;
  return [
    [(e * i - f * h) * inv, (c * h - b * i) * inv, (b * f - c * e) * inv],
    [(f * g - d * i) * inv, (a * i - c * g) * inv, (c * d - a * f) * inv],
    [(d * h - e * g) * inv, (b * g - a * h) * inv, (a * e - b * d) * inv],
  ];
};

const transformNormal = (n, p) => {
  const v = [
    n[0] * p[0][0] + n[1] * p[1][0] + n[2] * p[2][0],
    n[0] * p[0][1] + n[1] * p[1][1] + n[2] * p[2][1],
    n[0] * p[0][2] + n[1] * p[1][2] + n[2] * p[2][2],
  ];
  const length = Math.hypot(v[0], v[1], v[2]);
  return length ? v.map((x) => x / length) : v;
};

// Blender up-axis transfer: (x, y, z) -> (x, z, -y), i.e. -90 degrees about X.
const framePoint = (p) => [p[0], p[2], -p[1]];
const frameNormal = (n) => [n[0], n[2], -n[1]];

const attributeArray = (attribute, label) => {
  if (!attribute) return null;
  const array = attribute.array ?? attribute;
  if (!array || typeof array.length !== "number") {
    fail("UNSUPPORTED_ATTRIBUTE", `${label}: attribute is not an array-like buffer`,
      { mesh: label });
  }
  return array;
};

const expandIndexed = (geometry, label) => {
  const index = geometry.index;
  if (!index) return geometry;
  if (typeof geometry.toNonIndexed === "function") {
    const expanded = geometry.toNonIndexed();
    if (!expanded || !expanded.attributes || !expanded.attributes.position) {
      fail("UNSUPPORTED_INDEX", `${label}: toNonIndexed() returned no position buffer`,
        { mesh: label });
    }
    return expanded;
  }
  const indexArray = attributeArray(index, label);
  const attributes = {};
  for (const [name, attribute] of Object.entries(geometry.attributes)) {
    const source = attributeArray(attribute, label);
    const itemSize = Number(attribute.itemSize || (name === "position" ? 3 : 1));
    const ArrayType = source.constructor && source.constructor !== Array
      ? source.constructor : Float32Array;
    const expanded = new ArrayType(indexArray.length * itemSize);
    for (let i = 0; i < indexArray.length; i += 1) {
      const read = Number(indexArray[i]) * itemSize;
      for (let c = 0; c < itemSize; c += 1) {
        expanded[i * itemSize + c] = source[read + c];
      }
    }
    attributes[name] = { array: expanded, itemSize, count: indexArray.length };
  }
  return { attributes, index: null, groups: geometry.groups || [] };
};

const meshPath = (names) => names.filter(Boolean).join("/");

const instanceMatrices = (node, label) => {
  const matrix = node.instanceMatrix;
  const array = matrix && (matrix.array ?? matrix);
  const count = Number(node.count ?? (array && typeof array.length === "number" ? array.length / 16 : 0));
  if (!array || typeof array.length !== "number" || !Number.isInteger(count) || count < 1
      || array.length < count * 16) {
    fail("UNSUPPORTED_INSTANCING",
      `${label}: instanced mesh has no readable instanceMatrix with count instances`,
      { mesh: label, code: "UNSUPPORTED_INSTANCING" });
  }
  const matrices = [];
  for (let instance = 0; instance < count; instance += 1) {
    const slice = Array.from(array.slice(instance * 16, instance * 16 + 16), Number);
    if (slice.some((value) => !Number.isFinite(value))) {
      fail("UNSUPPORTED_INSTANCING",
        `${label}: instance ${instance} has a non-finite instanceMatrix`,
        { mesh: label, instance });
    }
    matrices.push(elementsToMatrix(slice));
  }
  return matrices;
};

const collectMeshes = (scene) => {
  const meshes = [];
  const walk = (node, parentMatrix, names, isRoot) => {
    if (!node || typeof node !== "object") return;
    const world = node.matrixWorld && node.matrixWorld.elements
      ? elementsToMatrix(node.matrixWorld.elements)
      : matmul(parentMatrix, localMatrix(node));
    const geometry = node.geometry;
    if (geometry && (!geometry.attributes || !geometry.attributes.position)) {
      const label = meshPath([...names, String(node.name || "")]);
      fail("MISSING_POSITION", `${label || "<unnamed>"}: missing geometry.attributes.position`,
        { mesh: label || "<unnamed>" });
    }
    const isMeshNode = Boolean(geometry && geometry.attributes
      && geometry.attributes.position);
    const nextNames = isRoot ? [] : [...names, String(node.name || "")];
    if (isMeshNode) {
      const label = meshPath(nextNames);
      if (!label) fail("UNNAMED_MESH", "mesh has no source-derived name path");
      const instanced = Boolean(node.isInstancedMesh || node.instanceMatrix);
      if (instanced) {
        for (const [instance, matrix] of instanceMatrices(node, label).entries()) {
          meshes.push({
            node,
            label: `${label}#instance_${instance}`,
            hierarchy: [...nextNames.slice(0, -1)],
            world: matmul(world, matrix),
            geometry,
            instanced: true,
            instance,
          });
        }
      } else {
        meshes.push({ node, label, hierarchy: [...nextNames.slice(0, -1)], world,
          geometry, instanced: false, instance: null });
      }
    }
    for (const child of node.children || []) walk(child, world, nextNames, false);
  };
  walk(scene, identity(), [], true);
  return meshes;
};

const materialName = (mesh) => {
  const material = mesh.node.material;
  return material && material.name ? String(material.name) : "";
};

// Number#toString is the shortest decimal that parses back to the identical
// binary64 value.  Never use toFixed(), printf-style counts, or truncation.
const coordinate = (value, label) => {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    fail("NON_FINITE_COORDINATE", `${label}: non-finite coordinate ${value}`,
      { mesh: label });
  }
  return String(number);
};
const vertexLine = (values, label) => values.map((v) => coordinate(v, label)).join(" ");

const serializeMesh = (mesh, offsets) => {
  const position = mesh.geometry.attributes.position;
  if (!position) {
    fail("MISSING_POSITION", `${mesh.label}: missing geometry.attributes.position`,
      { mesh: mesh.label });
  }
  const positionArray = attributeArray(position, mesh.label);
  if (Number(position.itemSize || 3) !== 3 || positionArray.length % 3 !== 0) {
    fail("UNSUPPORTED_POSITION", `${mesh.label}: position is not a 3-component buffer`,
      { mesh: mesh.label });
  }
  let geometry;
  try {
    geometry = expandIndexed(mesh.geometry, mesh.label);
  } catch (error) {
    if (error instanceof ProducerError) throw error;
    fail("UNSUPPORTED_INDEX", `${mesh.label}: cannot expand index buffer: ${error.message}`,
      { mesh: mesh.label });
  }
  const expandedArray = attributeArray(geometry.attributes.position, mesh.label);
  const normalAttribute = geometry.attributes.normal;
  const uvAttribute = geometry.attributes.uv;
  const normalArray = attributeArray(normalAttribute, mesh.label);
  const uvArray = attributeArray(uvAttribute, mesh.label);
  const normals = normalMatrix(mesh.world);

  const lines = [`o ${mesh.label}`];
  const selectedMaterial = materialName(mesh);
  if (selectedMaterial) lines.push(`usemtl ${selectedMaterial}`);

  for (let i = 0; i < expandedArray.length; i += 3) {
    const worldPoint = transformPoint(mesh.world,
      [expandedArray[i], expandedArray[i + 1], expandedArray[i + 2]]);
    lines.push(`v ${vertexLine(framePoint(worldPoint), mesh.label)}`);
  }
  if (normalArray) {
    for (let i = 0; i < normalArray.length; i += 3) {
      const normal = transformNormal(
        [normalArray[i], normalArray[i + 1], normalArray[i + 2]], normals);
      lines.push(`vn ${vertexLine(frameNormal(normal), mesh.label)}`);
    }
  }
  if (uvArray) {
    const itemSize = Number(uvAttribute.itemSize || 2);
    for (let i = 0; i < uvArray.length; i += itemSize) {
      lines.push(`vt ${coordinate(uvArray[i], mesh.label)} ${coordinate(uvArray[i + 1], mesh.label)}`);
    }
  }

  const triangleCount = expandedArray.length / 9;
  const uvCount = uvArray ? uvArray.length / Number(uvAttribute.itemSize || 2) : 0;
  const normalCount = normalArray ? normalArray.length / 3 : 0;
  const face = (triangle) => {
    const local = triangle * 3 + 1;
    const v = [local + offsets.vertex, local + offsets.vertex + 1,
               local + offsets.vertex + 2];
    const vt = [local + offsets.uv, local + offsets.uv + 1, local + offsets.uv + 2];
    const vn = [local + offsets.normal, local + offsets.normal + 1,
                local + offsets.normal + 2];
    if (normalArray && uvArray) {
      return `f ${v[0]}/${vt[0]}/${vn[0]} ${v[1]}/${vt[1]}/${vn[1]} ${v[2]}/${vt[2]}/${vn[2]}`;
    }
    if (normalArray) return `f ${v[0]}//${vn[0]} ${v[1]}//${vn[1]} ${v[2]}//${vn[2]}`;
    if (uvArray) return `f ${v[0]}/${vt[0]} ${v[1]}/${vt[1]} ${v[2]}/${vt[2]}`;
    return `f ${v[0]} ${v[1]} ${v[2]}`;
  };
  for (let t = 0; t < triangleCount; t += 1) lines.push(face(t));

  return {
    text: lines.join("\n"),
    mesh: mesh.label,
    indexed: Boolean(mesh.geometry.index),
    sourceArrayType: positionArray.constructor?.name || "Array",
    sourceVertexCount: positionArray.length / 3,
    sourceIndexCount: mesh.geometry.index
      ? attributeArray(mesh.geometry.index, mesh.label).length : 0,
    outputVertexCount: expandedArray.length / 3,
    outputTriangleCount: triangleCount,
    normalCount,
    uvCount,
  };
};

const parseArgs = (argv) => {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith("--")) fail("BAD_ARGUMENT", `unexpected argument: ${key}`);
    const value = argv[i + 1];
    if (value === undefined || value.startsWith("--")) {
      fail("BAD_ARGUMENT", `missing value for ${key}`);
    }
    args[key.slice(2)] = value;
    i += 1;
  }
  return args;
};

const validateManifest = async (manifestPath, manifest, objPath) => {
  let disk;
  try {
    disk = JSON.parse(await readFile(manifestPath, "utf8"));
  } catch (error) {
    fail("MANIFEST_VALIDATION_FAILED", `cannot read back manifest: ${error.message}`);
  }
  let obj;
  try {
    obj = await readFile(objPath, "utf8");
  } catch (error) {
    fail("MANIFEST_VALIDATION_FAILED", `cannot read back OBJ: ${error.message}`);
  }
  const vertices = obj.split(/\r?\n/).filter((l) => l.startsWith("v ")).length;
  const faces = obj.split(/\r?\n/).filter((l) => l.startsWith("f ")).length;
  const problems = [];
  if (disk.artifact !== manifest.artifact) problems.push("artifact path");
  if (disk.mesh_count !== manifest.mesh_count) problems.push("mesh_count");
  if (disk.vertex_count !== vertices) problems.push(`vertex_count (manifest ${disk.vertex_count}, obj ${vertices})`);
  if (disk.triangle_count !== faces) problems.push(`triangle_count (manifest ${disk.triangle_count}, obj ${faces})`);
  if (disk.frame?.rotation_degrees_xyz?.join(",") !== FRAME.rotation_degrees_xyz.join(",")) {
    problems.push("frame rotation");
  }
  if (!Array.isArray(disk.meshes) || disk.meshes.length !== manifest.mesh_count) {
    problems.push("mesh records");
  }
  if (problems.length) {
    fail("MANIFEST_VALIDATION_FAILED", `artifact manifest is inconsistent: ${problems.join("; ")}`);
  }
};

const run = async () => {
  const args = parseArgs(process.argv.slice(2));
  if (!args.module || !args.out) {
    fail("BAD_ARGUMENT", "usage: export_native_scene.mjs --module <scene.js|scene.mjs> --out <artifact-directory> [--name scene.obj]");
  }
  if (!/\.(?:js|mjs)$/i.test(args.module)) {
    fail("BAD_MODULE_EXTENSION", `${args.module}: --module must be a .js or .mjs scene module`,
      { module: args.module });
  }
  const namespace = await import(pathToFileURL(path.resolve(args.module)).href);
  const createScene = namespace.createScene
    || (namespace.default && namespace.default.createScene);
  if (typeof createScene !== "function") {
    fail("MISSING_CREATE_SCENE", `${args.module}: missing createScene() export`,
      { module: args.module });
  }
  const scene = await createScene();
  if (!scene || typeof scene !== "object") {
    fail("EMPTY_SCENE", `${args.module}: createScene() returned no scene`,
      { module: args.module });
  }
  const meshes = collectMeshes(scene);
  if (!meshes.length) {
    fail("NO_MESHES", `${args.module}: createScene() returned no positioned meshes`,
      { module: args.module });
  }

  const outArg = path.resolve(args.out);
  const outIsObj = /\.obj$/i.test(outArg);
  const objName = outIsObj ? path.basename(outArg) : (args.name || "scene.obj");
  if (!/^[A-Za-z0-9._-]+\.obj$/i.test(objName)) {
    fail("BAD_ARTIFACT_NAME", `artifact name must be a simple .obj file name: ${objName}`);
  }
  if (outIsObj && args.name && args.name !== objName) {
    fail("BAD_ARGUMENT", "--name conflicts with an --out path that already ends in .obj");
  }
  const outDir = outIsObj ? path.dirname(outArg) : outArg;
  const objPath = outIsObj ? outArg : path.join(outDir, objName);
  const manifestPath = path.join(outDir, "manifest.json");

  const records = [];
  const chunks = ["# Native Three.js OBJ, Blender Z-up frame (-90 deg X)", ""];
  const offsets = { vertex: 0, normal: 0, uv: 0 };
  let triangleOffset = 0;
  for (const mesh of meshes) {
    const serialized = serializeMesh(mesh, offsets);
    offsets.vertex += serialized.outputVertexCount;
    offsets.normal += serialized.normalCount;
    offsets.uv += serialized.uvCount;
    chunks.push(serialized.text, "");
    records.push({
      mesh: serialized.mesh,
      hierarchy: mesh.hierarchy,
      instanced: mesh.instanced,
      instance: mesh.instance,
      indexed: serialized.indexed,
      source_array_type: serialized.sourceArrayType,
      source_vertex_count: serialized.sourceVertexCount,
      source_index_count: serialized.sourceIndexCount,
      output_vertex_count: serialized.outputVertexCount,
      output_triangle_count: serialized.outputTriangleCount,
      expansion: serialized.indexed ? "toNonIndexed" : "non-indexed",
      vertex_offset: offsets.vertex - serialized.outputVertexCount,
      triangle_offset: triangleOffset,
    });
    triangleOffset += serialized.outputTriangleCount;
  }
  const vertexCount = offsets.vertex;
  const triangleCount = records.reduce((sum, r) => sum + r.output_triangle_count, 0);

  const manifest = {
    schema_version: 1,
    status: "produced",
    source_module: args.module,
    artifact: objName,
    manifest: "manifest.json",
    frame: FRAME,
    mesh_count: records.length,
    vertex_count: vertexCount,
    triangle_count: triangleCount,
    meshes: records,
  };

  try {
    await mkdir(outDir, { recursive: true });
    await writeFile(objPath, `${chunks.join("\n")}\n`, "utf8");
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  } catch (error) {
    fail("WRITE_FAILED", `${outDir}: cannot write artifact set: ${error.message}`,
      { artifact_root: outDir });
  }
  await validateManifest(manifestPath, manifest, objPath);
  process.stdout.write(`${JSON.stringify({
    status: "produced",
    artifact_root: outDir,
    artifact: objPath,
    manifest: manifestPath,
    mesh_count: records.length,
    vertex_count: vertexCount,
    triangle_count: triangleCount,
    frame: FRAME.name,
  }, null, 2)}\n`);
};

run().catch((error) => {
  const payload = {
    status: "error",
    code: error.code || "PRODUCER_FAILED",
    message: error.message,
    ...(error.details || {}),
  };
  process.stderr.write(`${JSON.stringify(payload)}\n`);
  process.exitCode = 1;
});
