# Skill select

Recall existing skills that match this evolution scope. The default scope is a
selected feedback finding; legacy runs can use a semantic cluster. This runs
before the scoped goal is written, so the action is not known yet.

## Context

### Input

This scope's finding, pointer manifest, existing skills, and metadata.

```text
workspace/
├── traces/
│   └── derived/
│       └── findings/
│           └── <finding-id>/
│               ├── finding.json
│               └── manifest.jsonl
└── target/
    ├── to_be_improved_skills/
    │   ├── <skill>/
    │   └── maybe_many_more/
    └── to_be_improved_skills_metadata/
        └── metadata.json
```

### Output

Inputs stay in place. Recall writes
`workspace/run/<finding-id>/label-matching.json`.

```text
workspace/
├── traces/
│   └── derived/
│       └── findings/
│           └── <finding-id>/
│               ├── finding.json
│               └── manifest.jsonl
├── target/
│   ├── to_be_improved_skills/
│   │   ├── <skill>/
│   │   └── maybe_many_more/
│   └── to_be_improved_skills_metadata/
│       └── metadata.json
└── run/
    └── <finding-id>/
        └── label-matching.json
```

### Matching

One scope is one pointer manifest. By default it is under
`workspace/traces/derived/findings/<finding-id>/manifest.jsonl`, with detector
details in `finding.json`. Its labels are the `type` paths and confidence
values in `workspace/run/diagnosis.json` whose `cluster` equals that finding
ID. Each existing skill's labels are `skill_types` in `metadata.json`.
For methodology findings, diagnosis must label the reusable method capability,
not the task's surface topic. Read `features.lesson.kind` and
`method_fingerprint` only to disambiguate equally scored taxonomy matches; do
not match one-off paths, commands, or constants from trajectory excerpts.
`common/recall-config.json` selects the scoring strategy.
`weighted_path_similarity` scores confidence × weight × path similarity,
supports controlled parent/specialization matches, penalizes fallbacks,
applies thresholds, and keeps top-K candidates. `exact_overlap` is the
baseline.

## Constraints

Do not choose an operation or write `evolve-goal.json`. Keep recall scoped to
the assigned finding. Leave traces, skills, metadata, and the harness
unchanged. Select only taxonomy-backed skill types and evidence-backed matches.
Prefer an existing skill when its capability path covers the methodology;
creation is reserved for a genuinely unmatched method capability.

## Workflow

Run `common/skill_type_checker.py`. Undefined paths move to
`unmatched_skill_types`. For finding scope, run `recall_skills.py --clusters
workspace/traces/derived/findings --cluster <finding-id> --out
workspace/run/<finding-id>/label-matching.json`. Use `--strategy` only for an
explicit experiment. The output records strategy, config hash, candidate
scores, and per-path contributions. No passing candidate leaves `skills`
empty.

## Applies when

The assigned finding manifest, existing skills, and metadata exist.
