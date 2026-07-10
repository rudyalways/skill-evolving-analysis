# Per-Repo Survey Report Template

Copy to `notes/synthesis/survey-reports/<repo>.md` and fill all 12 sections.
Matrix rows: [agent-skill-architecture-survey-matrix.md](../notes/synthesis/agent-skill-architecture-survey-matrix.md)

```yaml
---
id: SR-<repo>-001
title: "<Repo> — Agent Skill Architecture Survey Report"
date: YYYY-MM-DD
repo: <repo>
evidence_level: L0|L1|L2|L3
matrix_version: 1
related: [T007]
---
```

# <Repo> — Agent Skill Architecture Survey Report

> Local path: `...` · Upstream: `...` · Evidence: L?

---

## 1. Architecture

One paragraph: runtime shape, skill subsystem placement, key crates/modules.

```text
[diagram optional]
```

**Matrix sections**: §1 Data Model, §2 Discovery

---

## 2. Skill Runtime

How skills enter the agent loop: per-turn vs session, load path, cache, budget.

**Matrix sections**: §3 Exposure, §4 Recommendation, §5 Runtime, §6 Offload, §7 Usage

**Standout dimensions**: (list 3–5 ★ cells)

---

## 3. Skill Lifecycle

Author → store → discover → … → delete. Which stages exist?

**Matrix section**: §8 Lifecycle

**Lifecycle score**: _/13

---

## 4. Skill Evolution

Closed loop? Candidate → eval → publish? Risks?

**Matrix sections**: §9 Evolution, §10 Quality

---

## 5. Multi-Agent Skill

Shared vs private, subagent bundles, isolation.

**Matrix sections**: §12 Relationship, §13 Multi-Agent

---

## 6. Skill Governance

Trust, audit, marketplace, critical-skill protection.

**Matrix section**: §11 Governance

---

## 7. Harness Integration

Hooks, session factory, tool factories, compaction, trace.

**Key integration points**: (file paths)

---

## 8. RL Readiness

Step traces, trajectory export, SkillRL/Claw-R1 fit.

**Matrix section**: §15 RL Readiness

---

## 9. Borrow for TaiChu

| Dimension / Pattern | Why |
|---------------------|-----|
| | |

---

## 10. Implement in TaiChu

| Priority | What | TaiChu seam |
|----------|------|-------------|
| P0 | | |
| P1 | | |

---

## 11. Do NOT Borrow

| Pattern | Why avoid |
|---------|-----------|
| | |

---

## 12. Score (1–10)

| Category | Score | Notes |
|----------|:-----:|-------|
| Data Model | | |
| Runtime | | |
| Lifecycle | | |
| Evolution | | |
| Governance | | |
| Agent Integration | | |
| RL Readiness | | |
| **Overall** | | |

---

## Evidence index

| Claim | Path | Level |
|-------|------|-------|
| | | |
