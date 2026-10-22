# Verifiter agent

## Session package

The default host-CLI pipeline creates a temporary allowlisted session view containing this brief as `AGENT.md`, `05_verifiter_agent`, `common`, and the selected run workspace. It does not copy the whole `skill_evolving_agents` tree. The optional Docker backend uses the shared `skill-evolver-agent-runtime` image and read-only mounts the same allowlisted files.

## Run

### Input

The selected run is available as `workspace`. The runner starts one verifier
request per affected skill. Each request embeds that skill's complete concrete
verification-input JSON directly in the prompt. Input also includes the one-op goal,
its active copy, raw skills, the
edited skills, and—when the scope is a feedback finding—the finding files
listed under the embedded input's `checks.step3.evidence.findings`, plus
their canonical-turn pointers. Because the active goal contains one op,
checker `--op` is 1. A `bundle` on that goal means several same-skill edits
were already merged into this op. Check the merged sections once. Do not
start a verification per source edit.

### Output

The prompt embeds a complete one-skill output JSON shape. Return only a JSON
object in that shape; do not write `workspace/run/verification.json`.
The runner parses and validates the response, retries the same request only for
malformed or contract-invalid JSON, and then aggregates all validated skill
responses into `workspace/run/verification.json`. Optimization retries remain
disabled. The output contains the SHA-256 reference to the verification input,
a status and evidence for all eight
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

The runner archives this output beside the one-op goal, verification input,
dated changelog, and terminal `judge.json`. It records verification phase
events before and after this stage; skipped or failed stages receive explicit
marker artifacts.

### Stop condition

Stop after returning the JSON object. Do not edit the skills. Leave the other
skills and ops for their own requests.
