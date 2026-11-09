---
name: threejs-source-mesh-export
description: One-command end-to-end exporter for a native .js/.mjs module exposing createScene(): directly import or execute the module, call scene.updateMatrixWorld(true), export the returned mesh's native geometry.attributes.position and geometry.index buffers through documented toNonIndexed/OBJExporter semantics, and preserve full round-trip numeric precision. The export must be followed by an executed independent world-space preflight that verifies every vertex against a source-derived reconstruction in the task-declared frame (native source coordinates by default; Blender Z-up -90 degree X only when the task explicitly requires it), rejecting manifest-only, count-only, and self-referential results. Use for Three.js modules, createScene, native geometry buffers, indexed meshes, assemblies, parts, links, part/link trees, wheels/rims, unit conversion, scene-root or part-local placement, up-axis transfer, single-OBJ export, one-command end-to-end producer runs, pre-submission checks, wrongly framed exports, missing preflight, and unverifiable without an independent reference.
---

# Three.js source mesh export

## Overview

Own the source-native path from an executable Three.js module to an OBJ
artifact tree. The input is a `.js` or `.mjs` module that exposes
`createScene()`; the output is the complete `part_meshes` and `links` tree
derived from the live scene graph. The workflow is producer-first: run the
bundled producer once, immediately, over the native module and artifact root.
Do not rebuild export logic with an ad-hoc script and do not hand-author a
normalized scene JSON, CSV, manifest, or other intermediate.

`scripts/export_part_meshes.mjs` imports or executes the module, calls
`createScene()`, traverses every returned mesh, and serializes the live
`geometry.attributes.position` and `geometry.index` buffers. It writes each
direct primitive Mesh under its part Group and a combined link OBJ for that
part. `scripts/check_part_meshes.mjs` independently reloads the module, derives
the part, link, and mesh name sets and expected triangles, and fails closed on a
missing, extra, renamed, or inexact path. Production and verification remain
separate processes.

Read `references/native-producer-contract.md` for the module ABI, tree layout,
buffer and expansion rules, OBJExporter ordering, precision, and rejection
behavior. Read `references/verification-contract.md` for the independent
name-set and precision preflight, the single-OBJ comparison, tolerances, the
legacy mapped path, and fail-closed semantics.

## When to Use

Use this skill when a Three.js scene is supplied as a `.js` or `.mjs` module
that exports or defines `createScene()` returning the scene object or a mesh to
export to OBJ, or when an OBJ artifact must preserve that scene's native
`BufferGeometry`. This includes indexed meshes that require triangle-expanded
output, part and link meshes, sibling part groups, assembly parts, wheels and
rims, unit conversion, and scene-root versus part-local placement.

Use it for a one-command end-to-end producer run over the native module. Choose
the producer by the requested artifact shape: `scripts/export_part_meshes.mjs`
for a `part_meshes`/`links` tree, otherwise `scripts/export-scene.mjs`. Apply
the Blender Z-up -90 degree X transfer only when the task explicitly requires
Blender Z-up; otherwise preserve native source coordinates. Do not require a
separate normalized scene, geometry dump, or manifest before execution.

Use it also when a required `part_meshes` tree must contain one directory per
source part and one OBJ per source mesh, together with a `links` tree containing
one OBJ per part. Use it when those output directories already exist but the
produced part, link, or mesh names do not match the source Group structure, or
when the coordinates do not round-trip the source buffers exactly.

Use it for a pre-submission check of an existing OBJ export when the expected
surface must come from the source module's live buffers rather than a producer
manifest, a hand-authored normalized scene, or a parameters-based rebuild.

Use it when any reported success rests on a producer manifest, matching vertex
or triangle counts, or ad hoc file diffs without an executed world-space
position comparison. Source inspection, a manifest, and matching counts do not
qualify as verification.

## Do Not Use

Do not use for generic artifact conformance, repository review, packaging, or
non-geometric acceptance checks; defer those to `artifact-conformance-preflight`.
Do not use when no readable source scene or task-derived part, frame, unit, and
tolerance contract is available, except to report the export as unverifiable.
Do not derive the expected surface from the producer exporter.

## Workflow

1. Confirm only the native `.js` or `.mjs` module path, the requested artifact
   shape, and the task-visible frame contract. Read the prompt for an explicit
   Blender/Z-up/rotation requirement; native source coordinates are the default.
   Then immediately run the documented one-command end-to-end producer. Do not
   inspect the scene, write a normalized intermediate, invoke a checker, probe
   transforms, or test file presence first.

   For a requested `part_meshes`/`links` tree:

   ```bash
   node scripts/export_part_meshes.mjs --module <scene.js|scene.mjs> \
     --out <artifact-root>
   ```

   For a single OBJ (pass `--frame blender-z-up` only when the task explicitly
   requires it):

   ```bash
   node scripts/export-scene.mjs --module <scene.js|scene.mjs> \
     --out <artifact.obj|artifact-directory> [--name scene.obj] \
     [--frame native|blender-z-up]
   ```

2. That command is the production path. It directly imports or executes the
   module, calls its `createScene()` entrypoint, and calls
   `scene.updateMatrixWorld(true)` so every scene graph world matrix is
   refreshed before any geometry is read. It then walks the returned mesh or
   scene and reads each mesh's native `geometry.attributes.position` and
   `geometry.index` buffers directly, with no hand-authored normalized
   intermediate and no manifest prerequisite.

3. Export with explicit world-space and target-serializer semantics. For each
   mesh, apply its `matrixWorld` once, then apply the task-declared frame once:
   no axis transfer for native coordinates, or the Blender Z-up -90 degree X
   transfer only when the task explicitly requires it. Never apply a frame the
   task did not request. When an index exists, clone and triangle-expand it with
   `toNonIndexed()` or byte-equivalent expansion before face traversal. Document
   and verify `toNonIndexed`/`OBJExporter` behavior for index expansion, source
   triangle and vertex order, one-based references, normals, UVs, and transform
   handling; do not assume OBJExporter refreshes or applies the scene graph for
   you. Serialize enough digits to recover the source buffer values, then reparse
   the written OBJ and compare it with those values. The producer writes the
   requested OBJ and a `manifest.json` run record; the record is evidence only.

4. Before submission, run the independent position preflight as a separate
   executed step. For a part/link tree use `scripts/check_part_meshes.mjs
   --module <scene.js|scene.mjs> --root <artifact-root>`. For a single OBJ use:

   ```bash
   node scripts/check-export.mjs --module <scene.js|scene.mjs> \
     --artifact <artifact.obj> [--tolerance <task-tolerance>] \
     [--frame native|blender-z-up] [--json <check.json>]
   ```

   It reloads the module, calls `createScene()`, calls
   `scene.updateMatrixWorld(true)`, and reconstructs source world-space positions
   through its own code. It compares every exported vertex at the task-derived
   tolerance in the task-declared frame, reporting the compared frame, maximum
   position delta, source and output bounds, round-trip precision, and failing
   vertex indices. A clean manifest, matching counts, or
   producer/reference-exporter agreement is not a substitute for this executed
   check.

5. Only a concrete producer failure permits a different production path. Read
   the structured producer error first. Then take at most one bounded action:
   run the one compatibility probe when the failure is an ambiguous transform
   or scene construct, or write one source-derived replacement under the same
   module ABI, native-buffer, expansion, frame, naming, precision, and run-record
   contract after recording the producer error code. Run the same independent
   preflight once afterward and require it to exit zero. Do not probe additional
   paths, matrices, precisions, or file-presence conditions, and do not start a
   second fallback pass.

6. Reserve enough budget to deliver the complete requested artifact set and run
   the preflight. Reject submission when the preflight was not executed or
   exits nonzero. If it fails, report the concrete failing paths, frame, and
   values instead of repairing and probing repeatedly or patching individual OBJ
   files. If an independent source-derived oracle cannot be established, report
   `unverifiable` with a nonzero exit.

7. When the task explicitly requires the `part_meshes` and `links` tree
   instead of one OBJ, use the inherited one-command native producer
   `scripts/export_part_meshes.mjs --module <scene.js|scene.mjs> --out
   <artifact-root>` and verify with `scripts/check_part_meshes.mjs`; it follows
   the same native-buffer, expansion, naming, and precision rules. The
   inherited `scripts/export_native_scene.mjs` and
   `scripts/check_native_scene.mjs` remain available for the previous producer's
   compatibility fixtures. The inherited `scripts/export_threejs_scene.mjs` and
   `scripts/check_native_export.mjs` remain available for legacy single-OBJ
   fixtures but are not the default source-native path.
   `scripts/export_scene_meshes.mjs` and
   `scripts/export_scene_meshes.py --check` are legacy-only.

Read `references/native-scene-producer.md` for the producer invocation, native
buffer and frame contract, manifest rules, rejection behavior, and the
proxy-versus-independent distinction. `scripts/fixtures/native-module/scene.mjs`
is the clean native control; `scripts/fixtures/native-module/wrongly_framed.mjs`
is the matching-count, clean-manifest, wrongly framed near-miss.

## Constraints

- Producer-first bounded execution: the bundled producer is the only production
  path and runs immediately after the native module path and OBJ output path are
  confirmed. The whole workflow permits one producer invocation, one run
  record, one mandatory independent preflight, and at most one compatibility
  probe after a recorded producer error. Do not run additional exploratory
  matrix, precision, naming, hierarchy, or file-presence inspections after those
  calls.
- The producer's only scene input is the native `.js` or `.mjs` module exposing
  `createScene()`; it ships with native-module fixtures containing a nested
  non-identity parent transform and an instanced mesh. Never require or accept a
  manually normalized intermediate scene, geometry, JSON, CSV, or manifest
  before production, and never replace module execution with a static scrape or
  producer-side re-export.
- Call `scene.updateMatrixWorld(true)` after `createScene()` and before reading
  geometry, then apply each mesh's `matrixWorld` explicitly. Do not rely on a
  stale world matrix, on local transforms alone, or on OBJExporter to refresh or
  apply the scene graph.
- Export the returned mesh's native `geometry.attributes.position` and
  `geometry.index` buffers. When an index exists, use `toNonIndexed()` or an
  equivalent expansion so every index triple becomes a triangle-expanded,
  non-indexed position triple before faces are written. Never retessellate
  `geometry.parameters`, `geometry.type`, or a primitive description, and never
  copy exporter-derived vertices into the expected side.
- Use documented OBJExporter-compatible semantics: one object record per source
  mesh or instance, source face and vertex order, one-based references, the
  original triangle winding, and explicit handling of normals and UVs. Do not
  reorder, merge, split, or rewind faces.
- Apply only the frame the task declares. Native source coordinates are the
  default and require no axis transfer. When and only when the task explicitly
  requires Blender Z-up, apply the -90 degree X transfer exactly once after the
  applied `matrixWorld`: `(x, y, z)` to `(x, z, -y)`, with the same rotation
  applied to normals. Do not omit a required transfer, apply it twice, or accept
  a self-consistent export in another frame. Do not add a transfer the task did
  not request.
- Derive part and link mesh names from the source scene Group structure. A part
  directory name equals the source Group name; a link OBJ base name equals a
  part name; a part mesh OBJ base name equals the source Mesh name produced by a
  primitive. Do not invent, sanitize, prefix, suffix, or material-bucket names.
- Serialize every coordinate at full round-trip numeric precision. Do not use
  fixed-decimal formatting, printf-style rounding, truncation, or padding; a
  small rounding change can alter triangle order and surface sampling even when
  bounds, centroids, and tolerant nearest-point checks look correct. A
  re-imported OBJ must recover the native position values within the stated
  tolerance.
- Keep production and independent verification as separate scripts. Never
  accept the producer's own manifest or run record, matching vertex or triangle
  counts, ad hoc diff output, a hand-authored normalized intermediate scene, or
  producer/reference-exporter agreement as proof of frame correctness or
  positional equivalence.
- The tolerance and frame come from the task-visible contract, not from
  benchmark-specific constants or producer defaults. No task-visible rotation
  requirement means native coordinates.
- Replacement or custom export code requires a recorded structured producer
  error and stops after one bounded fallback pass using the same contract.
  Without that error, do not write an alternative producer, and do not add
  exploratory probes after the single preflight.
- Compare the complete produced artifact set as exact sets in both directions.
  Report every missing, extra, renamed, inexact, and wrongly framed record with
  its concrete path and vertex index. Never stop at the first mismatch when a
  complete set comparison is possible.
- Fail closed as `unverifiable` with a nonzero exit when the source module,
  `createScene()`, `updateMatrixWorld(true)`, live position or index buffers,
  artifact, or source-derived reconstruction cannot be established, or when no
  independent source-derived or task-supplied oracle exists.
- Keep all tolerances and fixture displacements task-derived or synthetic. Do
  not encode benchmark paths, hidden thresholds, trace-specific mesh values, or
  hidden verifier outputs in the producer or checker.
- Preserve source mesh boundaries and triangle order. Do not merge sibling
  meshes, drop a mesh, or replace the requested OBJ artifact with a report,
  manifest, or prose restatement.

## Verification

Require one executed independent world-space comparison after production, using
the separate preflight entry point:

```bash
node scripts/check_part_meshes.mjs --module <scene.js|scene.mjs> --root <artifact-root>
node scripts/check-export.mjs --module <scene.js|scene.mjs> \
  --artifact <artifact.obj> --tolerance <task-tolerance> \
  [--frame native|blender-z-up] --json <check.json>
```

The checker independently calls `createScene()`, calls
`scene.updateMatrixWorld(true)`, derives every expected vertex from the native
`geometry.attributes.position` and `geometry.index` buffers and each mesh's
`matrixWorld`, and expands indexed geometry with the documented `toNonIndexed`
semantics. It compares every exported vertex at the task-derived tolerance in
the task-declared frame; it applies the -90 degree X transfer only when the task
requires Blender Z-up.

The report must name the compared frame, tolerance, maximum position delta,
source and output bounding boxes, round-trip precision, and failing vertex
indices for the declared comparison. It must exit nonzero on any frame,
position, index-expansion, or precision mismatch. A wrong-frame case is
attributed to the frame; an unrequested rotation is a frame mismatch.

Prohibit self-referential expectations: expected values may not be produced by
the same export code path, a producer-derived reference, a patched reference, or
a copy of producer output. Do not use the producer manifest, its run record,
matching counts, or ad hoc file diffs as the acceptance oracle, and do not run
further manual probes as a substitute for delivering the artifact. If no
source-derived or task-supplied reconstruction can be executed, report the
artifact `unverifiable` with a nonzero exit.

Exercise the native controls end to end:

```bash
node scripts/export-scene.mjs \
  --module scripts/fixtures/native-module/scene.mjs --out <clean-root>
node scripts/check-export.mjs \
  --module scripts/fixtures/native-module/scene.mjs \
  --artifact <clean-root>/scene.obj --tolerance <task-tolerance>

node scripts/export-scene.mjs \
  --module scripts/fixtures/native-module/wrongly_framed.mjs --out <wrong-root>
node scripts/check-export.mjs \
  --module scripts/fixtures/native-module/scene.mjs \
  --artifact <wrong-root>/scene.obj --tolerance <task-tolerance>
```

The clean native module must exit zero with every mesh passing, zero maximum
position delta within tolerance, and round-trip precision preserved. The
`scripts/fixtures/native-module/wrongly_framed.mjs` near-miss has the same
counts, names, and a clean manifest but a wrong world frame; its preflight must
exit nonzero and name the frame, maximum position delta, and failing vertex
indices. The inherited `scripts/check_native_scene.mjs` remains the compatibility
checker for the previous producer, and
`scripts/fixtures/native-module/instanced_scene.mjs`,
`scripts/fixtures/native-module/missing_create_scene.mjs`,
`scripts/fixtures/native-module/missing_buffers.mjs`, and
`scripts/fixtures/native-module/incompatible_instancing.mjs` retain their
structured controls. Preserve the inherited part/tree checks in
`scripts/check_part_meshes.mjs` and the legacy single-OBJ checks in
`scripts/check_native_export.mjs` and `scripts/check_mesh_conformance.py`.

Producer exit zero, manifest agreement, matching bounds or counts, and agreement
with a reference exporter or producer-derived reference are not independent
acceptance evidence. Any nonzero exit is a failure, not a warning, and does not
authorize another probe or replacement pass.

## Output Format

`scripts/export-scene.mjs` writes the requested `.obj` file and a
`manifest.json` run record in the same artifact directory. The record names the
native `.js`/`.mjs` module path, the executed `createScene()` entrypoint, the
`scene.updateMatrixWorld(true)` call, the returned mesh or scene, the native
`geometry.attributes.position` and `geometry.index` counts, the
`toNonIndexed`/`OBJExporter` decisions for index expansion, triangle order,
normals, UVs, and transforms, the matrixWorld application, the numeric precision
used, and the independent checker command and its executed result. The run
record is evidence only and must never be a prerequisite that the agent
reconstructs by hand.

The artifact contract is explicit:

- each part directory name equals the source Group name;
- each `links` OBJ base name equals a part name, and that link OBJ contains the
  combined triangles of the part's meshes;
- each part mesh OBJ base name equals the source Mesh name produced by a
  primitive;
- each OBJ vertex comes from the native `geometry.attributes.position` buffer
  and each triangular face from `geometry.index`, or from the
  `geometry.toNonIndexed()` geometry when index expansion is selected;
- face winding, triangle order, one-based references, and global vertex offsets
  match OBJExporter semantics;
- coordinates are emitted at full round-trip precision, with no fixed-decimal
  loss.

Report the completed artifact and its evidence: the exact producer command and
source module path; artifact path or tree; the returned mesh; position and index
buffer counts; expansion decisions; expected and actual part, mesh, and link
sets when a tree is requested; and the independent preflight result. The report
must state the compared frame, task tolerance, maximum position delta, source
and output bounds, round-trip precision, failing vertex indices, and the
checker's exit status. State acceptance only after the executed independent
preflight exits zero. Otherwise report the concrete mismatched paths, frame, and
values or an explicit `unverifiable` status naming the missing independent
input. Keep the requested OBJ artifact.

## Limitations

When source names are duplicated or ambiguous at the same level, report the
naming constraint as unverifiable or require an explicit source-level
disambiguation rule instead of guessing names. When a mesh has no index, uses
unsupported attribute types, or carries unsupported material or morph data,
state the chosen `toNonIndexed`, OBJExporter, or precision behavior explicitly
and report the affected record rather than silently dropping it.

Constructive solid geometry, instancing, and shader-displaced geometry may need
additional source sampling or a flattened source primitive. The helper checks
OBJ and JSON triangle meshes directly; for glTF, extract positioned triangle
primitives into one of those forms before checking. This is a local
source-derived preflight, not a replica of or substitute for any hidden
objective verifier.
