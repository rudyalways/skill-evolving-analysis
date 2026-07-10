# Protocol — Recording Future Research

Use this checklist at the **start** and **end** of every research session.

## Start of session

1. Create session log: `store/sessions/YYYY-MM-DD-<short-topic>.md`
2. Note repos touched, evidence level target (L1/L2/L3)
3. If new raw input: drop in `data/inbox/` then `./scripts/ingest.sh`

## During session

| Action | Where to write |
|--------|----------------|
| New cross-cutting insight | `notes/synthesis/<topic>.md` |
| Per-repo deep dive | `notes/synthesis/repos/<repo>.md` |
| Paper/thread overview | `topics/<name>/overview.md` |
| Daily scratch | `notes/daily/YYYY-MM-DD.md` |
| TaiChu implementation spec | `notes/synthesis/taichu-*.md` |
| Table/matrix export | `data/processed/<name>.yaml` |

## End of session

1. Add YAML frontmatter to new `.md` files (`config/metadata-schema.yaml`)
2. Run for each new file:
   ```bash
   ./scripts/record.sh <path> <L0-L4> <category>
   ```
3. Append rows to `INDEX.md` (Notes, Topics, Raw, Processed as needed)
4. Update `store/manifest.yaml` (script does this automatically)
5. Add changelog row to `INDEX.md`
6. Close session log with: deliverables list, open questions, next L3 queue

## Categories (for manifest)

`synthesis` | `repo` | `topic` | `session` | `spec` | `taxonomy` | `survey` | `processed` | `template`

## TaiChu-specific

Implementation work in `drafts/zk/TaiChu` should be **referenced** from here:

```yaml
related_repo: /Users/maybewu/Documents/Projects/drafts/zk/TaiChu
implementation_status: spec-only | in-progress | merged
```

Copy specs into `notes/synthesis/taichu-*.md` — do not rely on TaiChu repo alone.
