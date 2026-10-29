# Benchmark design: golden skills, simulators, and multi-turn traces

This document turns the source registry into an executable benchmark design.
It covers final-stage golden skills, generated tasks, user simulators,
multi-turn traces, and internal-stage golden artifacts.

See [benchmark-source-registry.md](benchmark-source-registry.md) for candidate
sources and the authority/eligibility rules.

## 1. Treat a skill as four benchmark artifacts

A skill is not only a markdown file. Split it into parts with different
visibility:

| Skill part | Benchmark role | Visible to worker? |
|---|---|---|
| `description`, `when_to_use`, inputs, preconditions | Task specification | Yes |
| `workflow`, decision points, failure handling | Golden solution / reference | No |
| `verification`, assertions, evals | Oracle for simulator and judge | No |
| Examples, fixtures, resources | Environment and task seeds | Partly |

This supports two benchmark modes:

### A. Authoring benchmark

Input: evidence, existing skills, constraints, and available resources.

Output: a new or updated skill.

Golden: the complete reviewed skill, including workflow, verification,
resources, and evals.

What is measured:

- was the right capability gap identified;
- was the minimum sufficient operation chosen;
- did the authored skill preserve existing behavior;
- do the verification assertions and evals actually cover the change;
- are resources used rather than speculative.

### B. Execution benchmark

Input: a task card derived from the visible skill sections.

Output: work performed by the agent.

Golden: hidden workflow and verification. The simulator and judge evaluate
observable outcomes against verification, not against exact prose.

What is measured:

- task success;
- verification pass;
- forbidden-action and safety violations;
- recovery after failure;
- user satisfaction;
- turns, tool calls, tokens, and wall time.

Do not expose both the workflow and verification to the worker. That leaks both
the solution and the test.

## 2. Golden skill bundle

A benchmark-ready golden skill should be a directory:

```text
golden-skill/
  SKILL.md
  task-cards/
    001.json
    002.json
  environment/
    fixtures/
    tool-contracts/
    initial-state/
  simulator/
    personas.json
    scenario-facts.json
  stage-goldens/
    preprocessing.json
    diagnosis.json
    recall.json
    goal.json
    optimize.json
    verification.json
    judge.json
  review/
    sources.json
    reviewers.json
    decisions.json
```

`SKILL.md` remains canonical. The surrounding files make it executable and
reviewable.

### Golden grading

Every artifact carries provenance and review state:

```json
{
  "origin": "expert | reference_run | counterfactual | contract | agent_synthetic",
  "confidence": "contract | draft | silver | gold",
  "sources": ["source-id"],
  "reviewers": [
    {"role": "domain_expert", "name": "..."},
    {"role": "user_advocate", "name": "..."}
  ],
  "notes": "..."
}
```

Agent-authored drafts are not gold. Contract invariants can be gold without
domain review; semantic decisions cannot.

## 3. Generate related tasks from the golden skill

Extract a task contract before generating tasks:

- required inputs and preconditions;
- required tools and resources;
- expected observations;
- verification assertions;
- allowed and forbidden actions;
- failure, escalation, and stop conditions.

Then apply mutation operators:

| Operator | Example |
|---|---|
| Slot substitution | different destination, repository, app version, dataset |
| Context variation | missing input, ambiguous request, conflicting constraints |
| Progressive disclosure | user reveals requirements across turns |
| Tool failure | timeout, permission error, partial result |
| Near miss | similar task that should use a different skill |
| Negative task | out of scope; expected refusal or no-change |
| Adversarial user | asks for a shortcut, unsafe action, or fabricated result |
| Recovery task | first attempt fails; agent must recover and verify |

Task card:

```json
{
  "task_id": "travel-plan-003",
  "source_skill": "trip-planning",
  "visible_inputs": {},
  "environment": "sandbox-or-simulator",
  "expected_outcome": "verification-pass",
  "allowed_actions": [],
  "forbidden_actions": [],
  "stop_conditions": [],
  "seeds": [1, 2, 3]
}
```

Hold out generator seeds and task variants before tuning.

## 4. User simulator

The simulator represents the person who owns the task, not the evaluator.

It needs:

- persona and communication style;
- a goal, constraints, and hidden facts;
- a response policy for questions;
- a tool/environment simulator or real sandbox;
- the verification section as a private oracle;
- stop conditions: success, failure, budget, safety violation.

It must not:

- reveal the verification rubric;
- tell the agent the expected workflow;
- accept unsupported claims;
- silently repair the agent's work.

When the agent claims success, the simulator checks verification and returns
only observable feedback:

> "The itinerary still has an impossible transfer time. Fix it and show the
> revised schedule."

Not:

> "You failed assertion V3."

## 5. Multi-turn trace generation

For each task, generate several traces:

```text
task seed
  -> simulator persona
  -> worker agent
  -> simulator response / tool result
  -> ... repeated turns ...
  -> final verification
  -> judge
```

Variants:

- cooperative user;
- vague user;
- changing requirements;
- impatient user;
- adversarial user;
- missing information;
- environment failure;
- near-miss or out-of-scope request.

Record messages, tool calls, tool results, state changes, verification checks,
turn count, token/call cost, and final judgment.

Freeze a held-out trace set before changing prompts or models.

## 6. Final-stage golden

There are two valid interpretations:

1. **Authoring final stage:** the full reviewed skill bundle is golden.
2. **Execution final stage:** the hidden workflow plus verification is golden;
   the simulator and judge evaluate the worker against it.

Acceptable alternatives are allowed. Different valid workflows can pass the
same verification.

## 7. Internal-stage goldens

Internal stages do not need to wait for a complete final benchmark. Use a
portfolio of methods with explicit confidence levels.

| Method | Produces | Confidence |
|---|---|---|
| Contract invariants | Schema validity, policy gates, idempotency, dedupe, atomic publish | High |
| Deterministic stage outputs | Preprocessing, signal detection, selection, gate decisions | High |
| Reference-pipeline distillation | Intermediate artifacts from a strong, human-reviewed run | Medium |
| Backward annotation from final golden | Evidence spans → diagnosis → goal → diff | Medium |
| Counterfactual mutation | Perturb one boundary; expected stage change | High for synthetic cases |
| Cross-stage consistency | Diagnosis justifies goal; goal justifies diff; diff satisfies verification | Medium |
| Expert trace annotation | Humans label diagnosis, goal, verification decisions | High after adjudication |
| Downstream outcome | Final success as weak supervision | Low/medium |

### Reference-pipeline distillation

Run a strong reference configuration on golden traces, including human
intervention. Freeze:

- canonical turns and selected evidence;
- findings and confidence;
- diagnosis gaps and evidence references;
- recalled skills;
- goal operations and resource decisions;
- diff and resource files;
- verification result and judge decision.

Then review every stage. These are **reference artifacts**, not automatic gold.

### Backward annotation

Start from the final reviewed skill and ask:

- which evidence supports each diagnosis gap;
- which gap requires this operation instead of no-change;
- which workflow section or resource satisfies the gap;
- which verification assertion fails if the change is absent.

This aligns internal labels to one reviewed final artifact.

### Counterfactual stage goldens

Mutate one boundary at a time:

- remove one evidence span → diagnosis confidence drops or rejects;
- duplicate an existing resource → create becomes no-change or merge;
- remove a skill behavior → update becomes justified;
- two skills cover the same source → merge candidate;
- two independent workflows share one skill → split candidate;
- a skill has post-creation non-use and full subsumption → delete candidate;
- replay the same finding → idempotent no-change.

These are cheap, exact, and reusable across workflows.

### Cross-stage constraints

Use contracts as internal oracles:

```text
diagnosis gap type
  -> allowed goal operation
  -> required resource plan
  -> required verification assertions
  -> expected judge outcome
```

Examples:

- a no-gap diagnosis cannot justify a create operation;
- `references: use` must produce an authored reference;
- a behavioral claim without replay must remain unverified;
- a merge source must be removed; a split source must be removed after both
  parts are produced;
- a delete candidate must pass retirement evidence and archive rollback.

## 8. Review and scoring

Final-stage execution:

- verification pass/fail;
- task completion;
- safety and forbidden-action violations;
- recovery after failure;
- turns, tool calls, tokens, wall time;
- simulator satisfaction;
- human spot-check agreement.

Internal stages:

- contract validity;
- diagnosis precision/recall;
- goal operation and resource precision;
- optimize diff and resource compliance;
- verification/judge accuracy;
- idempotency and replay behavior;
- cross-stage consistency.

Report simulator-human agreement and look for reward hacking. A simulator must
not be satisfiable by confident prose or repeated claims.

## 9. Current implementation and gaps

Implemented:

- `evaluation/benchmark_core.py` — stage adapters, golden case runner,
  contract validation, review grades, HTML dashboard.
- `evaluation/cases/golden/` — six proposed cases covering create, update,
  merge, split, delete, and no-change.
- Draft/silver/gold review gates. Agent-authored cases are `draft`;
  `--require-gold` requires two independent reviewers with domain-expert and
  user-advocate roles.

Not implemented yet:

- generated task cards from a golden skill;
- user simulator and environment/tool simulator;
- multi-turn trace generation and trace corpus;
- stage-golden bundles and adjudication workflow;
- simulator-human agreement measurement;
- executable sandbox adapters for software, SEO, travel, and app operation.

## 10. First build

1. Pick one domain with executable verification: software/CLI or SEO on a test
   site.
2. Write 3 golden skills with visible, workflow, verification, and eval
   sections.
3. Generate 10 task cards per skill with the mutation operators.
4. Build one simulator per task family and a tool/environment adapter.
5. Run 3 seeds × 3 personas and freeze held-out traces.
6. Build internal goldens from contracts and counterfactuals first, then
   reference runs, then expert annotation.
7. Review final-stage goldens and only the internal artifacts that affect
   acceptance.

The discipline is:

> Worker sees the task. Simulator sees verification. Golden workflow stays
> hidden. Internal-stage labels carry provenance.
