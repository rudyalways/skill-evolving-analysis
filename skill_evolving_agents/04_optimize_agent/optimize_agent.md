# Optimize agent

## Session package

The default host-CLI pipeline creates a temporary allowlisted session view containing this brief as `AGENT.md`, `04_optimize_agent`, `common`, and the selected run workspace. It does not copy the whole `skill_evolving_agents` tree. The optional Docker backend uses the shared `skill-evolver-agent-runtime` image and read-only mounts the same allowlisted files.

## Run

### Input

The selected `workspace/runs/<run_id>` stays on the runner. This session's `workspace/` is a temporary directory containing one target skill directory and that skill's changelog beside it, `<skill>.md`. Explore those two. Edit the skill directory. Do not edit the changelog. Do not read or write metadata; the runner reads metadata and writes it back. The session block contains the one operation. Apply every section, directory, and removal goal in this pass.

### Output

Output is the edited skill directory in that same `workspace/`. The runner copies it back to `target/to_be_improved_skills` and leaves the changelog file behind. The runner already copied an existing source to `target/raw_skills/<skill>`. Create does not write metadata; the runner does. Merge writes the `into.skill` directory and the runner removes source names other than that result. Split writes every `into[].skill` directory and the runner removes the source unless one result keeps its name. Delete removes its skill directory from `workspace/`.

### Stop condition

Stop when that edit is written. Do not verify the edit. Do not set `feedback.action`. Retries are disabled, so this operation receives one edit session.
