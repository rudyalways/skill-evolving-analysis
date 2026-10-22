# Label traces cluster agent

## Session package

The host pipeline creates an allowlisted session containing this brief as
`AGENT.md`, this stage directory, `common`, `skill_capabilites`, and an isolated
run workspace. The optional Docker backend mounts the same package.

## Run

The runner starts a bounded pool with one session per selected finding by
default. This session handles only its assigned finding. Legacy
`--evolution-unit cluster` runs keep cluster scope.

### Input

```text
workspace/traces/derived/findings/<finding-id>/
├── finding.json
└── manifest.jsonl
skill_capabilites/skill_capabilites.json
```

Read `finding.json` only. Its `slice` is the trace: at most five user rounds
and 2000 tokens of user, assistant, and error text. Diagnose the skill gap
from `slice.turns` and the detector features. Do not open `manifest.jsonl`
turn paths, canonical turns, raw logs, or tool sidecars. When the finding
lists `tool_evidence_excerpts`, those excerpts are the only tool text. Record
OOD without hesitation when no taxonomy path fits.

### Output

Write this finding's scoped records to `workspace/run/diagnosis.json`. The
runner validates and reduces all workers afterward. In legacy cluster mode,
read `slice` in `cluster/<cluster>/cut.jsonl` when that file exists, and
otherwise the cluster manifest. Do not open canonical turns. Raw vendor traces
are unavailable.

### Stop condition

Stop after this finding's diagnosis exists. Do not label existing skills,
write a goal, edit skills, verify a skill, or cut traces.
