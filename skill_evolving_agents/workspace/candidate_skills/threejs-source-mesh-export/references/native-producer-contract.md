# Native producer contract

Read this when producing an OBJ from a `.js` or `.mjs` Three.js scene module,
when deciding whether an input is an acceptable native source, or when checking
that indexed geometry was triangle-expanded rather than retessellated.

Contents: module ABI; producer-first sequence; single-OBJ command; native
buffers and instancing; indexed expansion; OBJExporter semantics; full precision;
manifest; budget and fallback; rejection rules; independent check.

## Module ABI

The only scene input is an executable ES module with a `.js` or `.mjs`
extension that exports `createScene` (named export or
`default.createScene`). The producer imports the module, calls
`createScene()` with no arguments, and traverses the returned object graph.
Actual `THREE.Group`, `THREE.Mesh`, and `THREE.InstancedMesh` instances and
plain objects with the same `position`, `quaternion` or `rotation`, `scale`,
`children`, `geometry`, `name`, `isInstancedMesh`, `count`, and
`instanceMatrix` fields are all acceptable. The module is executed, not
statically scraped or re-exported.

A JSON, CSV, manifest, or other normalized mesh file is never producer input.
It may be emitted as evidence, but it cannot replace module execution.

## Producer-first sequence

After confirming only the native module path and the requested OBJ output path
or directory, run the bundled producer immediately. The complete sequence is:

1. one producer invocation;
2. the producer's one built-in manifest validation;
3. one independent geometry check, which is also the single permitted
   compatibility probe;
4. at most one bounded fallback, and only after a recorded producer error.

Do not inspect or normalize the scene first, run a checker before the producer,
list output files, or spend calls on matrix, precision, naming, or file-presence
exploration. A checker-only loop or an ad-hoc exporter written before the
producer is attempted is not a compliant workflow.

## Single-OBJ command

```bash
node scripts/export_native_scene.mjs --module <scene.js|scene.mjs> \
  --out <artifact-directory|artifact.obj> [--name scene.obj]
```

This one command imports or executes the module, calls `createScene()`, walks
the returned graph, composes each mesh's world transform from the scene root
through every ancestor, expands every instanced mesh from its `instanceMatrix`,
writes the requested OBJ and `manifest.json`, and then validates the manifest
against the written OBJ. If `--out` already ends in `.obj`, it is treated as the
OBJ path and `manifest.json` is written beside it.

## Default part/link tree command

When the task explicitly requires the `part_meshes` plus `links` tree, run the
inherited one-command producer instead:

```bash
node scripts/export_part_meshes.mjs --module <scene.js|scene.mjs> \
  --out <artifact-root> [--report <report.json>] [--no-verify]
```

It writes `part_meshes/<Group name>/<Mesh name>.obj` for every direct
primitive Mesh child of a part Group and `links/<Group name>.obj` for the
combined triangles of that part. A part is a Group with direct primitive Mesh
children, including a nested Group; container Groups without direct primitive
children are not parts. Source object names are used verbatim and must be unique
and safe at their level. A duplicate or path-unsafe name is a fail-closed naming
error, not a cue to guess a suffix. The command writes no hand-authored
intermediate. Verify with `scripts/check_part_meshes.mjs` as a separate process.

`scripts/fixtures/native-scene.mjs` is the clean single-OBJ control. The
inherited `scripts/fixtures/native_scene.mjs` is the native part/tree control.

## Native buffers and instancing

For each mesh, read `geometry.attributes.position` and `geometry.index`
directly. Apply the composed world transform from the scene root through every
ancestor to the mesh. For an `InstancedMesh`, compose each instance's
`instanceMatrix` with that world transform and export one object record per
instance; never collapse instances or export only the base mesh. Read optional
`geometry.attributes.normal` and `geometry.attributes.uv` from the same
geometry; do not synthesize a replacement surface.

Never read `geometry.parameters`, `geometry.type`, or a manual primitive
description to rebuild positions. Parameter retessellation changes seams, caps,
and vertex sampling even when bounds appear identical.

## Indexed expansion

When `geometry.index` is non-null, call `geometry.toNonIndexed()` (or an
equivalent in-memory expansion for a plain BufferGeometry-compatible object)
before face traversal. Every source index triple becomes one triangle-expanded,
non-indexed position triple, so the output triangle count is the source index
count divided by three. When `geometry.index` is null, traverse the position
buffer sequentially in triples. A producer that writes indexed faces or rebuilds
a primitive from its parameters does not satisfy this contract.

## OBJExporter semantics

Use Three.js `OBJExporter`-compatible output. Each part mesh, combined link OBJ,
and single-OBJ object is serialized in expanded triangle order with one-based
face references:

- emit `o <name>` for each source mesh or expanded instance, using source names
  verbatim (an instance suffix is allowed only to keep object names unique);
- emit `v` for every transformed position in expanded triangle order;
- emit `vn` and `vt` when the source geometry supplies normal and UV
  attributes, and reference the matching indices in `f`;
- emit `f v/vt/vn`, `f v//vn`, `f v/vt`, or `f v` as the available attributes
  allow;
- preserve `usemtl` and split faces at `geometry.groups` when the selected
  serializer emits material groups; the default producer writes one
  position/index surface per object;
- keep one mesh record per returned mesh; never merge sibling meshes.

Face indices are one-based and local to the OBJ file, so each object's vertex,
normal, and UV offsets advance by that object's expanded counts. The exported
triangle sequence preserves the source index order and winding; no face is
reordered or rewound.

## Full-precision coordinates

Write every `v`, `vn`, and `vt` coordinate at full round-trip numeric
precision. Convert the numeric value with the runtime's shortest round-trip
decimal form, such as JavaScript `String(value)` or Python `repr(float)`, which
parses back to the identical binary value. Never use a fixed-decimal formatter,
a printf-style fixed decimal count, manual truncation, or zero padding: those
are lossy coordinate formatters and can change triangle order and surface
sampling even when bounds and tolerant nearest-point distances appear correct.
Report a non-finite coordinate as a rejected mesh.

A correct producer writes Float32 or Float64 source components without lossy
rounding, so re-importing the OBJ and comparing it with the native position
values stays within the stated tolerance, commonly `1e-12`.

## Artifact manifest

`manifest.json` records the source module, artifact filename, frame, mesh and
vertex/triangle totals, and per-mesh source buffer counts, expansion mode,
output counts, offsets, hierarchy, and instancing metadata. The producer
validates it once after writing: the OBJ must exist, its `v` and `f` records
must match the totals, and the mesh records and frame must be consistent. Do not
hand-author, patch, or re-validate a manifest, and do not treat manifest
agreement as acceptance evidence.

## Budget checkpoint and fallback

Immediately after the producer returns and its manifest validates, reserve
enough remaining budget to deliver the complete OBJ artifact set, run the one
independent check, and report its diagnostics. Do not use that budget for extra
matrix, precision, naming, or path probes.

Only a concrete producer failure permits a different production path. Read its
structured error code and message first. Then take at most one of: run the one
compatibility probe when the failure is an ambiguous transform or unsupported
scene construct, or write one source-derived replacement under the same module
ABI, native-buffer, expansion, frame, naming, and precision contract. Record the
producer error code. Run the same independent check once and stop after that
single repair pass; do not start a second fallback.

## Rejection rules

Exit nonzero and name the module or mesh path when:

- `--module` or `--out` is missing, or the module is not `.js`/`.mjs`;
- the module has no callable `createScene()`;
- `createScene()` returns no meshes or no Group with direct primitive Mesh
  children;
- a part or mesh name is duplicated at the same level, empty, or unsafe as a
  path component;
- a mesh has no `geometry.attributes.position`, or the position is not a
  three-component array-like buffer;
- an instanced mesh lacks a readable, finite `instanceMatrix` or count;
- an attribute cannot be read as an array-like buffer, or a coordinate is
  non-finite;
- the artifact directory or file cannot be written, or the written manifest
  does not match the written OBJ.

Do not fall back to a normalized intermediate, a parameters rebuild, or a
silent skip after a rejection. Do not patch an individual OBJ file after a
preflight name or precision failure.

## Independent check

`scripts/check_native_scene.mjs` is a separate process and the single
compatibility probe. It imports the module itself, calls `createScene()`,
derives the expected vertex sequence from the live position/index buffers,
expands indexed geometry, composes hierarchy and world transforms including
instance expansion, applies the -90 degree X frame rotation in its own code, and
compares the complete OBJ by object, expanded face count, winding, component
order, non-indexed output, vertex order, and every coordinate. It reports
hierarchy, world transforms, instanced-mesh expansion, indexed versus
non-indexed geometry, Float32 positions, concrete failing vertex indices,
expected and actual bounds, tolerance, maximum position delta, and frame, and
exits nonzero on any violation.

The checker's expectation is the live source module or another task-visible
independent oracle. Agreement with a reference exporter, a producer-side
manifest, a patched reference, or a copy of producer output is not independent
evidence. When no source-derived or task-supplied oracle is available, report
the artifact `unverifiable` with a nonzero status instead of pass.

```bash
node scripts/check_native_scene.mjs --module <scene.js|scene.mjs> \
  --root <artifact-directory> --tolerance 1e-12 [--json <report.json>]
```

The clean fixture `scripts/fixtures/native-module/scene.mjs` proves the positive
path; `scripts/fixtures/native-module/instanced_scene.mjs` adds a nested
non-identity transform and two expanded instances. The `wrongly_framed/` artifact
is self-consistent yet frame-attributed. The `near_miss/` artifact fails a
one-micrometre tolerance by a hair while its sibling passes. The
`precision_truncated/` artifact is rejected by the round-trip precision check.
These are regression fixtures, not task thresholds.
