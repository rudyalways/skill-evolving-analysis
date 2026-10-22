# Verifier

Check one goal op and write the result. This is the verifiter agent. The op
lists the skills to check. Leave the other ops for their own loop. The host
applies the validated Judge formula to this result and ends the op with pass
or fail; retries are disabled.

## Context

Checks cover changelog reversal, goal alignment, difficulty, unnecessary complexity, the goal checklist, regression of existing capabilities or sections, overfitting, and removal of unhelpful or redundant information. `verification-input.template.json` is the machine template for the shared rubric, scoring scale, and weights; its `skills` list is intentionally empty. `verification-input.example.json` illustrates one fully materialized skill with its own eight checks and goal-specific assertions. Before this stage, the runner copies the machine template to `workspace/run/verification-input.json`, materializes all checks under each affected skill, injects that skill's goal-specific section/directory/avoid/removal expectations, and generates stable assertion IDs that point back to those requirements. It also injects run and operation identifiers, evidence for every finding selected into a bundle, and configured quality values. `verification-output.template.json` is the empty machine envelope. `verification-output.example.json` illustrates one skill with eight scored steps and one scored result for every shared and goal-specific assertion. `verification_from_goal.py` creates those per-skill step and assertion-result slots from the runtime input. The runner also writes claimed changes and before/after content hashes to `workspace/run/changelog.json` and to the affected skill metadata. The scripts below do the mechanical checks. A fail prints `skill`, `check`, `problem`, `fix`, and `next`. `fix` is the suggested edit and `next` records its repair stage, but the pipeline does not retry it. `common/skill_format.json` is the closed list of sections and directories. `other` or `ood` is allowed when the goal also names the heading or directory. The copy from before the edit is `target/raw_skills/<skill>`. The edited copy is `target/to_be_improved_skills/<skill>`.

## Constraints

Do not set `action`. Judge does that. Do not hand-write `verification_steps`, `per_skill`, or `changelog`; `verification_from_goal.py` copies the runner-owned change manifest. Do not drop `problem`, `fix`, or `next` when a script fails. Do not reject a skill because it has a heading or directory outside `common/skill_format.json`. Name that heading or directory as `other` or `ood` on the goal. An outside heading or directory that changes and was not named fails the diff. One that does not change does not fail the skill. Do not edit `target/raw_skills` after the copy is taken.

## Workflow

The runner prompt contains one skill's complete concrete input JSON and its
complete required output JSON. Treat the embedded input as authoritative.
Evaluate its shared assertions from `checks`, its materialized applicability
and assertions under the single `skills[].checks` item, and every item under
`skills[].requirements`. Do not substitute a generic checklist. Return only
the completed output JSON in the prompt; do not write the output file. The
runner parses and contract-validates the response before writing it. It may
repeat the identical request when the response is malformed JSON or violates
the output contract; this is response repair, not an optimization retry.

Run these scripts on the one-op `workspace/run/evolve-goal.json` with `--op 1`, in this order. A bundled same-skill update is still that one op: evaluate all entries in `checks.step3.evidence.findings`, but do not start separate verification outputs per source edit. Copy each fail block into that skill's `feedback`. For every applicable step, write one `assertion_results` item per shared and per-skill input assertion, choosing only a configured score anchor and recording causal reasoning and concrete evidence. The rounded step score is the arithmetic mean of its assertion scores. It passes only when the mean meets `scoring.pass_threshold` and every assertion passes. When `skills[].checks[].applicable` is false, keep the builder's `not_applicable` status, null score, explanation, and empty evidence/results. Compute the skill score from applicable steps only, renormalizing `scoring.step_weights`; it passes only when its score meets the threshold and every applicable step passes. In the one-skill response, `overall_score` equals that skill score and `bottleneck_skills` contains that skill. Overall status passes only when the skill passes and replay is not fail. Fill `applicable_weight` and `failed_required_steps`. Leave `action` null for Judge. Leave `ood` empty when nothing is outside the named checks or the closed list.

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
  shapes before prompting. Each verifier response contains one
  `verification_steps` item and one `feedback.per_skill` item. The runner
  aggregates them and copies the full changelog into the final output.
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
