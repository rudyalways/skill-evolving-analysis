---
id: T002
title: Claw-R1 — Step-Level Data Middleware for Agentic RL
date: 2026-06
tags: [claw-r1, data-pool, gateway, step-level, middleware, infrastructure]
status: active
source: https://arxiv.org/abs/2606.09138
related: [T001, T003]
---

# Claw-R1

**Full title:** A Step-Level Data Middleware System for Agentic Reinforcement Learning  
**Authors:** Wang et al. (AgentR1)  
**Code:** [github.com/AgentR1/Claw-R1](https://github.com/AgentR1/Claw-R1)  
**Demo video:** [youtu.be/Pw47dAOw6B0](https://youtu.be/Pw47dAOw6B0)

## Layer in the stack

**Infrastructure / data system** — not a new RL algorithm.

| Paper | Focus | Layer |
|-------|-------|-------|
| SkillRL | How the policy learns from experience | RL algorithm / training method |
| **Claw-R1** | How agent interaction data is collected, managed, fed into RL | Infrastructure / data system |

## One-line thesis

Treat agent interaction traces as **persistent, managed data assets** — not transient logs — via a Gateway + Data Pool middleware layer.

## Problem

Agent RL is becoming a **data engineering problem**. With 10,000 agents producing millions of steps, current systems treat interactions as temporary stdout that gets deleted. You lose granularity, queryability, and curation.

## Core architecture

```
Agent → Gateway Server → Step records → Data Pool → RL Trainer
```

### Gateway Server

All agent requests pass through a unified API entry point:

```
Agent → Gateway → LLM   (not Agent → LLM directly)
```

Automatically records: prompt, response, reward, tool calls, metadata, timestamps.

Supports white-box agents (API submit), black-box agents (point `base_url` to gateway), and online live interactions.

### Step-level data

Instead of storing only whole trajectories, each step is an independent data asset:

| Step | State | Action | Reward | Prompt ID | Response ID |
|------|-------|--------|--------|-----------|-------------|
| 1 | … | Search | 0 | … | … |
| 2 | … | Read webpage | 1 | … | … |
| 3 | … | Answer | 1 | … | … |

Queryable: *"Show all failed search steps where reward < 0 and tool = browser"*

### Data Pool (Replay Buffer++)

```
Step → Metadata → Filtering → Versioning → Quality labels → Training readiness
```

Traditional replay buffer stores trajectories. Claw-R1's Data Pool adds:

- Multi-dimensional rewards (rule-based / discriminative RM / generative RM)
- Human feedback integration
- Policy version tracking (freshness-aware curation)
- Channel-based partitioning (train/val isolation)
- Pluggable `TrainingBackend` → GRPO, PPO, DPO, or any downstream RL

## Why step-level?

A 20-step trajectory with 19 correct steps and 1 wrong step — trajectory-level storage loses granularity. Step-level lets you train **only the wrong step**.

## Algorithm-agnostic

Claw-R1 does not care which RL algorithm you use. It prepares data; the trainer selects steps → batches → GRPO/PPO/DPO/etc.

## Analogy

Infrastructure analogous to:

- Feature stores (recommendation systems)
- Data lakes (analytics)
- Experience replay buffers (classical RL)

…but designed specifically for LLM agents.

## Pros / cons

**Pros**

- Step-level granularity for credit assignment
- Queryable, filterable, versioned data
- Works with heterogeneous agents (white-box + black-box)
- Decouples data collection from training engine
- Interactive inspection and curation UI

**Cons**

- Does not improve policy by itself (indirect)
- Requires gateway integration
- Data quality / reward labeling still a bottleneck
- Storage and lifecycle management overhead at scale

## Open questions

- [ ] Data Pool schema — exact step record format
- [ ] Integration path with SkillRL trajectory builder
- [ ] Relationship to OpenClaw-RL (online RL) vs Claw-R1 (data middleware)
- [ ] Curation policies — how does freshness-aware filtering work in practice?

## Related notes

- [Cross-paper comparison](../../notes/synthesis/comparison.md)
- [Combined architecture](../../notes/synthesis/combined-pipeline.md)
