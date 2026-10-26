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

A `resource_opportunity` has a separate bounded exception. Use it only when
the finding meets the configured resource confidence, occurrence, and
independent-window thresholds; records no equivalent resource; includes all
deterministic false-positive guards; and provides a non-empty contract for the
named resource. Never generalize this exception to ordinary single-session
signals.

An authored-resource lifecycle is the second bounded resource exception. When
`resource_evidence_mode` is `authored_lifecycle`, use the separately configured
authored-resource thresholds instead of the independent-window threshold. It
may qualify in one trace only when the finding records at least the configured
number of distinct lifecycle stages (normally create, successful validation or
execution, and revision or observed reuse), includes
`successful-post-authoring-validation` plus the ordinary resource guards,
records no equivalent resource, and provides the named resource contract. Do
not reject such a finding merely because `distinct_windows` is one, and do not
apply this exception to an unvalidated add-file event.

Treat every resource contract as a provenance ceiling. For a reference
opportunity with `content_available: false`, request only a navigational index,
source locator, and runtime freshness-check procedure. Do not ask Optimize to
copy source knowledge, exact headings, excerpts, or a current content digest
that the finding does not contain. A later run may enrich the reference after
the detector supplies that evidence.

For any resource contract with `content_available: true`, compare the supplied
content with the bounded `resources` rows in recalled-skill evidence. A skill
description that claims the resource exists, an empty directory, a manifest,
or a placeholder is not an applied effect when the captured content is absent
or semantically different. In that case propose the smallest update that
replaces or reconciles the resource and its verification; do not choose
`no_change` merely because SKILL.md already names the expected path.

For methodology findings, preserve only the generalized method in
`features.lesson`: prerequisites, decision rule, failure guard, minimal
successful sequence, and non-generic completion contract. Check
`features.quality.value` and the configured methodology thresholds. A
single-task methodology create must meet the explicit methodology exception
and remains provisional; cross-task consolidated evidence may be stable.
Prefer updating a recalled skill. Use `no_change` when the candidate restates
the prompt, says only to inspect/edit/test, embeds one-off paths or constants,
or adds no information beyond the recalled skill.

For trace-free inventory maintenance, treat
`duplicate_create_evidence_collision` as provenance evidence that a create was
published from a finding already applied to another current skill. Review the
complete skill documents and prefer a merge when one result can preserve both
capability surfaces without duplication. Do not reject this candidate merely
because its maintenance wrapper has no turns; choose `no_change` when the
documents establish genuinely separate responsibilities.
When the candidate names exactly one `created_skill` and one `prior_owner`,
merge into `prior_owner` by default and retire `created_skill`. Invent a new
target name only when neither existing skill can represent the combined
capability without misleading activation; explain that exception and check it
against the rest of the inventory before proposing it.

For a `resource_opportunity` finding, preserve its normalized mechanic and
script contract. A detector recommendation of `resource=scripts` and
`resource_decision=use` is rebuttable but strong evidence: choose `scripts:
use` when the boundedness, pacing, termination, non-destructive, repetition,
and fixture guards remain valid. Override it only with a concrete reason such
as an equivalent existing script, unsafe semantics, a false normalization
match, or insufficient independent invocations. Do not answer with the generic
example reason that no repeated transformation exists when the finding records
qualified repetitions.

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

For an update that changes any `SKILL.md` section, set the `evals` resource
decision to `use`, include `evals` in `dirs`, and require at least one focused
regression case sourced from the active finding. Preserve the existing eval
suite. An update that changes only resource files or performs other
directory-only maintenance may omit evals when it does not change behavior.

Plan supporting resources explicitly. Every create, update, merge result, and
split result must include `resource_plan`, with exactly one record for each of
`scripts`, `references`, `assets`, `agents`, and `evals`. Each record has
`resource`, `decision` (`use` or `omit`), a concrete `reason`, and `confidence`
from 0 to 1. A `use` decision must have a matching canonical entry in `dirs`;
an `omit` decision must not. This records both positive and negative decisions
for audit, search, and learning. A directory goal is an authorization and an
acceptance contract, not a request for an empty folder. Request only the
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
  deterministically after acceptance. The resource-plan decision for `agents`
  refers only to delegated prompt files, never to generated interface metadata.
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

For update and merge, resource planning is additive to inheritance. Preserve
and reconcile every authored file already present under `scripts`,
`references`, `assets`, delegated `agents`, and `evals`. Here `omit` means
"do not add this resource capability from the new finding"; it never means
"delete an inherited resource." If any source already contains a resource
kind, the runner changes that result's decision to `use` and adds a concrete
directory goal before Optimize. A merge must union and deduplicate source eval
cases and retain nested resource paths. Removal is allowed only through a
concrete `remove` item naming the file or resource suite and explaining why it
is obsolete. Generated `agents/openai.yaml` is excluded from inheritance
because the runner regenerates it after acceptance.

Use this exact resource-plan shape on each affected result record:

```json
"resource_plan": [
  {"resource": "scripts", "decision": "omit", "reason": "No repeated deterministic transformation is supported by the finding.", "confidence": 0.9},
  {"resource": "references", "decision": "omit", "reason": "The required knowledge fits in the main workflow.", "confidence": 0.85},
  {"resource": "assets", "decision": "omit", "reason": "The skill produces no reusable deliverable files.", "confidence": 0.95},
  {"resource": "agents", "decision": "omit", "reason": "The finding does not demonstrate a reusable delegated prompt.", "confidence": 0.9},
  {"resource": "evals", "decision": "use", "reason": "The finding supplies observable positive and near-miss behavior.", "confidence": 0.95}
]
```

The reasons above illustrate the required specificity; replace them with the
actual evidence-based decisions for the operation.

When the new skill composes existing skills, list their exact names in optional
`dependencies`; do not duplicate their instructions. When creation requires
external knowledge, request a source ledger with URL, pinned revision,
retrieval timestamp, and SHA-256 digest. Trace-derived skills use finding and
session provenance supplied deterministically by the runner.

## Applies when

This finding's records are in `diagnosis.json` and its `label-matching.json`
exists. `action.ops` is non-empty unless the validated disposition is
`no_change`. The runner slices selected operations and does not return here.
