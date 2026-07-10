---
id: SR-genericagent-001
title: GenericAgent — Agent Skill Architecture Survey Report
date: 2026-07-08
repo: genericagent
evidence_level: L3
matrix_version: 1
related: [T007]
---

# GenericAgent — Agent Skill Architecture Survey Report

> **Local**: `/Users/maybewu/Documents/Projects/oss/genericagent`  
> **Upstream**: [lsdefine/genericagent](https://github.com/lsdefine/genericagent)  
> **Paper**: [arXiv:2604.17091](https://arxiv.org/abs/2604.17091)  
> **Matrix**: [agent-skill-architecture-survey-matrix.md](../agent-skill-architecture-survey-matrix.md)

---

## 1. Architecture

Minimal Python framework (~3K LOC seed): **9 atomic tools** + ~100-line agent loop. **Does not use SKILL.md** — skills are **`memory/*_sop.md` procedures** in an L0–L4 tiered tree, loaded on demand via `file_read`. Philosophy: **don't preload skills, evolve them** by crystallizing execution paths after tasks.

```text
Task → agent loop → file_read(SOP) on demand
        ↓ success
start_long_term_update → L2/L3 memory (action-verified)
        ↓
personal skill tree grows
```

**Quote — README philosophy**

```markdown
# README.md:38-40
> Design philosophy — **don't preload skills, evolve them.**
Every time GenericAgent solves a new task, it automatically crystallizes the
execution path into a reusable **Skill**.
```

**Evidence**: `ga.py`, `memory/memory_management_sop.md`, `agent_loop.py`

---

## 2. Skill Runtime

| Pattern | Implementation | Evidence |
|---------|----------------|----------|
| Discovery | L1 index ≤30 lines → pick SOP | `memory_management_sop.md` |
| Load | `file_read` full SOP | `ga.py:423-425` |
| Anchor prompt | rebuild working memory; **only latest user msg to API** | `ga.py:539-549` |
| Per-turn catalog | · related_sop hints | `ga.py:547` |
| Access stats | `file_access_stats.json` weak ranking | `log_memory_access` |

**Quote — anchor cost control**

Only latest user message sent to API after anchor rebuild — **6× token reduction** claimed in README (L0 marketing; mechanism in `ga.py` L3).

**Standout**: Skill Miner philosophy ★ · Token-efficient anchor ★  
**Weakness**: Not agentskills.io compatible · no gates

---

## 3. Skill Lifecycle

| Stage | GenericAgent | Evidence |
|-------|--------------|----------|
| Human seed | L0 protocols in memory/ | `memory/*.md` |
| AI crystallize | `start_long_term_update` | `ga.py:508-523` |
| Verified write | only **action-verified** axioms | `memory_management_sop.md` |
| Morphling | long-horizon SOP `/morphling` | `morphling_sop.md` |
| Formal approve/rollback | · | — |

**Lifecycle score**: **7/13** — strong mine/write; weak governance

**Quote — long term update gate**

```python
# ga.py:508-523 (paraphrased from lifecycle survey)
# start_long_term_update: agent self-trigger; only verified-success info → L2/L3
```

---

## 4. Skill Evolution

**Closest to SkillRL "trajectory → abstraction" spirit** among surveyed repos — but **without** formal candidate pool, eval harness, or versioned SkillBank.

| Mechanism | Path |
|-----------|------|
| Crystallize on success | `start_long_term_update` |
| Goal Mode inspect/improve | `reflect/goal_mode.py` |
| Reflect scheduler | `reflect/scheduler.py` |
| Plan VERIFY gate | `ga.py:472-475` |

**Matrix §9**: Reflection ◐ · Candidate ◐ (implicit) · Auto Patch ◐ · **no** merge/gate/RL

---

## 5. Multi-Agent Skill

| Pattern | Status | Evidence |
|---------|--------|----------|
| Agent team BBS | ◐ coordination | `reflect/agent_team_worker.py` |
| Checklist subprocess | ◐ workers | reflect/ |
| Skill bundles per role | · | — |
| Skill transfer | · summary only | — |

Not a multi-agent **skill architecture** — team features are reflect-oriented.

---

## 6. Skill Governance

| Control | Status |
|---------|--------|
| L0 memory_management_sop protocol | ★ documentation |
| Plan VERIFY | ◐ plan mode only |
| Versioning / audit / trust tier | · |
| Critical skill protection | · |

Weakest governance in survey except evolution **intent**.

---

## 7. Harness Integration

| Component | Path |
|-----------|------|
| Agent loop | `agent_loop.py:42-107` |
| Handler dispatch | `ga.py` do_* tools |
| Plugin hooks | `plugins/hooks.py` — agent/turn/tool events |
| Reflect cron | `reflect/scheduler.py` |
| Context compress | `llmcore.py:40-111` |

Simple harness — useful as **miner philosophy**, not runtime template.

---

## 8. RL Readiness

| Signal | Status |
|--------|--------|
| Model response logs | ◐ `temp/model_responses/` |
| Trajectory schema | · |
| Reward | · |
| SkillRL | ◐ conceptual (SOP mine) |
| Claw-R1 | · |

---

## 9. Borrow for TaiChu

| Pattern | Why |
|---------|-----|
| Skill Miner: task→trajectory→candidate | SkillRL alignment |
| Action-verified write axiom | only publish after regression pass |
| L0 skill-update SOP markdown | human-readable governance doc |
| Anchor prompt pattern | mobile token savings |
| Reflect scheduler | periodic review cron (HarmonyOS health) |
| `/morphling` long-horizon crystallize | MetaSkill inspiration |

---

## 10. Implement in TaiChu

| P | What | Seam |
|---|------|------|
| P2 | FailureMiner / SuccessMiner on interaction_log | post-turn job |
| P2 | L0 `skill-update-sop.md` in docs | docs/architecture |
| P3 | Anchor-style context rebuild option | session config |
| **Never** | direct crystallize → canonical | use proposals path |

---

## 11. Do NOT Borrow

| Pattern | Why |
|---------|-----|
| Ungated `file_patch` to production SOP/skill |固化错误 workaround |
| Non-SKILL.md as primary format | TaiChu standard is SKILL.md |
| Sync blocking loop | TaiChu is async Rust |

---

## 12. Score (1–10)

| Category | Score | Notes |
|----------|:-----:|-------|
| Data Model | 5 | SOP not SKILL.md |
| Runtime | 5 | on-demand read; no catalog rank |
| Lifecycle | 7 | crystallize strong |
| Evolution | 6 | philosophy ★; engineering weak |
| Governance | 2 | protocol doc only |
| Agent Integration | 3 | weak multi-agent skills |
| RL Readiness | 2 | minimal |
| **Overall** | **4.8** | **Best SkillRL-style miner inspiration** |

---

## Evidence index

| ID | Claim | Path / URL | Level |
|----|-------|------------|-------|
| GA-01 | Don't preload, evolve | `README.md:38-40` | L0 |
| GA-02 | L0–L4 memory tiers | `memory/memory_management_sop.md` | L3 |
| GA-03 | start_long_term_update | `ga.py:508-523` | L3 |
| GA-04 | Plan VERIFY | `ga.py:472-475` | L3 |
| GA-05 | Paper | https://arxiv.org/abs/2604.17091 | L0 |
| GA-06 | Upstream | https://github.com/lsdefine/genericagent | L0 |
