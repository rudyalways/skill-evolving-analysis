---
id: SR-hermes-001
title: Hermes Agent — Agent Skill Architecture Survey Report
date: 2026-07-08
repo: hermes-agent
evidence_level: L3
matrix_version: 1
related: [T007]
---

# Hermes Agent — Agent Skill Architecture Survey Report

> **Local**: `/Users/maybewu/Documents/Projects/oss/hermes-agent`  
> **Upstream**: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)  
> **Matrix**: [agent-skill-architecture-survey-matrix.md](../agent-skill-architecture-survey-matrix.md)

---

## 1. Architecture

Hermes is a Python monolith (`run_agent.py` ~9.8k lines) combining: OpenAI tool-calling agent loop, Gateway, **40+ tools**, frozen MEMORY prefix cache, and **Atropos RL environment**. Skills follow [agentskills.io](https://agentskills.io)-compatible `SKILL.md` under `~/.hermes/skills/`, with **progressive disclosure** (`skills_list` → `skill_view`) and **agent-writable** procedural memory via `skill_manage`.

```text
AIAgent loop → tools (skills_list, skill_view, skill_manage)
                    ↓ post-turn
            _spawn_background_review → quiet agent → patch/create skill
                    ↓
            ~/.hermes/skills/  (+ skills_guard scan)
```

**Evidence**

| Claim | Source |
|-------|--------|
| Skill manager purpose | `tools/skill_manager_tool.py:1-12` |
| agentskills layout | `skill_manager_tool.py:22-32` |
| Background review | `run_agent.py:1768-1796`, `9626` |
| Skills docs | [hermes skills.md](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md) |

**Quote — skill_manage header**

```python
# tools/skill_manager_tool.py:5-8
"""
Allows the agent to create, update, and delete skills, turning successful
approaches into reusable procedural knowledge. New skills are created in
~/.hermes/skills/.
"""
```

**Quote — procedural vs declarative memory**

```python
# tools/skill_manager_tool.py:10-12
# Skills are the agent's procedural memory: they capture *how to do a specific
# type of task* based on proven experience. General memory (MEMORY.md, USER.md) is
# broad and declarative. Skills are narrow and actionable.
```

---

## 2. Skill Runtime

| Pattern | Implementation | Evidence |
|---------|----------------|----------|
| Progressive disclosure | metadata index in prompt → `skill_view` | `tools/skills_tool.py`, `agent/prompt_builder.py` |
| Session preload | CLI `--skills a,b` loads full text at start | `cli.py` (~8999) |
| Per-turn catalog | · frozen index (prefix cache) | `prompt_caching.py` |
| Background evolution | async review every ~10 tool iters | `run_agent.py:9604-9610` |
| CRUD | `skill_manage` create/edit/patch/delete/write_file | `skill_manager_tool.py` |

**Quote — review prompt**

```python
# run_agent.py:1773-1775
"If a relevant skill already exists, update it with what you learned. "
"Otherwise, create a new skill if the approach is reusable."
```

**Standout**: Auto Patch ★ · Self Reflection ★ · Progressive disclosure ★  
**Weakness**: No RRF ranking · No proposal queue · No read-before-write enforcement

---

## 3. Skill Lifecycle

| Stage | Hermes | Evidence |
|-------|--------|----------|
| Human written | bundled + hub | `skills_sync.py` |
| AI written | ★ immediate via `skill_manage` | `skill_manager_tool.py` |
| Reviewed | ◐ background review agent | `run_agent.py:_spawn_background_review` |
| Published | ★ direct to `~/.hermes/skills/` | no staging dir |
| Deleted | ★ `skill_manage(delete)` | `skill_manager_tool.py` |
| Versioned | ◐ bundled origin-hash manifest | `skills_sync.py` |

**Lifecycle score**: **10/13** — missing formal approve/rollback/proposal staging

**Known risks (public issues)**

| Issue | URL | Problem |
|-------|-----|---------|
| #55647 | [skill_manage patches hallucinate](https://github.com/NousResearch/hermes-agent/issues/55647) | background review patches without reading current `SKILL.md` |
| #54195 | [symlink discovery](https://github.com/NousResearch/hermes-agent/issues/54195) | skill_manage vs skill_view path mismatch |
| #25083 | [critical skill protection](https://github.com/NousResearch/hermes-agent/issues/25083) | agent can modify governance skills |

---

## 4. Skill Evolution

**Most aggressive online CRUD loop** in the survey:

```text
Nudge (every 10 tool calls) OR post-turn
        ↓
_spawn_background_review (fork quiet agent)
        ↓
skill_manage: create | edit | patch | delete
        ↓
skills_guard security scan
        ↓
Immediate write to ~/.hermes/skills/
```

| Dimension | Status |
|-----------|--------|
| Reflection | ★ `_SKILL_REVIEW_PROMPT` |
| Auto Patch | ★ `patch` action |
| Candidate pool | · (writes directly) |
| Merge gate | · |
| RL | ★ Atropos + `rl_training_tool` |

**Offline evolution** (separate repo, Web L0): [hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) — GEPA/DSPy — **not cloned locally**.

---

## 5. Multi-Agent Skill

| Pattern | Status | Evidence |
|---------|--------|----------|
| delegate_task | ★ isolated child context, parent sees summary | `tools/delegate_tool.py` |
| Skill preload on delegate | · no `skills=[]` param | lifecycle survey |
| Shared index | child uses same skills_list/view | same ~/.hermes |
| Skill isolation | ★ context isolation via delegate | `delegate_tool.py` |

Subagents **inherit toolsets subset**, not complementary skill bundles.

---

## 6. Skill Governance

| Control | Status | Evidence |
|---------|--------|----------|
| skills_guard scan | ★ on write | `skill_manager_tool.py:47-50` |
| Security on hub install | ★ `should_allow_install` | `skills_guard.py` |
| Critical skill lock | ❌ issue #25083 | public issue |
| Read-before-write | ❌ issue #55647 | public issue |
| Proposal staging | · | — |

**Quote — security on agent-created skills**

```python
# tools/skill_manager_tool.py:47-48
# Import security scanner — agent-created skills get the same scrutiny as
# community hub installs.
```

---

## 7. Harness Integration

| Component | Path |
|-----------|------|
| Main loop | `run_agent.py`, `environments/agent_loop.py` |
| Prompt layers | `agent/prompt_builder.py` |
| Frozen prefix cache | `agent/prompt_caching.py`, `tools/memory_tool.py` |
| Context compression | `agent/context_compressor.py` |
| Gateway hooks | `gateway/hooks.py` — `agent:step` |
| Trajectory | `agent/trajectory.py` JSONL |

Skills integrate as **tools in the tool loop**, not as a separate pipeline stage (contrast OpenSquilla).

---

## 8. RL Readiness

| Signal | Status | Evidence |
|--------|--------|----------|
| Step trace | ★ `agent:step` hook | `gateway/hooks.py` |
| Trajectory | ★ JSONL + SQLite | `agent/trajectory.py`, `hermes_state.py` |
| Reward | ★ Atropos env | `environments/hermes_base_env.py` |
| Online RL | ★ `rl_training_tool` | `tools/rl_training_tool.py` |
| SkillRL | ◐ skills as procedural memory in traj | conceptual |
| Claw-R1 | ★ rich step metadata | strong middleware candidate |

**Strongest RL readiness** among the 8 for skill-augmented policy training.

---

## 9. Borrow for TaiChu

| Pattern | Why |
|---------|-----|
| `_spawn_background_review` async pattern | Post-turn miner without blocking user |
| `skill_manage` **actions** (as candidate-only tool) | CRUD API design |
| `skills_guard` scan | Before device load |
| Frozen catalog + on-demand load | Matches TaiChu prefix cache design |
| Atropos env interface | If pursuing SkillRL experiments |
| Procedural vs declarative split | Clear skill/memory boundary |

---

## 10. Implement in TaiChu

| Priority | What | Seam |
|----------|------|------|
| P1 | `skill_manage` → writes `~/.taichu/proposals/` only | `builtintools/` new tool |
| P1 | Post-turn async review task | session handle after turn |
| P1 | `skills_guard`-style scanner | pre-publish |
| P2 | Atropos-compatible trace export | `interaction_log` schema |
| P0 | **Require `skill_view` before `patch`** | hard gate (fix Hermes #55647 class) |

---

## 11. Do NOT Borrow

| Pattern | Why |
|---------|-----|
| Direct production `skill_manage(patch)` | issue #55647 hallucinated deletes |
| No critical-skill protection | issue #25083 |
| 9.8k-line monolith structure | take tools/patterns only |
| Ungated auto-merge | use OpenSquilla accept_proposal instead |

---

## 12. Score (1–10)

| Category | Score | Notes |
|----------|:-----:|-------|
| Data Model | 8 | Standard SKILL.md + assets |
| Runtime | 8 | Progressive disclosure ★; no per-turn rank |
| Lifecycle | 8 | 10/13 stages |
| Evolution | 9 | Strongest CRUD; weakest gates |
| Governance | 5 | scan yes; critical lock no |
| Agent Integration | 7 | delegate yes; no skill bundles |
| RL Readiness | 8 | Atropos ★ |
| **Overall** | **8.1** | Best RL + online CRUD; risky ungated patch |

---

## Evidence index

| ID | Claim | Path / URL | Level |
|----|-------|------------|-------|
| H-01 | skill_manage header | `tools/skill_manager_tool.py:1-32` | L3 |
| H-02 | Review prompt | `run_agent.py:1768-1775` | L3 |
| H-03 | Spawn review | `run_agent.py:1792`, `9626` | L3 |
| H-04 | Patch hallucinate issue | https://github.com/NousResearch/hermes-agent/issues/55647 | L0 |
| H-05 | Skills user docs | https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md | L0 |
| H-06 | RL tool | `tools/rl_training_tool.py` | L2 |
