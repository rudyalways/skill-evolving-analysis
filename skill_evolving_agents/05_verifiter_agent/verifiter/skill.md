# Verifier

Check one goal op and write the result. This is the verifiter agent. The op lists the skills to check. Leave the other ops for their own loop. The judge agent reads this result and either ends the op or sends it back to Edit.

## Context

Checks are a changelog reverse check, alignment with the evolve goal, difficulty, not too complicated and not overfitting, and the checklist from the goal capabilities. The runner writes `workspace/run/verification-input.json` before this stage. It contains each skill's section, directory, and avoid expectations; finding evidence for the difficulty decision; quality thresholds; and explicit assertions for all five steps. Its shape is `verification-input.example.json`. The runner also writes claimed changes and before/after content hashes to `workspace/run/changelog.json` and to the affected skill metadata. The output shape is `verification-output.example.json`. The scripts below do the mechanical checks. A fail prints `skill`, `check`, `problem`, `fix`, and `next`. `fix` is the edit. `next` is the state to run again: Goal, Generate, Update, Delete, Merge, or Split. `common/skill_format.json` is the closed list of sections and directories. `other` or `ood` is allowed when the goal also names the heading or directory. The copy from before the edit is `target/raw_skills/<skill>`. The edited copy is `target/to_be_improved_skills/<skill>`.

## Constraints

Do not set `action`. Judge does that. Do not hand-write `verification_steps`, `per_skill`, or `changelog`; `verification_from_goal.py` copies the runner-owned change manifest. Do not drop `problem`, `fix`, or `next` when a script fails. Do not reject a skill because it has a heading or directory outside `common/skill_format.json`. Name that heading or directory as `other` or `ood` on the goal. An outside heading or directory that changes and was not named fails the diff. One that does not change does not fail the skill. Do not edit `target/raw_skills` after the copy is taken.

## Workflow

First read `workspace/run/verification-input.json`. Evaluate every assertion and every item under `skills[].requirements`; do not substitute a generic checklist. Run these scripts on the one-op `workspace/run/evolve-goal.json` with `--op 1`, in this order. A bundled same-skill update is still that one op. Do not loop over `bundle.selected`. Copy each fail block into that skill's `feedback`, and into `overall_feedback` when more than one skill fails. For every step, write a 0-to-1 `score`, `status`, causal `reasoning`, and concrete `evidence`. A step passes exactly when its score meets `scoring.pass_threshold`. Compute each skill score with `scoring.step_weights`; `overall_score` is the mean skill score. Set per-skill status from its score. Overall status may additionally fail on a behavioral replay hard gate. Leave `action` null for Judge. Leave `ood` empty when nothing is outside the named checks or the closed list.

Always fill `feedback.replay`. When a post-edit replay exists, set `available`
true, set status from the replay, and record measured `before` and `after`
objects. Without one, set status to `not_run`, explain why, and keep
before/after null. In that case, describe any pass as structural only. Never
invent replay numbers. When the active skill contains `evals/evals.json` and
the cases are runnable, execute paired baseline and candidate cases using the
same model, tools, inputs, and budget. Follow
`04_optimize_agent/skill-create/references/evaluation-loop.md` and preserve
the grading, blind-comparison, analysis, benchmark, transcript, output, and
timing artifacts under this operation. A behavioral regression makes replay
and overall status fail even if every structural check passes.

Grade expectations from inspected transcript and output evidence. Check
substance, not just names or keyword presence; extract and verify additional
claims; flag weak expectations. Blind comparison must not reveal which output
used the skill. Aggregate repeated runs with `common/skill_evaluation.py` and
report variance, errors, time, token, and tool-call deltas.

When replay is available, write measured artifacts to
`workspace/run/replay/manifest.json` and
`workspace/run/replay/benchmark.json`, and write hidden cases to
`workspace/run/replay/held-out-evals.json`. Generate held-out cases after
Optimize finishes; keep them outside the candidate skill, and reject prompt or
source-trace overlap with development evals. The manifest must identify the run,
skill, backend, model, candidate and baseline content hashes, eval IDs, both
configurations, and trial count, and must set `executed: true`. The benchmark
must contain deterministic `run_summary` output from
`common/skill_evaluation.py aggregate`. If either artifact is missing or
invalid, replay is not available and must not be claimed.

Set replay `kind` to `paired_skill_eval` only for this isolated paired
evaluation. Its `after` metrics include `held_out_cases`,
`held_out_pass_rate`, and `activation_false_positive_rate`. Promotion requires
the configured minimum held-out count and pass rate and maximum false-positive
rate. Development-only improvement cannot satisfy promotion.

- `verification_from_goal.py` writes `workspace/run/verification.json`. It puts one `verification_steps` item and one `feedback.per_skill` item on each skill named in `action.ops`, and copies `workspace/run/changelog.json` into the output. The example shows each item once. `retries_used` starts at 0. On a later run it keeps the count already stored for that skill. Do not reset it.
- `verify_deleted.py` checks delete. The skill must be gone from `target/to_be_improved_skills`.
- `verify_transforms.py` checks merge and split source snapshots, source removal, result skills, and requested directories.
- `verify_sections.py` checks create and update against the sections and directories that op claims, including `scripts` when the goal names it. Create must contain them. Update must change the claimed sections and leave every other section and directory equal to `target/raw_skills`.
- `verify_goal.py` is the goal-align step, the item whose `ref` is `evolve-goal`. A claimed section or directory must be on the closed list or named as `other`.
- For a finding whose `features.candidate_source` is `methodology` or
  `methodology_consolidated`, run `verify_quality.py` with the one-op goal,
  that finding, both skill roots, and `common/preprocessing-config.json`.
  It deterministically checks the value gate, lesson alignment, generic
  checklist dilution, no-op updates, and redundancy with other skills.

## Applies when

The optimize loop has edited this op and it is ready to judge.
