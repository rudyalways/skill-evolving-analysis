---
id: SR-claude-rev-001
title: Claude Code Rev — Agent Skill Architecture Survey Report
date: 2026-07-08
repo: claude-code-rev
evidence_level: L3
matrix_version: 1
related: [T007, N2026-07-08-P0]
---

# Claude Code Rev (oboard) — Agent Skill Architecture Survey Report

> **Local**: `/Users/maybewu/Documents/Projects/oss/experimental/claude-code-rev`  
> **Upstream**: [oboard/claude-code-rev](https://github.com/oboard/claude-code-rev)  
> **Note**: Community source-map restoration — **not** Anthropic official. Distinct from [Yuyz0112/claude-code-reverse](https://github.com/Yuyz0112/claude-code-reverse) (LLM viz tool only).  
> **Matrix**: [agent-skill-architecture-survey-matrix.md](../agent-skill-architecture-survey-matrix.md)

---

## 1. Architecture

TypeScript/Bun CLI with React Ink REPL. Skills use a **three-channel model**:

1. **skill_listing** — incremental attachment per `agentId`
2. **Skill tool** / slash commands
3. **invoked_skills** — post-compaction attachment preserving loaded bodies

State tracked in `STATE.invokedSkills` Map; compaction is multi-tier (auto, micro, reactive, collapse).

```text
Turn → skill_listing (delta) → Skill tool → addInvokedSkill()
                                              ↓
Compact → summarize history → createSkillAttachmentIfNeeded()
                                              ↓
                                    invoked_skills attachment survives
```

**Evidence**: `utils/attachments.ts`, `services/compact/compact.ts`, `bootstrap/state.ts`

---

## 2. Skill Runtime

| Pattern | Implementation | Evidence |
|---------|----------------|----------|
| Incremental listing | `getSkillListingAttachments()` — only unsent skills | `attachments.ts:2717-2734` |
| Per-agent sent map | `sentSkillNames` per `agentId` | `attachments.ts:2699-2704` |
| Invoked registry | `addInvokedSkill()` on Skill tool / slash | `bootstrap/state.ts` |
| Usage ranking | 7-day half-life decay | `skillUsageTracking.ts:44-54` |
| Subagent preload | frontmatter `skills:[]` → initialMessages | `runAgent.ts:577-639` |

**Quote — compaction survival (critical)**

```typescript
// src/services/compact/compact.ts:1488-1492
/**
 * Creates an attachment for invoked skills to preserve their content across compaction.
 * Only includes skills scoped to the given agent (or main session when agentId is null/undefined).
 * This ensures skill guidelines remain available after the conversation is summarized
 */
```

**Quote — budget + most-recent-first**

```typescript
// compact.ts:1503-1520
// Sorted most-recent-first so budget pressure drops the least-relevant skills.
// Per-skill truncation keeps the head of each file ...
if (usedTokens + tokens > POST_COMPACT_SKILLS_TOKEN_BUDGET) {
  return false;
}
```

**Standout**: Compact ★ · Per-turn delta listing ★ · Subagent preload ★

**Known gap**: preload from frontmatter ≠ `addInvokedSkill` — compact may not protect preload-only skills (`repos/claude-code-rev.md`)

---

## 3. Skill Lifecycle

| Stage | Claude Rev | Evidence |
|-------|------------|----------|
| Human written | project/user skills | `loadSkillsDir.ts` |
| Generated | skillify bundled workflow | `skills/bundled/skillify.ts` |
| Reviewed | SkillImprovementSurvey UI | `SkillImprovementSurvey.tsx` |
| Published | user applies patch to disk | `applySkillImprovement` |
| Deleted | user removes project skill | FS |

**Lifecycle score**: **8/13** — strong improve path; no proposal store / formal version

---

## 4. Skill Evolution

```text
Every 5 user turns (post-sampling hook)
        ↓
skillImprovement.ts — aux small/fast model
        ↓
JSON [{section, change, reason}]
        ↓
SkillImprovementSurvey UI (user gate)
        ↓
applySkillImprovement → patch project SKILL.md
```

| File | Role |
|------|------|
| `utils/hooks/skillImprovement.ts` | trigger + aux model |
| `hooks/useSkillImprovementSurvey.ts` | UI gate |
| `skills/bundled/skillify.ts` | session → new skill |

**Matrix §9**: Reflection ★ · Teacher ★ (aux model) · Preference ★ (survey) · Auto Patch ◐ (after user)

**Not**: RL, GRPO, or automated merge without user.

---

## 5. Multi-Agent Skill

**Quote — subagent skill preload**

```typescript
// src/tools/AgentTool/runAgent.ts:577-578
// Preload skills from agent frontmatter
const skillsToPreload = agentDefinition.skills ?? []
```

| Pattern | Status |
|---------|--------|
| Task tool isolation | ★ dirty context stays in subagent |
| frontmatter `skills:[]` | ★ preload to child initialMessages |
| per-agent listing | ★ separate `sentSkillNames` |
| EXPERIMENTAL_SKILL_SEARCH | bundled+MCP only for subagent turn-0 | `attachments.ts:2651-2697` |

**Yuyz0112 viz tool** documents Task/subagent offload pattern ([GitHub](https://github.com/Yuyz0112/claude-code-reverse)) — harness insight only; oboard has full skill runtime.

---

## 6. Skill Governance

| Control | Status |
|---------|--------|
| Project-scoped improvement | only project invoked skills in skillImprovement |
| User survey gate | ★ before apply |
| Hooks schema | skill-scoped hooks `utils/settings/types.ts` |
| Formal audit/registry | · |

---

## 7. Harness Integration

| Component | Path |
|-----------|------|
| Central loop | `src/query.ts` |
| Post-sampling hooks | `utils/hooks/postSamplingHooks.ts` |
| Attachments per turn | `utils/attachments.ts` |
| Multi-tier compact | `services/compact/`, `contextCollapse/` |
| Session restore | `utils/sessionStorage.ts` |

Skills are **first-class attachments**, not only tool results — key architectural difference from TaiChu today.

---

## 8. RL Readiness

| Signal | Status |
|--------|--------|
| Session JSONL | ★ export |
| Step traces | ★ in session |
| Reward / RL trainer | · |
| SkillRL | ◐ traces only |
| Claw-R1 | ◐ good step capture, no gateway middleware |

Value is **runtime skill survival + subagent patterns**, not RL training infra.

---

## 9. Borrow for TaiChu

| Pattern | Priority |
|---------|----------|
| `InvokedSkillRegistry` + post-compact attachment | **P0** |
| Per-turn incremental skill listing (delta) | P0 |
| `ChildSessionSpec.skills: Vec<String>` preload | P0 |
| skillImprovement 5-turn + SideQuery small model | P1 |
| Usage decay ranking for Flutter picker | P2 |

Spec: [taichu-p0-skill-compaction-spec.md](../taichu-p0-skill-compaction-spec.md)

---

## 10. Implement in TaiChu

| P | What | File |
|---|------|------|
| P0 | `record_invoked_skill` on load_skill success | `load_skill.rs` + session state |
| P0 | Post-compact reinject (5K/skill, 25K total) | `compaction.rs` |
| P0 | Child preload | `session/manager.rs` |
| P1 | 5-turn improvement hook | align `big-small-model-collaboration.md` |

---

## 11. Do NOT Borrow

| Pattern | Why |
|---------|-----|
| Assume preload = invoked for compact | documented gap in oboard |
| Skip user gate on auto-patch | Hermes-class risk |
| Confuse with Yuyz0112 viz repo | no skill runtime there |

---

## 12. Score (1–10)

| Category | Score | Notes |
|----------|:-----:|-------|
| Data Model | 7 | Standard SKILL.md |
| Runtime | 9 | 3-channel + compact ★ |
| Lifecycle | 8 | survey-gated improve |
| Evolution | 7 | UI gate strong; no proposals |
| Governance | 6 | user gate; light audit |
| Agent Integration | 9 | subagent preload ★ |
| RL Readiness | 4 | traces only |
| **Overall** | **7.7** | **#1 for compaction survival** |

---

## Evidence index

| ID | Claim | Path / URL | Level |
|----|-------|------------|-------|
| CR-01 | invoked_skills compact | `compact.ts:1488-1534` | L3 |
| CR-02 | Subagent preload | `runAgent.ts:577-578` | L3 |
| CR-03 | skillImprovement | `hooks/skillImprovement.ts` | L3 |
| CR-04 | Incremental listing | `attachments.ts:2717-2734` | L3 |
| CR-05 | Usage decay | `skillUsageTracking.ts` | L3 |
| CR-06 | Upstream repo | https://github.com/oboard/claude-code-rev | L0 |
