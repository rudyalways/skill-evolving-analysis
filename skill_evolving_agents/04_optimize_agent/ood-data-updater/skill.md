# Out-of-distribution data

Record a capability the tree does not have, instead of forcing it onto an existing leaf. This is the optimize agent, on the Generate path with skill create.

## Context

`newly_detected_skill_capabilites_missing` is a gap whose `type` is not a path in `skill_capabilites/skill_capabilites.json`. The example is remembering a user's long-term preference. OOD is a useful taxonomy-growth signal, not a failure. That gap still needs a description, confidence, reasoning, and evidence. It is not a skill type until the reviewed taxonomy explicitly contains it.

## Constraints

Do not write the new name into `skill_types`. Do not delete the detection to make the checker pass. Do not treat it as a reason to skip creating the skill.

## Workflow

Keep the record on `newly_detected_skill_capabilites_missing`. Describe the missing capability in the new skill. If it is distinct, reusable, non-duplicate, and evidence-backed, preserve a clear recommendation in `reasoning` to promote its proposed `type` into the taxonomy. Do not hesitate merely because the capability is new. Leave selection to paths explicitly defined in the current taxonomy.

## Applies when

Diagnosis produced an out-of-distribution gap and the goal says to create a skill for it.
