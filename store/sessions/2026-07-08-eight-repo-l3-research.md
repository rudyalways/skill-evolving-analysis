---
id: S2026-07-08-001
title: Eight-repo L3 skill evolution research session
date: 2026-07-08
tags: [skillrl, claw-r1, l3, eight-repo, taichu, compaction, self-evolution]
status: archived
evidence_level: L3
summary: Full session archive — papers, 8 frameworks, L3 merged analysis, TaiChu P0 spec
related: [N2026-07-08-L3, N2026-07-08-P0]
---

# Session: 2026-07-08 — Eight-Repo L3 Skill Evolution Research

## Goal

Deep research on **Agent Harness + Skill Self-Evolution**, centered on:

- **SkillRL** (arXiv:2602.08234) — recursive skill-augmented RL
- **Claw-R1** (arXiv:2606.09138) — step-level data middleware

Plus **local source analysis** of 8 agent frameworks (7 OSS + private TaiChu).

## Corrections established

| Item | Correction |
|------|------------|
| Second paper | **Claw-R1**, not OpenClaw-RL |
| OpenClaw-RL | Separate RL training repo (`Gen-Verse/OpenClaw-RL`), not `openclaw/openclaw` |
| Claude Code RE | **`oboard/claude-code-rev`** at `oss/experimental/claude-code-rev` |
| Codex | `openai/codex` |
| TaiChu | Private Gitea `taichu.fun/gitea/SystemAgentDev/TaiChu` at `drafts/zk/TaiChu` |
| Methodology | L1–L3 evidence; honest about scope |

## Local repos verified (git remote)

| Repo | Path | Remote |
|------|------|--------|
| openclaw | `oss/openclaw` | github.com/openclaw/openclaw |
| openclaw-rl | `oss/openclaw-rl` | github.com/Gen-Verse/OpenClaw-RL |
| claude-code-rev | `oss/experimental/claude-code-rev` | github.com/oboard/claude-code-rev |
| genericagent | `oss/genericagent` | github.com/lsdefine/genericagent |
| codex | `oss/codex` | github.com/openai/codex |
| opensquilla | `oss/opensquilla` | github.com/opensquilla/opensquilla |
| zeroclaw | `oss/zeroclaw` | github.com/zeroclaw-labs/zeroclaw |
| hermes-agent | `oss/hermes-agent` | github.com/nousresearch/hermes-agent |
| TaiChu | `drafts/zk/TaiChu` | taichu.fun Gitea (private) |

**Not cloned:** `zeroclaw-labs/zeroclaw-skills`, `NousResearch/hermes-agent-self-evolution` (network timeout).

## Deliverables written to disk

### Papers & architecture

- [topics/skill-rl/overview.md](../../topics/skill-rl/overview.md)
- [topics/claw-r1/overview.md](../../topics/claw-r1/overview.md)
- [notes/synthesis/comparison.md](../../notes/synthesis/comparison.md)
- [notes/synthesis/combined-pipeline.md](../../notes/synthesis/combined-pipeline.md)
- [notes/synthesis/paper-index.md](../../notes/synthesis/paper-index.md)

### Taxonomy & proposed architecture

- [notes/synthesis/skill-evolution-taxonomy.md](../../notes/synthesis/skill-evolution-taxonomy.md)
- [notes/synthesis/proposed-skill-lifecycle-architecture.md](../../notes/synthesis/proposed-skill-lifecycle-architecture.md)
- [notes/synthesis/industry-harness-survey.md](../../notes/synthesis/industry-harness-survey.md)
- [notes/synthesis/official-blog-skill-evolution.md](../../notes/synthesis/official-blog-skill-evolution.md)
- [notes/synthesis/official-product-gap-consensus.md](../../notes/synthesis/official-product-gap-consensus.md)

### Eight-repo analysis (L1 → L3)

- [notes/synthesis/local-oss-repo-inventory.md](../../notes/synthesis/local-oss-repo-inventory.md)
- [notes/synthesis/eight-repo-source-analysis-framework.md](../../notes/synthesis/eight-repo-source-analysis-framework.md)
- [notes/synthesis/eight-repo-deep-source-analysis.md](../../notes/synthesis/eight-repo-deep-source-analysis.md)
- [notes/synthesis/eight-repo-comprehensive-survey.md](../../notes/synthesis/eight-repo-comprehensive-survey.md)
- [notes/synthesis/skill-lifecycle-and-dynamic-loading-survey.md](../../notes/synthesis/skill-lifecycle-and-dynamic-loading-survey.md)
- [notes/synthesis/survey-methodology-and-repo-confirmation.md](../../notes/synthesis/survey-methodology-and-repo-confirmation.md)
- [notes/synthesis/web-vs-local-reconciliation.md](../../notes/synthesis/web-vs-local-reconciliation.md)
- [notes/synthesis/l3-comprehensive-skill-analysis.md](../../notes/synthesis/l3-comprehensive-skill-analysis.md) ← **peak L3 merge**

### Per-repo (20-dim)

- [notes/synthesis/repos/openclaw.md](../../notes/synthesis/repos/openclaw.md)
- [notes/synthesis/repos/hermes-agent.md](../../notes/synthesis/repos/hermes-agent.md)
- [notes/synthesis/repos/codex.md](../../notes/synthesis/repos/codex.md)
- [notes/synthesis/repos/opensquilla.md](../../notes/synthesis/repos/opensquilla.md)
- [notes/synthesis/repos/genericagent.md](../../notes/synthesis/repos/genericagent.md)
- [notes/synthesis/repos/zeroclaw.md](../../notes/synthesis/repos/zeroclaw.md)
- [notes/synthesis/repos/claude-code-rev.md](../../notes/synthesis/repos/claude-code-rev.md)
- [notes/synthesis/repos/taichu.md](../../notes/synthesis/repos/taichu.md)

### TaiChu implementation

- [notes/synthesis/taichu-p0-skill-compaction-spec.md](../../notes/synthesis/taichu-p0-skill-compaction-spec.md)
- External: `drafts/zk/TaiChu/docs/architecture/skill-system-cross-repo-comparison.md` (1000+ lines, referenced)

## Key conclusions

### No single repo = full SkillRL + Claw-R1 loop

Best fragments: OpenClaw trajectory + OpenSquilla gates + Hermes skill_manage + Claude Rev invoked_skills compaction.

### Self-evolution strength (L3 merged)

1. Hermes ecosystem (online skill_manage + background review; offline GEPA web-only)
2. OpenSquilla (proposals + 5-gate + auto_propose + per-turn RRF)
3. OpenClaw (skill-workshop on agent_end)
4. GenericAgent (L0–L4 SOP crystallization)
5. oboard/claude-code-rev (invoked_skills compaction + skillImprovement)
6. ZeroClaw → Codex → TaiChu

### Critical TaiChu gaps

- No `invoked_skills` compaction survival (only Claude Rev has this)
- Missing subagent skill preload + inherit
- Integration seams: `transform_context`, `set_skill_name_filter`, `load_skill.rs`, `compaction.rs`

## L3 code paths cited

| Repo | Paths |
|------|-------|
| Hermes | `skill_manager_tool.py`, `run_agent.py:1768-1896`, `skills_guard.py` |
| OpenSquilla | `proposals_lib.py`, `skills_filter.py`, `auto_propose.py`, `runtime.py:250` |
| OpenClaw | `extensions/skill-workshop/`, `skills/workspace.ts`, `trajectory/metadata.ts` |
| Claude Rev | `compact.ts:1488-1534`, `skillImprovement.ts`, `runAgent.ts:577-646` |
| TaiChu | `load_skill.rs`, `api/mod.rs:674-694`, `compaction.rs` |

## Errors / blockers

- `git clone zeroclaw-skills` — DNS/timeout (exit 128)
- `hermes-agent-self-evolution` — not cloned; Web README only

## Open queue (next sessions)

| Priority | Task | Target level |
|----------|------|--------------|
| P0 | Implement TaiChu InvokedSkillRegistry + compaction reinject | implementation |
| P1 | Clone hermes-self-evolution when network works | L3 |
| P2 | L3 OpenClaw-RL training extension | L3 |
| P3 | L4 cross-validate with tests/CHANGELOG | L4 |
| Optional | HTML comparison dashboard | processed |
| Optional | Split L3 into `notes/synthesis/l3/{repo}.md` | L3 |

## Transcript reference

Full agent transcript: `agent-transcripts/98132ca9-6424-4168-a38f-f9493b440c76.jsonl` (Cursor project folder).
