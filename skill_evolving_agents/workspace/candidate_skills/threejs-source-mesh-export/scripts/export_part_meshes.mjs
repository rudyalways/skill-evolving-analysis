#!/usr/bin/env node
/**
 * Default producer-first part/link export.
 *
 * Usage:
 *   node scripts/export_part_meshes.mjs --module <scene.js|scene.mjs> \
 *     --out <artifact-root> [--report <producer-report.json>] [--no-verify]
 *
 * The only scene input is the native .js/.mjs module exporting createScene().
 * The command executes that entrypoint, calls it, and writes:
 *
 *   <artifact-root>/part_meshes/<Group name>/<Mesh name>.obj
 *   <artifact-root>/links/<Group name>.obj
 *
 * A part is a Group with direct primitive Mesh children.  Each direct Mesh is
 * a part mesh.  The links OBJ for a part contains the combined triangles of
 * that part's meshes.  Names are the source object names verbatim.
 *
 * Positions come from the live geometry.attributes.position buffer and faces
 * from geometry.index.  Indexed geometry is expanded to non-indexed triangles
 * (geometry.toNonIndexed() when available, otherwise an in-memory equivalent),
 * so every source index triple becomes one OBJ triangle.  Every coordinate is
 * written with the runtime's shortest round-trip decimal form via String(value).
 *
 * After writing, the command runs scripts/check_part_meshes.mjs as a separate
 * process and returns its exit status.  Pass --no-verify only for inspection
 * or for a deliberately near-miss artifact that another clean source checks.
 */

import { spawnSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import process from "node:process";

const CHECKER = fileURLToPath(new URL("./check_part_meshes.mjs", import.meta.url));

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

const eulerMatrix = (r) => {
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
    : eulerMatrix(vec3(node.rotation));
  return matmul(translation(vec3(node.position)),
                matmul(rotation, scaling(vec3(node.scale, [1, 1, 1]))));
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
 * Return expanded vertex records for one mesh.
 *
 * geometry.toNonIndexed() is used when the live geometry provides it.  Plain
 * BufferGeometry-compatible fixtures use the equivalent in-memory index
 * expansion.  Non-indexed geometry is traversed sequentially in triples.
 * Normals and UVs are carried from the same live attributes when present.
 */
const expandedVertices = (geometry) => {
  let source = geometry;
  if (geometry.index && typeof geometry.toNonIndexed === "function") {
    source = geometry.toNonIndexed();
  }
  const position = source.attributes && source.attributes.position;
  if (!position) throw new Error("mesh has no geometry.attributes.position");
  const values = arrayOf(position);
  const normals = source.attributes.normal ? arrayOf(source.attributes.normal) : null;
  const uvs = source.attributes.uv ? arrayOf(source.attributes.uv) : null;
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
  const vertices = [];
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
    vertices.push({
      p,
      n: normals ? [Number(normals[offset]), Number(normals[offset + 1]),
                    Number(normals[offset + 2])] : null,
      u: uvs ? [Number(uvs[index * 2]), Number(uvs[index * 2 + 1])] : null,
    });
  }
  return vertices;
};

const normalMatrix = (m) => {
  const a = [[m[0][0], m[0][1], m[0][2]], [m[1][0], m[1][1], m[1][2]],
             [m[2][0], m[2][1], m[2][2]]];
  const det = a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
    - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
    + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]);
  if (!Number.isFinite(det) || Math.abs(det) < 1e-15) return null;
  const inv = [
    [(a[1][1] * a[2][2] - a[1][2] * a[2][1]) / det,
     (a[0][2] * a[2][1] - a[0][1] * a[2][2]) / det,
     (a[0][1] * a[1][2] - a[0][2] * a[1][1]) / det],
    [(a[1][2] * a[2][0] - a[1][0] * a[2][2]) / det,
     (a[0][0] * a[2][2] - a[0][2] * a[2][0]) / det,
     (a[0][2] * a[1][0] - a[0][0] * a[1][2]) / det],
    [(a[1][0] * a[2][1] - a[1][1] * a[2][0]) / det,
     (a[0][1] * a[2][0] - a[0][0] * a[2][1]) / det,
     (a[0][0] * a[1][1] - a[0][1] * a[1][0]) / det],
  ];
  return inv[0].map((_, row) => inv.map((column) => column[row]));
};

const transformedVertex = (m, vertex, normals) => {
  const p = transform(m, vertex.p);
  let n = vertex.n;
  if (n) {
    const nm = normals || [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
    n = [
      nm[0][0] * n[0] + nm[0][1] * n[1] + nm[0][2] * n[2],
      nm[1][0] * n[0] + nm[1][1] * n[1] + nm[1][2] * n[2],
      nm[2][0] * n[0] + nm[2][1] * n[1] + nm[2][2] * n[2],
    ];
    const length = Math.hypot(n[0], n[1], n[2]);
    if (length > 0) n = n.map((value) => value / length);
  }
  return { p, n, u: vertex.u };
};

const deriveParts = (scene) => {
  const parts = [];
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
      } else {
        containingPart.meshes.push({ name: safeName(node.name, "primitive Mesh"), node, world });
      }
      return;
    }
    if (!isGroup(node)) return;

    const directMeshes = (node.children || []).filter(isMesh);
    let ownPart = containingPart;
    if (directMeshes.length) {
      ownPart = { name: safeName(node.name, "part Group"), meshes: [] };
      parts.push(ownPart);
    }
    for (const child of node.children || []) {
      visit(child, world, ownPart);
    }
  };

  visit(scene, identity(), null);

  if (ungrouped.length) {
    throw new Error(`primitive leaves outside a part Group: ${ungrouped.join(", ")}`);
  }
  if (!parts.length) {
    throw new Error("createScene() hierarchy has no Group with direct primitive Mesh children");
  }

  const partNames = new Set();
  for (const part of parts) {
    if (partNames.has(part.name)) {
      throw new Error(`duplicate part Group name ${JSON.stringify(part.name)}; `
        + "naming is ambiguous and must be disambiguated at the source");
    }
    partNames.add(part.name);
    const meshNames = new Set();
    for (const mesh of part.meshes) {
      if (meshNames.has(mesh.name)) {
        throw new Error(`duplicate primitive Mesh name ${JSON.stringify(mesh.name)} `
          + `in part ${JSON.stringify(part.name)}; naming is ambiguous`);
      }
      meshNames.add(mesh.name);
    }
  }
  return parts;
};

const objFromTriangles = (objectName, vertices) => {
  const lines = ["# source-native position/index export", `o ${objectName}`];
  for (const vertex of vertices) {
    lines.push(`v ${String(vertex.p[0])} ${String(vertex.p[1])} ${String(vertex.p[2])}`);
  }
  const hasNormals = vertices.length > 0 && vertices.every((vertex) => vertex.n);
  const hasUvs = vertices.length > 0 && vertices.every((vertex) => vertex.u);
  if (hasNormals) {
    for (const vertex of vertices) {
      lines.push(`vn ${String(vertex.n[0])} ${String(vertex.n[1])} ${String(vertex.n[2])}`);
    }
  }
  if (hasUvs) {
    for (const vertex of vertices) {
      lines.push(`vt ${String(vertex.u[0])} ${String(vertex.u[1])}`);
    }
  }
  for (let i = 0; i < vertices.length; i += 3) {
    const a = i + 1;
    const b = i + 2;
    const c = i + 3;
    if (hasNormals && hasUvs) {
      lines.push(`f ${a}/${a}/${a} ${b}/${b}/${b} ${c}/${c}/${c}`);
    } else if (hasNormals) {
      lines.push(`f ${a}//${a} ${b}//${b} ${c}//${c}`);
    } else if (hasUvs) {
      lines.push(`f ${a}/${a} ${b}/${b} ${c}/${c}`);
    } else {
      lines.push(`f ${a} ${b} ${c}`);
    }
  }
  return `${lines.join("\n")}\n`;
};

const writeText = async (file, text) => {
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, text, "utf8");
};

const parseArgs = (argv) => {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith("--")) throw new Error(`unexpected argument ${key}`);
    if (key === "--no-verify") {
      args.verify = false;
      continue;
    }
    const value = argv[i + 1];
    if (value === undefined || value.startsWith("--")) {
      throw new Error(`missing value for ${key}`);
    }
    args[key.slice(2)] = value;
    i += 1;
  }
  return args;
};

const main = async () => {
  const args = parseArgs(process.argv.slice(2));
  if (!args.module || !args.out) {
    throw new Error("usage: export_part_meshes.mjs --module <scene.js|scene.mjs> --out <artifact-root>");
  }
  if (!/\.(?:js|mjs)$/i.test(args.module)) {
    throw new Error("--module must be a .js or .mjs native module");
  }

  const modulePath = path.resolve(args.module);
  const namespace = await import(pathToFileURL(modulePath).href);
  const createScene = typeof namespace.createScene === "function"
    ? namespace.createScene
    : namespace.default && typeof namespace.default.createScene === "function"
      ? namespace.default.createScene : null;
  if (!createScene) {
    throw new Error(`${args.module}: native module does not export createScene()`);
  }

  const scene = await createScene();
  if (!scene || typeof scene !== "object") {
    throw new Error(`${args.module}: createScene() returned no scene graph`);
  }

  const outRoot = path.resolve(args.out);
  const parts = deriveParts(scene);
  const manifest = {
    status: "produced",
    source_module: modulePath,
    layout: "part_meshes/<part>/<mesh>.obj + links/<part>.obj",
    parts: {},
    meshes: [],
    links: [],
  };

  for (const part of parts) {
    const partVertices = [];
    manifest.parts[part.name] = [];
    for (const mesh of part.meshes) {
      const meshName = mesh.name;
      const localVertices = expandedVertices(mesh.node.geometry);
      const normals = normalMatrix(mesh.world);
      const vertices = localVertices.map((vertex) =>
        transformedVertex(mesh.world, vertex, normals));
      const rel = path.posix.join("part_meshes", part.name, `${meshName}.obj`);
      await writeText(path.join(outRoot, ...rel.split("/")),
                      objFromTriangles(meshName, vertices));
      manifest.parts[part.name].push(`${meshName}.obj`);
      manifest.meshes.push(rel);
      partVertices.push(...vertices);
    }
    const linkRel = path.posix.join("links", `${part.name}.obj`);
    await writeText(path.join(outRoot, ...linkRel.split("/")),
                    objFromTriangles(part.name, partVertices));
    manifest.links.push(linkRel);
  }

  if (args.report) {
    const reportPath = path.resolve(args.report);
    await mkdir(path.dirname(reportPath), { recursive: true });
    await writeFile(reportPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  }
  process.stdout.write(`${JSON.stringify(manifest, null, 2)}\n`);

  if (args.verify === false) {
    process.stderr.write("verification skipped: run scripts/check_part_meshes.mjs "
      + "against the clean source before acceptance\n");
    return 0;
  }

  const verdict = spawnSync(process.execPath,
    [CHECKER, "--module", modulePath, "--root", outRoot], { stdio: "inherit" });
  if (verdict.error) {
    throw new Error(`cannot run independent name-set and precision checker: ${verdict.error.message}`);
  }
  return verdict.status === null ? 2 : verdict.status;
};

main().then((code) => {
  process.exitCode = code;
}).catch((error) => {
  process.stderr.write(`export failed: ${error && error.message ? error.message : error}\n`);
  process.exitCode = 2;
});
