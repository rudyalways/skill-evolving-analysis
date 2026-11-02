# Trace-mining scenarios, reflection bank, and reasoning bank

## Why this exists

A trace can contain a reusable skill in several different shapes. Mining only
one shape — usually a clean failure followed by a successful retry — misses
skills that appear as:

- a correction after a failed action;
- a reasoning pivot ("wait", "actually", "let me think", "another approach");
- a plan revision after new evidence;
- a repeated instruction that eventually changes behavior;
- a verified multi-step workflow;
- a reference or asset reused across turns;
- a completion-contract repair;
- a critical-path decision;
- a no-change case that must remain negative evidence.

## Scenario taxonomy

| Scenario | Trigger | Required evidence | Negative case |
|---|---|---|---|
| `failure_recovery` | failed action | related repair + revalidation of the original failure | patch/import success alone |
| `reasoning_pivot` | reflection cue | changed action + later successful verification | reflective text with unchanged action |
| `direction_pivot` | explicit alternative | changed path + outcome | prose-only "maybe" |
| `verified_workflow` | modify + verify phases | ordered phases + completed verification | generic phase order with no gap |
| `critical_path` | ordering/deadline decision | concrete decision + outcome | vague prioritization |
| `completion_contract` | output/acceptance requirement | missing contract + verified fix | session completed only |
| `knowledge_acquisition` | inspect/search before change | new evidence + changed action | search with no use |
| `reference_reuse` | repeated source reads | cross-turn/session source root | one incidental read |
| `asset_reuse` | repeated starter/template use | repeated authored asset evidence | one copy |
| `user_correction` | correction-heavy turns | behavior change + verification | user frustration only |
| `repeated_instruction` | repeated user asks | short instruction-like texts + changed behavior | long completion reports |
| `unresolved_loop` | keep-going/retry | loop + eventual terminal state | deliberate sleep/wait |
| `no_change` | no gap / already applied | diagnosis/evidence proof | forced edit |

## Reflection bank

Each selected finding with reflection cues or a recovery lesson is written to:

```text
traces/derived/signals/reflection-bank.jsonl
```

Entry fields:

```json
{
  "reflection_id": "reflection-sig-...",
  "finding_id": "sig-...",
  "detector": "method-functional-reflection",
  "scenario": "reasoning_pivot",
  "marker_categories": ["reconsider", "pivot"],
  "cue_phrases": ["wait", "another approach"],
  "reflection_quote": "...",
  "rule": "...",
  "verified_recovery": false
}
```

Cues are extracted from:

- `wait`, `hold on`, `actually`;
- `let me think`, `let me reconsider`;
- `on second thought`, `not quite`, `hmm`;
- `no, wait`, `no, let me`;
- `instead`, `another approach`, `different approach`;
- error awareness, uncertainty, diagnosis, and verification markers.

Cue text alone is not a finding. The functional-reflection detector requires a
changed action and a later successful check.

## Reasoning bank

All findings with a lesson are written to:

```text
traces/derived/signals/reasoning-bank.jsonl
```

It records:

- scenario;
- lesson kind and rule;
- failure/verification signatures;
- verified recovery;
- confidence;
- evidence count.

The reasoning bank is retrieval/analysis material. It is not a gold label.

## Scenario coverage

Each preprocessing run writes:

```text
traces/derived/signals/scenario-coverage.json
```

It records which scenarios occurred and how many findings/reflections were
produced. Phase metrics expose the same counts under `mining`.

## Recall integration

Recall queries include:

- finding failure signature;
- lesson and reflection text;
- task context;
- evidence quotes.

Documents are section-aware: head plus a sample of every `##` section. Lexical
matches are merged with embedding matches. Matching records `query_context`,
`document_strategy`, `truncated_documents`, and `hybrid_lexical`.

## External methods considered

- **Skill-DisCo** — distills successful traces into parameterized control-flow
  subgraphs and compiles executable skills.
  <https://arxiv.org/abs/2606.26669>
- **ReuseRL / SkillRL** — extracts a shared skill dictionary using an MDL
  objective and penalizes idiosyncratic behavior.
  <https://arxiv.org/abs/2605.31509>
- **ReasoningBank** — stores and retrieves reasoning experiences rather than
  raw trajectories.
  <https://www.research.google/blog/reasoningbank-enabling-agents-to-learn-from-experience/>
- **OpenClaw-RL** — trains agents from interaction rather than static traces.
  <https://arxiv.org/abs/2603.10165>
- **“A Lesson Is an Untested Counterfactual”** — warns that stored failure
  lessons encode untested causal claims; a reflection bank must retain the
  evidence and verification status.
  <https://zenodo.org/records/22798759>

## Design rule

```text
successful trace -> workflow candidate
failure trace -> repair/revalidation candidate
reflection cue -> pivot candidate only with action change and verification
repeated evidence -> reference/asset candidate
no gap -> no_change, not a forced skill
```

The reflection bank must never be treated as a validated skill library.
