# Evidence Levels

Fixed vocabulary for all artifacts in this workspace.

| Level | Name | Meaning | Example |
|:-----:|------|---------|---------|
| **L0** | README / docs | Official description, blog, issue summary | GitHub README, arXiv abstract |
| **L1** | First-pass source | Directory scan, grep, entry files | `find skills/`, import graph |
| **L2** | Module read | Key files read with line-level citations | `skill_manager_tool.py`, `proposals_lib.py` |
| **L3** | Deep path | Full subsystem walk (agent loop → compact → evolve) | skill-workshop, OpenSquilla pipeline |
| **L4** | Cross-validated | L3 + tests + CHANGELOG + second repo corroboration | — |

## Usage in frontmatter

```yaml
evidence_level: L2
```

## Honest claims

| Allowed | Not allowed |
|---------|-------------|
| "L2 evidence shows `skill_manage` CRUD" | "We read the entire codebase" |
| "L3 deep-read of proposals_lib" | "Fully analyzed all 8 repos line-by-line" |
| "Web L0 only (clone failed)" | "Verified in source" without level tag |

## Upgrade path

L0 → L1 → L2 → L3 per repo, tracked in `store/manifest.yaml` field `evidence_level`.
