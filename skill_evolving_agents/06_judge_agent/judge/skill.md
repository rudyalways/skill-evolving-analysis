# Judge

Decide whether this op passes or fails. This is the judge agent. It reads the verifiter output for the current op and does not check the skill again. Do not return to Edit, cut traces, labeling, or the goal.

## Context

The verifiter agent writes status, feedback, and `ood` in `workspace/run/verification.json` for one goal op. The shape is `05_verifiter_agent/verifiter/verification-output.example.json`. The op lists the skills this session edited. Several source edits of the same skill are already one op, so one `pass` or `fail` covers that bundle. Do not re-rank `bundle.selected`. The merge gate already kept the edits with the highest super score. `pass` stays gated on overall status and every per-skill status. `feedback.retry_budget` is 0 and `retries_used` stays 0. Both `pass` and `fail` end the op. The next op is a new loop.

Scoring strategy version 1 is already validated before Judge. Assertion scores
use the fixed 0, 0.25, 0.5, 0.75, and 1 anchors. A step score is the mean of
its assertions. A skill score is the applicability-renormalized weighted mean
of its steps, but every applicable assertion and step is a required gate.
Overall score is the minimum skill score, not an average. Overall pass requires
every skill to pass and an available replay not to fail. Judge must not
override those formulas or compensate for a failed gate with a high score
elsewhere.

## Constraints

Do not re-run the section or directory diff. Do not mark pass when a skill status is fail. Do not send this op back to any earlier stage; retries are disabled. Do not edit `target/raw_skills`. Do not drop an `ood` item. Do not start the next goal op in this step.

Do not mark pass when an available behavioral replay failed or shows a
material regression against baseline. Do not treat `not_run` as behavioral
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
