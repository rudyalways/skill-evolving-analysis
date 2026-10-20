# Skill create

Create a skill from the goal. This is step 5.2.1, the Generate state. Step 5.1 is select and does not run here. Step 5.2.2 records an out-of-distribution gap on this same branch.

## Experience

A new skill is a `SKILL.md` plus, when needed, one child directory from `evolver_skills/reference-skill_format/skill_format.json`: references, scripts, agents, assets, or evals. The core headings are Overview, When to Use, Do not use this skill when, Workflow, Output Format, and Limitations. It is written under `workspace/target/`. A skill may use a heading or directory outside that list. Put it on the goal as `other` or `ood`, with `heading` for a section and `name` for a directory, so the checker can compare that part.

## Don't

Do not create a skill for behavior the model and harness already do well. Do not create a skill when the goal action is update, delete, merge, or split. Do not file an unknown capability under a nearby leaf to force a match.

## Must

Read `workspace/run/evolve-goal.json`. The shape is `evolver_skills/step4-goal-generator/evolve-goal.example.json`. When an `action.ops` item has `op` create, read each item in `skills`: the skill name, its description, its labels, and the `sections` and `dirs` on that item. Those lists are only what this skill needs. Write those headings and directories, not every name in the example. Add the skill under `target/to_be_improved_skills` and write those labels, each a capability path and a weight, into `target/to_be_improved_skills_metadata/metadata.json`. Hand an out-of-distribution gap to `step5.2.2-ood-data-updater`.

## Applies when

The goal says create, or Judge sent the run back to Generate.
