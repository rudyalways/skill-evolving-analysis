# Skill create

## Overview

Create a concise, evidence-backed skill from one validated create operation.
This is Optimize's Generate state. The design adapts public skill-authoring
guidance to this pipeline's closed section and directory vocabulary; see
`references/public-skill-authoring.md`.

## When to Use

Use only when the session operation is `op: create`. The working directory
is `workspace/`. Write the new skill at `workspace/<skill>/`. Its changelog,
if any, is `workspace/<skill>.md` beside that directory. Read it and do not
edit it.

## Do Not Use

Do not use for update, delete, merge, or split. Do not create behavior the
model and harness already perform well, duplicate a recalled skill, or force an
unknown capability into a nearby taxonomy leaf.

## Workflow

1. Read the create record's name, description, labels, sections, and dirs. If
   any supporting directory is named, inspect
   `workspace/_templates/complete-skill/` once for file shape and resource
   boundaries. It is a reference, not an output or a scaffold to copy wholesale.
2. Extract intent from its trace evidence: triggers, expected result,
   corrections, edge cases, and completion evidence. Do not interview the user
   when those facts are already in the trace.
3. Design the smallest reusable procedure that resolves the diagnosed pattern.
   Choose the degree of freedom deliberately: prose for judgment, a template
   for constrained variation, and a script only for fragile deterministic work.
   Reuse an existing procedure only when the goal names that dependency. Do not
   open metadata to look for one.
4. Write `workspace/<skill>/SKILL.md` with only the headings
   named by the goal. Use the canonical heading text from
   `common/skill_format.json` as a level-2 Markdown heading, for example
   `## Overview`. `# Overview` fails verification: the section checker does not
   see a level-1 heading and reports that section missing.
5. Use progressive disclosure. Keep essential procedure in `SKILL.md`; put
   detailed evidence or domain material in `references`, deterministic helpers
   in `scripts`, delegated prompts in `agents`, reusable output material in
   `assets`, and behavioral fixtures in `evals` only when those dirs are named.
6. Make the frontmatter description state both what the skill does and the
   concrete contexts that should trigger it. Use a lowercase hyphenated name.
7. For objectively verifiable behavior, create discriminating positive and
   near-miss cases. Follow `references/evaluation-loop.md`; do not treat a
   structural check as behavioral proof.
8. Do not read or write metadata. The runner writes the metadata record from
   the goal. Do not edit `workspace/<skill>.md`. Hand an out-of-distribution
   capability to `ood-data-updater`.

## Constraints

- Treat `common/skill_format.json` as authoritative. Use `other` or `ood` only
  when the goal explicitly names the custom heading or directory.
- Write every required section as a level-2 heading. `# Overview` is not an
  accepted form of `## Overview`. The checker then reports the section missing.
- Important. The description goes on the same line as `description:`. Do not
  write `description: >` or `description: |`. The checker reads only that line,
  so `>` is the description and the run fails before verification with
  "frontmatter description contains angle brackets". No `<` or `>` on that line.
  `name` is lowercase hyphen-case, matches the directory, and is at most 64
  characters. `description` is at most 1024 characters. Allowed fields are name,
  description, license, compatibility, allowed-tools, and metadata.
- Important. When the goal says a first case and a later restatement are each
  enough, do not write "all of the following are true" and do not make the
  restatement a required condition. That wording scored 0.99 and still failed.
- Keep `SKILL.md` at most 500 lines. Do not repeat reference content. Remove
  `TODO`, `[TODO`, `EXAMPLE_SCRIPT`, `EXAMPLE_REFERENCE`, and
  `EXAMPLE_ASSET` before completion.
- Use only references, scripts, agents, assets, evals, or a directory the goal
  names as other or ood. No symbolic links. No file over 10MB.
- Keep resource files at most four path components below their canonical
  directory and state when to read or execute each non-asset resource.
- Give reference files over 100 lines a table of contents or search guidance.
- Add scripts only when they replace repeated or error-prone generated code.
- Every requested resource must implement its directory goal. Omit unrequested
  resource directories even when they exist in the complete reference skill.
- Do not author `agents/openai.yaml`; the runner generates its interface fields
  deterministically after Judge accepts the operation.
- Compile every generated Python script and execute a representative safe
  fixture. Do not claim an unexecuted script works.
- Do not add a README, an installation guide, or a changelog file inside the
  skill directory. The changelog is the `<skill>.md` file beside the skill
  directory. Do not edit it. Do not read or write metadata.
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

Write the skill under `workspace/<skill>/`. Do not write metadata and do not
edit the changelog file beside the directory. The runner appends one short
line to the changelog after this session and writes the metadata record.

The runner reconstructs metadata deterministically. A single-session create
also receives a `lifecycle` record with provisional status, origin run and
finding, session IDs, confidence, and evidence counts. The runner writes it.

## Limitations

This stage authors and structurally verifies a skill. Behavioral comparison
requires a runnable execution/replay facility; when none exists, record that
fact and never label structural success as behavioral improvement.
Platform-specific packaging remains limited to files explicitly authorized by
the goal, except deterministic post-acceptance interface metadata generated by
the runner.
