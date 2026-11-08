# Verification playbook

Load this file when replaying fixtures, interpreting a preflight report, or
building a new regression case. Run commands from the skill directory.

## Contents

1. Clean baselines and pivot fixtures
2. Deriving allowed category sets
3. One failure fixture per invariant class
4. Companion deliverables and semantic encodings
5. Reading companion and field-encoding reports
6. Geometry and mesh equivalence, including source-scene reconstruction and part/link independence
7. Completion evidence

## Clean baseline

```bash
python3 scripts/preflight.py scripts/fixtures/artifact-clean.json --spec scripts/fixtures/spec-clean.json
```

Expect exit `0`, `status: clean`, and zero violations. The clean spec covers
equality, a converted numeric range, and calibration.

## Clean pivot baseline

```bash
python3 scripts/preflight.py scripts/fixtures/artifact-pivot-clean.json --spec scripts/fixtures/spec-pivot-clean.json
```

Expect exit `0`, `status: clean`, one passing `structural` invariant over the
pivot objects, and one passing `domain_membership` invariant over the row
categories. This is the near-miss baseline for a workbook: plausible structure
and in-domain labels pass, while any wrong row, aggregation, cache, or category
field must fail.

## Pivot failure fixtures

```bash
python3 scripts/preflight.py scripts/fixtures/artifact-pivot-wrong-aggregation.json --spec scripts/fixtures/spec-pivot-structural.json
python3 scripts/preflight.py scripts/fixtures/artifact-pivot-wrong-row.json --spec scripts/fixtures/spec-pivot-structural.json
python3 scripts/preflight.py scripts/fixtures/artifact-pivot-missing-cache.json --spec scripts/fixtures/spec-pivot-structural.json
python3 scripts/preflight.py scripts/fixtures/artifact-pivot-domain-violation.json --spec scripts/fixtures/spec-pivot-domain.json
```

Each run must exit `1`. The first three must report `invariant_class:
structural` for an unlisted aggregation mode, an empty required row list, and a
cache that omits a referenced value field respectively. The last must report
`invariant_class: domain_membership` for the out-of-domain region label and must
name the row locator, field, observed label, and allowed set.

## Deriving allowed category sets

Take the allowed set from task-visible source material: the task statement, an
enumeration in the prompt, or a reference table the task declares authoritative.
Record that source in `expected_source`. Do not derive the set by scanning the
submitted artifact, a prior output, or a pivot's own cache, because that would
make any label self-validating. When the task states no allowed set, record the
domain rule as unverifiable and block submission.

## One failure fixture per invariant class

```bash
python3 scripts/preflight.py scripts/fixtures/artifact-equality-mismatch.json --spec scripts/fixtures/spec-equality.json
python3 scripts/preflight.py scripts/fixtures/artifact-range-violation.json --spec scripts/fixtures/spec-range.json
python3 scripts/preflight.py scripts/fixtures/artifact-calibration-violation.json --spec scripts/fixtures/spec-calibration.json
python3 scripts/preflight.py scripts/fixtures/artifact-recompute-delta.json --spec scripts/fixtures/spec-recompute.json
python3 scripts/preflight.py scripts/fixtures/artifact-null-sentinel-violation.json --spec scripts/fixtures/spec-null-sentinel.json
```

Each run must exit `1` and classify its violation with the matching
`invariant_class`.

## Companion deliverables

```bash
python3 scripts/preflight.py scripts/fixtures/artifact-graph-typed.json --spec scripts/fixtures/spec-companion-clean.json
python3 scripts/preflight.py scripts/fixtures/artifact-graph-typed.json --spec scripts/fixtures/spec-companion-misencoded.json
python3 scripts/preflight.py scripts/fixtures/artifact-graph-typed.json --spec scripts/fixtures/spec-companion-missing.json
```

The first run must exit `0` with a passing `companion_artifact` invariant: the
DOT companion maps start to `oval`, task to `box`, and terminal to
`doublecircle`. The second run must exit `1` even though its `graph_structure`
invariant passes, because the terminal node `End` parses but carries
`shape=box`; the violation must name the deliverable, locator `End`, field
`shape`, observed `box`, and expected `doublecircle`. The third run must exit
`1` for the absent declared file rather than skipping the companion.

## Deriving a semantic-encoding contract

Build the deliverable inventory from the task text before extracting any
mapping: the primary data artifact, each graph or workbook, and every companion
visualization or rendered representation. Require one constraint group per named
deliverable. A task that names a JSON graph and its DOT rendering needs both a
`graph_structure` group and a `companion_artifact` group.

For a visualization, take the node-type-to-shape or node-type-to-style mapping
from task-visible conventions: a legend specification, an explicit shape rule
in the prompt, or an authoritative style table. Record each type and its
required encoding in the spec. Do not scan the rendered file for the shapes it
happens to use, because that makes any encoding self-validating, and do not
copy a producer's mapping table as the expected contract. When the task shows a
companion but states no convention, record the encoding as unverifiable and
block submission.

Parse the companion before judging it. File existence, a nonzero byte count, a
successful parse, or a correct primary graph does not show that a semantic
distinction is encoded. Check each declared source node against the companion
node and its declared attribute, and report the deliverable, locator, observed
encoding, and expected encoding. For SVG, read element attributes by `id` or
`data-node-id`; for DOT, read node-statement attributes; for JSON, read the
declared node array and attribute path.

## Reading a companion_artifact report

Check that a violation contains `deliverable`, `locator`, `field`, `observed`,
`expected`, and `diagnosis`, and that the report status is `violations` rather
than `clean`. A green structured-data or graph preflight is incomplete
whenever another named deliverable exists. Repair the rendering rule or
template that maps the node type to its shape or style, regenerate the
companion, and rerun the same spec.

If a rendering expectation cannot be checked from bounded task-visible
evidence, report it as unverifiable instead of passing it silently. Do not use
oracle-supplied expected shapes, benchmark-specific constants, or a hard-coded
mapping in the validator.

## Worked near-miss examples

- `artifact-structurally-valid-calibration-fail.json` with
  `spec-calibration.json`: the document parses and has the expected record
  shape, yet confidence separation is below the threshold. This proves a
  structural pass is not conformance.
- `artifact-recompute-delta.json` with `spec-recompute.json`: record `r2`
  differs from `scripts/fixtures/oracle_duration.py` by a small delta, so the
  report shows the observed value, the independently recomputed value, and
  `observed_delta`. A self-referential spec
  (`spec-recompute-self-reference.json`) must report unverifiable instead.
- `artifact-null-sentinel-violation.json` with `spec-null-sentinel.json`: the
  spec declares `po_number` nullable and forbids `PO-INVALID`. Record `po-1`
  encodes the missing value as JSON null and passes; record `po-3` encodes it
  as `PO-INVALID`, so the run exits `1` with a `field_encoding` violation
  naming `po-3`, `po_number`, the observed sentinel, and the required null
  encoding. This is the case a record-level diff against a
  producer-derived expected set misses.

## Reading a field_encoding report

Check that the violation contains `locator`, `field`, `observed`, `expected`,
and `diagnosis`, and that `status` is `violations` rather than `clean`. Fix the
producing normalization rule, not the single record, rebuild the artifact, and
rerun the same spec. A second run must show zero `field_encoding` violations,
including every contract-declared nullable field encoded as JSON null.

When the contract does not state an encoding rule, do not invent one. Record
the field as unverifiable with the missing rule as the reason.

## Geometry and mesh equivalence

The expected surface may be compared only after the provenance gate passes.
Before running a geometry case, confirm the spec's `provenance` records the
source-scene path, `frame` (`scene_root` or `part_local`), source units, and the
derivation step that rebuilt the surface. Confirm the record does not point at
the submitted export, a manifest, an intermediate mesh, or a producer-owned
reader or transform path. If any of those checks fail, the expected report is
`unverifiable` with exit `1`, not a distance comparison.

```bash
python3 scripts/preflight.py scripts/fixtures/source-scene-box.json --spec scripts/fixtures/spec-geometry-clean.json
python3 scripts/preflight.py scripts/fixtures/source-scene-box.json --spec scripts/fixtures/spec-geometry-displaced.json
python3 scripts/preflight.py scripts/fixtures/source-scene-box.json --spec scripts/fixtures/spec-geometry-unverifiable.json
python3 scripts/preflight.py scripts/fixtures/source-scene-box.json --spec scripts/fixtures/spec-geometry-producer-source.json
```

The first run must exit `0` with a passing `geometry_conformance` invariant. The
fixture source scene declares a 1x2x3 meter box; the equivalent mesh has the same
six faces with 24 independent vertices and 12 triangles, so its counts differ
from the reconstructed 8-vertex box while the surface agrees. Its entry must
record `provenance.source_scene_path`, `frame: scene_root`, `units`, and
`derivation`, and a Chamfer distance within tolerance. The second run uses an
identically structured mesh translated by 0.5 meter, so counts, face count, and
degenerate-face count all look valid but the `geometry` entry must report a
per-mesh `observed_delta` of `0.5`, a Chamfer distance above the 0.01 tolerance,
`displacement_class: frame_or_placement`, and the process must exit `1`. The
third run points at a missing source scene and must report an unverifiable
constraint with exit `1`, never a clean pass. The fourth marks the expected
surface as producer output and must also exit `1` with an unverifiable
provenance reason.

To read a geometry report, check the top-level `geometry` array for one entry per
mesh with `deliverable`, `artifact_path`, `mesh`, `source_geometry`,
`source_scene_path`, `frame`, `units`, `derivation`, `provenance`, `evidence`,
`metric`, `tolerance`, `observed_delta`, `chamfer`, `displacement_class`,
`centered_delta`, `counts`, and `status`, then read each failure in the
`violations` array. A violation must name the deliverable, mesh locator, observed
Chamfer distance, `max_nearest` delta, source scene, artifact path, provenance
frame, displacement class, and the task-stated tolerance. `frame_or_placement`
means re-centering both surfaces brings the symmetric mean within tolerance;
`shape` means a real surface difference remains. Repair the transform, unit
conversion, frame choice, or export rule that produced the deviation, rebuild
the mesh, and replay the complete preflight; do not hand-edit the exported file.

Source-scene reconstruction procedure for a part-and-link export:

1. Anchor the run with `--artifact-root <dir>` and record the artifact root, the
   task-derived source-scene spec, and every expected mesh's provenance in the
   report.
2. Read the source scene's primitive type, dimensions, position, rotation, and
   scale directly from the task source. Record whether the expected surface is
   reconstructed in `scene_root` or `part_local` frame and the units used.
3. Parse the OBJ vertices and faces for every part and link mesh separately.
   Copying a part OBJ to a link path, or comparing the link with the part,
   establishes only that the two files agree with each other.
4. Rebuild the expected surface from the source scene's primitives and
   transforms in the recorded frame. Do not read a part, link, manifest,
   intermediate artifact, producer parser, or expected mesh produced by the
   exporter. Derive `part_local` surfaces with scene-root placement removed.
5. Compute the symmetric surface/Chamfer distance per mesh. Record pass or fail
   with the reconstruction path, provenance, stated tolerance, measured
   distance, and displacement class.
6. Run the independent assembly and world-transform oracle on the clean and
   near-miss roots, then the part/link regression pair:

```bash
python3 scripts/independent_mesh_oracle.py scripts/fixtures/mesh-oracle/source-scene.json scripts/fixtures/mesh-oracle/clean --spec scripts/fixtures/mesh-oracle/spec-oracle.json
python3 scripts/independent_mesh_oracle.py scripts/fixtures/mesh-oracle/source-scene.json scripts/fixtures/mesh-oracle/near-miss --spec scripts/fixtures/mesh-oracle/spec-oracle.json
python3 scripts/preflight.py --artifact-root scripts/fixtures/geometry-rig-equivalent --spec scripts/fixtures/spec-rig-clean.json
python3 scripts/preflight.py --artifact-root scripts/fixtures/geometry-rig-displaced --spec scripts/fixtures/spec-rig-displaced.json
python3 scripts/preflight.py --artifact-root scripts/fixtures/geometry-rig-equivalent --spec scripts/fixtures/spec-rig-no-provenance.json
```

The oracle clean root must exit `0` with six passing meshes after composing the
root, turret, and arm node chain. The near-miss root must exit `1` with
`transform_scale`, `transform_translation`, `mis_parented`, `transform_rotation`,
`primitive_omission`, and `primitive_duplication` violations, each naming its
mesh and reporting expected and observed placement and shape; a local
parse-and-export check that compares the exporter with itself must not change
that result. The equivalent root must exit `0` with four passing entries that
carry provenance frame, units, and derivation. The displaced root has matching
part/link vertex and face counts and a near-zero triangle delta but every mesh
is 0.5 meter from the source; it must exit `1` with four `geometry_conformance`
violations naming each mesh, its Chamfer distance, and its provenance frame, and
`export_path_checks` entries marked `structural_only`. The no-provenance spec
must exit `1` with four unverifiable entries, even though the same export would
otherwise be a clean surface: a clean comparison whose provenance is missing
cannot be accepted. A run that accepts the displaced root because the links
match the parts has failed the independence requirement.

When no independent source reconstruction is available, mark the constraint
unverifiable with the missing scene, provenance, mapping, tolerance, or frame
convention as the reason, keep the nonzero exit, and block submission. Never
derive the expectation from the exporter's own output to turn the run green.

Do not derive the tolerance, unit factor, frame convention, provenance, or
mesh-to-source mapping from the submitted mesh. Take them from the task
statement or a task-visible source-scene constraint. When the source scene,
primitive parameters, provenance record, mapping, tolerance, or frame convention
is absent, record the invariant as unverifiable rather than accepting the mesh
because its counts look right.

## Completion evidence

Keep the final command, per-invariant counts, per-mesh geometry Chamfer distances
and displacement classes, recorded provenance, exit status, and the full report
with the submission. Do not claim a clean pass from a structural check alone, and
do not claim a clean pass while a named companion deliverable is absent,
unparseable, or untested, or while a named mesh lacks recorded independent
provenance, an independently derivable source shape, or remains outside the
stated tolerance.
