# Diagnosis

Produce Label A, the demand side. This is step 2, the LabelA state.

## Experience

Analyze the derived traces and the gaps they show. Step 1, `step1-cut-traces`, writes those topic slices to `workspace/traces/derived_traces`. The raw jsonl files stay read-only in `workspace/traces/target_agent_traces`, and, when present, `workspace/traces/reference_agent_traces_optional`. Each improvement area is one label: a path under `data/skill_capabilites`, a directory or a markdown file without the suffix. Question and response carry the domain. The full trace carries the gap. Each label has a description of the problem, a confidence from 0 to 1, reasoning, and an evidence list of quotes.

## Don't

Do not invent a capability path. Do not treat a name that is not in the tree as a known leaf. Do not leave evidence as a single string. Do not label existing skills here. That is Label B.

## Must

Write `workspace/run/diagnosis.json`. The shape is `diagnosis.example.json` in this folder.

- `type` is Label A, a relative path such as `job/methodology`. Wrap a fill-in value in `<>`.
- Run `evolve-goal-checker.py`. A `type` that is not in the tree moves to `newly_detected_skill_capabilites_missing`.
- Record feedback on the format above, the content above, the framework, and the template. Template feedback is a list. Each feedback record has description, confidence, reasoning, and `evidence_list`.

## Applies when

Traces have been cut into topics, or Judge sent the run back to LabelA.
