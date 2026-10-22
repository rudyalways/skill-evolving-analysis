# Judge formula

This is the reference contract for the deterministic host Judge. It reads the
verifiter output for the current op, sets pass or fail from the already
validated formula, and does not check the skill again.

## Context

The verifiter agent writes status, feedback, and `ood` in `workspace/run/verification.json` for one goal op. The shape is `05_verifiter_agent/verifiter/verification-output.example.json`. The op lists the skills this session edited. Several source edits of the same skill are already one op, so one `pass` or `fail` covers that bundle. Do not re-rank `bundle.selected`. The merge gate already kept the edits with the highest super score. `pass` stays gated on the final score against `pass_threshold`. `feedback.retry_budget` is 0 and `retries_used` stays 0. Both `pass` and `fail` end the op. The next op is a new loop.

Scoring strategy version 1 is already validated before Judge. The decision
score starts at 1.0 and subtracts each listed penalty once. The sections and
directories the goal named share a 0.80 claim budget: a missing section, a
missing directory, or a goal contradiction costs one share, and a missing
near-miss eval costs half a share. Shape misses (heading level, unclaimed
heading, tighter wording, description shape) cost 0.05 each and stop at 0.20,
so shape alone still passes. A replay failure costs 0.125 and still passes on
its own. Step scores are diagnostic means. Overall score is the minimum skill
score. Pass and fail come only from comparing that score with
`pass_threshold`. Judge must not add another gate.

## Constraints

Do not re-run the section or directory diff. Do not mark pass when a skill status is fail. Do not send this op back to any earlier stage; retries are disabled. Do not edit `target/raw_skills`. Do not drop an `ood` item. Do not start the next goal op in this step.

Do not mark pass when the final score is below `pass_threshold`. A replay
failure is already priced into that score. Do not treat `not_run` as behavioral
proof: a structurally passing operation may proceed only with the explicit
replay limitation preserved. Prefer a causal edit from the post-hoc analysis
over a broad rewrite, and do not optimize repeatedly against one eval case.
For `paired_skill_eval`, do not pass a replay that misses held-out count/pass
thresholds, exceeds the activation false-positive limit, reuses development
prompts or source traces, or wins only on development cases.

## Workflow

Read `workspace/run/verification.json` for this op. Set `feedback.action.op` to `pass` or `fail` and leave `feedback.action.to` empty. Keep every `retries_used` value at 0. Both decisions end this op; the loop then takes the next op.

After this decision, the runner writes `judge.json` in the operation archive.
It binds the goal, verification input, verification output, and changelog by
SHA-256. Do not write that file yourself.

## Applies when

Verify has written `verification.json`.
