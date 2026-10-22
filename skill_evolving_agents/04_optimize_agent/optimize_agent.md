# Optimize agent

## Session package

The default host-CLI pipeline creates a temporary allowlisted session view containing this brief as `AGENT.md`, `04_optimize_agent`, `common`, and the selected run workspace. It does not copy the whole `skill_evolving_agents` tree. The optional Docker backend uses the shared `skill-evolver-agent-runtime` image and read-only mounts the same allowlisted files.

## Run

### Input

The selected `workspace/runs/<run_id>` is available as `workspace`: through a temporary symlink for a host CLI or a bind mount for Docker. Input includes one authoritative op goal at `workspace/run/<cluster>/ops/<op>/evolve-goal.json`, its active compatibility copy at `workspace/run/evolve-goal.json`, and the skills that op lists under `workspace/target/to_be_improved_skills`. The active file contains exactly one `action.ops` item. When several findings update the same skill, the runner has already merged the top edits into that one item. `bundle.selected` names those source edits. Apply every section and directory goal in this pass. Do not start another session per source edit. A return session also reads `feedback.action` `back` in `workspace/run/verification.json`. The section list comes from the session package.

### Output

Output is the edited skills under worker-local `workspace/target/to_be_improved_skills`. Before update, delete, merge, or split, copy every source skill to `workspace/target/raw_skills`. Create writes that skill's labels into `workspace/target/to_be_improved_skills_metadata/metadata.json`. Merge writes the `into.skill` result and removes source names other than that result. Split writes every `into[].skill` result and removes the source unless one result keeps its name. Delete removes its named skill. An out-of-distribution gap stays on `newly_detected_skill_capabilites_missing` in `workspace/run/diagnosis.json`. The runner executes operations with disjoint affected skill names in parallel copies; conflicting operations run in later batches. A single reducer merges validated skills, snapshots, metadata, verification, statuses, and logs into the authoritative run.

### Stop condition

Stop when that edit is written. Do not verify the edit. Do not set `feedback.action`. A later session edits this same op again only when Judge has set `back`.
