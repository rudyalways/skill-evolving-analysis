# Cut traces

Cut raw traces into related topics. This is step 1, the CutTraces state. Step 2 reads the slices. Do not label them here.

## Experience

The raw traces are read-only jsonl files in `workspace/traces/target_agent_traces`, and, when present, `workspace/traces/reference_agent_traces_optional`. A topic slice is the traces that belong to one subject. A trace that fits no subject stays in `unassigned`. Step 2, `step2-dignosis`, reads `workspace/traces/derived_traces`.

## Don't

Do not edit or delete the raw jsonl files. Do not drop a trace that fits no topic. Do not assign a capability label. That is step 2. Do not copy the example topic when the traces support a different cut. List length is not fixed.

## Must

Write one file per topic under `workspace/traces/derived_traces`, plus `unassigned.json` when any trace fits no topic. Each topic file has `topic`, `source`, and `traces`. `source` is `target_agent_traces` or `reference_agent_traces_optional`. `traces` names the raw files in that slice. `unassigned` has `source`, `trace`, and `reason`. The shape is `cut-traces.example.json` in this folder. Wrap fill-in values in `<>`.

## Applies when

Raw traces are in the traces directory. This is the label agent.
