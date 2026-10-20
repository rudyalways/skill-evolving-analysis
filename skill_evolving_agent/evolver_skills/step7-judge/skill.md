# Judge

Decide whether the run stops or goes back. This is step 7. It reads the verifier output and does not check the skill again.

## Experience

Step 6 writes status, feedback, and `ood` in `workspace/run/verification.json`. The shape is `evolver_skills/step6-verifiter/verification.example.json`. Judge reads that file, the goal, and the checker result already recorded there. `action.op` is `pass` or `back`. `pass` stops. `back` re-enters an earlier state. A failed skill status, a failed checker line, or an `ood` item the goal did not name is a reason to go back. A pass status with an empty `ood` list can stop.

## Don't

Do not re-run the section or directory diff. Do not mark pass when a skill status is fail. Do not send the run back without naming the earlier state. Do not edit `target/raw_skills`. Do not drop an `ood` item when choosing where to go back.

## Must

Read `workspace/run/verification.json`. Set `feedback.action`. `op` is `pass` or `back`. `pass` stops the machine and leaves `to` empty. `back` sets `to` to an earlier state: CutTraces, LabelA, LabelB, Goal, Select, Update, or Generate.

## Applies when

Verify has written `verification.json`.
