---
id: SR-zeroclaw-001
title: ZeroClaw — Agent Skill Architecture Survey Report
date: 2026-07-08
repo: zeroclaw
evidence_level: L3
matrix_version: 1
related: [T007]
---

# ZeroClaw — Agent Skill Architecture Survey Report

> **Local**: `/Users/maybewu/Documents/Projects/oss/zeroclaw`  
> **Upstream**: [zeroclaw-labs/zeroclaw](https://github.com/zeroclaw-labs/zeroclaw)  
> **Registry**: [zeroclaw-labs/zeroclaw-skills](https://github.com/zeroclaw-labs/zeroclaw-skills) (community; **not cloned locally** — DNS timeout in session)  
> **Matrix**: [agent-skill-architecture-survey-matrix.md](../agent-skill-architecture-survey-matrix.md)

---

## 1. Architecture

Rust modular runtime: agent loop, tools, memory (pluggable backends), **skills module**, gateway, goals/SOP engine, subagent registry. Skills are `SKILL.md` or `SKILL.toml` in workspace with **Full vs Compact injection modes** and a dedicated **`skills/audit.rs`** security scanner. Evolution is **not** a focus — governance at install/load time is.

```text
workspace/skills/ → load_skills_with_config
        ↓
prompt_injection_mode: Full | Compact
        ↓
SkillToolHandler (placeholder → native tool schema)
        ↓
zeroclaw skills audit <name>  [user responsibility]
```

**Evidence**: `src/skills/mod.rs`, `src/skills/audit.rs`, `src/skills/tool_handler.rs`

---

## 2. Skill Runtime

| Pattern | Implementation | Evidence |
|---------|----------------|----------|
| Full injection | preload instructions+tools in prompt | `skills/mod.rs:800-814` |
| Compact injection | summary + on-demand read at location | same |
| `always` flag | full text even in compact mode | `skills/mod.rs` |
| Per-turn filter | · session-level only | — |
| Loop detection | warn → hard stop on tool stagnation | `agent/loop_/detection.rs` |

**Quote — zip bomb limits (audit)**

```rust
// src/skills/audit.rs:16-20
/// Maximum number of entries allowed in a skill zip archive.
const ZIP_MAX_ENTRIES: usize = 1_000;
/// Maximum total decompressed size across all entries (50 MB).
/// Prevents zip-bomb extraction from filling disk.
```

**Standout**: Audit ★ · Compact/Full mode ★ · Loop detection ★

---

## 3. Skill Lifecycle

| Stage | ZeroClaw | Evidence |
|-------|----------|----------|
| Installed | workspace copy / open-skills sync | `skills/mod.rs` |
| Audited | `audit_skill_directory` | `skills/audit.rs` |
| Loaded | runtime scan | `load_skills_with_config` |
| Evolved | · | — |
| Deleted | user removes dir | FS |
| Memory consolidated | nightly cron (memory, not skills) | `cron/consolidation.rs` |

**Lifecycle score**: **5/13**

---

## 4. Skill Evolution

**No runtime evolution loop.**

| Mechanism | Target |
|-----------|--------|
| `skills/audit.rs` | security at load |
| `cron/consolidation.rs` | **memory** hygiene |
| `memory/hygiene.rs` | archival |

Skills are **governed objects**, not self-modifying agents.

**Matrix §9**: 2/16 — audit only.

---

## 5. Multi-Agent Skill

| Pattern | Status | Evidence |
|---------|--------|----------|
| SubAgentRegistry | ★ concurrency limits | `tools/subagent_spawn.rs` |
| Team topology | Single/LeadSubagent/StarTeam/MeshTeam | `agent/team_orchestration.rs` |
| Per-subagent skills param | · | — |
| SOP engine | goals + step gate eval | `goals/engine.rs` |

Skills attach to **workspace**, not subagent role bundles.

---

## 6. Skill Governance

| Control | Evidence |
|---------|----------|
| Zip-bomb / traversal / injection patterns | `skills/audit.rs` |
| Registry disclaimer | zeroclaw-skills README (Web L0) |
| Economic threshold | `economic/mod.rs` |
| SOP audit logger | `tools/sop_execute.rs` with_audit |

**Quote — registry realism (Web / README)**

> Registry CI does **structure validation, secret detection, dangerous regex, file-policy** — but registry is **not a vetted security boundary**; users must `zeroclaw skills audit <name>` and read SKILL.md themselves.  
> — [zeroclaw-labs/zeroclaw-skills](https://github.com/zeroclaw-labs/zeroclaw-skills) (L0, not locally cloned)

**TaiChu lesson**: CI scan ≠ security boundary — same as enterprise marketplace risk (cf. OpenClaw Verge article).

---

## 7. Harness Integration

| Component | Path |
|-----------|------|
| Agent loop | `agent/loop_.rs` (~7000 lines) |
| auto_compact_history | `agent/loop_/history.rs` |
| HookHandler trait | `hooks/traits.rs` |
| SessionMemoryHook | placeholder/no-op — weakness | `hooks/builtin/session_memory.rs` |
| MCP | `tools/mod.rs` |

---

## 8. RL Readiness

| Signal | Status |
|--------|--------|
| OTEL / runtime_trace | ◐ `observability/` |
| Economic tracker | ◐ task payment model — not RL |
| Trajectory export | · |
| SkillRL / Claw-R1 | · |

Low RL readiness; value is **Rust audit patterns** for TaiChu.

---

## 9. Borrow for TaiChu

| Pattern | Why |
|---------|-----|
| `audit_skill_directory` patterns | pre-load community skills on device |
| Full vs Compact injection config | user-tunable token policy |
| Zip-bomb / path traversal checks | HarmonyOS device safety |
| LoopDetector stagnation stop | long-running agent sessions |
| trust_tier + `mutable_by_agent: false` metadata | schema design |
| Registry disclaimer pattern | honest community skill UX |

---

## 10. Implement in TaiChu

| P | What | Seam |
|---|------|------|
| P1 | Port audit checks to skill loader | before canonical publish |
| P2 | `prompt_injection_mode` config | prompt_builder |
| P2 | Loop detection on tool repeat | agent-loop |
| P1 | trust_tier in SkillManifest | registry schema |

---

## 11. Do NOT Borrow

| Pattern | Why |
|---------|-----|
| Assume registry CI = safe | explicit disclaimer |
| SessionMemoryHook as-is | no-op in upstream |
| SOP-only without SKILL.md evolution | TaiChu uses SKILL.md standard |

---

## 12. Score (1–10)

| Category | Score | Notes |
|----------|:-----:|-------|
| Data Model | 6 | md/toml; version field |
| Runtime | 5 | session inject; no per-turn rank |
| Lifecycle | 5 | load/audit only |
| Evolution | 2 | none |
| Governance | 7 | audit ★ |
| Agent Integration | 4 | subagent no skill API |
| RL Readiness | 2 | minimal |
| **Overall** | **5.0** | **Best audit template for TaiChu** |

---

## Evidence index

| ID | Claim | Path / URL | Level |
|----|-------|------------|-------|
| ZC-01 | Zip audit limits | `src/skills/audit.rs:16-28` | L3 |
| ZC-02 | Skills module | `src/skills/mod.rs` | L3 |
| ZC-03 | Loop detection | `agent/loop_/detection.rs` | L2 |
| ZC-04 | Registry repo | https://github.com/zeroclaw-labs/zeroclaw-skills | L0 |
| ZC-05 | Main repo | https://github.com/zeroclaw-labs/zeroclaw | L0 |
