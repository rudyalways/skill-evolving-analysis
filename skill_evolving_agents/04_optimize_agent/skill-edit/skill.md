# Skill edit

Apply an update, delete, merge, or split operation from the active goal. This
is the optimize agent's Generate state for existing skills. `skill-create`
applies only to create operations; its refusal for a non-create operation is
not a `no_change` decision when this skill applies.

## Context

Read the single operation in `workspace/run/evolve-goal.json`. Read only the
source skills named by that operation under
`workspace/target/to_be_improved_skills`. Section and directory names follow
`common/skill_format.json`.

## Workflow

Before changing or removing any existing skill, copy its complete directory to
`workspace/target/raw_skills/<skill>`.

- `update`: edit every record in `skills`. Apply its section and directory
  goals and delete every concrete item in optional `remove`, while preserving
  unrelated useful content.
- `delete`: snapshot every record in `skills`, then remove its skill directory.
- `merge`: snapshot every source named in `skills`, write the combined skill
  named by `into.skill`, apply `into.remove`, and remove source directories
  other than that result.
- `split`: snapshot the source named by `skill`, write every result in `into`,
  apply each result's `remove`, and remove the source unless one result keeps
  the same name.

Write all results under `workspace/target/to_be_improved_skills`. Keep the
active goal and diagnosis unchanged.

## Constraints

Do not create an unrelated skill. Do not treat an update, delete, merge, or
split as `no_change` merely because `skill-create` does not apply. Do not skip
the raw snapshot. Do not verify or judge the edit in this stage.

## Stop condition

Stop after all requested edits and raw snapshots exist. A later verifier and
judge session handles acceptance or retry.
