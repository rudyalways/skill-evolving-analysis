# Existing skills labeler

Label the existing skills. This is the skills agent. Label each skill until it has at least 3 labels, and each label has a weight.

## Context

An existing skill lives under `workspace/target/to_be_improved_skills`. Label B is its `skill_types` in `to_be_improved_skills_metadata/metadata.json`. Each label is a path in `skill_capabilites/skill_capabilites.json` plus a weight from 0 to 1. The description says how those labels cover the skill. The goal agent later recalls skills by these labels, before it chooses an action. The metadata record names the skill directory.

## Constraints

Do not stop a skill at one or two labels. Do not omit the weight. Do not invent a capability path. Do not put an out-of-distribution name into `skill_types`. Do not wipe labels that are already correct. Add until the skill has three. Do not drop an undefined name silently. Do not copy the example unmatched item when every label is a real path.

## Workflow

List the existing skills. For each skill, write or extend its metadata record. Set `skill` to that skill's directory name. Write `skill_types` until it has at least 3 items. Each item is `type` and `weight`. `type` is a path defined in `skill_capabilites/skill_capabilites.json`. An undefined name goes in `unmatched_skill_types` as `type` and `weight`, the same shape as the example. If no defined path fits, leave `skill_types` empty and keep the unmatched names there.

## Applies when

Existing skills are under `workspace/target/to_be_improved_skills`. This agent runs once. This is the skills agent.
