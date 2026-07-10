---
id: SR-opensquilla-001
title: OpenSquilla — Agent Skill Architecture Survey Report
date: 2026-07-08
repo: opensquilla
evidence_level: L3
matrix_version: 1
related: [T007]
---

# OpenSquilla — Agent Skill Architecture Survey Report

> **Local**: `/Users/maybewu/Documents/Projects/oss/opensquilla`  
> **Upstream**: [opensquilla/opensquilla](https://github.com/opensquilla/opensquilla)  
> **Matrix**: [agent-skill-architecture-survey-matrix.md](../agent-skill-architecture-survey-matrix.md)  
> **Detail card**: [repos/opensquilla.md](../repos/opensquilla.md)

---

## 1. Architecture

OpenSquilla is a **staged harness** around an explicit Agent FSM (`IDLE→THINKING→TOOL_CALLING→DONE`). Skills are first-class `SkillSpec` objects loaded through a **6-layer precedence** system, filtered **every turn** by pipeline step `filter_skills`, injected via `SkillInjector`, and evolved through a **proposals directory** with multi-gate acceptance.

```text
Gateway → TurnRunnerHarness → Pipeline (filter_skills → inject) → Agent FSM
                                              ↓
                                    proposals/ → accept → MANAGED
```

**Evidence**

| Claim | Source |
|-------|--------|
| 6-layer precedence | `src/opensquilla/skills/loader.py:184-244` — `EXTRA < BUNDLED < MANAGED < PERSONAL < PROJECT < WORKSPACE` |
| Per-turn filter step | `src/opensquilla/engine/steps/skills_filter.py:1` — *"Step 3: Gate skills deterministically, optionally filter by relevance, inject."* |
| MetaSkill DAG | `src/opensquilla/skills/meta/orchestrator.py` |
| Docs | [Meta-Skills](https://www.opensquilla.ai/docs/features/meta-skills/) — *"Meta-skills package repeatable multi-step work as reusable, inspectable workflows"* |

**Matrix**: §1 Data Model 9/14 ★ · §2 Discovery 15/17 ★

---

## 2. Skill Runtime

| Pattern | Implementation | Evidence |
|---------|----------------|----------|
| **Per-turn catalog** | ★ `filter_skills()` runs each turn in pipeline | `skills_filter.py:1`, tests `test_skills_default_prompt_contract.py` |
| **Recommendation** | ★ `HybridRetriever` lexical + semantic RRF, top-k default 5 | `skills_filter.py:22-45`, `_get_retriever()` |
| **Progressive disclosure** | `inject_full` / `inject_compact` (name+location only) | `skills/injector.py` |
| **Pinned skills** | `always`, meta_match bypass retrieval | `skills_filter.py` (pinned block ~162-188 per lifecycle survey) |
| **Invoked tracking** | `collect_invoked_skills(turn_segments)` | `engine/runtime.py:250`, tests `test_decision_log_skills_invoked.py` |
| **Meta invoke** | `meta_invoke(name)` runs DAG, not skill_view on meta | `injector.py:40-49` |

**Quote — filter step header**

```python
# src/opensquilla/engine/steps/skills_filter.py:1
"""Step 3: Gate skills deterministically, optionally filter by relevance, inject."""
```

**Standout dimensions**: Per Turn Loading ★ · Recommend ★ · Skill Graph ★ · Refresh Policy ★

---

## 3. Skill Lifecycle

| Stage | OpenSquilla | Evidence |
|-------|-------------|----------|
| Human / imported | hub install → layers | `skills/loader.py` |
| Generated | `auto_propose`, Dream hook | `skills/creator/auto_propose.py`, `memory/dream/runner.py` |
| Reviewed | `evaluate_proposal_gates` | `skills/proposals_lib.py` |
| Published | `accept_proposal()` → MANAGED | `proposals_lib.py:425` |
| Deleted | `reject_proposal()` | `proposals_lib.py` |
| Versioned | `skills-lock.json` SHA256 | `skills/hub/lockfile.py` |

**Lifecycle score**: **12/13** (rollback ◐)

**Quote — loader layers**

```python
# src/opensquilla/skills/loader.py:184-189
SkillLayer.EXTRA,
SkillLayer.BUNDLED,
SkillLayer.MANAGED,
# ... PERSONAL, PROJECT, WORKSPACE
```

---

## 4. Skill Evolution

**Strongest productized loop** among the 8 frameworks:

```text
Decision log / Dream signal
        ↓
auto_propose / meta-skill-creator
        ↓
~/.opensquilla/proposals/{id}/ + gates.json
        ↓
evaluate_proposal_gates (4 gates)
        ↓
runtime_e2e meta vs baseline judge
        ↓
accept_proposal → MANAGED skills
```

| Mechanism | Path |
|-----------|------|
| Auto propose | `skills/creator/auto_propose.py` |
| Gates | `skills/proposals_lib.py` |
| E2E judge | `skills/creator/runtime_e2e.py` |
| Dream reflection | `memory/dream/runner.py`, `dream/candidates.py` |

**Matrix §9**: Candidate ★ · Merge ★ · Pairwise ★ (meta vs baseline) · Auto Version ★

**Quality §10**: Regression ★ (`eval_prompts`) · A/B ★ · Integration Test ★ (`runtime_e2e`)

---

## 5. Multi-Agent Skill

| Pattern | Status | Evidence |
|---------|--------|----------|
| MetaOrchestrator DAG | ★ skill_exec + agent + tool_call steps | `skills/meta/orchestrator.py` |
| Subagent one-shot | ◐ meta agent executor, not skill preload list | `meta/executors/agent.py` |
| Complementary skills | ◐ via DAG composition | meta steps reference multiple skills |
| Skill isolation | one-shot subagent contexts | `engine/subagent.py` |

**Docs quote**: MetaSkill = *"reusable workflow made of multiple steps / skills / checks / outputs"* ([OpenSquilla Meta-Skills](https://www.opensquilla.ai/docs/features/meta-skills/))

---

## 6. Skill Governance

| Control | Implementation |
|---------|----------------|
| Policy chain | `tools/policy/chain.py` — 30+ builtins |
| Proposal gates | `gates.json` + `evaluate_proposal_gates` |
| Hub quarantine | install scan |
| requires_tools gate | `skills/eligibility.py` |
| Lock file provenance | SHA256 pin |

**Risk**: Large `engine/agent.py` (~6000 lines) — operational complexity, not security per se.

---

## 7. Harness Integration

| Hook / Stage | Path |
|--------------|------|
| TurnRunnerHarness | `engine/turn_runner/harness.py` |
| Pipeline steps | `engine/pipeline.py` |
| TurnHook / ToolHook / CompactionHook | `engine/hooks/types.py` |
| Decision log | `observability/decision_log.py` |
| Context budget | `context_budget.py` |

Skills are **not bolted on** — they are a pipeline stage with deterministic gating before LLM sees catalog.

---

## 8. RL Readiness

| Signal | Status | Evidence |
|--------|--------|----------|
| Step trace | ★ `PipelineStepRecord` | `observability/trace.py` |
| Trajectory | ★ `TraceContext` | pipeline log |
| Tool trace | ★ decision log `skills_invoked` | tests `test_decision_log_skills_invoked.py` |
| Reward | · | — |
| Offline RL | ◐ traces exportable | no trainer in-repo |
| SkillRL | ◐ proposals + eval mirror SkillBank update | conceptual fit |
| Claw-R1 | ★ step-level pipeline records | best OSS middleware alongside OpenClaw trajectory |

**Note**: Squilla Router LightGBM (`squilla_router/`) is **model routing**, not skill RL.

---

## 9. Borrow for TaiChu

| Pattern | Why |
|---------|-----|
| `proposals/` + `gates.json` + `accept_proposal` | Safest evolution publish path |
| Per-turn `HybridRetriever` + pinned always | Best OSS skill recommendation |
| `collect_invoked_skills` telemetry | Feeds miner + compact survival |
| `runtime_e2e` judge | Promotion A/B before publish |
| `inject_compact` + user_message injection | Aligns with TaiChu user prefix philosophy |
| MetaSkill DAG | P3 workflow layer after atomic skills stable |

---

## 10. Implement in TaiChu

| Priority | What | TaiChu seam |
|----------|------|-------------|
| P1 | `~/.taichu/proposals/` + gates | new module; mirror `proposals_lib.py` |
| P1 | RRF on Toollery `before_prompt` | `tool_search_bridge.rs:370-382` |
| P2 | `skills_invoked` in interaction_log | JSONL schema extension |
| P2 | `runtime_e2e` harness | integration test crate |
| P3 | MetaSkill orchestrator | new `meta/` after P0/P1 |

---

## 11. Do NOT Borrow

| Pattern | Why |
|---------|-----|
| Full 6000-line agent FSM monolith | TaiChu Pi-mono loop is different; take patterns not structure |
| Dream cron complexity wholesale | adopt gate concept first, Dream later |
| Auto-accept without human policy | gates are the point — keep human/policy path for `critical` skills |

---

## 12. Score (1–10)

| Category | Score | Notes |
|----------|:-----:|-------|
| Data Model | 9 | SkillSpec + MetaSkill + lock SHA |
| Runtime | 9 | Per-turn RRF ★ |
| Lifecycle | 12/13 → **9** | Near-complete |
| Evolution | 9 | 4-gate + E2E |
| Governance | 8 | gates + policy chain |
| Agent Integration | 9 | MetaSkill DAG |
| RL Readiness | 6 | traces strong; no RL trainer |
| **Overall** | **9.0** | Best single-repo skill evolution productization |

---

## Evidence index

| ID | Claim | Path / URL | Level |
|----|-------|------------|-------|
| OS-01 | 6-layer loader | `skills/loader.py:184-244` | L3 |
| OS-02 | Per-turn filter | `engine/steps/skills_filter.py:1` | L3 |
| OS-03 | accept_proposal | `skills/proposals_lib.py:425` | L3 |
| OS-04 | collect_invoked_skills | `engine/runtime.py:250` + tests | L3 |
| OS-05 | MetaSkill docs | https://www.opensquilla.ai/docs/features/meta-skills/ | L0 |
| OS-06 | HybridRetriever | `skills_filter.py:22-45` | L3 |
