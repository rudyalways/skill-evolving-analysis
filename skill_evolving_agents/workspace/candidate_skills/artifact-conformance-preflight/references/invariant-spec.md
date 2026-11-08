# Constraint spec reference

Load this file when writing or reviewing the task-derived JSON spec that
`scripts/preflight.py` consumes. The spec is data; the validator hard-codes no
expected values, unit tables, nullable fields, sentinels, pivot structures, or
category domains.

## Contents

1. Spec shape
2. Invariant adapters
3. Field encoding rules
4. Structural object rules
5. Allowed-domain rules
6. Independent recompute oracles
7. Recording unverifiable constraints
8. Graph structure rules
9. Companion-artifact rules
10. Geometry-conformance rules, including the independence gate and provenance

## 1. Spec shape

```json
{
  "spec_revision": "task-rev-1",
  "records_path": "records",
  "invariants": [
    {
      "id": "eq-total",
      "class": "equality",
      "field": "computed_total",
      "expected_field": "stated_total",
      "expected_source": "task statement, totals table",
      "record_locator": "id"
    },
    {
      "id": "range-duration",
      "class": "numeric_range",
      "field": "duration_minutes",
      "min": 60,
      "max": 3600,
      "unit": {"from": "minutes", "to": "seconds", "factor": 60, "offset": 0},
      "expected_source": "task statement, duration bound in seconds",
      "record_locator": "id"
    },
    {
      "id": "confidence-separation",
      "class": "calibration",
      "confidence": "confidence",
      "group_by": "evidence_strength",
      "order": ["weak", "medium", "strong"],
      "min_separation": 0.1,
      "expected_source": "task statement, calibration rule",
      "record_locator": "id"
    },
    {
      "id": "encode-po-number",
      "class": "field_encoding",
      "field": "po_number",
      "nullable": ["po_number"],
      "forbidden_sentinels": ["PO-INVALID", "N/A", "TBD", ""],
      "expected_source": "task statement, PO number is nullable and must be null when absent",
      "record_locator": "id"
    },
    {
      "id": "recompute-distance",
      "class": "independent_recompute",
      "field": "distance_km",
      "oracle_path": "oracles/route_distance.py",
      "tolerance": 0.01,
      "expected_source": "task statement, distance equals summed segment lengths",
      "record_locator": "id"
    },
    {
      "id": "pivot-object-shape",
      "class": "structural",
      "objects_path": "pivots",
      "record_locator": "name",
      "required_fields": ["row_fields", "column_fields", "value_fields", "aggregation", "cache_fields"],
      "non_empty_list_fields": ["row_fields", "column_fields", "value_fields"],
      "aggregation_field": "aggregation",
      "allowed_aggregations": ["sum", "count", "average"],
      "cache_field": "cache_fields",
      "cache_sources": ["row_fields", "column_fields", "value_fields"],
      "expected_source": "task statement, pivot object contract"
    },
    {
      "id": "region-domain",
      "class": "domain_membership",
      "objects_path": "rows",
      "field": "region",
      "allowed": ["North", "South", "East", "West"],
      "case_sensitive": true,
      "allow_null": false,
      "expected_source": "task statement, region enumeration",
      "record_locator": "id"
    },
    {
      "id": "flow-viz-shapes",
      "class": "companion_artifact",
      "deliverable_path": "flow.dot",
      "format": "dot",
      "source_nodes_path": "graph.nodes",
      "source_id_field": "id",
      "source_type_field": "type",
      "node_id_attribute": "id",
      "encoding": {
        "attribute": "shape",
        "mapping": {"start": "oval", "task": "box", "terminal": "doublecircle"}
      },
      "expected_source": "task statement, node types start=oval, task=box, terminal=doublecircle in the rendered flow diagram"
    },
    {
      "id": "graph-reachability",
      "class": "graph_structure",
      "objects_path": "graph",
      "nodes_path": "nodes",
      "edges_path": "edges",
      "node_id_field": "id",
      "edge_source_field": "source",
      "edge_target_field": "target",
      "entry_node": "Start",
      "terminal_nodes": ["End"],
      "expected_source": "task statement, every node reachable from Start and every edge target a node except the declared terminal End"
    }
  ]
}
```

For `records_path`, use a top-level key such as `records`; omit it when the
artifact root is already an array or when reading JSON Lines. For a literal
equality instead of a paired field, use `expected` and still supply
`expected_source`. A unit conversion is a linear `factor` plus optional
`offset` from the spec. A `structural` or `domain_membership` invariant may set
`objects_path` to select a different top-level collection, such as `pivots` or
`rows`; omit it to use the records already selected by `records_path`. The
category names and field names in these examples are illustrative only; every
contract for a real artifact is read from that task's visible statement.

## 2. Invariant adapters

- `equality` compares a field with a literal `expected` value or a same-record
  `expected_field`. Numeric comparisons honor `tolerance`.
- `numeric_range` applies the optional linear unit conversion and then checks
  `min` and `max`; at least one bound is required.
- `calibration` groups records by `group_by`, averages `confidence`, and checks
  that every adjacent pair in `order` has at least `min_separation`.
- `independent_recompute` checks a derived numeric field against a separately
  implemented `oracle_path` module or a non-empty `metamorphic` relation list.
- `field_encoding` checks per-field nullability and forbidden sentinel values
  declared by the contract.
- `structural` checks required object fields, non-empty field lists, the
  aggregation mode, and pivot cache presence for each declared artifact object.
- `domain_membership` checks each categorical value against the allowed set the
  task declares for its field.
- `graph_structure` checks that every node is reachable from the declared entry
  node and that every edge target exists unless it is a declared terminal node.
- `companion_artifact` checks that each declared companion deliverable exists,
  parses, and encodes every declared semantic distinction for the nodes it
  represents; it never passes on existence, size, or successful parsing alone.
- `unverifiable` records a constraint that cannot be traced or checked; supply
  a concrete `reason` and block submission.

Every non-unverifiable invariant needs a traceable `expected_source`.

## 3. Field encoding rules

Use `field_encoding` when the contract declares which fields may be null, which
must be non-null, and which literal strings are forbidden placeholders.

- `field` or `fields` lists the fields to inspect. A field is also inspected
  when it appears in `nullable`, `non_nullable`, or `require_present`.
- `nullable` lists fields where JSON null is the contract-declared encoding for
  a missing value. A placeholder or sentinel string in a nullable field is a
  violation even though it is not null.
- `non_nullable` lists fields that must carry a value; a null or absent value
  is a violation.
- `forbidden_sentinels` is a list of literal strings such as `PO-INVALID`,
  `N/A`, `TBD`, or `""`. Any inspected field holding one is a violation.
- `require_present` lists fields whose key must exist even when its value is
  null. Without it, an absent optional key passes.

A field_encoding violation reports `invariant_class: field_encoding`, the
record `locator`, the `field`, the `observed` value, the `expected` null or
non-sentinel rule, and a `diagnosis`. Repair the producing normalization rule
so declared missing values become JSON null everywhere, then rebuild.

Do not infer a nullable field or a sentinel list when the task is silent; mark
the invariant `unverifiable` with the missing rule as the reason.

## 4. Structural object rules

Use `structural` when the deliverable is a composite artifact whose objects,
such as pivot tables, must expose a specific shape. The rule applies to the
collection named by `objects_path`, or to the `records_path` collection when
`objects_path` is omitted.

- `required_fields` lists keys that must exist and must not be null.
- `non_empty_list_fields` lists keys whose value must be a non-empty list of
  non-empty strings, typically `row_fields`, `column_fields`, and
  `value_fields`.
- `aggregation_field` names the aggregation key, and `allowed_aggregations`
  lists the task-declared modes. The observed mode must be one of them; set
  `case_sensitive: false` only when the task treats modes case-insensitively.
- `cache_field` names the pivot cache list. `required_cache_fields` lists
  fields the task requires in that cache. `cache_sources` lists field-list
  keys, such as `row_fields` and `value_fields`, whose members must all appear
  in the cache.

Every structural violation reports `invariant_class: structural`, the object
`locator`, the `field`, the `observed` value, the `expected` requirement, and a
`diagnosis`. Empty or missing row/column/value lists, an unlisted aggregation
mode, and a cache that omits a referenced field are all violations, not
warnings. Do not derive these requirements from the producer's output.

## 5. Allowed-domain rules

Use `domain_membership` for each categorical field whose allowed set the task
states. Supply the set from the task-visible source material, never from the
artifact being checked.

- `field` or `fields` names the categorical paths to inspect.
- `allowed` is the shared allowed set. `allowed_by_field` maps a field to its
  own set and takes precedence for that field.
- `case_sensitive` defaults to `true`; set it to `false` only when the task
  treats labels case-insensitively.
- `allow_null` defaults to `false`; when true, a JSON null passes, while a
  missing key or an out-of-domain string still fails.

A violation reports the object or row `locator`, the `field`, the observed
label, the allowed set, and a diagnosis. Report every out-of-domain label; do
not collapse a category column to a single aggregate failure. If the task does
not state the allowed set, mark the rule unverifiable rather than copying the
categories that happen to appear in the artifact.

## 6. Independent recompute oracles

An oracle module is any task-derived Python file exposing
`recompute(record)`; its path resolves relative to the spec file. A
`metamorphic` entry is an object with `kind` set to `positive`, `bounds`,
`representation`, or `round_trip`, plus that kind's parameters.

Never satisfy `independent_recompute` with `expected_field` equal to the
submitted field, a producer path, or a copied output. An expected set produced
by the same transformation as the artifact is not independent evidence, even
when it is stored in a separate file. The validator reports a self-referential
spec as unverifiable.

## 7. Recording unverifiable constraints

Use class `unverifiable`, or leave a required input absent, when provenance,
an independent oracle, a metamorphic relation, or an explicit encoding rule is
missing. Include a concrete `reason`. Unverifiable constraints keep the report
at `status: violations` and exit code `1`; they are never silently dropped.

## 8. Graph structure rules

Use `graph_structure` when the deliverable is a directed graph or network and
the task states an entry node, a node set, and directed edges. The rule is
checked against the complete graph object, not a rendered image, a sample, or a
partial adjacency list.

Required spec fields:

- `entry_node` is the declared entry node id. A graph has exactly one entry
  node for this check; derive it from the task-visible statement.
- `nodes_path` and `edges_path` are dotted paths to the node and edge arrays
  inside the selected graph object. They default to `nodes` and `edges`.
- `node_id_field`, `edge_source_field`, and `edge_target_field` name the id,
  source, and target keys. They default to `id`, `source`, and `target`.
- `objects_path` optionally selects the graph object in the artifact document,
  such as `graph`; omit it when the artifact root is the graph object.
- `terminal_nodes` is the optional declared terminal-node exception, supplied
  from the task-visible contract. Multiple inbound paths into a terminal node
  are legitimate and are never flagged. The exception waives only the
  edge-target existence rule, not node reachability.

Reachability algorithm: build the directed adjacency map from every edge whose
source is a node, start a breadth-first traversal at `entry_node`, and collect
the reachable set. Compare that set with the node-id set; every node must be
reachable. Independently, for every edge, require its target to be in the node
set unless it is in `terminal_nodes`. This is deterministic and depends only on
the spec and the complete graph.

Violation locators:

- An unreachable node reports `locator` and `observed` as the node id,
  `field: "node"`, `expected` as reachable from the declared entry node, and a
  diagnosis naming that node id and entry node.
- A dangling target reports `locator` as the source node id, `field` as the
  target field, `observed` as the missing target, `expected` as an existing
  node or declared terminal node, and a diagnosis naming the source and target.
- A missing entry node reports `locator` as the declared entry id, `field` as
  the node-id field, and a diagnosis stating that reachability cannot start.

Mark the invariant `unverifiable` when the graph object, node collection, edge
collection, node ids, or edge endpoints are absent or not structurally exposed;
do not manufacture a pass or silently skip the check. Do not hard-code node
names, graph sizes, or expected reachable sets: the entry node, terminal
exception, paths, and endpoint fields are data from the task-derived spec.

## 9. Companion-artifact rules

Use `companion_artifact` for each deliverable the task names beside the primary
data artifact, such as a JSON graph and its DOT, HTML, SVG, or other rendered
representation. Enumerate deliverables from the task text and spec first; one
invariant per declared deliverable, including a separate invariant for each
rendering. Never treat the primary artifact's structural or graph pass as
evidence about a companion.

Required spec fields:

- `deliverable_path` is the declared path to the companion. A relative path
  resolves against the spec file's directory. When the task names the
  deliverable but the file is absent, the validator reports a violation; do not
  omit the invariant because the file is missing.
- `format` is `dot`, `svg`, `html`, `json`, or `auto`. `auto` selects by extension.
  `dot` parses portable node statements of the form `id [key=value, ...]` and
  ignores edge and graph-default statements. `svg` parses XML elements carrying
  `id` or `data-node-id` and compares their attributes. `html` parses
  elements carrying `id` or `data-node-id` and reads their attributes.
  `json` parses a node
  array at `nodes_path` (default `nodes`) keyed by `id_field` (default `id`).
- `source_nodes_path` selects the node collection in the primary artifact whose
  semantic types drive the check, for example `graph.nodes`.
- `source_id_field` and `source_type_field` name the node id and semantic type
  keys in the primary artifact. They default to `id` and `type`.
- `node_id_attribute` names the companion attribute that carries the source
  node id when it differs from the lookup key. DOT uses the node identifier and
  usually needs no separate attribute.
- `encoding` or `encodings` declares the semantic-encoding contract. Each entry
  has an `attribute` such as `shape`, `style`, `class`, or `annotation`, and a
  `mapping` from each task-declared node type or semantic category to the value
  that the rendering must carry. Use multiple entries when the task fixes more
  than one distinction, such as shape and fill color.
- `expected_source` records where the mapping came from, such as a legend rule,
  a prompt-stated convention, or an authoritative style table.

The validator loads the complete primary document, resolves each source node
and its type, requires a corresponding companion node, and compares the declared
attribute with the mapping value. It reports a violation when:

- the declared path is absent, unreadable, or unparseable;
- the companion parses but exposes no nodes;
- a source node has no companion counterpart;
- the encoding attribute is absent, or differs from the mapped value;
- the source node has no type, so its encoding cannot be checked.

When a task-declared node type has no mapping entry, or the companion format
does not expose the needed attribute, record the invariant as unverifiable and
block submission rather than accepting the rendering. Do not derive the mapping
by inspecting the companion, and do not hard-code shapes, colors, node names, or
file paths in the validator; they are data in the spec.

Violation locators:

- An absent, unreadable, unparseable, or node-less companion reports
  `deliverable` and `locator` as the declared path, `field` as
  `deliverable_path` or `nodes`, and `observed` as `absent`, `unreadable`,
  `unparseable`, or `no node declarations`.
- A missing node reports `deliverable`, the source node id as `locator`,
  `field` as the id attribute, `observed` as `absent`, and the expected presence
  in the companion.
- A misencoded node reports `deliverable`, the source node id as `locator`,
  `field` as the encoding attribute, the observed value, and the expected value
  qualified by the node type.

A rendering expectation that cannot be checked from bounded task-visible
evidence is `unverifiable`, not a silent pass and not a fabricated pass.

## 10. Geometry-conformance rules

Use `geometry_conformance` for each exported mesh or geometric artifact that
acceptance must compare with a task-visible Three.js source scene. Counts alone
never establish this invariant: a mesh with the right vertex, face, normal, and
degenerate-face counts can still be displaced, rotated, or scaled away from the
source-defined shape. Identical vertex or face counts, near-zero triangle
deltas, link meshes that mirror their part meshes, `exact_union=True`, file or
mesh counts, and an inline `ALL CHECKS PASSED` report are export-path
self-consistency. They prove only that the exporter is internally consistent and
are structural-only evidence; they never establish geometric conformance.

The expected surface must be reconstructed from the source scene's primitive
parameters, node hierarchy, and composed world transforms through a path
separate from the producer. `scripts/independent_mesh_oracle.py` performs that
recomputation and rejects omitted, duplicated, mis-parented, translated,
rotated, or scaled primitives. An expected
mesh loaded from the exporter's output, a stored expected mesh, a part or link
mesh, or any path the producer also writes is self-referential and must be
marked unverifiable rather than accepted.

Read `references/mesh-geometry-conformance.md` for the mandatory gate, the
source-scene-to-surface derivation procedure, frame and unit conventions, the
full `geometry_conformance` spec schema, placement-versus-shape attribution,
tolerance comparison, unverifiable conditions, and the worked box and part/link
fixtures. That reference is the detailed contract for this invariant class.
