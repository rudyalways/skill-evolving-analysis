# Goal generator

Fill one finding's goal from its diagnosis and label matching. The runner starts
one session per selected finding by default. Recall has already named related
skills. The action is chosen here.

## Context

The defect comes from the skill, not the harness. Read this finding's records
in `workspace/run/diagnosis.json`,
`workspace/run/<finding-id>/label-matching.json`, and its `finding.json`.
Choose create, update, delete, merge, split, or `<other>` from the diagnosed
root cause and detector evidence. If diagnosis has no skill-capability gap,
write `action.disposition` as `no_change`, explain `action.reason`, and leave
`action.ops` empty. Do not invent an `other` operation merely to keep the list
non-empty.

Before proposing `create`, read `common/preprocessing-config.json` section
`evolution_policy`. A finding must meet its confidence, evidence-record, and
recurrence thresholds. When the general single-session switch is enabled, an
evidence-rich finding may create an initial provisional skill without meeting
the distinct-session threshold. The runner records that provisional lifecycle
and its evidence provenance in metadata so later seeded runs can improve it.
Single-session creation may also be allowed by the OOD or repeated cut-pattern
exception.
For the repeated-pattern exception, verify `finding.json` identifies
`features.candidate_source` as `cut_pattern` and meets the configured
confidence and distinct-window thresholds. Otherwise choose an evidence-backed
update or a no-change disposition.

For methodology findings, preserve only the generalized method in
`features.lesson`: prerequisites, decision rule, failure guard, minimal
successful sequence, and non-generic completion contract. Check
`features.quality.value` and the configured methodology thresholds. A
single-task methodology create must meet the explicit methodology exception
and remains provisional; cross-task consolidated evidence may be stable.
Prefer updating a recalled skill. Use `no_change` when the candidate restates
the prompt, says only to inspect/edit/test, embeds one-off paths or constants,
or adds no information beyond the recalled skill.

## Constraints

Do not put easy experience that the model and harness already do well into a skill. Do not turn an entire trajectory into a verbose checklist: retain only evidence-dependent, reusable methodology. Do not set `improve_harness` inside scope. Do not recall skills again. Do not ignore a skill named in `label-matching.json`. Do not copy every op, skill, section, or dir from the example. Do not add an `other` item unless the heading or directory is outside the closed list. Do not name the same skill in two actions.
Keep the goal compact: choose the minimum sufficient operation, limit
reasoning and plan to three sentences each, and do not inspect checker or
contract source. Run
`python3 03_goal_agent/goal-generator/one_action.py <evolve-goal-path>` once
after writing the output; do not search for the validator. If it fails, use
its error message to correct the JSON without opening the checker.

## Workflow

Write `workspace/run/<finding-id>/evolve-goal.json`. Do not write another
scope's goal. Run the exact validator command above on that file. A skill name
may appear in only one `action.ops` item. Fill `goal`, `reasoning`, `plan`,
`action`, and `feedback_to`. Keep only applicable ops and fields. A no-change
disposition stops before Optimize, Verifiter, and Judge. The runner later
deduplicates identical operations proposed by different findings.

`goal` is always an object, never a summary string. `feedback_to` is always
one non-empty string, never an object copied from diagnosis feedback. For
`no_change`, write exactly this shape with concrete explanatory strings:

```json
{
  "goal": {
    "improve_harness": {"scope": "out_of_scope"},
    "improve_skills": [],
    "avoid": "Do not create or edit a skill without policy-qualified evidence."
  },
  "reasoning": "Explain the evidence and policy decision.",
  "plan": "Leave skills unchanged.",
  "feedback_to": "diagnosis",
  "action": {
    "disposition": "no_change",
    "reason": "Explain why no operation is allowed.",
    "ops": []
  }
}
```

Each item in `action.ops` is an object. The five op names are fixed: `create`, `update`, `delete`, `merge`, `split`. Use `other` only when the action is not one of those. Each op has its own parameters. For `create`, `update`, and `delete`, the records are always under the key `skills`; never use a key named `create`, `update`, or `delete` as the record list. A create skill has a description, its sections, its dirs, and at least 3 labels. A label is a path in `skill_capabilites/skill_capabilites.json` and a weight. The core sections are overview, when_to_use, do_not_use, workflow, constraints, verification, output_format, and limitations. Workflow includes methodology, instructions, procedure, and process. State_machine is optional and is used only when states, transitions, retries, or terminal conditions add value. An update skill has a goal, a facet, `sections`, and `dirs`. Each section is `section` and `goal`. Each dir is `dir` and `goal`. When an update, merge result, or split result must remove obsolete or redundant content, list each concrete removal in optional `remove`; do not hide a removal inside a broad section goal. Names and backward-compatible aliases come from `common/skill_format.json`. `other` and `ood` name a heading or directory that is not one of those closed names. An other section also has `heading`. An other dir also has `name`. A delete skill has a reason. `merge` names the skills to combine and `into`, the resulting skill, what it covers, and its dirs. `split` names one skill and `into`, the parts, what each part keeps, and the dirs that part keeps. `other` has a description, the skills it touches, and its dirs. The example uses angle brackets only to mark fields that must be replaced. Write concrete values without angle brackets, and never copy placeholder text into any output field. Name the skills on every op from the label matching. Put the recalled skills on `improve_skills`. A cluster with no recalled skills can be a create. A cluster with recalled skills can be an update, merge, split, or delete.

For an objectively verifiable create, include the canonical `evals` directory
with a goal to capture evidence-backed positive and near-miss behavioral cases.
Do not request evals for purely subjective output unless the finding supplies
observable acceptance criteria.

Plan supporting resources explicitly. A directory goal is an authorization and
an acceptance contract, not a request for an empty folder. Request only the
resources supported by the finding:

- `references` for substantial conditional knowledge, schemas, policies, or
  source material that would distract from the main workflow. Name the subject
  and say when the skill should read it.
- `scripts` for deterministic, repeated, or error-prone transformations and
  checks. State the input, output, failure behavior, and representative fixture
  the optimizer must execute.
- `assets` for reusable starter files that are copied or adapted into the
  user's deliverable. Name the artifact and its intended use.
- `agents` only for a concrete delegated prompt. Do not request
  `agents/openai.yaml`; the runner generates that interface metadata
  deterministically after acceptance.
- `evals` for observable activation or outcome behavior, with positive and
  near-miss cases.

Leave a directory out when there is no concrete resource goal. Do not request
all resource types merely to make a skill look complete. Create, merge, and
split sessions receive a complete reference skill for file-shape guidance; its
presence is not evidence that any resource belongs in the result.
Resource goals may name paths up to four levels below their canonical resource
directory, for example `references/providers/aws.md`,
`scripts/lib/parser.py`, or `assets/templates/react-app/`. Prefer the shallowest
structure that keeps genuinely distinct modes or components understandable.

When the new skill composes existing skills, list their exact names in optional
`dependencies`; do not duplicate their instructions. When creation requires
external knowledge, request a source ledger with URL, pinned revision,
retrieval timestamp, and SHA-256 digest. Trace-derived skills use finding and
session provenance supplied deterministically by the runner.

## Applies when

This finding's records are in `diagnosis.json` and its `label-matching.json`
exists. `action.ops` is non-empty unless the validated disposition is
`no_change`. The runner slices selected operations and does not return here.
