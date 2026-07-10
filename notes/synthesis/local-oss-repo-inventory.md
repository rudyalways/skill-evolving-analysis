---
id: N2026-07-08-006
title: Local OSS repo inventory — skill/memory/evolution
date: 2026-07-08
tags: [oss-inventory, openclaw, hermes-agent, genericagent, taichu]
status: active
related: [N2026-07-08-005, T005]
---

# Local OSS Repo Inventory

> All paths on this Mac: `/Users/maybewu/Documents/Projects/...` (not `/Users/x/`)

## Quick lookup

| # | Local path | Upstream | Branch | Last commit |
|---|------------|----------|--------|-------------|
| 1 | `oss/openclaw` | https://github.com/openclaw/openclaw | main | 2026-04-27 |
| 2 | `oss/experimental/claude-code-rev` | https://github.com/oboard/claude-code-rev | main | 2026-04-08 |
| 3 | `drafts/zk/TaiChu` | https://taichu.fun/gitea/SystemAgentDev/TaiChu.git | xyz_ops_update | 2026-06-11 |
| 4 | `oss/genericagent` | https://github.com/lsdefine/genericagent | main | 2026-06-29 |
| 5 | `oss/codex` | https://github.com/openai/codex | main | 2026-06-07 |
| 6 | `oss/opensquilla` | git@github.com:opensquilla/opensquilla.git | main | 2026-07-01 |
| 7 | `oss/zeroclaw` | https://github.com/zeroclaw-labs/zeroclaw | main | 2026-03-04 |
| 8 | `oss/hermes-agent` | https://github.com/nousresearch/hermes-agent | main | 2026-04-10 |

---

## Skill / Memory / Evolution matrix

| Repo | SKILL.md count | Memory | Skill self-evolution |
|------|----------------|--------|---------------------|
| **openclaw** | ~83 bundled | memory-core + dreaming + promotion | compaction re-distill; skill-creator; **no auto skill replace** |
| **claude-code-rev** | 2 bundled | memdir (MEMORY.md, daily logs) | `/dream` distills logs → memory; **no skill auto-update** |
| **TaiChu** | 17 canonical (+ snapshots) | compaction only | **docs/planned** — comparison doc exists |
| **genericagent** | 0 (uses L3 SOP `.md`) | L1–L4 tiered memory | **`start_long_term_update`**, `/morphling` — strongest SOP crystallization |
| **codex** | ~18 samples | 2-phase memories (distill) | memory auto-write; skills user-managed |
| **opensquilla** | ~91 bundled | dream factory + session flush | **meta-skill-creator** + proposals pipeline |
| **zeroclaw** | 0 bundled (user workspace) | vector + nightly consolidation | memory distill cron; no skill auto-create |
| **hermes-agent** | ~122 bundled | MEMORY.md + plugins | **`skill_manage` tool** — agent CRUD skills |

---

## Per-repo notes

### 1. openclaw
- Personal AI assistant, multi-channel gateway
- `skills/`, `.agents/skills/`, ClawHub registry
- `extensions/memory-core` — hybrid search, temporal decay
- **Dreaming** (Light/Deep/REM → memory promotion)
- Compaction **re-distill** in `compaction-safeguard.ts`
- Key: `src/`, `extensions/memory-core/`, `skills/`

### 2. claude-code-rev
- Restored Claude Code from source maps (oboard)
- `src/memdir/` — auto-memory, team mem, `autoDreamEnabled`
- Nightly `/dream` skill distills daily logs
- Key: `src/memdir/`, `src/skills/bundled/`

### 3. TaiChu
- HarmonyOS + cloud agent stack (your project)
- 16 system skills + `init-local-user` in `skills/system/`
- Compaction in `core/agent-session/`; no persistent memory yet
- **Already has**: `docs/architecture/skill-system-cross-repo-comparison.md`
- Key: `services/rust/taichu-service/`, `skills/`, `core/agent-session/`

### 4. genericagent
- Minimal self-evolving agent (~3K LOC)
- **No AgentSkills** — L3 `*_sop.md` in `memory/` instead
- L1→L4 memory hierarchy; `reflect/scheduler.py` archive cron
- **`/morphling`** — absorb external skills into SOPs
- **`start_long_term_update`** — session → long-term distill
- Key: `ga.py`, `memory/`, `reflect/`

### 5. codex (OpenAI)
- Official Codex CLI (Rust)
- `codex-rs/skills/`, `codex-rs/memories/` — 2-phase async distill
- Skills = load/manage; memories = auto on session start
- Key: `codex-rs/core/`, `codex-rs/memories/`, `codex-rs/ext/skills/`

### 6. opensquilla
- Token-efficient agent microkernel
- 91 bundled skills incl. meta-skills
- `memory/dream/`, session flush/distill, repair queue
- **meta-skill-creator** → proposals in `~/.opensquilla/proposals/`
- Key: `src/opensquilla/memory/`, `skills/`

### 7. zeroclaw
- Rust agent runtime (~5MB RAM)
- Loads `~/.zeroclaw/workspace/skills/*/SKILL.md`; syncs open-skills
- Nightly **consolidation cron** → `MEMORY.md`
- Key: `src/memory/`, `src/cron/consolidation.rs`, `src/skills/`

### 8. hermes-agent (Nous Research)
- Explicit **self-improving** agent
- **`skill_manage`** — create/edit/patch/delete skills at runtime
- Memory nudges + post-turn skill review in `run_agent.py`
- 122 bundled skills; agent writes to `~/.hermes/skills/`
- Key: `tools/skill_manager_tool.py`, `agent/memory_manager.py`, `skills/`

---

## Rankings for skill-evolving-analysis project

| Capability | Best repos to study |
|------------|---------------------|
| Skill auto-CRUD at runtime | **hermes-agent** (`skill_manage`) |
| Trajectory → SOP/skill distill | **genericagent** (`start_long_term_update`, morphling) |
| Memory → promotion loop | **openclaw** (dreaming), **opensquilla** (dream factory) |
| Skill proposal + acceptance | **opensquilla** (meta-skill-creator) |
| Step-level / official CLI patterns | **codex** (memories 2-phase) |
| Your integration target | **TaiChu** (gap: no evolution yet; comparison doc ready) |

---

## TaiChu cross-reference

Existing doc: `drafts/zk/TaiChu/docs/architecture/skill-system-cross-repo-comparison.md`
