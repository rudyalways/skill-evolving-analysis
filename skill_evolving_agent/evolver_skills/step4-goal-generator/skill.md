# Goal generator

Choose the action. This is step 4, the Goal state. Skill selection comes after, and only for some actions.

## Experience

The defect comes from the skill, not the harness. Improving the harness is out of scope. The action is create, update, delete, merge, split, or `<other>` when none of those fit. Create and delete do not match existing skills. Update, merge, and split do.

## Don't

Do not put easy experience that the model and harness already do well into a skill. Do not set `improve_harness` inside scope. Do not pick the target skills here. Do not fill `improve_skills` for create or delete. Do not copy every op, skill, section, or dir from the example. Do not add an `other` item unless the heading or directory is outside the closed list. Do not name the same skill in two actions.

## Must

Write `workspace/run/evolve-goal.json`. The shape is `evolve-goal.example.json` in this folder. Run `one_action.py` on that file. A skill name may appear in only one item of `action.ops`. On fail, the lines `problem`, `fix`, and `next` say which skill to remove from the extra action. `next` is Goal. Fill `goal`, `reasoning`, `plan`, `action`, and `feedback_to`. The example shows each object shape once, including `other`. A real goal keeps only the ops and list items that apply. `skills`, `sections`, `dirs`, `labels`, and `into` can be any length. Omit `dirs` when no directory changes. Omit a section that this change does not touch.

Each item in `action.ops` is an object. The five op names are fixed: `create`, `update`, `delete`, `merge`, `split`. Use `<other>` only when the action is not one of those. Each op has its own parameters. `create` is a list of new skills, each with a description, its sections, its dirs, and at least 3 labels. A label is a `skill_capabilites` path and a weight. The core sections are overview, when_to_use, do_not_use, workflow, output, and limitations. `update` is a list of existing skills, each with a goal, a facet, `sections`, and `dirs`. Each section is `section` and `goal`. Each dir is `dir` and `goal`. Names come from `evolver_skills/reference-skill_format/skill_format.json`. `other` and `ood` name a heading or directory that is not one of those closed names. An other section also has `heading`. An other dir also has `name`. `delete` is a list of skills, each with a reason. `merge` names the skills to combine and `into`, the resulting skill, what it covers, and its dirs. `split` names one skill and `into`, the parts, what each part keeps, and the dirs that part keeps. `<other>` has a description, the skills it touches, and its dirs. Wrap fill-in values in `<>`. Leave the op names unwrapped. Fill create and delete here. Leave the skill names on update, merge, and split for skill select, and leave `improve_skills` for that same match.

## Applies when

Label A and Label B exist. This is the label agent. The optimize loop reads the goal after this step and does not return here.
