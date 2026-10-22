# Evidence-based evaluation loop

Use this loop when the goal names `evals` and the behavior can be replayed.
It adapts Anthropic's grader, blind comparator, analyzer, benchmark, and
history patterns to the existing Optimize → Verifiter → Judge lifecycle.

## 1. Build discriminating cases

- Derive positive cases from trace evidence.
- Add near-misses that should not trigger the skill.
- Write observable expectations that cannot pass through filename or keyword
  presence alone.
- Include important correctness, completion, recovery, and verification
  outcomes.

Validate the fixture:

```bash
python3 common/skill_evaluation.py validate \
  target/to_be_improved_skills/<skill>/evals/evals.json \
  --skill <skill>
```

## 2. Execute paired runs

For every runnable case, execute the same prompt and inputs:

1. `without_skill`: use the pre-edit skill for updates, or no candidate skill
   for creates.
2. `with_skill`: use the generated candidate.

Randomize which output is called A or B and retain the hidden mapping. Keep
the model, tools, environment, input files, and execution budget equal.
Capture the complete transcript, outputs, errors, tool calls, tokens, and
wall-clock timing.

Run repeated trials when behavior is nondeterministic. Never present one
sample as a stable benchmark.

## 3. Grade evidence

For each expectation, record:

- `text`
- `passed`: boolean, with no partial credit
- `evidence`: a quote, output location, or concrete contradiction

The burden of proof is on passing. Inspect substantive output rather than
trusting the executor's claim. Extract additional factual, process, and
quality claims and verify them. Flag weak expectations that would accept a
clearly wrong output.

## 4. Compare blindly

Compare A and B without revealing which candidate produced them. Generate a
task-specific rubric covering correctness and completeness first, then
structure and usability. Expectations are supporting evidence, not a
substitute for output quality. Allow `TIE`, but do not default to it.

## 5. Analyze causation

After choosing a winner, reveal the mapping and compare both skills and
transcripts. Separate:

- instruction-following failures,
- unclear or missing skill guidance,
- missing deterministic tools,
- uncovered edge cases,
- evaluator or expectation defects.

Every recommended edit must cite evidence and explain how it could change the
outcome. Do not blame the skill for unrelated runtime failures.

## 6. Aggregate and decide

Store benchmark rows with:

- `eval_id`, `configuration`, and `run_number`
- `result.pass_rate`, `time_seconds`, `tokens`, `tool_calls`, and `errors`
- per-expectation evidence

Aggregate them with:

```bash
python3 common/skill_evaluation.py aggregate benchmark.json
```

Inspect means, variance, regressions, and errors. Judge may publish only when
the candidate passes structural checks and behavioral evidence does not show
a material regression. Preserve losing attempts and analysis for auditability.

## 7. Improve iteratively

Change the smallest causal part of the skill, rerun the same paired cases, and
retain version lineage:

- parent version
- expectation pass rate
- comparison result (`won`, `lost`, `tie`)
- whether it is the current best

Do not optimize repeatedly against a single case. Add fresh or held-out cases
when repeated iterations risk overfitting.
