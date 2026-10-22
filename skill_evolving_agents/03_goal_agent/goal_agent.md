# Goal agent

## Session package

The default host-CLI pipeline creates a temporary allowlisted session view containing this brief as `AGENT.md`, `03_goal_agent`, `common`, `skill_capabilites`, and the selected run workspace. It does not copy the whole `skill_evolving_agents` tree. The optional Docker backend uses the shared `skill-evolver-agent-runtime` image and read-only mounts the same allowlisted files.

## Run

An isolated copy of the selected run is available as `workspace`. The section
list, capability taxonomy, skill labels, and reduced diagnosis are present.
The runner starts a bounded pool with one session per selected finding by
default. This session writes only its assigned scope; the runner validates and
merges the outputs.

### Input

```text
workspace/
├── traces/
│   └── derived/
│       └── findings/
│           └── <finding-id>/
│               ├── finding.json
│               └── manifest.jsonl
├── run/
│   └── diagnosis.json
└── target/
    ├── to_be_improved_skills/
    │   ├── <skill>/
    │   └── maybe_many_more/
    └── to_be_improved_skills_metadata/
        └── metadata.json
skill_capabilites/
└── skill_capabilites.json
```

### Output

Select runs first for this finding. Run `recall_skills.py --clusters
workspace/traces/derived/findings --cluster <finding-id> --out
workspace/run/<finding-id>/label-matching.json`. It names existing skills whose
labels overlap the finding's diagnosis; it does not choose an action. Write the
goal to `workspace/run/<finding-id>/evolve-goal.json`. Address the diagnosed
root cause and detector evidence. Treat OOD records as real gaps and preserve
an evidence-backed promotion recommendation while choosing create or update.

```text
workspace/
└── run/
    ├── diagnosis.json
    └── <cluster>/
        ├── label-matching.json
        └── evolve-goal.json
```

Legacy cluster mode reads `cluster/<cluster>` or `cut` and uses the same output
shape.

### Stop condition

Stop when this scope's goal either has at least one valid `action.ops` item or
has a validated `no_change` disposition with an empty skill list. The runner
skips no-change scopes, deduplicates identical proposed operations,
slices selected ops, and conflict-batches overlapping skill edits. Do not edit
skills, verify a skill, cut traces, or write labels.
