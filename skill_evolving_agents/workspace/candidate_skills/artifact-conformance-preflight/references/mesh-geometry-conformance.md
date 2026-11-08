# Mesh geometry conformance

Read this reference when a deliverable contains an exported part mesh or link
mesh and acceptance depends on matching a task-visible Three.js source scene.
It defines the mandatory geometry gate, the independence test for the expected
surface, the task-derived tolerance rule, the source-scene-to-surface
derivation, the independent assembly and hierarchy oracle, the spec schema,
frame and unit normalization, per-mesh failure attribution, tolerance
comparison, and the worked fixture checks.

## Contents

1. Mandatory gate and admitted evidence
2. Source-scene-to-surface derivation
3. Frames, units, and scene structure
4. Constraint spec schema
5. Surface metric and tolerance comparison
6. Complete part-and-link enumeration
7. Placement versus shape attribution
8. Failure report and exit behavior
9. Unverifiable conditions
10. Worked examples
11. Independent assembly and world-transform oracle
12. Independence test and task-derived tolerance

## 1. Mandatory gate and admitted evidence

Run the geometry gate after every part mesh and link mesh exists and before
packaging the deliverable. It is an executed comparison, not a statement in a
report. The expected surface must be derived independently from the task source
scene, and every named mesh must have a recorded result.

The following are **not** geometric equivalence evidence, even when they agree:

- the producer's own reconstruction, exporter, parser, transform path, or
  intermediate mesh;
- exact per-mesh vertex, face, normal, or triangle-count equality;
- a near-zero triangle delta or `exact_union=True`;
- file counts, mesh counts, a successful parse, or a mesh that opens;
- link meshes that duplicate or mirror their part meshes;
- an inline producer report such as `ALL CHECKS PASSED`.

These are export-path self-consistency. The validator may record them as
`structural_only` for diagnosis, but they never increment a geometry pass and
never change the independent source-scene result. Only a separately
implemented source reader and surface builder, plus a recorded provenance
record, can admit a distance comparison.

## 2. Source-scene-to-surface derivation

1. Locate the task-visible source scene named by the task or spec. A Three.js
   source-scene export is a JSON document with a `units` string, a
   `primitives` array, and optional `nodes` whose entries carry `id`, `parent`,
   `position`, `rotation_euler_deg`, and `scale`. A primitive has an `id`, a
   `type` of `box`, `sphere`, `cylinder`, or `plane`, type-specific dimensions
   (`size` or `dimensions`), optional `position`, `rotation_euler_deg`, and
   `scale`, and an optional `node` or `parent` naming the scene node whose
   world transform it inherits.
2. Read primitive parameters directly from that scene. Do not read them from
   the submitted export, its manifest, a stored expected mesh, the producer's
   manifest, or an intermediate file. A source path that names a manifest,
   export, intermediate, submitted artifact, or mesh suffix is producer-owned
   even when `source_kind` is unset.
3. Rebuild each expected surface in the validator's own builder: apply
   per-axis scale, then Euler rotation in the fixed order `Rz * Ry * Rx`, then
   translation. Record any different task convention in the spec and build the
   expected primitive to match it.
4. Tessellate the reconstructed primitive deterministically. Triangle indices
   are local to the expected surface; correspondence with the submitted mesh is
   by nearest surface point, never by vertex index or triangle index.
5. For a part-local comparison, remove the scene-root placement from the
   primitive before building it, and normalize the submitted part to the same
   local frame. For a scene-root comparison, keep the primitive's position and
   applied scene transform.
6. Record `provenance.source_scene_path`, `provenance.frame`,
   `provenance.units`, and `provenance.derivation`; require `reader` and
   `transform_path`, or an `independence_evidence` object with
   `independent_of_exporter: true`, plus its own `reader` and `transform_path`.
   State the independence evidence explicitly: a separate reader, a separate
   composition path, and source parameters that never passed through the
   producer's primitive decomposition, expected coordinates, or transform code.
7. Map every exported mesh name to one source primitive id or a list of ids
   whose surfaces are combined. A mesh with no mapping is unverifiable, never
   a pass.

## 3. Frames, units, and scene structure

- `scene_root` is the scene's world frame. It includes the primitive's own
  position, rotation, and scale and any scene transform the task declares.
- `part_local` is the part's own frame with scene-root placement removed. The
  submitted part must be normalized to the same local frame.
- `units` is the source-scene unit string and must agree with `source.units`
  when both are declared. `unit_conversion` is the task-derived linear
  `factor` plus optional `offset` that converts the submitted mesh into those
  units.
- `frame_transform` normalizes the submitted mesh after unit conversion. It
  may be a three- or four-row matrix with three or four columns, or an object
  with `scale`, `rotation_euler_deg`, and `translation`. It captures the
  axis-convention change and any group transform the task states.
- Source primitive transforms come from the source scene, never from the
  exporter. Normalize both surfaces before measuring.

Do not derive the tolerance, unit factor, frame convention, mapping, or
expected shape from the submitted mesh. Every one of them comes from the task
statement or the task-derived spec.

## 4. Constraint spec schema

Use one `geometry_conformance` invariant per exported mesh deliverable. A
deliverable file with several named meshes may be checked by one invariant;
separate part and link files each need their own invariant entry.

```json
{
  "id": "exported-crate-geometry",
  "class": "geometry_conformance",
  "deliverable_path": "mesh-box-equivalent.obj",
  "format": "obj",
  "source": {
    "scene_path": "source-scene-box.json",
    "units": "meters"
  },
  "provenance": {
    "source_scene_path": "source-scene-box.json",
    "frame": "scene_root",
    "units": "meters",
    "derivation": "read the task source scene primitive type, dimensions, and transform, then rebuild the expected surface with the preflight builder",
    "reader": "task source-scene primitive reader",
    "transform_path": "independent primitive composition plus frame_transform normalization",
    "independence_evidence": {
      "reader": "second source-scene reader implemented outside the exporter",
      "transform_path": "separate 4x4 primitive and parent-chain composition",
      "independent_of_exporter": true
    }
  },
  "mesh_to_source": {"crate": "crate"},
  "unit_conversion": {"from": "centimeters", "to": "meters", "factor": 0.01, "offset": 0.0},
  "frame_transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]],
  "acceptance_tolerance": 0.01,
  "tolerance": 0.01,
  "metric": "chamfer",
  "sample_count": 512,
  "expected_source": "task statement: exported crate matches the source 1x2x3 m box within 0.01 m"
}
```

Required fields:

- `deliverable_path` is the exported mesh path, resolved against
  `--artifact-root` when supplied and otherwise against the spec directory.
  `mesh_path` is an accepted alias.
- `format` is `obj`, `json`, or `auto`. OBJ meshes use `o` or `g` object names
  and are triangulated from polygons. JSON meshes expose a `meshes` array or one
  `vertices`/`faces` object with names.
- `source` independently exposes `primitives` or a `scene_path` whose document
  has a `primitives` array. `source.mesh_path`, `source.expected_mesh_path`,
  `source.path`, `source.export_path`, `source.link_mesh_path`, and
  `source.part_mesh_path` are rejected: they derive the expectation from the
  export path.
- `provenance` is required before any comparison. Without it every mesh is
  unverifiable and the run exits `1`.
- `mesh_to_source` maps each exported mesh name to one primitive id or a list
  of ids. When the deliverable has exactly one mesh and the scene has exactly
  one primitive, the mapping may be omitted.
- `acceptance_tolerance` is the task-derived pass threshold. `tolerance` is a
  backward-compatible fallback used only when `acceptance_tolerance` is absent;
  when both appear, the task-derived value wins and a looser `tolerance` never
  overrides it. An absent or non-numeric task threshold makes the invariant
  unverifiable; never choose a local default.
- `unit_conversion`, `frame_transform`, `metric`, and `sample_count` are the
  normalization and measurement inputs. `metric` is `max_nearest` (symmetric
  maximum nearest-point deviation) or `chamfer` (symmetric mean nearest-point
  deviation); `sample_count` defaults to 512.
- `expected_source` records the task-visible source of the tolerance, units,
  and mapping.
- `provenance.reader` and `provenance.transform_path` are required
  independence inputs, or an `independence_evidence` object with
  `independent_of_exporter: true` must carry both. A reconstruction that shares
  the producer's primitive decomposition, expected coordinates, or transform
  path is rejected as self-referential even when its distances are small.
- `export_path_checks` optionally declares part/link pairs:
  `{"pairs": [{"part_path": ..., "part_mesh": ..., "link_path": ...,
  "link_mesh": ...}]}`. The validator records matching counts and triangle
  deltas as `status: structural_only`; those records never count toward
  `pass_count`.

`mesh_provenance` may override `source_scene_path`, `frame`, `units`,
`derivation`, `reader`, or `transform_path` for one named mesh, for example
when one deliverable mixes scene-root and part-local meshes. Every override is
subject to the same gate and must not point a mesh at itself.

`evidence: export_path`, `self_consistency_only: true`, `exact_union: true`,
and any declared evidence value of `producer_reconstruction`,
`self_comparison`, `counts`, `file_counts`, or `all_checks_passed` are rejected
as non-independent.

## 5. Surface metric and tolerance comparison

For each named mesh, sample the submitted surface and the reconstructed source
surface deterministically, including triangle vertices, edge midpoints,
centroids, and area-weighted barycentric points. For every sample, compute the
nearest point on the other mesh's triangles. `max_nearest` is the larger of the
two one-sided maxima; `chamfer` is the mean of the two one-sided means.

Pass only when the chosen metric is less than or equal to the task-derived
`acceptance_tolerance`. Report the actual per-mesh value, the threshold, and
the attribution so a near miss is visible. Do not relax the task-stated
tolerance to a looser local or tool default, average away a failing mesh, or
sample a subset of meshes. A spec that states only a looser local tolerance has
no admissible acceptance threshold and is unverifiable.

## 6. Complete part-and-link enumeration

Before packaging, enumerate every mesh the task names as a deliverable:

1. List every part file and every link file, including meshes nested in
   subdirectories such as `wheel_structure/outer_rim.obj` and
   `link_structure/outer_rim.obj`.
2. Compare the enumeration with the spec's deliverable entries and scene
   mapping. A declared part or link mesh with no geometry invariant is an
   incomplete inventory and blocks submission.
3. Run the validator over the complete artifact root, not one file at a time,
   so a missing or unmapped mesh is visible.
4. Require one `geometry` entry per mesh, each keyed by artifact path and mesh
   name, with observed distance, tolerance, provenance, and pass or fail.
5. Do not accept a part mesh's pass as evidence for its link mesh, or a link
   mesh that copies the part mesh as evidence for either. Each mesh is compared
   independently with the reconstructed source surface.

## 7. Placement versus shape attribution

For each failing mesh, report one attribution:

- `frame_or_placement`: after re-centering both surfaces on their own sample
  centroids, the symmetric mean comes within tolerance. The exported shape is
  consistent but translated, rotated, mirrored, or assigned to the wrong
  frame, unit, or scene transform.
- `transform`: the composed world transform differs from the source-derived
  transform, including a wrong parent chain, rotation, or scale rather than a
  pure translation.
- `assembly`: the mesh omits, duplicates, or substitutes a source primitive,
  so primitive membership is wrong even if one component resembles the source.
- `shape`: a surface difference remains after centering. The primitive
  dimensions, topology, tessellation, or part identity is wrong.

Report the mesh path, observed distance, task threshold, frame, and attribution
together. A placement failure points at the producing transform or frame rule;
a transform or assembly failure points at the parent chain, primitive
membership, or transform composition; a shape failure points at the primitive
dimensions or part selection. Repair the producing rule and re-export rather
than editing individual mesh files.

## 8. Failure report and exit behavior

Each compared mesh produces an entry with `deliverable`, `artifact_path`,
`mesh`, `source_geometry`, `source_scene_path`,
`evidence: independent_source_reconstruction`, `frame`, `units`, `derivation`,
`provenance`, `metric`, `tolerance` (the threshold), `observed_delta`,
`max_nearest`, `chamfer`, `displacement_class`, `centered_delta`, submitted
`counts`, optional `source_counts`, and `status` of `pass`, `fail`, or
`unverifiable`. A self-referential or under-provenanced mesh records
`evidence: unverifiable` and no distance.

A failed mesh adds a structured violation with `invariant_class:
geometry_conformance`, the mesh name in `locator`, `field: chamfer`,
`observed_delta`, `chamfer`, `max_nearest`, `displacement_class`, `deliverable`,
`artifact_path`, `source_scene_path`, `frame`, `units`, `derivation`, and the
task-stated tolerance in `expected`, and the attribution keyword in
`displacement_class`. Any out-of-tolerance mesh keeps the report at
`status: violations` and the process exit at `1`. Exit `0` only when every mesh
passes with recorded provenance and independence evidence.

## 9. Unverifiable conditions

Mark the invariant unverifiable, with a concrete reason, when provenance is
absent or malformed; its source path or units disagree with the declared scene;
it points at the export, a manifest, an intermediate mesh, or a producer-owned
reader or transform path; the independence evidence is absent, declares
`independent_of_exporter: false`, or shares the producer's primitive
decomposition, expected coordinates, or transform path; the source scene is
missing or unreadable; no primitives or a supported primitive type are
available; a named mesh has no source mapping; the mesh or source has no
measurable surface; or no task-stated `acceptance_tolerance` or frame
normalization can be derived.

An unverifiable geometry constraint blocks submission and exits `1`. Never
silently pass it because the producer's checks are clean, the counts match, or
the mesh opens.

## 10. Worked examples

From the skill directory:

```bash
python3 scripts/preflight.py scripts/fixtures/source-scene-box.json --spec scripts/fixtures/spec-geometry-clean.json
python3 scripts/preflight.py scripts/fixtures/source-scene-box.json --spec scripts/fixtures/spec-geometry-displaced.json
python3 scripts/preflight.py scripts/fixtures/source-scene-box.json --spec scripts/fixtures/spec-geometry-unverifiable.json
python3 scripts/preflight.py scripts/fixtures/source-scene-box.json --spec scripts/fixtures/spec-geometry-producer-source.json
python3 scripts/preflight.py scripts/fixtures/source-scene-box.json --spec scripts/fixtures/spec-geometry-manifest-source.json
```

`source-scene-box.json` declares a 1x2x3 meter box.
`mesh-box-equivalent.obj` has the same six faces with 24 separate vertices and
12 triangles; its vertex count differs from the 8-vertex source, yet the clean
spec exits `0`. `mesh-box-displaced.obj` has the same 24 vertices, 12 faces,
and zero degenerate faces but is translated 0.5 meter in x; its spec exits `1`
with Chamfer about `0.27`, `displacement_class: frame_or_placement`, and the
`0.01` tolerance. The missing-source spec exits `1` as unverifiable, the
producer-source spec exits `1` as unverifiable, and the manifest-source spec
exits `1` because the path names a producer manifest even without
`source_kind`.

The part-and-link regression uses two artifact roots:

```bash
python3 scripts/preflight.py --artifact-root scripts/fixtures/geometry-rig-equivalent --spec scripts/fixtures/spec-rig-clean.json
python3 scripts/preflight.py --artifact-root scripts/fixtures/geometry-rig-displaced --spec scripts/fixtures/spec-rig-displaced.json
python3 scripts/preflight.py --artifact-root scripts/fixtures/geometry-rig-equivalent --spec scripts/fixtures/spec-rig-no-provenance.json
```

The displaced root contains `wheel_structure/outer_rim.obj`,
`support_structure.obj`, and their link copies with identical vertices and
faces and a near-zero triangle delta, so the producer's self-comparison is
clean. Every mesh is nevertheless shifted 0.5 meter from
`source-scene-rig.json`. The run exits `1` with four `geometry_conformance`
violations for `wheel_structure/outer_rim`, `link_wheel_structure/outer_rim`,
`support_structure`, and `link_support_structure`; Chamfer is about `0.18` and
`0.4` against the `0.01` tolerance, each classified `frame_or_placement`, with
`export_path_checks` marked `structural_only`. The equivalent root exits `0`
with four passing entries carrying `frame: scene_root`, source units, and the
derivation step. The no-provenance root exits `1` with an unverifiable entry
per mesh even though the export is self-consistent. This pair proves that
matching part/link geometry cannot substitute for the independent source-scene
comparison.

## 11. Independent assembly and world-transform oracle

`scripts/independent_mesh_oracle.py` is the executable check for primitive
membership, node hierarchy, and composed world transforms. It reads the task
source scene directly, builds every primitive through a separate 4x4 matrix
path (`T * Rz * Ry * Rx * S` composed with the node parent chain), combines the
primitive ids named by each `mesh_to_source` entry, and compares the result with
the exported OBJ or GLB artifact. It never reads the exporter, its manifest, an
intermediate mesh, or the submitted artifact as the expectation.

```bash
python3 scripts/independent_mesh_oracle.py SOURCE_SCENE ARTIFACT --spec TOLERANCE_SPEC [--report REPORT.json]
```

The tolerance spec records `acceptance_tolerance` (the task-derived threshold;
legacy specs may fall back to `tolerance` only when it is absent), an
`independence_evidence` object with `reader`, `transform_path`, and
`independent_of_exporter: true`, optional `units` and `unit_conversion`, optional
`frame_transform`, `sample_count`, and a `mesh_to_source` mapping from artifact
path or mesh name to one primitive id or a list of ids. With a directory
artifact, keys are relative paths; with a single GLB, keys are mesh names. Every
source primitive must be mapped and every exported mesh must have a mapping.
An absent task threshold or missing/self-referential independence evidence is
reported as `unverifiable`, never guessed. `status: clean` and exit `0` require
all meshes to pass; any violation or unverifiable constraint keeps
`status: violations` and exit `1`.

Each mesh entry reports expected and observed `bounds`, `centroid`,
`triangle_count`, `triangle_delta`, `observed_delta`, and per-primitive status.
A violation carries `code`, the affected `mesh`, `artifact_path`, `primitive`,
`expected`, `observed`, `tolerance`, and a `transform` object with expected and
observed centroid and bounds, `translation_delta`, and `size_ratio`.

The code distinguishes these near misses:

- `primitive_omission`: a mapped source primitive has no exported counterpart.
- `primitive_duplication`: more than one exported component has the primitive's
  expected placement and shape.
- `mis_parented`: the exported component matches the primitive's local surface
  but not its composed world transform, so a node parent was not applied.
- `transform_translation`, `transform_rotation`, `transform_scale`, or
  `transform_composite`: the component exists but its placement or shape differs
  from the source-derived world transform.

Worked fixtures live under `scripts/fixtures/mesh-oracle/`:

```bash
python3 scripts/independent_mesh_oracle.py scripts/fixtures/mesh-oracle/source-scene.json scripts/fixtures/mesh-oracle/clean --spec scripts/fixtures/mesh-oracle/spec-oracle.json
python3 scripts/independent_mesh_oracle.py scripts/fixtures/mesh-oracle/source-scene.json scripts/fixtures/mesh-oracle/near-miss --spec scripts/fixtures/mesh-oracle/spec-oracle.json
```

The source scene has a root, turret, and arm node chain and four primitives. The
clean root exits `0` with six passing meshes, including a two-primitive assembly
and a duplicated export that is expected to contain one pedestal. The near-miss
root exits `1` with `transform_scale`, `transform_translation`, `mis_parented`,
`transform_rotation`, `primitive_omission`, and `primitive_duplication`
violations. A run that accepts the near miss because the exporter's local check
or a count comparison is clean has failed the independence requirement.

## 12. Independence test and task-derived tolerance

Run this test before trusting any numeric pass:

1. Read the task statement or task-derived spec and record
   `acceptance_tolerance`. Do not infer it from the exporter, a tool default, or
   a looser local setting. When the task states no threshold, mark the invariant
   unverifiable and block packaging.
2. Require `provenance.reader` and `provenance.transform_path`, or an
   `independence_evidence` object with `independent_of_exporter: true` and both
   fields. The reader must parse the task source scene independently; the
   transform path must compose primitive and parent transforms independently.
3. Reject independence evidence that names the producer, exporter, submitted
   artifact, manifest, intermediate mesh, or the same primitive, coordinate, or
   transform path. A numerically matching self-referential reconstruction is
   still unverifiable.
4. Compare every exported part and link mesh with that independent derivation.
   On failure, emit one record per mesh with `artifact_path`, `mesh`,
   `observed_delta`, `chamfer`, `tolerance`, and `displacement_class` set to
   `frame_or_placement`, `transform`, `assembly`, or `shape`.
5. Exit `1` on any violation or unverifiable constraint. Exit `0` only when
   every mesh is below the task-derived threshold and its independence evidence
   is present.

Worked regressions:

```bash
python3 scripts/preflight.py --artifact-root scripts/fixtures/geometry-oracle-self-referential --spec scripts/fixtures/geometry-oracle-self-referential/spec.json
python3 scripts/preflight.py --artifact-root scripts/fixtures/geometry-tolerance-near-miss --spec scripts/fixtures/geometry-tolerance-near-miss/spec.json
```

The self-referential root is displaced from the task source yet locally
consistent with the producer's own primitive reconstruction; it exits `1` as
unverifiable and never clean. The tolerance near-miss displaces the crate by
`0.03` meter; its looser local `0.05` tolerance would pass, but the task-stated
`0.01` `acceptance_tolerance` produces a `geometry_conformance` violation with
observed Chamfer about `0.016` and `displacement_class: frame_or_placement`.
