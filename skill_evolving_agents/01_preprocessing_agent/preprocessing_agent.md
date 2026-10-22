# Preprocessing agent

## Session package

The default host-CLI pipeline creates a temporary allowlisted session view containing this brief as `AGENT.md`, `01_preprocessing_agent`, `common`, and the selected run workspace. It does not copy the whole `skill_evolving_agents` tree. The optional Docker backend uses the shared `skill-evolver-agent-runtime` image and read-only mounts the same allowlisted files.

## Run

The runner deterministically normalizes Codex, Claude Code, and Cursor logs,
detects feedback findings, deduplicates projected text, computes compact
features, and writes pointer-only manifests before any model session. This
agent runs only with `--review-clusters`. Review canonical turns and optional
semantic cluster names; never read raw vendor logs.

The deterministic work is selected by a named mining profile in
`common/preprocessing-config.json`. Strategy implementations and their
allowlisted registry are under `01_preprocessing_agent/trace_mining`.
Experiment profiles write beneath `derived/experiments/<profile>` and are not
inputs to this review or to later agents.

### Input

```text
workspace/traces/derived/
├── normalized/
│   ├── turns/
│   │   └── <trace-id>.json
│   └── tool_evidence/
│       └── <trace-id>.jsonl
├── features/
│   ├── trace-features.jsonl
│   └── dedup-manifest.jsonl
├── signals/
│   ├── findings.jsonl
│   └── patterns.jsonl
├── findings/
│   └── <signal-id>/
│       ├── finding.json
│       └── manifest.jsonl
└── cluster/
    └── <cluster>/
        ├── manifest.jsonl
        └── representatives.jsonl
```

### Output

When a deterministic cluster name is unclear, rename only that cluster
directory and update every `cluster` field in its `manifest.jsonl`. Keep trace
IDs, turn paths, scores, normalized turns, evidence, and feature files
unchanged.

```text
workspace/traces/derived/cluster/
└── <clear-cluster-name>/
    └── manifest.jsonl
```

Each manifest record points to a pretty canonical turn. Read detailed tool
evidence only when the turn's `tool_summary.evidence_path` is non-null and the
cluster meaning depends on tool execution.

### Stop condition

Stop after any unclear deterministic names have been improved and every
manifest field matches its directory. Do not normalize, copy, or label traces.
