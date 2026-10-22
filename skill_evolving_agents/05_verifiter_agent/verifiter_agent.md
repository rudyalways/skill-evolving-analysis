# Verifiter agent

## Session package

The default host-CLI pipeline creates a temporary allowlisted session view containing this brief as `AGENT.md`, `05_verifiter_agent`, `common`, and the selected run workspace. It does not copy the whole `skill_evolving_agents` tree. The optional Docker backend uses the shared `skill-evolver-agent-runtime` image and read-only mounts the same allowlisted files.

## Run

### Input

The selected run is available as `workspace`. Input includes the one-op goal,
its active copy, `workspace/run/verification-input.json`, raw skills, the
edited skills, and—when the scope is a
feedback finding—`workspace/traces/derived/findings/<finding-id>/finding.json`
plus its canonical-turn pointers. Because the active goal contains one op,
checker `--op` is 1. A `bundle` on that goal means several same-skill edits
were already merged into this op. Check the merged sections once. Do not
start a verification per source edit.

### Output

Output is active `workspace/run/verification.json` for that op: the SHA-256
reference to the verification input, a status and evidence for all eight
input-bound steps, normalized weighted scores and causal reasoning, the
runner-owned changelog copied from
`workspace/run/changelog.json`, overall and per-skill status, feedback, and
`ood`. Verify that the edit addresses the
detector evidence and diagnosed root cause. Define the expected before/after
behavior for a replay. If a new replay is available, rerun the targeted
detector and record whether severity, confidence, or occurrence count improved;
record `feedback.replay.available` as true and put measured objects in `before`
and `after`. Otherwise record `available: false`, `status: not_run`, a reason,
and null before/after values. A structural pass without replay does not
demonstrate behavioral improvement. Do not claim the old immutable trace itself
changed. `feedback.action` remains null for Judge.

### Stop condition

Stop when that file is written. Do not edit the skills. Leave the other ops for their own loop.
