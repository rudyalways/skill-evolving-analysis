# Run guide

Two images, built from `Dockerfile.label` and `Dockerfile.optimize`. The repo stays one directory. Each image contains only that agent's skills, so a session cannot read the other agent's instructions. Both mount the same `workspace/runs/<run_id>`. The goal file there is the handoff.

## Images

The label image contains cut traces, Label A, Label B, the goal, select, the section list, and `data/skill_capabilites`.

The optimize image contains create, the out-of-distribution note, verify, judge, and the section checker. It reads the goal from the mounted run.

Neither image contains a live run. The blank layout is `workspace` on the host. A mount covers `workspace` for a real run.

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
mount="$PWD/skill_evolving_agent/workspace/runs/$id:/opt/skill-evolver/skill_evolving_agent/workspace"
docker build -f skill_evolving_agent/Dockerfile.label -t skill-evolver-label .
docker build -f skill_evolving_agent/Dockerfile.optimize -t skill-evolver-optimize .
docker run -d --name "$id-label" -v "$mount" skill-evolver-label
```

The host path is `workspace/runs/<run_id>`. Inside the container that directory is `workspace`. The container refuses to start when that path is not a mount.

## Sessions

A session is `docker exec -it "$id-label" sh`, then later `docker exec -it "$id-optimize" sh`.

A runner outside the agent starts each step. It hands the agent only that step's `skill.md`. The next step starts only after the previous step has a `done` line in `logs/execution.jsonl` and its output file is in place.

The label container cuts traces, writes Label A, Label B, and the goal, and selects skills when the action is update, merge, or split. It writes `run/evolve-goal.json` and stops. Remove that container. The host directory stays.

```bash
docker rm -f "$id-label"
docker run -d --name "$id-optimize" -v "$mount" skill-evolver-optimize
```

The optimize container takes one goal op at a time and passes `--op` to the verifier scripts. create, update, and delete name one skill. merge and split name two. On `back`, the runner re-enters that op's edit once, then moves to the next op.

Each step appends `{"step": "<step1>", "event": "<started|done|failed>", "at": "<iso8601>"}` to `logs/execution.jsonl`.

## Stop

```bash
docker rm -f "$id-optimize"
```

The container is gone. `workspace/runs/<run_id>/` is still on the host. That directory is the copy used for stats, auditing, and a later run:

- `traces/target_agent_traces` and `traces/reference_agent_traces_optional`, still read-only
- `traces/derived_traces`
- `target/to_be_improved_skills` and `target/raw_skills`
- `target/to_be_improved_skills_metadata/metadata.json`
- `run/diagnosis.json`, `run/evolve-goal.json`, and `run/verification.json`. The example for each file stays in its evolver skill
- `logs/execution.jsonl`
