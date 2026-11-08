# Verification contract

Read this reference when running the manifest gate, interpreting the check
report, or selecting a regression fixture. `SKILL.md` owns the procedure; this
file holds the detailed contract and the fixture matrix.

Contents: native scene artifact preflight, source-derived part/link name-set
preflight, source-native OBJ comparison, complete-artifact Chamfer preflight,
legacy one-command invocation,
manifest derivation, report and attribution, non-evidence, regression matrix,
completion evidence.

## Native scene artifact preflight

The mandatory execution order for a native module is: enter the `.js`/`.mjs`
module, call its `createScene()` entrypoint, call
`scene.updateMatrixWorld(true)`, read the returned mesh's native
`geometry.attributes.position` and `geometry.index` buffers, apply the
`toNonIndexed`/`OBJExporter` semantics, export the requested OBJ, then run the
independent frame and position preflight. Verification is an executed step, not
a reading of the producer's output.

For artifacts from the one-command `scripts/export-scene.mjs` producer, run the
separate executed preflight before submission:

```bash
node scripts/check-export.mjs --module <scene.js|scene.mjs> \
  --artifact <artifact.obj> [--tolerance 1e-12] [--json <check.json>]
```

The checker reloads and executes the native module, calls `createScene()`, calls
`scene.updateMatrixWorld(true)`, and derives expected vertices only from
`geometry.attributes.position` and `geometry.index` under each mesh's
`matrixWorld`. It expands indexed geometry with `toNonIndexed()` semantics,
applies the Blender Z-up -90 degree X frame transfer in its own code, and
compares every exported vertex in both the as-exported frame and the rotated
frame. It reports the compared frame, task-derived tolerance, maximum position
delta, source and output bounding boxes, round-trip precision, and failing
vertex indices for both comparisons, with frame attribution when the
as-exported comparison passes and the rotated comparison fails. It exits
nonzero on any frame, position, index-expansion, or precision mismatch.

The manifest and the producer run record are integrity evidence only. They are
never the expected values and are never a prerequisite the agent must build by
hand. Agreement with the producer, its manifest, matching vertex or triangle
counts, ad hoc file diffs, or a reference exporter is not evidence. When no
source-derived or task-supplied reconstruction can be executed, report
`unverifiable` with a nonzero status. See `native-scene-producer.md` for the
producer and frame contract; the older `scripts/check_native_scene.mjs` remains
the inherited compatibility checker for the previous producer.

## Source-derived part/link name-set preflight

The part/link tree preflight, used when that layout is explicitly requested,
reloads the native module and compares the complete produced tree with
source-derived name sets and coordinates:

```bash
node scripts/check_part_meshes.mjs --module <scene.js|scene.mjs> \
  --root <artifact-root> [--coordinate-tolerance 1e-12] [--report <check.json>]
```

The checker calls `createScene()` itself and derives:

- part directories from Group objects with direct primitive Mesh children;
- part mesh OBJ paths from those Mesh children;
- link OBJ paths from the same part names.

It enumerates `part_meshes/<part>/<mesh>.obj` and `links/<part>.obj`, compares
both directions, and reports every missing part directory, extra part
directory, missing or extra part mesh, missing or extra link OBJ, unexpected
OBJ, and inexact coordinate with its concrete path. It recomputes each expected
triangle from `geometry.attributes.position` and `geometry.index` under the same
`toNonIndexed()` expansion, source triangle order, and composed world transform
as production, then compares the serialized coordinates at
`--coordinate-tolerance`. Directory existence, file counts, matching names
alone, and a clean producer exit are never accepted as the whole preflight.

A renamed part or mesh and a rounded coordinate are distinct failures:
the first fails the name-set gate before geometry, and the second passes the
name sets but reports an `inexact_*_coordinate` record naming the artifact path.
Both exit nonzero.

## Source-native OBJ comparison

The default producer is `scripts/export_native_scene.mjs` (see
`native-scene-producer.md`). The inherited commands below remain for legacy
single-OBJ fixtures and are not the default source-native path:

```bash
node scripts/export_threejs_scene.mjs --module <scene.js|scene.mjs> \
  --out <artifact.obj> [--report <report.json>]

node scripts/check_native_export.mjs \
  --config scripts/fixtures/native_export_spec.json \
  --artifact <artifact.obj> [--json <check.json>]
```

The checker executes the configured clean module with its own bridge, calls
`createScene()`, and derives expected vertices and triangles from the live
`geometry.attributes.position` and `geometry.index` buffers under the composed
world transform. It parses the submitted OBJ independently and compares the
expanded triangle sequence. For an indexed source mesh, the expected sequence
must be the `toNonIndexed()` triangle-expanded sequence, not the original index
buffer and not a reconstruction from `geometry.parameters`. A missing position
attribute, non-triangle face, missing mesh, extra mesh, or unavailable clean
module is `unverifiable` and exits nonzero.

The task-derived tolerance comes from the check config. Each violation reports
the mesh path, observed maximum position distance, tolerance, coordinate error,
and `placement` versus `shape` attribution. A separate `coordinate_error` gate
uses `coordinate_tolerance` (default `1e-12`) so fixed-decimal serialization
fails even when the loose surface distance is within tolerance. Attribution is `placement` when a
translation alone brings the submitted triangles within tolerance and `shape`
when it does not; do not report a clean pass when the observed distance exceeds
tolerance.

### Seeded negative control

Run the producer on `scripts/fixtures/native_scene_displaced.mjs` (part
placement), `scripts/fixtures/native_scene_displaced_link.mjs` (link
placement), and `scripts/fixtures/native_scene_displaced_pair.mjs` (both), then
check each artifact against the clean `scripts/fixtures/native_scene.mjs`
config. Each control must exit nonzero and name the displaced mesh path with
its observed distance, the same task-derived tolerance, and `placement`
attribution. A checker that passes either seeded displacement is an
unverifiable oracle, not a clean result.

## Complete-artifact Chamfer preflight

Run the independent geometry-fidelity gate over the complete output tree:

```bash
python3 scripts/check_mesh_conformance.py <artifact-root> \
  --spec <task-derived-spec.json> [--report <check.json>]
```

The spec is the only source of tolerance, frame, units, part/link mapping or
contract, and reference source. The checker reconstructs the expected surface
independently from task-supplied ground truth or a separately implemented
source-scene reconstruction, computes a bidirectional Chamfer distance and
coverage for every part and link mesh, and emits `mesh_path`, `metric`,
`observed`, `threshold`, `coverage`, `attribution`, and `status`. It exits
nonzero on any violation and nonzero `unverifiable` when the independent
reference or complete tree cannot be established. It must not import the
producer, read its report, or use a patched reference or produced OBJ as the
expectation.

The one-command native fixture is verified separately:

```bash
node scripts/export_threejs_scene.mjs \
  --module scripts/fixtures/native-scene.mjs --out <fixture.obj>
node scripts/check_native_export.mjs \
  --config scripts/fixtures/native-scene-spec.json --artifact <fixture.obj>
```

The indexed `outer_rim` must be triangle-expanded to `source_index_count / 3`
faces, `support` must be traversed directly, and every mesh must have zero
`coordinate_error` within `coordinate_tolerance`. This proves expansion and
full-precision serialization; it does not replace the Chamfer preflight over
the complete tree.

## Legacy one-command invocation

Run the inherited part/link production and validation path as one command from
the native module:

```bash
node scripts/export_scene_meshes.mjs --module <scene.js|scene.mjs> \
  --out <artifact-root> --spec <spec.json> --report <report.json>
```

The producer imports or executes the module, calls `createScene()`, writes the
complete part and link OBJ tree, then invokes `scripts/check_mesh_conformance.py`
as a separate process over that actual tree and returns the checker's exit code.
The spec supplies only the task-derived frame, units, tolerance, and part or
mapping contract; it supplies no scene geometry. Export-only mode (`--spec`
omitted) exists for inspection and is not acceptance evidence. The legacy
`scripts/export_scene_meshes.py --check` mode serves only older mapped evals; it
is not the source-native acceptance path.

A manually authored normalized scene JSON, an export manifest, or the
producer's own verify report may be emitted as evidence, but none may be
required as an input or used as the expectation.

## Manifest derivation

The checker executes the same native `.js`/`.mjs` module that the producer used
and calls its `createScene()` export. Starting at the returned root, it applies
the task-visible `part_contract`:

- `group_type` is the part boundary. Each Group with direct primitive leaf
  children is one part directory.
- `primitive_leaf_type` is the link boundary. Each primitive leaf beneath that
  Group is one link OBJ inside the part directory.
- Names are the source object names verbatim, including duplicate or unsafe
  names. Do not sanitize, suffix, material-bucket, or merge them.

The resulting expected sets are `(part_directory, link_obj_name)` path pairs.
Compare them with the produced tree as exact sets, in both directions. Emit a
record for every missing part directory, extra part directory, missing link OBJ,
extra link OBJ, and renamed pair (expected path and actual path). Renaming is a
remove-plus-add and must be reported explicitly. Exit nonzero on any difference,
before geometry acceptance.

The expectation may not come from the producer, its `--manifest` output, a
hand-maintained mapping, the produced tree, or a caller-supplied expected list.
If `createScene()`, `part_contract`, or source names cannot be established,
report `unverifiable` and exit nonzero.

## Report and attribution

Each mesh record carries `mesh`, `metric` (`chamfer`), `observed`, `tolerance`,
`coverage`, `min_coverage`, `attribution`, and `status`. The checker records
every mesh in the tree, emits every violation, and prints a final
`failed meshes (N): ...` line; it does not stop at the first failure. Coverage
below `min_coverage` also fails. Attribution is `none`, `placement`, `frame`,
`unit`, `frame+unit`, or `shape`:

- `placement`: a translation alone brings the mesh within tolerance.
- `frame`: an axis rotation alone brings it within tolerance.
- `unit`: a uniform scale alone brings it within tolerance.
- `frame+unit`: the rotation and scale together bring it within tolerance.
- `shape`: no rigid transform or uniform scale is sufficient.
- `unverifiable`: independent input is missing.

The checker rebuilds every expected surface from source primitive kind,
arguments, local transform, full parent chain, and scene-root transform in the
declared frame and units, compares each submitted mesh with bidirectional
Chamfer, and exits nonzero. It must not import the producer, share its parser or
normalizer, or read producer output as input. When no independent recomputation
or task-grounded metamorphic check (invariance, bounds, reversibility, or
cross-representation agreement) is possible, report the constraint as
`unverifiable`; do not substitute agreement with the exporter's own verify
script.

## Non-evidence

Directory existence, file counts, manifests, a clean producer exit, coverage of
whatever was produced, and agreement between an export script and its own verify
script are not geometric evidence. Only the independently reconstructed,
bidirectional Chamfer result over the submitted tree is.

## Regression matrix

| Fixture | Expected result |
| --- | --- |
| `scripts/fixtures/native_scene.mjs` + `scripts/fixtures/native_export_spec.json` with `export_threejs_scene.mjs` and `check_native_export.mjs` | Zero exit; indexed `outer_rim` triangles equal its expanded position sequence and non-indexed `support` triangles match directly |
| `scripts/fixtures/native_scene_displaced.mjs` against the clean native config | Nonzero naming the displaced part mesh with observed distance, tolerance, `placement` |
| `scripts/fixtures/native_scene_displaced_link.mjs` against the clean native config | Nonzero naming the displaced link mesh with observed distance, tolerance, `placement` |
| `scripts/fixtures/native_scene_displaced_pair.mjs` against the clean native config | Nonzero naming both displaced meshes with observed values, tolerance, `placement` |
| A producer that retessellates `geometry.parameters` or accepts a hand-authored JSON/CSV intermediate | Rejected as a non-native producer; not accepted as clean |
| A module without a `createScene()` export | Nonzero named rejection, no artifact accepted |
| `scripts/fixtures/multipart-scene.mjs` + `scripts/fixtures/multipart_spec.json` | Four sibling part directories, eight link OBJs, zero exit, all geometry passing |
| `scripts/fixtures/multipart_collapsed/` | Nonzero manifest gate listing missing `left_rail`, `right_rail`, `front_axle`, `rear_axle`; extra `rails`, `axles`; missing and extra link OBJs and renamed pairs |
| `scripts/fixtures/native-scene.mjs` + `scripts/fixtures/native-scene-spec.json` with `export_threejs_scene.mjs` and `check_native_export.mjs` | Zero exit; indexed `outer_rim` is triangle-expanded and every `coordinate_error` is zero |
| `scripts/fixtures/native_scene.mjs` + `scripts/fixtures/native_spec.json`, one command with `--spec` | Clean native control, zero exit |
| `scripts/fixtures/native_scene.mjs` + `export_part_meshes.mjs` then `check_part_meshes.mjs` | Zero exit; two part directories, two part mesh OBJs, two link OBJs, all coordinates exact |
| `scripts/fixtures/native-part-scene-renamed.mjs` produced then checked against clean `native_scene.mjs` | Nonzero; missing and extra part directory, part mesh, and link OBJ paths named |
| `scripts/fixtures/native-part-scene-rounded.mjs` produced then checked against clean `native_scene.mjs` | Nonzero; name sets pass but the part mesh and link OBJ are named as inexact coordinates |
| `scripts/fixtures/native_shape_distorted.mjs` with `scripts/fixtures/native_shape_distorted_ref.json` | Locally patched reference passes, proving the export is self-consistent but not geometrically correct |
| `scripts/fixtures/native_shape_distorted.mjs` with the clean native config | Nonzero `shape` violation naming `assembly/wheel_structure/outer_rim` with observed distance greater than tolerance |
| `scripts/fixtures/shape_distorted/` + `scripts/fixtures/spec.json` | Nonzero independent Chamfer failure naming `wheel_structure/outer_rim.obj` with `shape` |
| `scripts/fixtures/native_patched_reference_spec.json` | Nonzero `unverifiable`, because the reconstruction method is patched rather than source-derived |
| `scripts/fixtures/native_scene_displaced.mjs` with the clean spec | Nonzero naming `wheel_structure/outer_rim.obj` with observed distance, tolerance, `placement` |
| `scripts/fixtures/native_scene_displaced_pair.mjs` with the clean spec and `scripts/fixtures/native_producer_verify.json` present | Nonzero naming both `wheel_structure/outer_rim.obj` and `assembly/support.obj` with observed values, tolerance, and `placement`, despite the producer report claiming success |
| `scripts/fixtures/native_self_consistent_spec.json` | Nonzero `unverifiable`, because its reconstruction method or source is producer-derived |
| `scripts/fixtures/spec.json` + `scripts/fixtures/clean/` | Legacy clean control, zero exit, attribution `none` |
| `scripts/fixtures/displaced_part/`, `displaced_link/`, `displaced_rim_1p46/`, `displaced_support_0p075/` | Nonzero, `placement`, naming the affected link |
| `scripts/fixtures/shape_distorted/`, `frame_mismatch/`, `unit_mismatch/` | Nonzero with `shape`, `frame`, and `unit` respectively |

`scripts/fixtures/native-scene.mjs` re-exports the same clean `createScene()`
for the one-command acceptance path. `native_shape_distorted.mjs` scales one
rim position buffer and recomputes its normals, so the OBJ is internally
self-consistent while the independent Chamfer check reports `shape`.
`scripts/fixtures/native_scene.mjs` is the source for the native control,
`native_scene_displaced.mjs` displaces only the outer rim, and
`native_scene_displaced_pair.mjs` displaces both the outer rim and the support
link. Keep `native_spec.json` pointing at the clean module so displacement
appears as a geometry violation rather than as a different expectation. The
`assembly/support.obj` path follows the declared part rule: `assembly` is a
Group with a direct primitive leaf, so that leaf is a link OBJ inside the
`assembly` part directory.

`scripts/fixtures/source_scene.json` and `scripts/fixtures/spec.json` are the
legacy mapped controls used by `scripts/export_scene_meshes.py`; they remain for
the existing eval cases and are not the source-native path. A normalized scene
JSON may be emitted as post-extraction evidence, but it is never an input to the
source-native producer or the manifest expectation.

## Completion evidence

Report the name-set comparison and every part mesh and link OBJ record first,
then any legacy manifest result and mesh records. For the default tree, report
the producer command, artifact root, expected and actual part/mesh/link sets,
each coordinate error against the precision tolerance, and every
missing/extra/inexact path. A clean run of the producer alone is not evidence;
run the independent checker over the complete tree. Acceptance requires a
zero exit from the checker after both gates pass. A clean producer run, matching
file counts, a self-consistent union, or coverage of whatever was produced is
not manifest evidence. Re-run the clean control and every representative
near-miss after each repair.
