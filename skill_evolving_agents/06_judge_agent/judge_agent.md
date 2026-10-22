# Judge agent

## Session package

The default host-CLI pipeline creates a temporary allowlisted session view containing this brief as `AGENT.md`, `06_judge_agent`, `common`, and the selected run workspace. It does not copy the whole `skill_evolving_agents` tree. The optional Docker backend uses the shared `skill-evolver-agent-runtime` image and read-only mounts the same allowlisted files.

## Run

### Input

The selected run is available as `workspace`. Input includes the active
verification, authoritative one-op goal, active goal copy, and any finding
evidence referenced by that goal.

### Output

Output is `feedback.action` on `workspace/run/verification.json`. `pass` is
valid only when overall and every per-skill status pass and the verification
connects the edit to the original detector evidence. When replay metrics exist,
compare before/after severity, confidence, and occurrences. Without a replay,
`pass` means structural pass only; preserve `replay.status: not_run` and do not
claim that behavior improved or invent improved metrics.
Set only `pass` or `fail`; both end the op. Retries are disabled.

### Stop condition

Stop after setting `feedback.action`. Do not check the skill again. Do not edit `target/to_be_improved_skills`. Do not return to cut traces, labeling, or the goal.
