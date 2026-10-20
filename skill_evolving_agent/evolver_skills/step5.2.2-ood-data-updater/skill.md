# Out-of-distribution data

Record a capability the tree does not have, instead of forcing it onto an existing leaf. This is step 5.2.2, on the Generate path with step 5.2.1.

## Experience

`newly_detected_skill_capabilites_missing` is a gap whose `type` is not a path under `data/skill_capabilites`. The example is remembering a user's long-term preference. That gap still needs a description, confidence, reasoning, and evidence. It is not a skill type until the tree has a leaf for it.

## Don't

Do not write the new name into `skill_types`. Do not delete the detection to make the checker pass. Do not treat it as a reason to skip creating the skill.

## Must

Keep the record on `newly_detected_skill_capabilites_missing`. Describe the missing capability in the new skill. Leave selection to named leaves only.

## Applies when

Diagnosis produced an out-of-distribution gap and the goal says to create a skill for it.
