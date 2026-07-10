---
id: SR-taichu-001
title: TaiChu — Agent Skill Architecture Survey Report
date: 2026-07-08
repo: taichu
evidence_level: L3
matrix_version: 1
related: [T007, N2026-07-08-P0]
---

# TaiChu — Agent Skill Architecture Survey Report

> **Local**: `/Users/maybewu/Documents/Projects/drafts/zk/TaiChu` (private)  
> **Upstream**: [taichu.fun Gitea SystemAgentDev/TaiChu](https://taichu.fun/gitea/SystemAgentDev/TaiChu)  
> **Cross-repo doc**: `docs/architecture/skill-system-cross-repo-comparison.md` (1000+ lines, 2026-07-06)  
> **Matrix**: [agent-skill-architecture-survey-matrix.md](../agent-skill-architecture-survey-matrix.md)  
> **P0 spec**: [taichu-p0-skill-compaction-spec.md](../taichu-p0-skill-compaction-spec.md)

---

## 1. Architecture

TaiChu is a **Rust layered SDK** (L1–L5) with 端云协同: `taichu-core-sdk` Runtime/SessionManager, Pi-mono agent loop, `builtintools` (`load_skill`), `agent-session` compaction, subagent relay. Skills = **17 canonical** `skills/system/{name}/SKILL.md` + cloud `skill_catalog.json` — catalog is strong, **lifecycle as versioned asset** is not yet built.

```text
Session scan → XML <local_skills>/<cloud_skills> (system)
        ↓ per turn
# Available Skills user prefix (A-system / NLU)
        ↓
load_skill → ToolResult body
        ↓
compaction.rs summarize  ← ❌ may drop skill body
```

**Evidence**

| Claim | Path |
|-------|------|
| SDK layers | `docs/overview.md`, `core/taichu-core-sdk/` |
| 8-repo comparison | `docs/architecture/skill-system-cross-repo-comparison.md` |
| load_skill tool | `core/builtintools/src/skill/load_skill.rs` |

**Matrix**: §1 Data Model 6/14 · §2 Discovery remote ★ workspace ❌ · Overall **5.0**

---

## 2. Skill Runtime

| Pattern | Implementation | Evidence |
|---------|----------------|----------|
| Per-turn catalog | ★ `# Available Skills` user prefix | `taichu-service/src/api/mod.rs:674-694` |
| Cache-friendly expose | skills in **user** msg not system | `transient.rs` comments, lifecycle survey |
| Progressive disclosure | XML metadata → `load_skill` body | `prompt_builder.rs` |
| Per-turn filter | Toollery `before_prompt` → `skill_filter` | `agent-plugin/src/tool_search_bridge.rs:370-382` |
| runs_on 端云 | ★ unique among 8 repos | `load_skill.rs:110-132` |
| Compaction survival | ❌ no invoked_skills | `compaction.rs`, `context-and-skills.md:64-68` |

**Quote — load_skill runs_on / remote delegation**

```rust
// core/builtintools/src/skill/load_skill.rs:120-131
text: format!(
    "技能「{}」在远程设备上执行（runs_on: {}）。\n\
     请查看 <devices> 中对应的在线设备，\n\
     使用 run_subagent(target_id=...) 委托执行。",
    name, runs_on.join(", ")
),
details: json!({
    "remote_delegation": true,
}),
```

**Quote — name lookup scope**

```rust
// load_skill.rs:30 (params schema description)
// "Name lookup does not search the current session workspace."
```

**Standout**: Use ★ (runs_on) · Per-turn expose ★ · Compact ❌

---

## 3. Skill Lifecycle

| Stage | TaiChu | Status |
|-------|--------|--------|
| Human canonical | 17 system skills | ★ |
| Cloud publish | skill_catalog.json + device sync | ★ |
| Discover / expose / load | scan + prefix + load_skill | ★ |
| Observe | interaction_log JSONL | ◐ |
| Generated / reviewed / approved | — | · |
| Rollback | — | ❌ |

**Lifecycle score**: **4/13**

**Quote — documented compact risk**

From `context-and-skills.md:64-68` (referenced in comparison doc):

> After compaction, `load_skill` ToolResult content may be summarized away — multi-turn skill-guided tasks lose procedural fidelity.

---

## 4. Skill Evolution

**No runtime evolution.** Roadmap P2: proposals store (per `skill-system-cross-repo-comparison.md` L978-985).

Recommended path (from matrix synthesis):

```text
interaction_log → miner → .taichu/skill-candidates/
        → regression → gates → PR → ~/.taichu/skills/
```

**Not**: Hermes-style direct canonical patch.

**Matrix §9**: 1/16

---

## 5. Multi-Agent Skill

| Pattern | Status | Evidence |
|---------|--------|----------|
| run_subagent / relay | ★ exists | `core/subagent/` |
| Child skill preload | ❌ | `session/manager.rs:1736-1796` |
| Inherit parent invoked | ❌ child rescans canonical only | comparison doc L776-781 |
| Complementary bundles | ❌ | matrix §13 |

**Gap vs Claude Rev**: no `ChildSessionSpec.skills: Vec<String>` preload.

---

## 6. Skill Governance

| Control | Status |
|---------|--------|
| ToolDomains filtering | ◐ `tool_domains.rs` |
| runs_on capability routing | ★ |
| trust_tier / audit / proposal gates | · |
| Agent CRUD on skills | · |

**Target schema** (from web-deep guide):

```yaml
trust_tier: bundled | team | personal | generated | community
mutable_by_agent: false  # for published skills
requires_human_approval: true  # for generated
```

---

## 7. Harness Integration

| Seam | Location | Notes |
|------|----------|-------|
| Per-turn user prefix | `SessionOptions.transform_context` | **not** `ContextOptions.hook_chain` |
| Skill filter | `set_skill_name_filter` + Toollery | per-turn |
| Extra tools | `Runtime::add_tool_factory` | **not** `SessionOptions.extra_tool_factories` |
| Trace | `interaction_log` JSONL | Claw-R1 extension point |
| Compact | `agent-session/src/compaction.rs` | P0 target |

Ref: [survey-methodology-and-repo-confirmation.md](../survey-methodology-and-repo-confirmation.md) §TaiChu seams

---

## 8. RL Readiness

| Signal | Status |
|--------|--------|
| interaction_log | ◐ partial step trace |
| Trajectory schema | · |
| Reward / Atropos | · |
| SkillRL | ◐ log-only foundation |
| Claw-R1 | ◐ hooks + log; needs step schema |

Align export with OpenClaw `openclaw-trajectory` fields when extending log.

---

## 9. Borrow for TaiChu

| Source | Pattern |
|--------|---------|
| **Claude Rev** | invoked_skills compact, subagent preload, skillImprovement |
| **OpenSquilla** | proposals + gates, RRF, collect_invoked_skills |
| **Codex** | SKILL.md layout, metadata budget, implicit trigger |
| **OpenClaw** | 6-layer scope, skillFilter, trajectory JSONL |
| **Hermes** | review async + skill_manage (candidate-only) + skills_guard |
| **ZeroClaw** | audit.rs patterns, trust_tier metadata |
| **GenericAgent** | Skill Miner philosophy (not ungated write) |

**Keep**: runs_on, user prefix per-turn, load_skill wire, Toollery filter.

---

## 10. Implement in TaiChu

| P | What | Spec / file |
|---|------|-------------|
| **P0** | InvokedSkillRegistry + post-compact reinject | [taichu-p0-skill-compaction-spec.md](../taichu-p0-skill-compaction-spec.md) |
| **P0** | ChildSessionSpec.skills preload | `session/manager.rs` |
| P1 | `~/.taichu/proposals/` + gates | new crate/module |
| P1 | skill_manage → candidates only | `builtintools/` |
| P2 | RRF on Toollery | `tool_search_bridge.rs` |
| P3 | MetaSkill DAG | new `meta/` |

---

## 11. Do NOT Borrow

| Pattern | Why |
|---------|-----|
| Hermes direct production patch | issue #55647 class |
| OpenClaw marketplace trust | security |
| GenericAgent ungated crystallize | no eval |
| `SessionOptions.extra_tool_factories` | migrated API |
| Workspace skill scan in session | intentionally disabled for A-system |

---

## 12. Score (1–10)

| Category | Score | Notes |
|----------|:-----:|-------|
| Data Model | 6 | SKILL.md ★; no version/trust |
| Runtime | 7 | runs_on ★; compact ❌ |
| Lifecycle | 4 | 4/13 stages |
| Evolution | 1 | none |
| Governance | 3 | ToolDomains only |
| Agent Integration | 5 | subagent skill gap |
| RL Readiness | 3 | log foundation |
| **Overall** | **5.0** | **Best seams + 端云; lifecycle immature** |

---

## Evidence index

| ID | Claim | Path / URL | Level |
|----|-------|------------|-------|
| TC-01 | runs_on delegation | `builtintools/src/skill/load_skill.rs:110-132` | L3 |
| TC-02 | Per-turn prefix | `taichu-service/src/api/mod.rs:674-694` | L3 |
| TC-03 | Tool filter | `agent-plugin/src/tool_search_bridge.rs:370-382` | L3 |
| TC-04 | Compact gap | `agent-session/src/compaction.rs`, `context-and-skills.md:64-68` | L3 |
| TC-05 | Child no inherit | `session/manager.rs:1736-1796` | L2 |
| TC-06 | 8-repo comparison | `docs/architecture/skill-system-cross-repo-comparison.md` | L2 |
| TC-07 | P0 spec | [taichu-p0-skill-compaction-spec.md](../taichu-p0-skill-compaction-spec.md) | L3 |
| TC-08 | Private upstream | https://taichu.fun/gitea/SystemAgentDev/TaiChu | L0 |
