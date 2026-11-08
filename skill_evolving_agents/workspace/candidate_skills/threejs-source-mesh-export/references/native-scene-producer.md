# Native scene producer contract

Read this when a Three.js scene arrives as an executable `.js`/`.mjs` module,
when deciding whether a one-command producer is acceptable, or when
distinguishing producer-derived agreement from independent artifact evidence.

Contents (search these headings): input ABI; one-command invocation; native
buffer export; indexed expansion and ordering; Blender Z-up transfer;
precision; artifact manifest; rejection behavior; independent verification;
unverifiable cases.

## Input ABI

The only scene input is an ES module with a `.js` or `.mjs` extension that
exports `createScene` as a named export or `default.createScene`. The producer
imports the module, calls `createScene()` with no arguments, and walks the
returned object graph. Real `THREE.Object3D`/`THREE.Mesh` instances and plain
objects exposing the same `position`, `quaternion` or `rotation`, `scale`,
`children`, `geometry`, and `name` fields are both acceptable.

A JSON, CSV, manifest, or normalized scene file is never input. Do not require
the agent to hand-author or normalize a scene before production, and do not
static-scrape the module instead of executing it.

## One-command invocation

Run the bundled producer first, before writing custom export code and before
invoking any checker:

```bash
node scripts/export_native_scene.mjs --module <scene.js|scene.mjs> \
  --out <artifact-directory|artifact.obj> [--name scene.obj]
```

The command writes the requested OBJ and `manifest.json` under the artifact
directory, then validates the manifest counts and frame against the written
files. If `--out` already ends in `.obj`, it is treated as the OBJ path and
`manifest.json` is written beside it. It is the default first action once the source module path and artifact
arguments are confirmed.

## Native buffer export

For each positioned mesh read `geometry.attributes.position` and
`geometry.index` directly. Apply the composed world transform from the scene
root through every ancestor. For an `InstancedMesh`, compose each instance's
`instanceMatrix` with that world transform and export one object record per
instance. Read optional `normal` and `uv` attributes from the same geometry.
Never rebuild the surface from `geometry.parameters`, `geometry.type`, or a
primitive description: parameter retessellation changes seams, caps, and vertex
sampling even when bounds agree.

## Indexed expansion and OBJ ordering

When `geometry.index` is non-null, call `geometry.toNonIndexed()` or perform an
equivalent per-index expansion before face traversal. Every index triple becomes
one expanded position triple, so the output triangle count is the source index
count divided by three. When the index is null, traverse the position buffer
sequentially in triples. Emit one `o` record per source mesh in traversal order,
one `v` per expanded position in source triangle order, and one-based faces with
the available `v/vt/vn`, `v//vn`, `v/vt`, or `v` form. Keep one mesh record per
source mesh; never merge siblings or reorder faces.

## Blender Z-up frame transfer

After the world transform, apply the artifact frame transfer to every vertex:
rotation of -90 degrees about X, mapping `(x, y, z)` to `(x, z, -y)`. Apply the
same rotation to every normal. This is the Blender Z-up convention when the
source scene is Y-up. Do not apply the rotation twice, omit it, or substitute a
different axis order. The manifest records the frame name and
`rotation_degrees_xyz: [-90, 0, 0]`.

A producer that emits self-consistent but unframed coordinates is still wrong;
matching bounds, centroids, or a reference-exporter byte comparison does not
make it acceptable.

## Full-precision coordinates

Write every coordinate with the runtime's shortest round-trip decimal form,
such as JavaScript `String(value)`. Never use `toFixed`, a printf-style fixed
count, truncation, or zero padding. Fixed decimals can change canonical sort
order and sparse surface sampling even when bounds and tolerant nearest-point
distances look correct. A non-finite coordinate is a rejected mesh.

## Artifact manifest

`manifest.json` is evidence, not the acceptance oracle. It records the source
module, artifact filename, frame, mesh and vertex/triangle totals, and per-mesh
source buffer counts, expansion mode, output counts, and offsets. The producer
validates the manifest after writing: the OBJ must exist, its `v` and `f`
records must match the manifest totals, and the mesh records and frame must be
consistent. An agent-reconstructed manifest is not producer evidence.

## Rejection behavior

Exit nonzero with a structured error identifying the module or mesh when:

- `--module` or `--out` is missing, or the module is not `.js`/`.mjs`;
- the module has no callable `createScene()`;
- `createScene()` returns no scene or no positioned meshes;
- a positioned node lacks `geometry.attributes.position`, or its position is
  not a three-component array-like buffer;
- an index or optional attribute exists but is not an array-like buffer;
- a coordinate is non-finite;
- the artifact directory or file cannot be written;
- the written manifest does not match the written OBJ.

Do not fall back to a normalized intermediate, a parameters rebuild, or a
silent skip after a rejection.

## Independent verification

`scripts/check_native_scene.mjs` is a separate process from the producer and
the single permitted compatibility probe. It imports the module itself, calls
`createScene()`, derives the expected vertex sequence from the live
position/index buffers, expands indexed geometry, composes hierarchy and world
transforms including instanced-mesh expansion, applies the -90 degree X frame
rotation in its own code, and compares the complete OBJ by object, expanded face
count, winding, component order, non-indexed output, vertex order, and every
coordinate. It reports hierarchy, world transforms, indexed versus non-indexed
geometry, Float32 positions, concrete failing vertex indices, expected and
actual bounds, tolerance, maximum position delta, and frame, and exits nonzero
on any violation.

The checker's expectation is the live source module or another task-visible
independent oracle. Agreement with a reference exporter, a producer-side
manifest, a patched reference, or a copy of producer output is not independent
evidence. When no source-derived or task-supplied oracle is available, report
the artifact `unverifiable` with a nonzero status instead of pass.

Run it once after the producer and its manifest validation. It is also the only
compatibility probe:



```bash
node scripts/check_native_scene.mjs --module <scene.js|scene.mjs> \
  --root <artifact-directory> [--tolerance 1e-12] [--json <report.json>]
```

The clean fixture `scripts/fixtures/native-module/scene.mjs` with the
`clean/` artifact proves the positive path, and
`scripts/fixtures/native-module/instanced_scene.mjs` covers a nested
non-identity transform with two expanded instances. The `wrongly_framed/` artifact is
self-consistent, matches the manifest, and has the same bounds set, yet the
checker reports a frame-attributed coordinate violation. The `near_miss/`
artifact fails a one-micrometre tolerance by a hair while its sibling mesh
passes, and `precision_truncated/` is rejected by the round-trip precision
check. These are regression fixtures, not task thresholds.
