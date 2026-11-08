#!/usr/bin/env node
/**
 * One-command native Three.js part/link producer.
 *
 * Usage:
 *   node scripts/export_scene_meshes.mjs --module <scene.mjs> --out <artifact-root> \
 *     [--spec <spec.json> --report <report.json>]
 *
 * The only scene input is the .js/.mjs module exporting createScene().  The
 * producer executes that factory and derives the part set from the returned
 * Group hierarchy: a part is a Group with primitive leaf children, and each
 * primitive leaf becomes one link OBJ inside that part's directory.  Object
 * names are used verbatim.  No normalized scene JSON is read.
 *
 * With --spec the same command then runs check_mesh_conformance.py as a
 * separate process over the actual output tree and returns its exit status.
 * Export-only mode without --spec is for inspection, not acceptance evidence.
 */

import { spawnSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import process from "node:process";

const CHECKER = fileURLToPath(new URL("./check_mesh_conformance.py", import.meta.url));

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

const eulerXYZ = (r) => {
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
  const rotation = node.quaternion
    ? quaternionMatrix(node.quaternion)
    : eulerXYZ(vec3(node.rotation));
  return matmul(translation(vec3(node.position)),
                matmul(rotation, scaling(vec3(node.scale, [1, 1, 1]))));
};

const transform = (m, p) => [
  m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + m[0][3],
  m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + m[1][3],
  m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + m[2][3],
];

const primitiveName = (node) => {
  const raw = node.primitive
    || (node.geometry && (node.geometry.type
      || (node.geometry.constructor && node.geometry.constructor.name)));
  return raw ? String(raw).replace(/Geometry$/i, "").toLowerCase() : "";
};

const isPrimitive = (node) => Boolean(node && primitiveName(node));
const isGroup = (node) => Boolean(node && !isPrimitive(node)
  && (node.isGroup || node.type === "Group" || Array.isArray(node.children)));

const snake = (key) => String(key)
  .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
  .replace(/([A-Z])([A-Z][a-z])/g, "$1_$2")
  .toLowerCase();

const primitiveArgs = (node) => {
  const raw = node.args || (node.geometry && node.geometry.parameters) || {};
  if (Array.isArray(raw)) {
    const keys = {
      box: ["width", "height", "depth"],
      plane: ["width", "height"],
      sphere: ["radius", "width_segments", "height_segments"],
      cylinder: ["radius_top", "radius_bottom", "height", "radial_segments"],
      torus: ["radius", "tube", "radial_segments", "tubular_segments"],
    }[primitiveName(node)] || [];
    return Object.fromEntries(keys.map((key, i) => [key, Number(raw[i])]));
  }
  return Object.fromEntries(Object.entries(raw).map(([key, value]) =>
    [snake(key), Number(value)]));
};

const arg = (args, names, fallback) => {
  for (const name of names) {
    if (args[name] !== undefined && Number.isFinite(args[name])) return args[name];
  }
  return fallback;
};

const primitiveGeometry = (node) => {
  const name = primitiveName(node);
  const args = primitiveArgs(node);
  if (name === "box") {
    const [w, h, d] = [arg(args, ["width"], 1), arg(args, ["height"], 1),
                       arg(args, ["depth"], 1)];
    const [hw, hh, hd] = [w / 2, h / 2, d / 2];
    const verts = [
      [-hw, -hh, -hd], [hw, -hh, -hd], [hw, hh, -hd], [-hw, hh, -hd],
      [-hw, -hh, hd], [hw, -hh, hd], [hw, hh, hd], [-hw, hh, hd],
    ];
    const faces = [
      [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6], [0, 4, 5], [0, 5, 1],
      [3, 2, 6], [3, 6, 7], [0, 3, 7], [0, 7, 4], [1, 5, 6], [1, 6, 2],
    ];
    return { verts, faces };
  }
  if (name === "plane") {
    const [w, h] = [arg(args, ["width"], 1), arg(args, ["height"], 1)];
    const g = Math.max(2, Math.trunc(arg(args, ["segments"], 8)));
    const verts = [];
    for (let i = 0; i < g; i += 1) {
      for (let j = 0; j < g; j += 1) {
        verts.push([(i / (g - 1) - 0.5) * w, 0, (j / (g - 1) - 0.5) * h]);
      }
    }
    const faces = [];
    for (let i = 0; i < g - 1; i += 1) {
      for (let j = 0; j < g - 1; j += 1) {
        const a = i * g + j;
        const [b, c, d] = [a + 1, a + g, a + g + 1];
        faces.push([a, c, d], [a, d, b]);
      }
    }
    return { verts, faces };
  }
  if (name === "sphere") {
    const r = arg(args, ["radius"], 1);
    const nu = Math.max(8, Math.trunc(arg(args, ["width_segments"], 24)));
    const nv = Math.max(4, Math.trunc(arg(args, ["height_segments"], 16)));
    const verts = [];
    for (let i = 0; i <= nv; i += 1) {
      const phi = Math.PI * i / nv;
      for (let j = 0; j < nu; j += 1) {
        const theta = 2 * Math.PI * j / nu;
        verts.push([r * Math.sin(phi) * Math.cos(theta),
                    r * Math.cos(phi),
                    r * Math.sin(phi) * Math.sin(theta)]);
      }
    }
    const faces = [];
    for (let i = 0; i < nv; i += 1) {
      for (let j = 0; j < nu; j += 1) {
        const a = i * nu + j;
        const b = i * nu + (j + 1) % nu;
        const c = (i + 1) * nu + j;
        const d = (i + 1) * nu + (j + 1) % nu;
        faces.push([a, c, d], [a, d, b]);
      }
    }
    return { verts, faces };
  }
  if (name === "cylinder") {
    const rt = arg(args, ["radius_top"], arg(args, ["radius"], 1));
    const rb = arg(args, ["radius_bottom"], arg(args, ["radius"], rt));
    const h = arg(args, ["height"], 1);
    const n = Math.max(8, Math.trunc(arg(args, ["radial_segments"], 32)));
    const verts = [];
    for (const [y, r] of [[-h / 2, rb], [h / 2, rt]]) {
      for (let j = 0; j < n; j += 1) {
        const a = 2 * Math.PI * j / n;
        verts.push([r * Math.cos(a), y, r * Math.sin(a)]);
      }
    }
    const bottomCenter = verts.length;
    verts.push([0, -h / 2, 0]);
    const topCenter = verts.length;
    verts.push([0, h / 2, 0]);
    const faces = [];
    for (let j = 0; j < n; j += 1) {
      const k = (j + 1) % n;
      faces.push([j, k, n + j], [k, n + k, n + j],
                 [bottomCenter, k, j], [topCenter, n + j, n + k]);
    }
    return { verts, faces };
  }
  if (name === "torus") {
    const r = arg(args, ["radius"], 1);
    const tube = arg(args, ["tube"], 0.25);
    const nu = Math.max(8, Math.trunc(arg(args, ["radial_segments"], 24)));
    const nv = Math.max(8, Math.trunc(arg(args, ["tubular_segments"], 48)));
    const verts = [];
    for (let i = 0; i < nu; i += 1) {
      const u = 2 * Math.PI * i / nu;
      for (let j = 0; j < nv; j += 1) {
        const v = 2 * Math.PI * j / nv;
        verts.push([(r + tube * Math.cos(v)) * Math.cos(u),
                    tube * Math.sin(v),
                    (r + tube * Math.cos(v)) * Math.sin(u)]);
      }
    }
    const faces = [];
    for (let i = 0; i < nu; i += 1) {
      for (let j = 0; j < nv; j += 1) {
        const a = i * nv + j;
        const b = i * nv + (j + 1) % nv;
        const c = ((i + 1) % nu) * nv + j;
        const d = ((i + 1) % nu) * nv + (j + 1) % nv;
        faces.push([a, c, d], [a, d, b]);
      }
    }
    return { verts, faces };
  }
  throw new Error(`unsupported source primitive ${name || "<missing>"}`);
};

const safeName = (name, kind) => {
  const value = String(name || "");
  if (!value || value === "." || value === ".." || value.includes("/")
      || value.includes("\\") || value.includes("\0")) {
    throw new Error(`${kind} has no safe source object name: ${JSON.stringify(name)}`);
  }
  return value;
};

const deriveParts = (scene) => {
  const root = isPrimitive(scene)
    ? identity()
    : localMatrix(scene);
  const parts = [];
  const ungrouped = [];

  const visit = (node, parentMatrix, containingPart) => {
    const world = matmul(parentMatrix, localMatrix(node));
    if (isPrimitive(node)) {
      if ((node.children || []).length) {
        throw new Error(`primitive ${JSON.stringify(node.name)} is not a leaf`);
      }
      if (!containingPart) {
        ungrouped.push(String(node.name || "<unnamed>"));
      } else {
        containingPart.primitives.push({ node, world });
      }
      return;
    }
    if (!isGroup(node)) return;

    const directPrimitives = (node.children || []).filter(isPrimitive);
    let ownPart = containingPart;
    if (directPrimitives.length) {
      ownPart = { name: safeName(node.name, "part Group"), primitives: [] };
      parts.push(ownPart);
    }
    for (const child of node.children || []) {
      visit(child, world, ownPart);
    }
  };

  for (const child of scene.children || []) {
    visit(child, root, null);
  }
  if (ungrouped.length) {
    throw new Error(`primitive leaves outside a part Group: ${ungrouped.join(", ")}`);
  }
  if (!parts.length) {
    throw new Error("createScene() hierarchy has no Group part with primitive leaves");
  }
  const partNames = new Set();
  for (const part of parts) {
    if (partNames.has(part.name)) {
      throw new Error(`duplicate part Group name ${JSON.stringify(part.name)}`);
    }
    partNames.add(part.name);
    const leafNames = new Set();
    for (const leaf of part.primitives) {
      const name = safeName(leaf.node.name, "primitive leaf");
      if (leafNames.has(name)) {
        throw new Error(`duplicate primitive leaf ${JSON.stringify(name)} in part ${JSON.stringify(part.name)}`);
      }
      leafNames.add(name);
    }
  }
  return parts;
};

const writeObj = async (file, geometry) => {
  const lines = ["# deterministic source-native part export"];
  for (const p of geometry.verts) {
    // Full round-trip precision; fixed-decimal formatting is prohibited.
    lines.push(`v ${String(Number(p[0]))} ${String(Number(p[1]))} ${String(Number(p[2]))}`);
  }
  for (const [a, b, c] of geometry.faces) {
    lines.push(`f ${a + 1} ${b + 1} ${c + 1}`);
  }
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, `${lines.join("\n")}\n`, "utf8");
};

const parseArgs = (argv) => {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith("--")) throw new Error(`unexpected argument ${key}`);
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
    throw new Error("usage: export_scene_meshes.mjs --module <scene.js|scene.mjs> --out <artifact-root>");
  }
  if (!/\.(?:js|mjs)$/i.test(args.module)) {
    throw new Error("--module must be a .js or .mjs native module");
  }

  const moduleUrl = pathToFileURL(path.resolve(args.module)).href;
  const namespace = await import(moduleUrl);
  const createScene = typeof namespace.createScene === "function"
    ? namespace.createScene
    : namespace.default && typeof namespace.default.createScene === "function"
      ? namespace.default.createScene : null;
  if (!createScene) {
    throw new Error("native module does not export createScene()");
  }

  const scene = await createScene();
  if (!scene || typeof scene !== "object") {
    throw new Error("createScene() did not return a scene graph");
  }

  const outRoot = path.resolve(args.out);
  const parts = deriveParts(scene);
  const manifest = { status: "produced", source_module: path.resolve(args.module),
                     parts: {}, links: [] };

  for (const part of parts) {
    manifest.parts[part.name] = [];
    for (const leaf of part.primitives) {
      const linkName = safeName(leaf.node.name, "primitive leaf");
      const rel = path.posix.join(part.name, `${linkName}.obj`);
      const geometry = primitiveGeometry(leaf.node);
      const verts = geometry.verts.map((p) => transform(leaf.world, p));
      await writeObj(path.join(outRoot, ...rel.split("/")),
                     { verts, faces: geometry.faces });
      manifest.parts[part.name].push(`${linkName}.obj`);
      manifest.links.push(rel);
    }
  }

  if (args.manifest) {
    const manifestPath = path.resolve(args.manifest);
    await mkdir(path.dirname(manifestPath), { recursive: true });
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  }
  process.stdout.write(`${JSON.stringify(manifest, null, 2)}\n`);

  if (!args.spec) {
    process.stderr.write("export-only run: pass --spec to run the independent "
      + "source-derived checker over this tree before acceptance\n");
    return 0;
  }
  const python = process.env.PYTHON || "python3";
  const checkerArgs = [CHECKER, outRoot, "--spec", path.resolve(args.spec)];
  if (args.report) checkerArgs.push("--report", path.resolve(args.report));
  const verdict = spawnSync(python, checkerArgs, { stdio: "inherit" });
  if (verdict.error) {
    throw new Error(`cannot run independent checker: ${verdict.error.message}`);
  }
  return verdict.status === null ? 2 : verdict.status;
};

main().then((code) => {
  process.exitCode = code;
}).catch((error) => {
  process.stderr.write(`export failed: ${error && error.message ? error.message : error}\n`);
  process.exitCode = 2;
});
