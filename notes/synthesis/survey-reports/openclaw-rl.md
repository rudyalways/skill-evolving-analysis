---
id: SR-openclaw-rl-001
title: OpenClaw-RL — RL Harness Survey Report (non-skill-store)
date: 2026-07-08
repo: openclaw-rl
evidence_level: L0
matrix_version: 1
status: complete
related: [T007, T002]
---

# OpenClaw-RL — RL Harness Survey Report

> **Local**: `/Users/maybewu/Documents/Projects/oss/openclaw-rl`  
> **Upstream**: [Gen-Verse/OpenClaw-RL](https://github.com/Gen-Verse/OpenClaw-RL)  
> **Note**: **Not** `openclaw/openclaw`. Not a SKILL.md lifecycle system — **RL training layer** for conversation → policy signals.

---

## 1. Architecture

OpenClaw-RL trains personalized agents from everyday conversations. Architecture emphasizes **async decoupling**:

```text
Serving loop          ←→  Rollout collection
        ↓                      ↓
PRM / Judge evaluation  →  Policy training (GRPO / OPD / etc.)
```

**Evidence (L0 README)**: [Gen-Verse/OpenClaw-RL](https://github.com/Gen-Verse/OpenClaw-RL) — *"Train any agent simply by talking"*

**Relation to skill survey**: Provides **Claw-R1 / SkillRL data plane** complement to OpenClaw `openclaw-trajectory` JSONL — not skill Author/Store/Discover.

---

## 2. Skill Runtime

**N/A** — no skill catalog, loader, or progressive disclosure in this repo.

TaiChu relevance: export `interaction_log` in trajectory shape compatible with OpenClaw-RL + Claw-R1 step middleware.

---

## 3. Skill Lifecycle

All stages **N/A** for SKILL.md. See [web-expanded-lifecycle-matrix-merged.md](../web-expanded-lifecycle-matrix-merged.md) row OpenClaw-RL.

---

## 4. Skill Evolution

Evolution here = **policy weights**, not skill documents. Conversation feedback → PRM/judge → GRPO.

Offline skill evolution (SkillBank) remains separate pipeline: OpenSquilla gates + Hermes GEPA.

---

## 5. Multi-Agent Skill

N/A at skill layer. Multi-turn conversation may include tool traces usable for RL.

---

## 6. Skill Governance

N/A for skills. Training data governance is project-specific.

---

## 7. Harness Integration

Pairs with **OpenClaw gateway** trajectory export (`oss/openclaw/trajectory/`). Local clone at `oss/openclaw-rl` — **L0 README only** in this workspace (no L3 walk yet).

---

## 8. RL Readiness

| Signal | Status |
|--------|--------|
| Step / trajectory | ★ primary purpose |
| Reward / PRM / judge | ★ |
| SkillRL | ◐ skill usage in traj as features |
| Claw-R1 | ★ aligned middleware philosophy |

**Matrix §15**: Best dedicated **RL harness** row alongside Hermes Atropos.

---

## 9. Borrow for TaiChu

| Pattern | Why |
|---------|-----|
| Async serve/train split | scale skill eval harness |
| Conversation → training signal | long-term SkillRL loop |
| Trajectory schema alignment | unify interaction_log + openclaw-trajectory |

---

## 10. Implement in TaiChu

| P | What |
|---|------|
| P2 | Export interaction_log fields matching OpenClaw trajectory |
| P3 | Optional OpenClaw-RL integration for policy experiments |

---

## 11. Do NOT Borrow

| Pattern | Why |
|---------|-----|
| Treat as skill registry | wrong repo |
| Confuse with openclaw skill-workshop | different layer |

---

## 12. Score (1–10)

| Category | Score | Notes |
|----------|:-----:|-------|
| Data Model | — | N/A |
| Runtime | — | N/A |
| Lifecycle | — | N/A |
| Evolution | — | policy not skill |
| Governance | — | N/A |
| Agent Integration | — | N/A |
| RL Readiness | **8** | purpose-built |
| **Overall (RL only)** | **8.0** | RL layer, not skill architecture |

---

## Evidence index

| ID | Claim | URL | Level |
|----|-------|-----|-------|
| OCR-01 | Project purpose | https://github.com/Gen-Verse/OpenClaw-RL | L0 |
| OCR-02 | Distinct from openclaw | [survey-methodology](../survey-methodology-and-repo-confirmation.md) §2.2 | L1 |
