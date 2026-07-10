# Store — Persistent Research Archive

All research artifacts (past and future) are recorded on disk under this workspace.
Nothing lives only in chat history.

## Layout

```
store/
├── README.md                 ← this file
├── manifest.yaml             ← machine-readable catalog of ALL artifacts
├── sessions/                 ← per-session research logs (what was done, when, evidence level)
├── snapshots/                ← frozen exports (optional HTML/JSON dumps)
└── protocols/
    ├── recording.md          ← how to record future work
    └── evidence-levels.md    ← L0–L4 definitions

notes/                        ← primary analysis documents (human-readable)
├── synthesis/                ← cross-cutting analysis
├── daily/                    ← session/day logs
└── repos/                    ← per-repo deep dives (under synthesis/repos/)

data/
├── inbox/                    ← drop zone for new raw inputs
├── raw/                      ← immutable filed originals
├── processed/                ← extractions, tables, manifest copies
└── archive/                  ← symlink mirror / session bundles

topics/                       ← paper/thread overviews
config/                       ← tags, metadata schema
templates/                    ← copy for new entries
scripts/
├── ingest.sh                 ← file raw PDFs/exports → data/raw/
└── record.sh                 ← register new note → manifest + INDEX reminder
```

## Rules

| Rule | Detail |
|------|--------|
| **Chat is not the source of truth** | Every conclusion → `notes/` or `store/sessions/` |
| **Raw is immutable** | `data/raw/` copies never edited; use `data/processed/` for derivatives |
| **Every artifact has an ID** | Frontmatter `id:` per `config/metadata-schema.yaml` |
| **Manifest is updated** | Run `./scripts/record.sh` after creating significant files |
| **INDEX.md is the human index** | Append row in Notes & logs / Topics / Raw data |
| **Evidence level required** | L0 README … L4 cross-validated (see `protocols/evidence-levels.md`) |
| **Future sessions** | Start `store/sessions/YYYY-MM-DD-<topic>.md`; end with manifest update |

## Quick commands

```bash
# File a PDF or export
./scripts/ingest.sh data/inbox/paper.pdf papers

# Register a new analysis note
./scripts/record.sh notes/synthesis/my-analysis.md L2 synthesis

# Open master catalog
cat store/manifest.yaml
open INDEX.md
```

## Session archive (2026-07-08)

Primary session log: [sessions/2026-07-08-eight-repo-l3-research.md](sessions/2026-07-08-eight-repo-l3-research.md)

Peak deliverables:
- [l3-comprehensive-skill-analysis.md](../notes/synthesis/l3-comprehensive-skill-analysis.md)
- [taichu-p0-skill-compaction-spec.md](../notes/synthesis/taichu-p0-skill-compaction-spec.md)
- [skill-lifecycle-and-dynamic-loading-survey.md](../notes/synthesis/skill-lifecycle-and-dynamic-loading-survey.md)
