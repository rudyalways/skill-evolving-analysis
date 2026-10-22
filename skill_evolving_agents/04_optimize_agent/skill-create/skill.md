# Skill create

## Overview

Create a concise, evidence-backed skill from one validated create operation.
This is Optimize's Generate state. The design adapts public skill-authoring
guidance to this pipeline's closed section and directory vocabulary; see
`references/public-skill-authoring.md`.

## When to Use

Use only when `workspace/run/evolve-goal.json` contains one `op: create`, or
Judge sends that create operation back to Generate.

## Do Not Use

Do not use for update, delete, merge, or split. Do not create behavior the
model and harness already perform well, duplicate a recalled skill, or force an
unknown capability into a nearby taxonomy leaf.

## Workflow

1. Read the create record's name, description, labels, sections, and dirs.
2. Extract intent from its trace evidence: triggers, expected result,
   corrections, edge cases, and completion evidence. Do not interview the user
   when those facts are already in the trace.
3. Design the smallest reusable procedure that resolves the diagnosed pattern.
   Choose the degree of freedom deliberately: prose for judgment, a template
   for constrained variation, and a script only for fragile deterministic work.
   Reuse existing skills through metadata `dependencies` instead of copying
   their instructions.
4. Write `target/to_be_improved_skills/<skill>/SKILL.md` with only the headings
   named by the goal. Use canonical headings from `common/skill_format.json`.
5. Use progressive disclosure. Keep essential procedure in `SKILL.md`; put
   detailed evidence or domain material in `references`, deterministic helpers
   in `scripts`, delegated prompts in `agents`, reusable output material in
   `assets`, and behavioral fixtures in `evals` only when those dirs are named.
6. Make the frontmatter description state both what the skill does and the
   concrete contexts that should trigger it. Use a lowercase hyphenated name.
7. For objectively verifiable behavior, create discriminating positive and
   near-miss cases. Follow `references/evaluation-loop.md`; do not treat a
   structural check as behavioral proof.
8. Write metadata and preserve all existing records. Hand an
   out-of-distribution capability to `ood-data-updater`.
   For external knowledge, add a `sources` record with URL, pinned revision,
   retrieval timestamp, and SHA-256 content digest.

## Constraints

- Treat `common/skill_format.json` as authoritative. Use `other` or `ood` only
  when the goal explicitly names the custom heading or directory.
- Keep `SKILL.md` concise and below 500 lines. Do not repeat reference content.
- Keep names at most 64 characters and descriptions at most 1024 characters.
  Remove placeholders before completion.
- Keep references one level below `SKILL.md` and state when to read each one.
- Give reference files over 100 lines a table of contents or search guidance.
- Add scripts only when they replace repeated or error-prone generated code.
- Compile every generated Python script and execute a representative safe
  fixture. Do not claim an unexecuted script works.
- Do not add README, changelog, installation guide, or other process debris.
- Do not copy platform-specific Claude, Codex, or Cursor orchestration into a
  generated domain skill.
- Generalize trace-specific names, paths, IDs, and one-off corrections into
  reusable conditions. Do not read or author operation-level held-out evals;
  Verifiter creates those after this stage.

## Verification

Before returning:

1. Confirm the skill name and description are non-empty, the name is lowercase
   hyphen-case, and the description contains both capability and trigger.
2. Confirm every goal section and directory exists and no unrequested core
   section or directory was added.
3. Confirm the workflow addresses the finding's failure mode rather than merely
   restating its examples.
4. Confirm completion evidence is observable and negative triggers prevent
   broad accidental invocation.
5. If `evals` is named, write `evals/evals.json` using
   `references/eval-schema.md`, including positive and near-miss cases, then
   validate it with `common/skill_evaluation.py`.
6. Run any created script on a representative fixture.
7. When replay is available, retain paired baseline/candidate artifacts using
   `references/evaluation-artifacts.md`. Grade evidence, compare outputs
   blindly, analyze causation, and report variance rather than only averages.
8. Measure activation recall and near-miss false-positive rate separately from
   task success. A good workflow with an over-broad description is not ready
   for promotion.

## Output Format

Write the skill under `target/to_be_improved_skills`. Metadata uses the
top-level `skills_metadata` list. Each new record has `skill`, `description`,
`skill_types`, `unmatched_skill_types`, and `changelog`; it may include
`dependencies` and `sources`. Initialize `changelog` to `[]`; the runner adds
the content-hashed operation record before verification. Preserve existing
records and their changelog entries.

The runner reconstructs metadata deterministically. A single-session create
also receives a `lifecycle` record with provisional status, origin run and
finding, session IDs, confidence, and evidence counts. Do not remove it.

## Limitations

This stage authors and structurally verifies a skill. Behavioral comparison
requires a runnable execution/replay facility; when none exists, record that
fact and never label structural success as behavioral improvement. UI-specific
packaging and `agents/openai.yaml` remain outside this pipeline.
