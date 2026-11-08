# Skill edit

Work edit-first. Inspect the named skill, its changelog, and directly affected
files, then begin writing within the first quarter of the session. Never install
dependencies or create an environment; the host verifier provisions runtime
dependencies. If a dependency is unavailable, complete the requested files and
run only syntax or already-available checks.

Apply an update, delete, merge, or split operation from the active goal. This
is the optimize agent's Generate state for existing skills. `skill-create`
applies only to create operations; its refusal for a non-create operation is
not a `no_change` decision when this skill applies.

## Context

Read the operation in the session block. The working directory contains only
the skill directories that operation names, each with its changelog beside it
as `<skill>.md`. Explore the skill directory and that changelog. Do not edit
the changelog, and do not undo an accepted prior change unless this goal
names that change. Do not read or write metadata; the runner does that.
Section and directory names follow `common/skill_format.json`. Write every
required section as a level-2 heading (`## Overview`). The verifier does not recognize `# Overview` and reports that
section missing. Frontmatter `name` is lowercase hyphen-case, matches the
directory, and is at most 64 characters. `description` has no angle brackets
and is at most 1024 characters. Allowed fields are name, description, license,
compatibility, allowed-tools, and metadata. Keep `SKILL.md` at most 500 lines,
with no TODO or EXAMPLE_ placeholder, no symbolic links, and no file over
10MB. Reference files stay one directory level deep. An update changes every
claimed section and leaves frontmatter, the preamble, and every unclaimed
section identical to the raw snapshot. When the operation includes
`description_goal`, change only the one-line frontmatter description in that
direction and preserve every other frontmatter field. Without that field,
frontmatter remains immutable. A claimed section must actually change.
Delete removes the skill directory. Merge and split keep the source snapshot
and remove only the sources the operation names.

When the operation's `references` goal says the source is oversized,
progressive-disclosure extraction is mandatory acceptance work. Move
conditional schemas, modes, long examples, and detailed check catalogs into
linked reference files until `SKILL.md` is at or below the stated hard token
cap. Adding or updating a reference while leaving the main file above that cap
is a failed edit.

## Workflow

Read the changelog file beside the skill, `<skill>.md`. The runner already
copied the source to `target/raw_skills/<skill>`. Do not copy it yourself.

- `update`: edit the skill directory in `workspace/`. Apply its section and directory
  goals and delete every concrete item in optional `remove`, while preserving
  unrelated useful content. When the update changes any `SKILL.md` section,
  preserve the existing `evals/evals.json` cases and add or revise a focused
  regression case for the active finding. Put its finding ID in
  `source_trace_ids` and validate the complete eval file. A directory-only
  maintenance update follows only the resource goals it was given.
- `delete`: remove its skill directory from `workspace/`.
- `merge`: write the combined skill named by `into.skill` in `workspace/`.
  The runner removes source directories other than that result. Union and
  reconcile every authored resource from every source: preserve nested paths,
  deduplicate equivalent files, and preserve all eval cases while rewriting
  their `skill_name` for the result when required by the schema. If two source
  files use the same path with different useful content, reconcile them or
  retain clearly namespaced copies; never silently overwrite one.
- `split`: write every result in `into` under `workspace/`. The runner removes
  the source unless one result keeps the same name.

Leave `<skill>.md` unchanged. Do not write metadata.

## Constraints

Important. Put `description` on the same line as `description:`. Do not write
`description: >` or `description: |`. The checker reads only that line, so `>`
is the description and the run fails before verification with "frontmatter
description contains angle brackets". When the goal says a first case and a
later restatement are each enough, do not write "all of the following are
true". A required section is `## Overview`; `# Overview` is reported missing.

Do not create an unrelated skill. Do not treat an update, delete, merge, or
split as `no_change` merely because `skill-create` does not apply. Do not skip
the raw snapshot. Do not verify or judge the edit in this stage.

A behavioral update is incomplete if it edits a `SKILL.md` section without a
corresponding focused eval delta. Do not replace the existing eval suite with
only the new case.

Keep regression fixtures and their concrete identifiers in `evals/` (and in
fixture resources when needed), not in the operational contract. Do not copy
fixture-specific part names, filenames, expected paths, numeric constants, or
benchmark vocabulary into frontmatter, workflow, verification, constraints,
output-format, or limitation prose. State the invariant generically there
(for example, exact equality between the source-derived and emitted name
sets), then let the focused eval carry the concrete positive and near-miss
values. A fixture path may be named only to show how to run that eval; its
internal expected names and values must remain outside `SKILL.md`.

For an execution skill with a deterministic bundled producer, make the
producer the default first action after the agent confirms the real source and
output arguments. The skill must say to execute the shipped producer before
writing a replacement, inspect its structured failure if it fails, permit only
a bounded repair/fallback sequence, and reserve enough budget to validate the
complete requested artifact set. A checker-only loop, repeated source
exploration, or ad-hoc reimplementation before trying the producer is not a
compliant repair. Add a focused eval that observes producer execution and
complete artifact-set delivery under a bounded call/time budget.

An inherited resource is part of the accepted source behavior. Preserve it by
default even when the original model-authored resource decision said `omit`;
the runner will have normalized such a decision to `use`. Delete inherited
files only when the operation has a concrete matching `remove` item. The
runner deterministically validates preservation after this stage.

Every positive resource-plan decision must result in at least one authored
file. Mention each non-eval resource by relative path in `SKILL.md`; an orphaned
script, reference, asset, or delegated prompt fails deterministic validation.
Python helpers must compile. Generated `agents/openai.yaml` does not satisfy an
`agents: use` decision because it is interface metadata, not a delegated prompt.

Treat the existing frontmatter description as a recall contract. Preserve
every existing capability trigger unless the Goal explicitly removes it, while
adding the requested trigger language. Concision is not permission to silently
drop an independent capability trigger.

When the Goal requests progressive disclosure, it is mandatory acceptance
work. Move substantial conditional knowledge, schemas, modes, and worked
examples into linked `references/` files and reduce `SKILL.md` below the stated
hard token cap. Adding references while leaving `SKILL.md` oversized is not a
compliant edit.

For a source-native Three.js producer, preserve the source mesh discretization:
export the actual `geometry.attributes.position` and `geometry.index` buffers
returned by the runtime scene (support indexed and non-indexed geometry), then
apply the composed world transform. For OBJ output, clone the geometry, call
`toNonIndexed()` when an index exists so face traversal is triangle-expanded,
and use Three.js `OBJExporter` (or byte-equivalent target-serializer semantics).
Serialize vertex coordinates with full round-trip numeric precision. Do not use
`toFixed`, printf-style fixed decimals, or another lossy coordinate formatter:
small rounding changes can alter canonical sort order and sparse geometric
sampling even when bounds, centroids, and dense nearest-neighbor distances look
correct. Include a high-resolution curved indexed fixture whose verification
compares the serialized coordinates under the consumer's ordering and sampling
behavior, not only through a tolerant nearest-neighbor check.
Never rebuild the submitted producer
surface from `geometry.parameters`; parameter retessellation changes seams,
caps, and vertex sampling even when bounds appear identical. An independent
checker may reconstruct geometry separately, but that reconstruction must not
replace native-buffer export in the producer.

## Stop condition

Stop after all requested edits and raw snapshots exist. A later verifier and
judge session handles pass/fail acceptance; retries are disabled.
