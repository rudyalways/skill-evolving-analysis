---
id: N2026-07-08-001
title: SkillRL vs Claw-R1 — Cross-paper comparison
date: 2026-07-08
tags: [skillrl, claw-r1, synthesis]
status: active
related: [T001, T002, T003]
---

# SkillRL vs Claw-R1

These two papers target **different layers** of the agent RL stack. They are **complementary, not competing**.

| Paper | Focus | Layer |
|-------|-------|-------|
| [SkillRL](../../topics/skill-rl/overview.md) | How the policy learns from experience | RL algorithm / training method |
| [Claw-R1](../../topics/claw-r1/overview.md) | How agent interaction data is collected, managed, fed into RL | Infrastructure / data system |

---

## 1. SkillRL

**Paper:** [SkillRL: Evolving Agents via Recursive Skill-Augmented Reinforcement Learning](https://arxiv.org/abs/2602.08234) (2026)

### Motivation

Most LLM agents behave episodically — every task is almost independent. Existing memory methods save raw trajectories that are long, noisy, redundant, hard to retrieve, and don't generalize.

**Question:** Can we convert trajectories into reusable skills?

### Main idea — SkillBank

Instead of `Observation → Action → Observation → Action → ...`, store compact skills:

> "When searching webpages, first identify official sources, then compare, then verify."

### Pipeline

```
Environment → Rollouts → Teacher LLM → Skill distillation → SkillBank
    → Retrieve skills → Policy → GRPO → Better policy
    → New trajectories → Update SkillBank
```

The last arrow is key: **SkillBank co-evolves with the policy**.

### Experience distillation

- **Success** → positive skill (strategy + applicability)
- **Failure** → failure lesson (not discarded)

Example: 50-step failed trajectory becomes:

> Failure lesson: Do not search StackOverflow before official documentation.

### Hierarchical SkillBank

- **General skills** — reason before acting, verify answer, search official docs
- **Task-specific skills** — ALFWorld cabinet/drawer ordering; WebShop variant checking

Adaptive retrieval per task instead of dumping all trajectories.

### Recursive evolution

```
Policy → trajectories → skills → SkillBank → policy learns
    → better trajectories → better skills → ...
```

Policy and SkillBank co-evolve recursively.

### RL objective

Uses standard **GRPO**. Novelty is SkillBank + recursive evolution around it, not the RL algorithm itself.

### Pros / cons

| Pros | Cons |
|------|------|
| Much shorter context | Requires teacher LLM |
| Reusable, transferable | Skill extraction quality matters |
| Better generalization | Skill retrieval is another optimization |
| Learns from failures | |
| Hierarchical retrieval | |

---

## 2. Claw-R1

**Paper:** [Claw-R1: A Step-Level Data Middleware System for Agentic Reinforcement Learning](https://arxiv.org/abs/2606.09138) (2026)

This paper is **not** proposing a new RL algorithm. It asks: **How do we manage millions of agent interaction steps?**

### Core architecture

```
Agent → Gateway Server → Step records → Data Pool → RL Trainer
```

### Gateway Server

All requests pass through a unified gateway (not Agent → LLM directly). Records prompt, response, reward, tool calls, metadata, timestamps.

### Step-level data

Each step is an independent, queryable data asset:

| Step | Action | Reward |
|------|--------|--------|
| 1 | Search | 0 |
| 2 | Read webpage | 1 |
| 3 | Answer | 1 |

Query example: *all failed search steps where reward < 0 and tool = browser*

### Data Pool (Replay Buffer++)

```
Step → Metadata → Filtering → Versioning → Quality labels → Training readiness
```

Algorithm-agnostic — feeds GRPO, PPO, DPO, or any downstream RL.

### Why step-level?

20-step trajectory, 19 correct, 1 wrong — trajectory storage loses granularity. Step-level lets you train **only the wrong step**.

### Analogy

Feature stores (recsys) · Data lakes (analytics) · Experience replay (classical RL) — but for LLM agents.

---

## Side-by-side

| Aspect | SkillRL | Claw-R1 |
|--------|---------|---------|
| Main contribution | RL algorithm + skill learning | Data middleware |
| Uses RL | Yes (GRPO) | No (algorithm-agnostic) |
| Stores | Skills | Step records |
| Main abstraction | SkillBank | Data Pool |
| Focus | Better policy learning | Better data lifecycle |
| Learns from failures | Yes (distills failure lessons) | Records failures for later use |
| Training improvement | Direct | Indirect (through data management) |

---

## How they fit together

See [combined pipeline](combined-pipeline.md) for the full-stack architecture.

**Claw-R1** provides a high-quality, queryable stream of step-level interaction data.  
**SkillRL** consumes those trajectories, distills them into reusable skills, updates the policy with GRPO, and recursively evolves the SkillBank.

One manages the **data lifecycle**; the other improves the **learning algorithm**. Together: infrastructure + policy optimization = full-stack agentic RL.

## Research threads

1. Claw-R1 Data Pool → SkillRL trajectory builder integration
2. Step-level failure filtering (Claw-R1) → failure lesson distillation (SkillRL)
3. Skill retrieval quality vs step curation quality — which bottleneck dominates?
4. Shared GRPO training backends
5. Relationship to OpenClaw-RL (online RL from next-state signals) — orthogonal online layer?

## Evidence to collect

- [ ] Claw-R1 repo: step record schema, Data Pool API
- [ ] SkillRL repo: SkillBank JSON format, distillation prompts
- [ ] AgentR1 ecosystem: Claw-R1 + Agent-R1 + StepPO cross-references
- [ ] Demo video walkthrough of Claw-R1 curation UI
