# STORE — Quick Reference

**All research is persisted on disk.** Chat transcripts are supplementary, not authoritative.

## Where things live

| Content | Location |
|---------|----------|
| Master human index | [INDEX.md](INDEX.md) |
| Machine catalog | [store/manifest.yaml](store/manifest.yaml) |
| Session archives | [store/sessions/](store/sessions/) |
| Analysis notes | [notes/synthesis/](notes/synthesis/) |
| Per-repo deep dives | [notes/synthesis/repos/](notes/synthesis/repos/) |
| Daily logs | [notes/daily/](notes/daily/) |
| Raw inputs (immutable) | [data/raw/](data/raw/) |
| Processed exports | [data/processed/](data/processed/) |
| Future recording protocol | [store/protocols/recording.md](store/protocols/recording.md) |

## Record new work

```bash
# 1. Write your note
vim notes/synthesis/my-new-analysis.md

# 2. Register it
./scripts/record.sh notes/synthesis/my-new-analysis.md L2 synthesis

# 3. Paste printed rows into manifest.yaml + INDEX.md
```

## 2026-07-08 session (archived)

Full session log: [store/sessions/2026-07-08-eight-repo-l3-research.md](store/sessions/2026-07-08-eight-repo-l3-research.md)
