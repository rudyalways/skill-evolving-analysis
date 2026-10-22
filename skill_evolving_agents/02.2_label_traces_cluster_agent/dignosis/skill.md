# Diagnosis

Diagnose one selected feedback finding. The runner starts this once per finding
by default; legacy mode can use one semantic cluster.

## Context

Read `slice` on `workspace/traces/derived/findings/<finding-id>/finding.json`.
That object is the whole trace: at most `max_user_turns` user rounds and
`max_tokens` of user, assistant, and error text. Diagnose from `slice.turns`
and the detector features. Do not open canonical turn files, raw logs, or tool
sidecars. When the finding lists `tool_evidence_excerpts`, read those excerpts
only. Each improvement area is one taxonomy path or an OOD proposal. Legacy
cluster mode reads `slice` inside `cluster/<cluster>/cut.jsonl` when that file
exists, and otherwise the cluster manifest.

## Constraints

Do not invent a capability path or hide a real gap under a vague fallback.
Do not load raw vendor logs or unrelated tool sidecars. Do not label existing
skills here.

## Workflow

Write only this finding's records into worker-local
`workspace/run/diagnosis.json`. The runner validates, archives, and reduces all
scoped files. The shape is `diagnosis.example.json`.

- `type` is a relative taxonomy path. `cluster` is the finding ID (or the
  legacy cluster directory).
- Run `evolve-goal-checker.py`. It validates diagnosis only; it does not edit skill metadata. A missing or empty capability taxonomy fails before the diagnosis is changed. A `type` that is not defined in the JSON moves to `newly_detected_skill_capabilites_missing`.
- For a distinct, reusable, non-duplicate OOD capability, make `type` the proposed normalized path and state plainly in `reasoning` that it should be promoted into the taxonomy. Support promotion with concrete evidence; do not weaken or omit the recommendation merely because the path is new.
- Record feedback on the format above, the content above, the framework, and the template. Template feedback is a list. Each feedback record has description, confidence, reasoning, and `evidence_list`.

## Applies when

Canonical turns and a validated finding pointer manifest exist.
