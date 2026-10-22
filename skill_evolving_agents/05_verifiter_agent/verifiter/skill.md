# Verifier

Check one goal op and write the result. This is the verifiter agent. The op lists the skills to check. Leave the other ops for their own loop. The judge agent reads this result and either ends the op or sends it back to Edit.

## Context

Checks are a changelog reverse check, alignment with the evolve goal, difficulty, not too complicated and not overfitting, and the checklist from the goal capabilities. The output shape is `verification-output.example.json` in this folder. The scripts below do the mechanical checks. A fail prints `skill`, `check`, `problem`, `fix`, and `next`. `fix` is the edit. `next` is the state to run again: Goal, Generate, Update, Delete, Merge, or Split. `common/skill_format.json` is the closed list of sections and directories. `other` or `ood` is allowed when the goal also names the heading or directory. The copy from before the edit is `target/raw_skills/<skill>`. The edited copy is `target/to_be_improved_skills/<skill>`.

## Constraints

Do not set `action`. Judge does that. Do not hand-write `verification_steps` or `per_skill`. Do not drop `problem`, `fix`, or `next` when a script fails. Do not reject a skill because it has a heading or directory outside `common/skill_format.json`. Name that heading or directory as `other` or `ood` on the goal. An outside heading or directory that changes and was not named fails the diff. One that does not change does not fail the skill. Do not edit `target/raw_skills` after the copy is taken.

## Workflow

Run these scripts on the one-op `workspace/run/evolve-goal.json` with `--op 1`, in this order. A bundled same-skill update is still that one op. Do not loop over `bundle.selected`. Copy each fail block into that skill's `feedback`, and into `overall_feedback` when more than one skill fails. Set overall status and per-skill status to `pass` or `fail` from the script results. Leave `action` null for Judge. Leave `ood` empty when nothing is outside the named checks or the closed list.

Always fill `feedback.replay`. When a post-edit replay exists, set `available`
true, set status from the replay, and record measured `before` and `after`
objects. Without one, set status to `not_run`, explain why, and keep
before/after null. In that case, describe any pass as structural only.

- `verification_from_goal.py` writes `workspace/run/verification.json`. It puts one `verification_steps` item and one `feedback.per_skill` item on each skill named in `action.ops`. The example shows that item once. `retries_used` starts at 0. On a later run it keeps the count already stored for that skill. Do not reset it.
- `verify_deleted.py` checks delete. The skill must be gone from `target/to_be_improved_skills`.
- `verify_transforms.py` checks merge and split source snapshots, source removal, result skills, and requested directories.
- `verify_sections.py` checks create and update against the sections and directories that op claims, including `scripts` when the goal names it. Create must contain them. Update must change the claimed sections and leave every other section and directory equal to `target/raw_skills`.
- `verify_goal.py` is the goal-align step, the item whose `ref` is `evolve-goal`. A claimed section or directory must be on the closed list or named as `other`.

## Applies when

The optimize loop has edited this op and it is ready to judge.
