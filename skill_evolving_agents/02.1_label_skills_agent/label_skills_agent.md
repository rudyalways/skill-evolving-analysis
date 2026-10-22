# Label skills agent

## Session package

The default host-CLI pipeline creates a temporary allowlisted session view containing this brief as `AGENT.md`, `02.1_label_skills_agent`, `common`, `skill_capabilites`, and the selected run workspace. It does not copy the whole `skill_evolving_agents` tree. The optional Docker backend uses the shared `skill-evolver-agent-runtime` image and read-only mounts the same allowlisted files.

## Run

The selected `workspace/runs/<run_id>` is available as `workspace`: through a temporary symlink for a host CLI or a bind mount for Docker. The capability taxonomy JSON is already in the session package. This agent runs once for the whole skill set.

### Input

```text
workspace/
└── target/
    └── to_be_improved_skills/
        ├── <skill>/
        └── maybe_many_more/
skill_capabilites/
└── skill_capabilites.json
```

### Output

Output keeps the skills in place. This agent labels each existing skill with at least 3 labels. Each label is a path in `skill_capabilites/skill_capabilites.json` and a weight. It writes `workspace/target/to_be_improved_skills_metadata/metadata.json`.

```text
workspace/
└── target/
    ├── to_be_improved_skills/
    │   ├── <skill>/
    │   └── maybe_many_more/
    └── to_be_improved_skills_metadata/
        └── metadata.json
```

The session appends a line to `workspace/logs/execution.jsonl`.

### Stop condition

Stop when `metadata.json` is written. Do not label trace clusters. Do not write the goal. Do not edit `target/to_be_improved_skills`. Do not verify a skill. Do not cut traces.
