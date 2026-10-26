# Skill edit

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
section identical to the raw snapshot. A claimed section must actually change.
Delete removes the skill directory. Merge and split keep the source snapshot
and remove only the sources the operation names.

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

## Stop condition

Stop after all requested edits and raw snapshots exist. A later verifier and
judge session handles pass/fail acceptance; retries are disabled.
