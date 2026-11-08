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

For every `resource_opportunity`, `no_change` requires direct bounded content
evidence for every behavioral clause added by the current contract. File
presence, path names, byte counts, hashes, fixture names, and SKILL.md claims
do not prove semantic equivalence. If a relevant resource preview is empty or
truncated, or a new contract clause is absent from the bounded resource text,
propose the smallest update and regression eval; never infer implementation
from a large file size or from neighboring fixtures.

For methodology findings, preserve only the generalized method in
`features.lesson`: prerequisites, decision rule, failure guard, minimal
successful sequence, and non-generic completion contract. Check
`features.quality.value` and the configured methodology thresholds. A
single-task methodology create must meet the explicit methodology exception
and remains provisional; cross-task consolidated evidence may be stable.
Prefer updating a recalled skill. Use `no_change` when the candidate restates
the prompt, says only to inspect/edit/test, embeds one-off paths or constants,
or adds no information beyond the recalled skill.

For `objective_verifier_failure` or `cross_task_portable_preflight`, do not
write a workflow that assumes the hidden objective verifier is callable during
task execution. Preserve `failure_classes`, `verifier_visibility`, and the
portable-preflight rule. When `features.lesson.resource_hint` requests a
script, set `scripts: use` and require a config-driven validator with no
benchmark-specific constants: artifact path plus task-derived constraint spec
as input, structured violations as output, nonzero exit on violations, and
representative fixtures for every evidenced failure class. The script is a
local preflight, not a replica of or bypass for the hidden verifier.
When the current trace used or read a recalled skill and still produced an
`objective_verifier_failure`, treat that residual as behavioral evidence that
the current implementation is insufficient. Existing prose, fixture names,
hashes, or a validator that reports clean cannot justify `no_change` when the
diagnosis records a confident missing capability and the lesson is not an
`evaluation-contract-conflict`; choose the smallest update plus a focused eval.
Do not keep enlarging a broad audit or preflight skill when the residual is an
execution defect and the trace already spent substantial work diagnosing it.
If the applicable skill was read, its checker or scripts were not actually
executed, the same objective residual survived, and the missing knowledge is a
portable domain procedure (for example coordinate-frame-correct export),
prefer a focused execution skill with a deterministic helper and bounded evals.
Use update only when the recalled skill is itself the correct execution
surface; otherwise create the narrower skill and keep the broad preflight as a
consumer. This is a general audit-versus-repair separation rule, not permission
to encode benchmark names, hidden thresholds, or one trace's constants.
When an activated execution skill's checker ran but its bundled producer did
not, and the trace exhausted substantial time or tool calls before producing an
incomplete artifact, require a producer-first bounded-execution update. The
workflow must execute the applicable bundled producer immediately after
confirming its source and output arguments, validate the required artifact
manifest, and allow ad-hoc replacement code only after a concrete producer
failure. Require a bounded fallback sequence and a focused eval proving both
early producer execution and complete artifact-set delivery; do not solve the
timeout by weakening verification or encoding one benchmark's file names.
When that focused create claims to export, generate, transform, repair, or
otherwise produce an artifact, its `scripts` directory goal must include the
deterministic producer itself, with source inputs, artifact outputs,
frame/transform behavior, and failure semantics. A checker-only script is not
an execution surface and is invalid even if the skill prose says “export.” The
producer and an independent checker may be separate scripts or clearly
separated modes of one script; require fixtures and evals for both production
and rejection behavior.
The producer must directly consume the source format named by the skill's
activation trigger. Do not accept a helper that requires the agent to first
hand-author a normalized intermediate representation containing the same
geometry or semantics. For source-code scenes or modules, require an
end-to-end fixture in that native format and a one-command producer invocation
from source to requested artifact. Any generated manifest may record the run,
but it cannot be a prerequisite manually reconstructed by the agent.
When the lesson sets `oracle_independence_required`, prohibit a
self-referential validator: an expected value produced by the same code path
as the submitted value cannot establish correctness. Require either a second,
independently implemented recomputation path or task-grounded metamorphic
checks such as invariance, bounds, reversibility, or agreement across suitable
representations. If neither is possible, require the constraint to be reported
as unverifiable rather than manufacturing an expected value.
If the lesson sets `local_objective_conflict` or the learning disposition is
`evaluation-contract-conflict`, do not encode the hidden expected value and do
not request another skill rewrite merely to chase the posthoc oracle. Propose
`no_change` unless the finding contains a new task-visible convention,
independent input, or portable metamorphic rule that the current recalled skill
does not already preserve; describe the unresolved specification/oracle gap in
the reason.

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
contract source. Do not run, locate, or open a validator. The host freezes and
validates the candidate after the session. If the contract is invalid, the host
may start at most one focused repair session with a compact diagnostic; rewrite
only the named Goal file in that session and stop.

## Workflow

Write `workspace/run/<finding-id>/evolve-goal.json`. Do not write another
scope's goal. A skill name may appear in only one `action.ops` item. Fill `goal`, `reasoning`, `plan`,
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

Each item in `action.ops` is an object whose operation name is the non-empty
string value of the `op` key. The five op names are fixed: `create`, `update`,
`delete`, `merge`, `split`. Use `other` only when the action is not one of
those. For `create`, `update`, and `delete`, put every target record in the
sibling `skills` list; the records are always under the key `skills`. The
canonical envelope is
`{"op":"update","skills":[{"skill":"concrete-skill", ...}]}`. Never use
`{"update":{"skills":[...]}}`, `{"update":[...]}`, or flatten a singular
skill record onto the operation object. Each op has its own parameters. A
create skill has a description, its sections, its dirs, and at least 3 labels. A label is a path in `skill_capabilites/skill_capabilites.json` and a weight. The core sections are overview, when_to_use, do_not_use, workflow, constraints, verification, output_format, and limitations. Workflow includes methodology, instructions, procedure, and process. State_machine is optional and is used only when states, transitions, retries, or terminal conditions add value. An update skill has a goal, a facet, `sections`, and `dirs`. Each section is `section` and `goal`. Each dir is `dir` and `goal`. When an update, merge result, or split result must remove obsolete or redundant content, list each concrete removal in optional `remove`; do not hide a removal inside a broad section goal. Names and backward-compatible aliases come from `common/skill_format.json`. `other` and `ood` name a heading or directory that is not one of those closed names. An other section also has a `heading`. An other dir also has a `name`. A delete skill has a reason. `merge` names the skills to combine and `into`, the resulting skill, what it covers, and its dirs. `split` names one skill and `into`, the parts, what each part keeps, and the dirs that part keeps. `other` has a description, the skills it touches, and its dirs. Write concrete values without angle brackets or placeholders. Put recalled skills on `improve_skills`. A cluster with no recalled skills can be a create. With recalled skills, create is also legal when the recalled item is only an audit, preflight, or consumer and the missing capability is a distinct reusable execution surface. Explain why update would repeat the failed abstraction and give the new focused skill non-overlapping triggers. Otherwise use update, merge, split, or delete.

For an update, add optional `description_goal` whenever the evidence adds or
removes a trigger, capability, artifact type, failure mode, or other
retrieval-relevant scope. State how the one-line frontmatter description must
change so low-cost recall can discover the evolved behavior. Do not claim a
description change for wording-only cleanup.

For both create and update, `sections` is always a JSON list. Every section
item uses exactly the keys `section` and `goal`, both with non-empty strings.
Never use a section-name object map, and never use `content` in place of
`goal`.

Every record inside an operation's `skills` list must identify its target with
the exact key `skill` and a non-empty skill name. This applies to creates as
well as updates and deletes. Do not substitute `name`, `skill_name`, or a
description for this required identity field.

Each label record uses exactly `type` and `weight`. Set `type` to the complete
taxonomy path, such as `job/verification/evidence`, and set `weight` to a
number from 0 to 1. Do not use `label`, `path`, or a split taxonomy dimension
in place of `type`.

Every optional `remove` entry is a non-empty string that names the exact
content or resource being removed and explains why it is obsolete. Do not put
objects in `remove`.

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

When an update or merge source already exceeds the configured SKILL.md
progressive-disclosure threshold, set `references` to `use` and include a
`references` directory goal. Require Optimize to move substantial conditional
schemas, modes, and worked examples into discoverable reference files while
keeping activation, the concise core workflow, constraints, and verification
in SKILL.md. This is required maintenance for the edited result, even when the
new finding itself would otherwise fit in prose; do not grow an oversized
catch-all skill further.

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
