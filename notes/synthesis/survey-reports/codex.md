---
id: SR-codex-001
title: Codex — Agent Skill Architecture Survey Report
date: 2026-07-08
repo: codex
evidence_level: L3
matrix_version: 1
related: [T007]
---

# Codex (OpenAI) — Agent Skill Architecture Survey Report

> **Local**: `/Users/maybewu/Documents/Projects/oss/codex`  
> **Upstream**: [openai/codex](https://github.com/openai/codex)  
> **Official docs**: [Agent Skills – Codex](https://developers.openai.com/codex/skills)  
> **Matrix**: [agent-skill-architecture-survey-matrix.md](../agent-skill-architecture-survey-matrix.md)

---

## 1. Architecture

Rust monorepo: `ThreadManager → Session → run_turn`. Skills live in `core-skills` crate with **scope-based discovery** (User/Repo/System/Admin), **metadata budget**, **progressive disclosure**, and **per-turn injection** for mentioned/implicit skills. Codex **deliberately does not** implement runtime skill self-evolution — skills are filesystem assets + optional Record & Replay authoring.

```text
SkillsManager scan → AvailableSkills metadata (≤2% ctx)
        ↓ explicit $skill or implicit match
build_skill_injections() → full SKILL.md in user fragment (this turn only)
```

**Quote — official progressive disclosure**

> *"Skills use progressive disclosure to manage context efficiently: Codex starts with each skill's name, description, and file path. Codex loads the full SKILL.md instructions only when it decides to use a skill."*  
> — [developers.openai.com/codex/skills](https://developers.openai.com/codex/skills)

**Quote — metadata budget**

> *"this list uses at most 2% of the model's context window, or 8,000 characters when the context window is unknown."*  
> — same URL

---

## 2. Skill Runtime

| Pattern | Implementation | Evidence |
|---------|----------------|----------|
| Metadata budget | `SkillMetadataBudget`, truncate descriptions | `core-skills/src/render.rs`, `manager.rs` |
| Per-turn injection | only mentioned/implicit skills this turn | `core-skills/src/injection.rs:57-80` |
| Implicit invoke | shell command pattern → skill | `core/src/skills.rs:48-95` |
| Child turn_skills | independent enable set per child | `core-skills/manager_tests.rs:805` |
| Progressive disclosure | documented in render constants | `render.rs:27-43` |

**Quote — in-repo progressive disclosure instructions**

```rust
// codex-rs/core-skills/src/render.rs:30-33
// - How to use a skill (progressive disclosure):
//   1) After deciding to use a skill, open its `SKILL.md`. Read only enough to follow the workflow.
//   3) If `SKILL.md` points to extra folders such as `references/`, load only the specific files needed
```

**Quote — budget warning**

```rust
// render.rs:21
pub const SKILL_DESCRIPTION_TRUNCATED_WARNING: &str =
  "Skill descriptions were shortened to fit the skills context budget...";
```

**Standout**: Description as routing signal ★ · Budget aware ★ · Per-turn offload ★

---

## 3. Skill Lifecycle

| Stage | Codex | Evidence |
|-------|-------|----------|
| Human written | ★ primary path | FS + `$skill-creator` |
| Record & Replay | ◐ demo → draft skill | official docs |
| Generated in core | · | — |
| Published | FS write | user/git |
| Disabled | `skills.config` enabled=false | `~/.codex/config.toml` |
| Deleted | FS delete | — |

**Lifecycle score**: **6/13** — strong authoring standard; weak evolve/approve/rollback

**Quote — trigger rules**

> *"Explicit invocation: `/skills` or `$` mention. Implicit invocation: Codex can choose a skill when your task matches the skill description."*  
> — official docs

---

## 4. Skill Evolution

**Intentionally absent** in core runtime.

| Path | Status |
|------|--------|
| `$skill-creator` | ★ sample / built-in guidance |
| Record & Replay | ★ authoring assist (docs) |
| Auto patch / review loop | · |
| skillImprovement / skill_manage | · |

Sample: `skill-creator/SKILL.md` — instructs human+subagent validation, not closed-loop.

**Matrix §9**: Evolution 3/16 — by design.

---

## 5. Multi-Agent Skill

| Pattern | Evidence |
|---------|----------|
| Child **excludes** parent skills block | tests `!body_contains_text("<skills_instructions>")` — `subagent_notifications.rs:1180` |
| Child `turn_skills` independent subset | `core-skills/manager_tests.rs:805` |
| MultiAgent v2 spawn | `tools/handlers/multi_agents_v2.rs` |
| Guardian on risky ops | `guardian/mod.rs` |

**Design choice**: subagent skills **deliberately decoupled** from parent — complementary bundles via config, not inheritance.

---

## 6. Skill Governance

| Control | Evidence |
|---------|----------|
| Guardian JSON risk assessment | `guardian/mod.rs` — fail-closed |
| TUI skill approval tests | `core/tests/suite/skill_approval.rs` |
| `allow_implicit_invocation: false` | `agents/openai.yaml` policy in docs |
| Typed hooks (10 types) | `hook_runtime.rs`, `hook_config.rs` |

**Quote — implicit invocation policy**

```yaml
# developers.openai.com/codex/skills — agents/openai.yaml
policy:
  allow_implicit_invocation: false
```

---

## 7. Harness Integration

| Component | Path |
|-----------|------|
| Hook runtime | `hook_runtime.rs` — Pre/PostToolUse, Compact, SessionStart |
| Tool dispatch trace | `tools/tool_dispatch_trace.rs` |
| Context manager | `context_manager/` |
| TestCodex fixture | `core/tests/common/test_codex.rs` |

Best-in-class **typed hook** model for TaiChu Agent Hook Gateway alignment.

---

## 8. RL Readiness

| Signal | Status | Evidence |
|--------|--------|----------|
| tool_dispatch_trace | ◐ | `tool_dispatch_trace.rs` |
| Rollout metadata | ◐ | `turn_metadata.rs` |
| OTEL | ◐ | telemetry |
| Reward / trainer | · | — |
| SkillRL / Claw-R1 | ◐ traces only | not middleware-first |

Codex optimizes **production harness**, not RL dataset export.

---

## 9. Borrow for TaiChu

| Pattern | Why |
|---------|-----|
| SKILL.md directory standard + scripts/refs/assets | industry baseline |
| 2% metadata budget + description truncation | scale to many skills |
| description = routing signal | Toollery / NLU router |
| Per-turn inject mentioned only | token hygiene |
| Implicit shell → load_skill | device CLI patterns |
| Child independent skill enable set | subagent profiles |
| Typed hook runtime | extension-hooks design |
| Guardian-style secondary approval | high-risk tools |

---

## 10. Implement in TaiChu

| P | What | Seam |
|---|------|------|
| P1 | Metadata budget on `# Available Skills` | user prefix renderer |
| P1 | Implicit trigger from shell/device command | load_skill auto |
| P2 | `turn_skills` equivalent on ChildSessionSpec | subagent config |
| P2 | Hook types mirroring Codex | hook gateway |

---

## 11. Do NOT Borrow

| Pattern | Why |
|---------|-----|
| "No evolution" as product goal | TaiChu needs candidate/PR evolution |
| Manual-only skill-creator | need automated miner too |
| Assuming Codex does skill_manage | it doesn't |

---

## 12. Score (1–10)

| Category | Score | Notes |
|----------|:-----:|-------|
| Data Model | 9 | Reference standard |
| Runtime | 8 | Progressive disclosure ★ |
| Lifecycle | 6 | Authoring only |
| Evolution | 3 | By design |
| Governance | 8 | Guardian ★ |
| Agent Integration | 7 | child decoupling ★ |
| RL Readiness | 4 | traces only |
| **Overall** | **7.2** | **Best packaging/harness baseline** |

---

## Evidence index

| ID | Claim | Path / URL | Level |
|----|-------|------------|-------|
| CX-01 | Progressive disclosure | https://developers.openai.com/codex/skills | L0 |
| CX-02 | 2% / 8K budget | https://developers.openai.com/codex/skills | L0 |
| CX-03 | render.rs disclosure text | `core-skills/src/render.rs:27-43` | L3 |
| CX-04 | Budget warning | `core-skills/src/render.rs:21` | L3 |
| CX-05 | injection | `core-skills/src/injection.rs` | L3 |
| CX-06 | Child no parent skills | `subagent_notifications.rs:1180` | L3 |
| CX-07 | Guardian | `guardian/mod.rs` | L2 |
