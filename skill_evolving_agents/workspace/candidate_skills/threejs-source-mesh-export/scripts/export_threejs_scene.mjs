#!/usr/bin/env node
/**
 * Source-native Three.js OBJ producer.
 *
 * Usage:
 *   node scripts/export_threejs_scene.mjs --module <scene.js|scene.mjs> \
 *     --out <artifact.obj> [--report <report.json>]
 *
 * The only scene input is an executable .js/.mjs module exporting
 * createScene().  Every mesh returned by that factory is serialized from its
 * live geometry.attributes.position (and geometry.index when present); indexed
 * geometry is expanded with toNonIndexed() before OBJ face traversal.  Primitive
 * descriptors are never consulted and no normalized input is accepted.
 */

import { mkdir, writeFile } from "node:fs/promises";
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

const elementsToMatrix = (e) => [
  [e[0], e[4], e[8], e[12]],
  [e[1], e[5], e[9], e[13]],
  [e[2], e[6], e[10], e[14]],
  [e[3], e[7], e[11], e[15]],
];

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
  // inverse transpose of the upper-left 3x3
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

const attributeArray = (attribute) => {
  if (!attribute) return null;
  const array = attribute.array ?? attribute;
  if (!array || typeof array.length !== "number") {
    throw new Error("unsupported attribute: expected an array-like buffer");
  }
  return array;
};

const expandIndexed = (geometry) => {
  const position = geometry.attributes.position;
  const index = geometry.index;
  if (!index) return geometry;
  if (typeof geometry.toNonIndexed === "function") return geometry.toNonIndexed();

  const indexArray = attributeArray(index);
  const attributes = {};
  for (const [name, attribute] of Object.entries(geometry.attributes)) {
    const source = attributeArray(attribute);
    const itemSize = Number(attribute.itemSize || (name === "position" ? 3 : 1));
    const expanded = new Float32Array(indexArray.length * itemSize);
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

function collectMeshes(scene) {
  const meshes = [];
  const root = scene;
  const walk = (node, parentMatrix, names, isRoot) => {
    if (!node || typeof node !== "object") return;
    const world = node.matrixWorld && node.matrixWorld.elements
      ? elementsToMatrix(node.matrixWorld.elements)
      : matmul(parentMatrix, localMatrix(node));
    const geometry = node.geometry;
    const isMeshNode = Boolean(geometry && geometry.attributes
      && geometry.attributes.position);
    const nextNames = isRoot
      ? (isMeshNode ? [String(node.name || "scene")] : [])
      : [...names, String(node.name || "")];
    if (isMeshNode) {
      const label = meshPath(nextNames);
      if (!label) throw new Error("mesh without a name path");
      meshes.push({ node, label, world, geometry });
    }
    for (const child of node.children || []) {
      walk(child, world, nextNames, false);
    }
  };
  walk(root, identity(), [], true);
  return meshes;
}

const materialName = (mesh, group) => {
  const material = mesh.node.material;
  if (Array.isArray(material)) {
    const selected = group && material[group.materialIndex] !== undefined
      ? material[group.materialIndex]
      : material[0];
    return selected && selected.name ? String(selected.name) : "";
  }
  return material && material.name ? String(material.name) : "";
};

// Full round-trip precision: Number#toString emits the shortest decimal that
// parses back to the identical binary64 value.  Never use a fixed-decimal
// formatter or a printf-style fixed count; either destroys the native value.
const coordinate = (value) => {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    throw new Error(`non-finite coordinate: ${value}`);
  }
  return String(number);
};
const vertexLine = (values) => values.map(coordinate).join(" ");

const serializeMesh = (mesh, offsets) => {
  const position = mesh.geometry.attributes.position;
  if (!position) {
    throw new Error(`${mesh.label}: missing geometry.attributes.position`);
  }
  const positionArray = attributeArray(position);
  if (Number(position.itemSize || 3) !== 3 || positionArray.length % 3 !== 0) {
    throw new Error(`${mesh.label}: unsupported position attribute`);
  }

  const geometry = expandIndexed(mesh.geometry);
  const expanded = geometry.attributes.position;
  const expandedArray = attributeArray(expanded);
  const normalAttribute = geometry.attributes.normal;
  const uvAttribute = geometry.attributes.uv;
  const normalArray = attributeArray(normalAttribute);
  const uvArray = attributeArray(uvAttribute);
  const normals = normalMatrix(mesh.world);

  const lines = [`o ${mesh.label}`];
  const vertexOffset = offsets.vertex;
  const normalOffset = offsets.normal;
  const uvOffset = offsets.uv;
  const selectedMaterial = materialName(mesh, null);
  if (selectedMaterial) lines.push(`usemtl ${selectedMaterial}`);

  for (let i = 0; i < expandedArray.length; i += 3) {
    const point = transformPoint(mesh.world,
      [expandedArray[i], expandedArray[i + 1], expandedArray[i + 2]]);
    lines.push(`v ${vertexLine(point)}`);
  }
  if (normalArray) {
    for (let i = 0; i < normalArray.length; i += 3) {
      const normal = transformNormal(
        [normalArray[i], normalArray[i + 1], normalArray[i + 2]], normals);
      lines.push(`vn ${vertexLine(normal)}`);
    }
  }
  if (uvArray) {
    const itemSize = Number(uvAttribute.itemSize || 2);
    for (let i = 0; i < uvArray.length; i += itemSize) {
      lines.push(`vt ${coordinate(uvArray[i])} ${coordinate(uvArray[i + 1])}`);
    }
  }

  const triangleCount = expandedArray.length / 9;
  const groups = Array.isArray(geometry.groups) ? geometry.groups : [];
  const face = (triangle) => {
    const local = triangle * 3 + 1;
    const v = [local + vertexOffset, local + vertexOffset + 1,
               local + vertexOffset + 2];
    const vt = [local + uvOffset, local + uvOffset + 1, local + uvOffset + 2];
    const vn = [local + normalOffset, local + normalOffset + 1,
                local + normalOffset + 2];
    if (normalArray && uvArray) {
      return `f ${v[0]}/${vt[0]}/${vn[0]} ${v[1]}/${vt[1]}/${vn[1]} ${v[2]}/${vt[2]}/${vn[2]}`;
    }
    if (normalArray) return `f ${v[0]}//${vn[0]} ${v[1]}//${vn[1]} ${v[2]}//${vn[2]}`;
    if (uvArray) return `f ${v[0]}/${vt[0]} ${v[1]}/${vt[1]} ${v[2]}/${vt[2]}`;
    return `f ${v[0]} ${v[1]} ${v[2]}`;
  };

  if (groups.length) {
    for (const group of groups) {
      const name = materialName(mesh, group);
      if (name) lines.push(`usemtl ${name}`);
      const first = Math.floor(Number(group.start || 0) / 3);
      const count = Math.floor(Number(group.count || 0) / 3);
      for (let t = first; t < first + count && t < triangleCount; t += 1) {
        lines.push(face(t));
      }
    }
  } else {
    for (let t = 0; t < triangleCount; t += 1) lines.push(face(t));
  }

  const vertexCount = expandedArray.length / 3;
  const normalCount = normalArray ? normalArray.length / 3 : 0;
  const uvCount = uvArray ? uvArray.length / Number(uvAttribute.itemSize || 2) : 0;
  return {
    text: lines.join("\n"),
    indexed: Boolean(mesh.geometry.index),
    sourceVertexCount: positionArray.length / 3,
    sourceIndexCount: mesh.geometry.index ? attributeArray(mesh.geometry.index).length : 0,
    outputTriangleCount: triangleCount,
    vertexCount,
    normalCount,
    uvCount,
  };
}

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
  if (!args.module || !args.out) {
    throw new Error("usage: export_threejs_scene.mjs --module <scene.js|scene.mjs> --out <artifact.obj> [--report <report.json>]");
  }
  if (!/\.(?:js|mjs)$/i.test(args.module)) {
    throw new Error(`${args.module}: --module must be a .js or .mjs scene module`);
  }

  const modulePath = path.resolve(args.module);
  const namespace = await import(pathToFileURL(modulePath).href);
  const createScene = namespace.createScene
    || (namespace.default && namespace.default.createScene);
  if (typeof createScene !== "function") {
    throw new Error(`${args.module}: missing createScene() export`);
  }

  const scene = await createScene();
  if (!scene || typeof scene !== "object") {
    throw new Error(`${args.module}: createScene() returned no scene`);
  }
  const meshes = collectMeshes(scene);
  if (!meshes.length) {
    throw new Error(`${args.module}: createScene() returned no meshes`);
  }

  const records = [];
  const chunks = ["# Three.js OBJExporter-compatible native export", ""];
  const offsets = { vertex: 0, normal: 0, uv: 0 };
  for (const mesh of meshes) {
    const serialized = serializeMesh(mesh, offsets);
    offsets.vertex += serialized.vertexCount;
    offsets.normal += serialized.normalCount;
    offsets.uv += serialized.uvCount;
    chunks.push(serialized.text, "");
    records.push({
      mesh: mesh.label,
      indexed: serialized.indexed,
      source_vertex_count: serialized.sourceVertexCount,
      source_index_count: serialized.sourceIndexCount,
      output_triangle_count: serialized.outputTriangleCount,
    });
  }

  const artifactPath = path.resolve(args.out);
  await mkdir(path.dirname(artifactPath), { recursive: true });
  await writeFile(artifactPath, `${chunks.join("\n")}\n`, "utf8");

  if (args.report) {
    const reportPath = path.resolve(args.report);
    await mkdir(path.dirname(reportPath), { recursive: true });
    await writeFile(reportPath, `${JSON.stringify({
      source_module: args.module,
      artifact: args.out,
      mesh_count: records.length,
      meshes: records,
    }, null, 2)}\n`, "utf8");
  }

  process.stdout.write(`exported ${records.length} mesh(es) to ${args.out}\n`);
};

run().catch((error) => {
  process.stderr.write(`export failed: ${error.message}\n`);
  process.exit(1);
});
