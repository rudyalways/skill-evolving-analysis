# Run guide

One run is one container. The image holds the program. The run directory on the host holds the data. Delete the container when the session is finished. The host directory stays.

## Image

The image contains:

- `evolver_skills`, including `reference-skill_format`
- `data/skill_capabilites`

It does not contain a live run. The blank layout is `workspace` on the host. The image copies that layout. A mount covers `workspace` for a real run.

## Real run

On the host, copy the blank layout and fill the inputs:

```bash
id=run-001
dest=skill_evolving_agent/workspace/runs/$id
rm -rf "$dest"
mkdir -p "$dest"
for path in skill_evolving_agent/workspace/*; do
  [ "$(basename "$path")" = runs ] && continue
  cp -a "$path" "$dest/"
done
```

Put the raw jsonl files in `runs/$id/traces/target_agent_traces`. An optional reference set goes in `runs/$id/traces/reference_agent_traces_optional`. Put the existing skills in `runs/$id/target/to_be_improved_skills`.

`runs/$id` is the real workspace.

## Start

From the repo root:

```bash
docker build -f skill_evolving_agent/Dockerfile -t skill-evolver .
docker run -d --name "$id" \
  -v "$PWD/skill_evolving_agent/workspace/runs/$id:/opt/skill-evolver/skill_evolving_agent/workspace" \
  skill-evolver
```

The host path is `workspace/runs/<run_id>`. Inside the container that directory is `workspace`. The container refuses to start when that path is not a mount.

## Session

The container stays up. The agent session is `docker exec -it <run_id> sh`.

A runner outside the agent starts each step. It hands the agent only that step's `skill.md`. The next step starts only after the previous step has a `done` line in `logs/execution.jsonl` and its output file is in place. After the goal, the op picks step 5.1 or step 5.2. On `back`, the runner re-enters `action.to`.

Each step appends `{"step": "<step1>", "event": "<started|done|failed>", "at": "<iso8601>"}` to `logs/execution.jsonl`.

## Stop

```bash
docker rm -f "$id"
```

The container is gone. `workspace/runs/<run_id>/` is still on the host. That directory is the copy used for stats, auditing, and a later run:

- `traces/target_agent_traces` and `traces/reference_agent_traces_optional`, still read-only
- `traces/derived_traces`
- `target/to_be_improved_skills` and `target/raw_skills`
- `target/to_be_improved_skills_metadata/metadata.json`
- `run/diagnosis.json`, `run/evolve-goal.json`, and `run/verification.json`. The example for each file stays in its evolver skill
- `logs/execution.jsonl`
