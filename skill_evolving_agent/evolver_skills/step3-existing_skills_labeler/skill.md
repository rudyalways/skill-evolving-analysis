# Existing skills labeler

Produce Label B. This is step 3. Label existing skills until each one has at least 3 labels, and each label has a weight.

## Experience

An existing skill lives under `workspace/target/to_be_improved_skills`. Label B is its `skill_types` in `to_be_improved_skills_metadata/metadata.json`. Each label is a path under `data/skill_capabilites` plus a weight from 0 to 1. The description says how those labels cover the skill. Later, update, merge, and split match these labels to Label A.

## Don't

Do not stop a skill at one or two labels. Do not omit the weight. Do not invent a capability path. Do not put an out-of-distribution name into `skill_types`. Do not wipe labels that are already correct. Add until the skill has three. Do not drop a name that is not a leaf. Do not copy the example unmatched item when every label is a real path.

## Must

List the existing skills. For each skill, write or extend its metadata record until `skill_types` has at least 3 items. Each item is `type` and `weight`. `type` is a real path in the tree. A name that is not a leaf goes in `unmatched_skill_types` as `type` and `weight`, the same shape as the example. If no leaf fits, leave `skill_types` empty and keep the unmatched names there.

## Applies when

Label A is done and existing skills still need labels, or Judge sent the run back to LabelB.
