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
distinct-session thresholds. Single-session creation is allowed only by the
configured general switch or the configured OOD exception. Otherwise choose
an evidence-backed update or a no-change disposition.

## Constraints

Do not put easy experience that the model and harness already do well into a skill. Do not set `improve_harness` inside scope. Do not recall skills again. Do not ignore a skill named in `label-matching.json`. Do not copy every op, skill, section, or dir from the example. Do not add an `other` item unless the heading or directory is outside the closed list. Do not name the same skill in two actions.

## Workflow

Write `workspace/run/<finding-id>/evolve-goal.json`. Do not write another
scope's goal. Run `one_action.py` on that file. A skill name may appear in only
one `action.ops` item. Fill `goal`, `reasoning`, `plan`, `action`, and
`feedback_to`. Keep only applicable ops and fields. A no-change disposition
stops before Optimize, Verifiter, and Judge. The runner later
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

Each item in `action.ops` is an object. The five op names are fixed: `create`, `update`, `delete`, `merge`, `split`. Use `other` only when the action is not one of those. Each op has its own parameters. `create` is a list of new skills, each with a description, its sections, its dirs, and at least 3 labels. A label is a path in `skill_capabilites/skill_capabilites.json` and a weight. The core sections are overview, when_to_use, do_not_use, workflow, constraints, verification, output_format, and limitations. Workflow includes methodology, instructions, procedure, and process. State_machine is optional and is used only when states, transitions, retries, or terminal conditions add value. `update` is a list of existing skills, each with a goal, a facet, `sections`, and `dirs`. Each section is `section` and `goal`. Each dir is `dir` and `goal`. Names and backward-compatible aliases come from `common/skill_format.json`. `other` and `ood` name a heading or directory that is not one of those closed names. An other section also has `heading`. An other dir also has `name`. `delete` is a list of skills, each with a reason. `merge` names the skills to combine and `into`, the resulting skill, what it covers, and its dirs. `split` names one skill and `into`, the parts, what each part keeps, and the dirs that part keeps. `other` has a description, the skills it touches, and its dirs. The example uses angle brackets only to mark fields that must be replaced. Write concrete values without angle brackets, and never copy placeholder text into any output field. Name the skills on every op from the label matching. Put the recalled skills on `improve_skills`. A cluster with an empty `skills` list can be a create. A cluster with recalled skills can be an update, merge, split, or delete.

## Applies when

This finding's records are in `diagnosis.json` and its `label-matching.json`
exists. `action.ops` is non-empty unless the validated disposition is
`no_change`. The runner slices selected operations and does not return here.
