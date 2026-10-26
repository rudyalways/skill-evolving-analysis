# Verifier

Check one goal op and write the result. This is the verifiter agent. The op
lists the skills to check. Leave the other ops for their own loop. The host
applies the validated Judge formula to this result and ends the op with pass
or fail; retries are disabled.

## Context

Checks cover changelog reversal, goal alignment, difficulty, unnecessary complexity, the goal checklist, regression of existing capabilities or sections, overfitting, and removal of unhelpful or redundant information. `verification-input.template.json` is the machine template for the shared rubric, scoring scale, and weights; its `skills` list is intentionally empty. `verification-input.example.json` illustrates one fully materialized skill with its own eight checks and goal-specific assertions. Before this stage, the runner copies the machine template to `workspace/run/verification-input.json`, materializes all checks under each affected skill, injects that skill's goal-specific section/directory/avoid/removal expectations, and generates stable assertion IDs that point back to those requirements. It also injects run and operation identifiers, evidence for every finding selected into a bundle, and configured quality values. `verification-output.template.json` is the empty machine envelope. `verification-output.example.json` illustrates one skill with eight scored steps and one scored result for every shared and goal-specific assertion. `verification_from_goal.py` creates those per-skill step and assertion-result slots from the runtime input. The runner also writes claimed changes and before/after content hashes to `workspace/run/changelog.json` and to the affected skill metadata. The scripts below do the mechanical checks. A fail prints `skill`, `check`, `problem`, `fix`, and `next`. `fix` is the suggested edit and `next` records its repair stage, but the pipeline does not retry it. `common/skill_format.json` is the closed list of sections and directories. `other` or `ood` is allowed when the goal also names the heading or directory. The copy from before the edit is `target/raw_skills/<skill>`. The edited copy is `target/to_be_improved_skills/<skill>`.

## Constraints

Do not set `action`. Judge does that. Do not hand-write `verification_steps`, `per_skill`, or `changelog`; `verification_from_goal.py` copies the runner-owned change manifest. Do not drop `problem`, `fix`, or `next` when a script fails. The runner prompt lists the mechanical standards. Apply that list and one run of the prescribed scripts. Do not open the checker source or the parent repository to re-derive them. Match a claimed section or directory name with a loose regex. Case, extra words, and heading level do not matter: `overview`, `## Overview`, and `# Overview` are the same name. Pass that claim when its content is new, deleted, or changed in the direction of the goal. That match is enough. Do not fail it because the wording is tighter than the goal, including "all of the following are true", when the goal's cases are present. Frontmatter `name` is lowercase hyphen-case, matches the directory, and is at most 64 characters. `description` is required, at most 1024 characters, and contains no angle brackets. Allowed frontmatter fields are name, description, license, compatibility, allowed-tools, and metadata. `SKILL.md` is at most 500 lines and contains no `TODO`, `[TODO`, `EXAMPLE_SCRIPT`, `EXAMPLE_REFERENCE`, or `EXAMPLE_ASSET` placeholder. No symbolic links and no file over 10MB. Reference files are one directory level deep. A named Python script must compile. A named `evals` directory contains `evals/evals.json` with the goal's positive and near-miss cases. Directories are only references, scripts, agents, assets, evals, or a goal-named other/ood directory. Create contains every claimed section and directory. Update changes every claimed section and leaves frontmatter, the preamble, and every unclaimed section identical to `target/raw_skills`; both copies exist. Delete removes the skill directory. Merge and split keep the source snapshot and remove only the sources the operation names. `changelog.json` already stores the content hashes; do not reimplement that digest. List each defect once in `penalties` as `{id, target}`. The runner prices that list and writes the skill score. The score starts at 1.0. The sections and directories this goal names share a 0.80 claim budget. `missing_section`, `missing_directory`, and `goal_contradiction` each cost one share. `missing_near_miss_eval` costs half a share. `heading_level`, `unclaimed_heading`, `tighter_wording`, and `description_shape` each cost 0.05, and those shape charges stop at 0.20, so shape alone stays at or above 0.80 and still passes. `replay_fail` costs 0.125, and one replay failure still passes. Do not charge a section or directory the goal did not name. The 8 core sections are the inventory, not the divisor. A script finding is one listed penalty, not a veto. Pass when the priced score is at least `pass_threshold`. Do not reject a skill because it has a heading or directory outside `common/skill_format.json`. Name that heading or directory as `other` or `ood` on the goal. An outside heading or directory that changes and was not named fails the diff. One that does not change does not fail the skill. Do not edit `target/raw_skills` after the copy is taken.

A merge target may rewrite any section needed to preserve the named source
capabilities; do not apply the narrow-update unchanged-section rule to it.
Evaluate duplication against the exact named merge sources and target. An
unrelated inventory skill is not a forbidden duplicate merely because its
description is semantically similar.

For every update that changes a `SKILL.md` section, also verify that the
existing eval suite is preserved and a focused regression case sourced from
the active finding was added or revised. A behavioral section diff without an
eval delta fails the goal even when the changed prose is structurally valid.

For update and merge, verify that every authored source resource under
`scripts`, `references`, `assets`, delegated `agents`, and `evals` survives in
the result unless a concrete matching `remove` item authorizes deletion. A
merge unions source eval cases rather than selecting one suite. Generated
`agents/openai.yaml` is not an authored delegated-agent resource and is
regenerated after acceptance. Treat silent inherited-resource loss as a goal
failure even when the model-authored resource plan originally said `omit`.

For create and update, a positive resource decision requires a non-empty
authored resource and a discoverable relative-path reference from `SKILL.md`
for scripts, references, assets, and delegated prompts. An empty directory or
generated `agents/openai.yaml` alone does not satisfy the claim. Confirm Python
helpers compile before passing a scripts claim.

Check provenance fidelity. A resource may not claim facts, headings, copied
content, or digests absent from its finding contract. Do not fail a
navigational reference for lacking a current digest when the contract marks
`content_digest_available: false` and the Goal correctly asks for a runtime
freshness check instead.

## Workflow

The runner prompt contains one skill's complete concrete input JSON and a
compact exception-report schema. Treat the embedded input as authoritative.
Evaluate its shared assertions from `checks`, its materialized applicability
and assertions under the single `skills[].checks` item, and every item under
`skills[].requirements`. Do not substitute a generic checklist. Return only
failed assertion IDs, their evidence, priced penalties, concise feedback,
replay state, and OOD observations. Omit passing assertions: the runner
deterministically expands them and all runner-owned fields into the complete
verification document. Do not write the output file. The runner parses,
expands, and contract-validates the response before writing it. It may
repeat the identical request when the response is malformed JSON or violates
the output contract; this is response repair, not an optimization retry.

Run these scripts on the one-op `workspace/run/evolve-goal.json` with `--op 1`, in this order. A bundled same-skill update is still that one op: evaluate all entries in `checks.step3.evidence.findings`, but do not start separate verification outputs per source edit. Copy each fail block into that skill's `feedback`. For every applicable step, write one `assertion_results` item per shared and per-skill input assertion, with a score from 0 to 1 and causal reasoning and concrete evidence. The rounded step score is the arithmetic mean of its assertion scores and is diagnostic. When `skills[].checks[].applicable` is false, keep the builder's `not_applicable` status, null score, explanation, and empty evidence/results. List each defect once in `penalties`. The runner prices that list into the skill score and overall score: the 0.80 claim budget is split across the sections and directories this goal names, a missing or contradicted claim costs one share, a missing near-miss costs half a share, each shape miss costs 0.05 and shape charges stop at 0.20, and a replay failure costs 0.125. Pass when that score meets `pass_threshold`. In the one-skill response, `bottleneck_skills` contains that skill. Fill `applicable_weight` and `failed_required_steps`. Leave `action` null for Judge. Leave `ood` empty when nothing is outside the named checks or the closed list.

Always fill `feedback.replay`. When a post-edit replay exists, set `available`
true, set status from the replay, and record measured `before` and `after`
objects. Without one, set status to `not_run`, explain why, and keep
before/after null. In that case, describe any pass as structural only. Never
invent replay numbers. When the active skill contains `evals/evals.json` and
the cases are runnable, execute paired baseline and candidate cases using the
same model, tools, inputs, and budget. Follow
`04_optimize_agent/skill-create/references/evaluation-loop.md` and preserve
the grading, blind-comparison, analysis, benchmark, transcript, output, and
timing artifacts under this operation. A behavioral regression makes replay
and overall status fail even if every structural check passes.

Grade expectations from inspected transcript and output evidence. Check
substance, not just names or keyword presence; extract and verify additional
claims; flag weak expectations. Blind comparison must not reveal which output
used the skill. Aggregate repeated runs with `common/skill_evaluation.py` and
report variance, errors, time, token, and tool-call deltas.

When replay is available, write measured artifacts to
`workspace/run/replay/manifest.json` and
`workspace/run/replay/benchmark.json`, and write hidden cases to
`workspace/run/replay/held-out-evals.json`. Generate held-out cases after
Optimize finishes; keep them outside the candidate skill, and reject prompt or
source-trace overlap with development evals. The manifest must identify the run,
skill, backend, model, candidate and baseline content hashes, eval IDs, both
configurations, and trial count, and must set `executed: true`. The benchmark
must contain deterministic `run_summary` output from
`common/skill_evaluation.py aggregate`. If either artifact is missing or
invalid, replay is not available and must not be claimed.

Set replay `kind` to `paired_skill_eval` only for this isolated paired
evaluation. Its `after` metrics include `held_out_cases`,
`held_out_pass_rate`, and `activation_false_positive_rate`. Promotion requires
the configured minimum held-out count and pass rate and maximum false-positive
rate. Development-only improvement cannot satisfy promotion.

- The runner uses `verification_from_goal.py` to build the required output
  shape internally. Each verifier response is a compact exception report.
  The runner materializes one `verification_steps` item and one
  `feedback.per_skill` item, aggregates them, and copies the full changelog
  into the final output.
  `retry_budget` and every `retries_used` value stay 0 because parser retries
  do not retry or modify a skill.
- `verify_deleted.py` checks delete. The skill must be gone from `target/to_be_improved_skills`.
- `verify_transforms.py` checks merge and split source snapshots, source removal, result skills, and requested directories.
- `verify_sections.py` checks create and update against the sections and directories that op claims, including `scripts` when the goal names it. Create must contain them. Update must change the claimed sections and leave every other section and directory equal to `target/raw_skills`.
- `verify_goal.py` is the goal-align step, the item whose `ref` is `evolve-goal`. A claimed section or directory must be on the closed list or named as `other`.
- For a finding whose `features.candidate_source` is `methodology` or
  `methodology_consolidated`, run `verify_quality.py` with the one-op goal,
  that finding, both skill roots, and `common/preprocessing-config.json`.
  It deterministically checks the value gate, lesson alignment, generic
  checklist dilution, no-op updates, and redundancy with other skills.

## Applies when

The optimize loop has edited this op and it is ready to judge.
