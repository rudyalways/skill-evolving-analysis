---
id: T001
title: SkillRL — Recursive Skill-Augmented Reinforcement Learning
date: 2026-02
tags: [skillrl, skill-discovery, skillbank, recursive-evolution, grpo]
status: active
source: https://arxiv.org/abs/2602.08234
related: [T002, T003]
---

# SkillRL

**Full title:** Evolving Agents via Recursive Skill-Augmented Reinforcement Learning  
**Authors:** Xia et al. (aiming-lab)  
**Code:** [github.com/aiming-lab/SkillRL](https://github.com/aiming-lab/SkillRL)

## Layer in the stack

**RL algorithm / training method** — how the policy learns from experience.

| Paper | Focus | Layer |
|-------|-------|-------|
| **SkillRL** | How the policy learns from experience | RL algorithm / training method |
| Claw-R1 | How agent interaction data is collected, managed, fed into RL | Infrastructure / data system |

## One-line thesis

Convert raw trajectories into reusable **skills** stored in a hierarchical **SkillBank**; co-evolve the library and policy during GRPO.

## Motivation

Most LLM agents today:

```
Task 1 → trajectory
Task 2 → trajectory
Task 3 → trajectory
```

Every task is almost independent. Existing memory methods save raw trajectories:

```
database
----------
task A trajectory
task B trajectory
task C trajectory
```

Problems: trajectories are **long, noisy, redundant, hard to retrieve, don't generalize**.

The authors ask: *Can we convert trajectories into reusable skills?*

## Main idea

Instead of storing:

```
Observation → Action → Observation → Action → ...
```

Store:

```
Skill: "When searching webpages,
        first identify official sources,
        then compare,
        then verify."
```

Much shorter. They call this **SkillBank**.

## Pipeline

```
Environment
    ↓
Rollouts (success + failure)
    ↓
Teacher LLM → Skill distillation
    ↓
SkillBank → Retrieve skills → Policy
    ↓
GRPO → Better policy
    ↓
New trajectories → Update SkillBank  ← recursive
```

The SkillBank is **not fixed** — it evolves together with the policy.

## Experience distillation

**Success** → positive skill:

```
Applicable: Searching APIs
Strategy:   Search official docs first
Failure:    Do not trust cached pages
```

**Failure** → failure lesson (not discarded):

```
Failure lesson:
Do not search StackOverflow before official documentation.
```

10–20× token compression vs raw trajectories.

## Hierarchical SkillBank

| Level | Examples |
|-------|----------|
| **General skills** | Reason before acting; verify answer; search official docs |
| **Task-specific skills** | ALFWorld: open cabinet before drawer; WebShop: check variants before buying |

**Adaptive retrieval** — given task "Buy shoes", retrieve general (verify inventory) + task-specific (compare shoe sizes), not every previous trajectory.

## Recursive evolution

The most interesting contribution. Not just Policy → RL → Done, but:

```
Policy → Collect trajectories → Generate skills → Update SkillBank
    → Policy learns → Collect better trajectories → Generate better skills → ...
```

Policy and SkillBank **co-evolve recursively**. After validation epochs, analyze failures on weak categories → add/refine skills.

## RL objective

The RL algorithm itself is **not novel** — they use **GRPO**. The novelty is **SkillBank + recursive skill evolution** wrapped around GRPO.

Cold-start SFT teaches the agent to use skills before RL begins.

## Results

- +15.3% over strong baselines
- Benchmarks: ALFWorld, WebShop, 7 search-augmented tasks
- Faster convergence, robust as task complexity increases

## Pros / cons

**Pros:** shorter context, reusable, transferable, better generalization, learns from failures, hierarchical retrieval

**Cons:** requires teacher LLM, skill extraction quality matters, skill retrieval is another optimization problem

## Open questions

- [ ] SkillBank size growth / pruning strategy
- [ ] Retrieval threshold δ and Top-K sensitivity
- [ ] Can consume Claw-R1 step-level data as input trajectories?
- [ ] Recursive evolution frequency vs validation cost

## Related notes

- [Cross-paper comparison](../../notes/synthesis/comparison.md)
- [Combined architecture](../../notes/synthesis/combined-pipeline.md)
