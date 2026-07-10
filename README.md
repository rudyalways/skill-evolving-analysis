# Skill-Evolving Analysis

Deep research on **SkillRL** and **Claw-R1** — complementary layers of the agentic RL stack.

| Paper | Layer | Question |
|-------|-------|----------|
| **SkillRL** | RL algorithm | How does the policy learn from experience? |
| **Claw-R1** | Data infrastructure | How is agent interaction data collected, managed, and fed into RL? |

Together: **infrastructure + policy optimization = full-stack agentic RL**.

## Quick start

```bash
# Drop new raw material
cp ~/Downloads/claw-r1.pdf data/inbox/

# File it
./scripts/ingest.sh data/inbox/claw-r1.pdf papers

# Open dashboard
open html/index.html
```

## Key documents

- [INDEX.md](INDEX.md) — master catalog
- [STORE.md](STORE.md) — persistent archive quick reference
- [store/manifest.yaml](store/manifest.yaml) — machine-readable artifact catalog
- [Agent Skill Architecture Survey Matrix](notes/synthesis/agent-skill-architecture-survey-matrix.md) — **165 dim × 8 repos** (primary instrument)
- [Skill lifecycle full matrix](notes/synthesis/skill-lifecycle-full-matrix.md) — 9-stage condensed view
- [L3 merged analysis](notes/synthesis/l3-comprehensive-skill-analysis.md) — peak deliverable
- [TaiChu P0 spec](notes/synthesis/taichu-p0-skill-compaction-spec.md)
- [Comparison](notes/synthesis/comparison.md) — SkillRL vs Claw-R1
- [Combined pipeline](notes/synthesis/combined-pipeline.md) — how they fit together
- [SkillRL overview](topics/skill-rl/overview.md)
- [Claw-R1 overview](topics/claw-r1/overview.md)

## Directory layout

```
skill-evolving-analysis/
├── INDEX.md              ← master catalog (human)
├── STORE.md              ← archive quick reference
├── store/
│   ├── manifest.yaml     ← machine catalog
│   ├── sessions/         ← per-session research logs
│   └── protocols/        ← recording + evidence-level rules
├── topics/               ← one subdir per paper/thread
├── notes/
│   ├── synthesis/        ← cross-paper analysis
│   └── daily/            ← day/session logs
├── data/
│   ├── inbox/            ← drop zone
│   ├── raw/              ← filed originals (immutable)
│   ├── processed/        ← extractions, record-log.jsonl
│   └── archive/          ← session bundles
├── html/                 ← browsable dashboard
├── templates/            ← copy for new entries
├── scripts/
│   ├── ingest.sh         ← inbox → raw
│   └── record.sh         ← register new artifact
```

## Conventions

| Rule | Example |
|------|---------|
| Raw files are immutable | `data/raw/papers/2026-06-claw-r1-arxiv.pdf` |
| Notes use ISO dates | `notes/daily/2026-07-08.md` |
| Every entry → INDEX.md row | See `INDEX.md` |
| Every entry → manifest.yaml | Run `./scripts/record.sh` |
| Tag with frontmatter | `tags: [claw-r1, data-pool, gateway]` |
| Evidence level required | `evidence_level: L2` — see `store/protocols/evidence-levels.md` |
| Sessions archived | `store/sessions/YYYY-MM-DD-<topic>.md` |
