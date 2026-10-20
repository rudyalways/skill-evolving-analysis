# Skill select

Match Label A to Label B and choose the targeted skills. This is step 5.1. It runs only when the goal action is update, merge, or split. Step 5.2 is the create branch and does not run here.

## Experience

Label A is the demand: improvement areas from the traces, the `type` paths in the diagnosis. Label B is the supply: each existing skill's `skill_types`, at least 3 labels with a weight. A targeted skill is one whose labels overlap Label A. A higher weight is a stronger match. Hold a choice on domain and skill name.

## Don't

Do not run for create or delete. Do not select a skill whose type is not in the capability tree. Do not select on a vague description alone. Do not change the harness.

## Must

Read Label A from `workspace/run/diagnosis.json`. The shape is `evolver_skills/step2-dignosis/diagnosis.example.json` and Label B from `workspace/target/to_be_improved_skills_metadata/metadata.json`. Run `skill_type_checker.py`. A path that is not a leaf moves to `unmatched_skill_types` and is not selected. Write the matched skills into `improve_skills` on the goal, and into the skill fields on the update, merge, and split ops.

## Applies when

The goal action is update, merge, or split, or Judge sent the run back to Select.
