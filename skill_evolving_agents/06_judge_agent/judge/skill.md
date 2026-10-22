# Judge

Decide whether this op stops or goes back to Edit. This is the judge agent. It reads the verifiter output for the current op and does not check the skill again. The optimize agent is finished unless this decision sets `back`. Do not return to cut traces, labeling, or the goal.

## Context

The verifiter agent writes status, feedback, and `ood` in `workspace/run/verification.json` for one goal op. The shape is `05_verifiter_agent/verifiter/verification-output.example.json`. The op lists the skills this session edited. Several source edits of the same skill are already one op, so one `pass`, `back`, or `fail` covers that bundle. Do not re-rank `bundle.selected`. The merge gate already kept the edits with the highest super score. `pass` stays gated on overall status and every per-skill status. `feedback.retry_budget` is 1 for this op. `pass` ends the op. `back` runs Edit once more for this same op. `fail` ends the op when that retry is spent. The next op is a new loop.

## Constraints

Do not re-run the section or directory diff. Do not mark pass when a skill status is fail. Do not send this op back to CutTraces, LabelA, LabelB, Goal, or Select. Do not send back an op that has used `retry_budget`. Do not edit `target/raw_skills`. Do not drop an `ood` item when choosing where to go back. Do not start the next goal op in this step.

## Workflow

Read `workspace/run/verification.json` for this op. Set `feedback.action`. `op` is `pass`, `back`, or `fail`. `pass` leaves `to` empty. `back` sets `to` to this op's edit, Update, Generate, Delete, Merge, or Split, and adds 1 to `retries_used`. `fail` leaves `to` empty when `retries_used` is already at `retry_budget`. `pass` and `fail` end this op. The loop then takes the next op.

## Applies when

Verify has written `verification.json`.
