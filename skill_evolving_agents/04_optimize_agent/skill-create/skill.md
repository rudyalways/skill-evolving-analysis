# Skill create

Create a skill from the goal. This is the optimize agent, the Generate state. Select does not run here. The out-of-distribution note records a gap on this same branch.

## Context

A new skill is a `SKILL.md` plus, when needed, one child directory from `common/skill_format.json`: references, scripts, agents, assets, or evals. The core headings cover overview and purpose, when to use, when not to use, workflow, constraints and guardrails, verification, output format, and limitations. A state machine is optional for stateful workflows. It is written under `workspace/target/`. A skill may use a heading or directory outside that list. Put it on the goal as `other` or `ood`, with `heading` for a section and `name` for a directory, so the checker can compare that part.

## Constraints

Do not create a skill for behavior the model and harness already do well. Do not create a skill when the goal action is update, delete, merge, or split. Do not file an unknown capability under a nearby leaf to force a match.

## Workflow

Read `workspace/run/evolve-goal.json`. When an `action.ops` item has `op` create, read each item in `skills`: the skill name, its description, its labels, and the `sections` and `dirs` on that item. Those lists are only what this skill needs. Write those headings and directories. Add the skill under `target/to_be_improved_skills` and write those labels, each a capability path and a weight, into `target/to_be_improved_skills_metadata/metadata.json`. Hand an out-of-distribution gap to `ood-data-updater`.

## Applies when

The optimize loop has reached a create op, or Judge sent that op back to Generate.
