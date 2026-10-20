# Verifier

Check the skill change and write the result. This is step 6, the Verify state. Step 7 Judge reads this result and decides whether the run stops or goes back.

## Experience

Checks are a changelog reverse check, alignment with the evolve goal, difficulty, not too complicated and not overfitting, and the checklist from the goal capabilities. The output shape is `verification.example.json` in this folder. `verify_goal.py` is the goal-align step, the item whose `ref` is `evolve-goal`. It takes the run's goal and calls `evolver_skills/reference-skill_format/skill_format_checker.py`. That checker reads `evolver_skills/reference-skill_format/skill_format.json`. It accepts a goal section or dir that is on that list, and `other` or `ood` when the goal also names the heading or directory the skill uses. It checks that only those sections changed, including a heading named under `other`. It checks that only the dirs named on the goal changed, including a directory named under `other`. The copy from before the edit is `target/raw_skills/<skill>`. The edited copy is `target/to_be_improved_skills/<skill>`. The result is structured data: overall status, overall feedback, and the same pair per skill.

## Don't

Do not set `action`. Judge does that. Do not reject a skill because it has a heading or directory outside `evolver_skills/reference-skill_format/skill_format.json`. Name that heading or directory as `other` or `ood` on the goal. An outside heading or directory that changes and was not named fails the diff. One that does not change does not fail the skill. Do not edit `target/raw_skills` after the copy is taken.

## Must

Write `workspace/run/verification.json`. Follow `verification.example.json` in this folder. Keep a `feedback.ood` item only when a finding is not one of the named checks, or a heading or directory is outside the closed list. Leave `ood` empty when nothing is outside. Run `verify_goal.py` on `workspace/run/evolve-goal.json`. That is the goal-align step. It compares `target/raw_skills/<skill>` with `target/to_be_improved_skills/<skill>` for each update. Set overall status and per-skill status to `pass` or `fail`. Leave `action` for Judge.

## Applies when

A skill was updated or created and is ready to judge.
