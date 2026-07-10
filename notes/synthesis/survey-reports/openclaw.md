---
id: SR-openclaw-001
title: OpenClaw — Agent Skill Architecture Survey Report
date: 2026-07-08
repo: openclaw
evidence_level: L3
matrix_version: 1
related: [T007]
---

# OpenClaw — Agent Skill Architecture Survey Report

> **Local**: `/Users/maybewu/Documents/Projects/oss/openclaw`  
> **Upstream**: [openclaw/openclaw](https://github.com/openclaw/openclaw)  
> **Docs**: [docs/tools/skills.md](https://github.com/openclaw/openclaw/blob/main/docs/tools/skills.md)  
> **Matrix**: [agent-skill-architecture-survey-matrix.md](../agent-skill-architecture-survey-matrix.md)

---

## 1. Architecture

OpenClaw is a **multi-channel gateway** with pluggable harness (Pi/Codex), 70+ plugin hooks, hybrid memory (FTS+vector + **Dreaming**), and **AgentSkills-compatible** lazy skills. Skills use **6-source merge with explicit precedence**, **session snapshot versioning**, and optional **skill-workshop** extension for post-run evolution.

```text
Gateway → agent loop → skills snapshot (metadata XML)
                              ↓ read tool
                         full SKILL.md
                              ↓ agent_end
                    skill-workshop → proposals → scan → apply
```

**Quote — official docs precedence**

```markdown
# docs/tools/skills.md:19-30
OpenClaw loads skills from these sources, **highest precedence first**:
1. Workspace skills      `<workspace>/skills`
2. Project agent skills  `<workspace>/.agents/skills`
3. Personal agent skills `~/.agents/skills`
4. Managed/local skills  `~/.openclaw/skills`
5. Bundled skills
6. Extra skill folders   skills.load.extraDirs
```

**Quote — location vs visibility**

```markdown
# docs/tools/skills.md:50-52
Skill **location** and skill **visibility** are separate controls.
Location/precedence decides which copy of a same-named skill wins; agent
allowlists decide which skills an agent can actually use.
```

**Evidence**: `src/agents/skills/workspace.ts`, `skill-contract.ts`, `docs/tools/skills.md`

---

## 2. Skill Runtime

| Pattern | Implementation | Evidence |
|---------|----------------|----------|
| Lazy load | metadata in prompt; model uses **read tool** | `skill-contract.ts`, `workspace.ts` |
| Session snapshot | `resolveSkillsPromptForRun()` caches snapshot | `workspace.ts`, `refresh-state.ts` |
| Budget | max 150 skills / 18000 chars → compact XML | `workspace.ts` |
| Per-agent filter | `resolveEffectiveAgentSkillFilter()` whitelist | `agent-filter.ts:24-36` |
| Hot reload | chokidar → next-turn snapshot bump | `refresh-state.ts` |
| Recommendation | · alpha sort + budget truncate only | no RRF |

**Quote — skill-workshop purpose**

```typescript
// extensions/skill-workshop/index.ts:13-14
description:
  "Captures repeatable workflows as workspace skills, with pending review and safe writes.",
```

**Standout**: Scope/Priority ★ · Lazy Offload ★ · Per-agent visibility ★

---

## 3. Skill Lifecycle

| Stage | OpenClaw | Evidence |
|-------|----------|----------|
| Human written | workspace / managed files | `docs/tools/skills.md` |
| Generated | skill-workshop heuristic + LLM reviewer | `skill-workshop/index.ts:48+` |
| Reviewed | `reviewTranscriptForProposal()` | `skill-workshop/reviewer.ts` |
| Published | `applyProposalToWorkspace` append/replace | `skill-workshop/skills.ts` |
| Quarantined | `scanSkillContent()` critical | `skill-workshop/workshop.ts:54-61` |
| Deleted | user FS delete + workshop tool | `skill-workshop/tool.ts` |

**Lifecycle score**: **9/13** — strong workshop path; no formal version rollback

**Security context**: [The Verge — OpenClaw skill marketplace risk](https://www.theverge.com/news/874011/openclaw-ai-skill-clawhub-extensions-security-nightmare)

---

## 4. Skill Evolution

```text
agent_end (success)
    ↓
createProposalFromMessages() [regex signals]
    ↓
reviewTranscriptForProposal() [LLM reviewer session]
    ↓
proposals store: pending | applied | quarantined
    ↓
scanSkillContent() → apply or quarantine
    ↓
approvalPolicy: "auto" | manual
```

| File | Role |
|------|------|
| `extensions/skill-workshop/index.ts` | hook registration |
| `skill-workshop/signals.ts` | heuristic detection |
| `skill-workshop/reviewer.ts` | LLM review |
| `skill-workshop/store.ts` | proposal persistence |
| `security/skill-scanner.ts` | quarantine gate |

**Matrix §9**: Candidate ★ · Reflection ◐ · Auto Patch ◐ (auto policy)

**Separate RL repo**: [Gen-Verse/OpenClaw-RL](https://github.com/Gen-Verse/OpenClaw-RL) — training, not skill runtime.

---

## 5. Multi-Agent Skill

| Pattern | Status | Evidence |
|---------|--------|----------|
| Per-agent workspace | ★ each agent own `<ws>/skills` | `docs/tools/skills.md:34-42` |
| skillFilter allowlist | ★ `agents.list[].skills` | `docs/tools/skills.md:54-60` |
| Subagent | ◐ reduced system prompt | `subagent-system-prompt.ts` |
| Complementary preload | · no frontmatter skills list | — |

**Quote — per-agent scope table** (docs/tools/skills.md:36-42)

---

## 6. Skill Governance

| Control | Evidence |
|---------|----------|
| skill-scanner quarantine | `security/skill-scanner.ts` |
| Workshop pending review | `store.ts` |
| Agent allowlists | `agent-filter.ts` |
| ClawHub marketplace | external — **trust risk** (Verge article) |

---

## 7. Harness Integration

| API | Path |
|-----|------|
| Plugin hooks (70+) | `plugins/hooks.ts` |
| Context engine | `context-engine/types.ts` — assemble/afterTurn/compact |
| Trajectory export | `trajectory/runtime.ts` — `openclaw-trajectory` JSONL |
| Harness trait | `agents/harness/types.ts` |
| before_prompt_build | skill-workshop prepend guidance |

---

## 8. RL Readiness

| Signal | Status | Evidence |
|--------|--------|----------|
| Trajectory JSONL | ★ | `trajectory/types.ts`, `trajectory/export.ts` |
| Step metadata | ★ | `trajectory/metadata.ts` |
| Reward in-repo | ◐ | trajectory fields |
| OpenClaw-RL | ★ separate repo | Gen-Verse/OpenClaw-RL |
| Claw-R1 | ★ **best OSS step capture** alongside OpenSquilla pipeline | |
| SkillRL | ◐ trajectory → SkillBank manual pipeline | |

---

## 9. Borrow for TaiChu

| Pattern | Why |
|---------|-----|
| 6-layer scope + precedence | TaiChu multi-source skill dirs |
| Location vs visibility split | subagent / role allowlists |
| Session snapshot + watcher refresh | cache-friendly catalog |
| skill-workshop proposal flow | agent_end → store → scan → apply |
| Trajectory JSONL schema | Claw-R1 alignment on interaction_log |
| Lazy catalog + load_skill | already partial in TaiChu |

---

## 10. Implement in TaiChu

| Priority | What | Seam |
|----------|------|------|
| P1 | Multi-root skill merge priority | skill loader |
| P1 | `agent_end` proposal hook | session lifecycle |
| P1 | Trajectory export fields | interaction_log |
| P2 | per-agent skillFilter | subagent profiles |
| P2 | skill-scanner before apply | proposal gate |

---

## 11. Do NOT Borrow

| Pattern | Why |
|---------|-----|
| ClawHub marketplace trust model | Verge security report |
| Auto-apply without scanner | quarantine is essential |
| Heuristic-only signals alone | combine with eval gate (OpenSquilla) |

---

## 12. Score (1–10)

| Category | Score | Notes |
|----------|:-----:|-------|
| Data Model | 8 | Standard SKILL.md + 6 sources |
| Runtime | 8 | Snapshot + lazy ★; no ranker |
| Lifecycle | 8 | workshop 9/13 |
| Evolution | 7 | workshop strong; no RRF/gates |
| Governance | 7 | scanner + allowlist |
| Agent Integration | 8 | per-agent scope ★ |
| RL Readiness | 7 | trajectory ★ |
| **Overall** | **8.0** | Best scope model + RL export |

---

## Evidence index

| ID | Claim | Path / URL | Level |
|----|-------|------------|-------|
| OC-01 | 6-source precedence | `docs/tools/skills.md:19-30` | L0+L3 |
| OC-02 | Location vs visibility | `docs/tools/skills.md:50-52` | L0 |
| OC-03 | skill-workshop | `extensions/skill-workshop/index.ts` | L3 |
| OC-04 | Trajectory | `trajectory/runtime.ts` | L3 |
| OC-05 | Marketplace risk | https://www.theverge.com/news/874011/openclaw-ai-skill-clawhub-extensions-security-nightmare | L0 |
| OC-06 | agent filter | `agent-filter.ts` | L2 |
