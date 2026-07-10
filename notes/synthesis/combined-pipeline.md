---
id: T003
title: Combined pipeline — Claw-R1 + SkillRL
date: 2026-07-08
tags: [skillrl, claw-r1, synthesis, architecture]
status: active
related: [T001, T002, N2026-07-08-001]
---

# Combined pipeline: Claw-R1 + SkillRL

Full-stack agentic RL — infrastructure (data) + algorithm (learning).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Claw-R1                            │
│              (data lifecycle layer)                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   Agents                                                │
│      │                                                  │
│      ▼                                                  │
│   Gateway Server                                        │
│      │                                                  │
│      ▼                                                  │
│   Step Data Pool                                        │
│      │                                                  │
│      ▼                                                  │
│   Trajectory Builder                                    │
│      │                                                  │
└──────┼──────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│                      SkillRL                            │
│              (learning algorithm layer)                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   Trajectory (success + failure)                        │
│      │                                                  │
│      ▼                                                  │
│   Teacher LLM → Skill Distillation                      │
│      │                                                  │
│      ▼                                                  │
│   SkillBank (general + task-specific)                   │
│      │                                                  │
│      ▼                                                  │
│   Retrieve Skills → Policy                              │
│      │                                                  │
│      ▼                                                  │
│   GRPO → Updated Policy                                 │
│      │                                                  │
│      ▼                                                  │
│   More Agent Data ──────────────────────────┐           │
│                                             │           │
└─────────────────────────────────────────────┼───────────┘
                                              │
                                              ▼
                                    back to Claw-R1
```

## Division of labor

| Layer | System | Responsibility |
|-------|--------|----------------|
| Collection | Claw-R1 Gateway | Capture every step from heterogeneous agents |
| Storage | Claw-R1 Data Pool | Version, filter, label, query step records |
| Assembly | Trajectory Builder | Group steps into trainable trajectories |
| Abstraction | SkillRL distillation | Trajectories → compact skills + failure lessons |
| Memory | SkillRL SkillBank | Hierarchical, retrievable skill library |
| Optimization | SkillRL GRPO | Policy update with skill-augmented context |
| Evolution | SkillRL recursive loop | SkillBank co-evolves with policy |
| Feedback | Claw-R1 | New rollouts from improved policy re-enter Data Pool |

## Why this combination works

1. **Claw-R1 solves the data problem SkillRL assumes away.** SkillRL needs diverse success/failure trajectories; Claw-R1 provides them at scale with step-level granularity.

2. **SkillRL solves the compression problem Claw-R1 doesn't address.** Raw step records still grow unbounded; SkillBank distills them into reusable, token-efficient skills.

3. **Failure handling is complementary.** Claw-R1 records and queries failed steps; SkillRL distills them into failure lessons for policy context.

4. **Both are GRPO-compatible.** Claw-R1's TrainingBackend can serve GRPO batches; SkillRL consumes them with skill augmentation.

## Open design questions

- Where does the Trajectory Builder live — Claw-R1 extension or SkillRL preprocessor?
- Should skills be stored back into the Data Pool as a new asset type?
- Step-level training (Claw-R1 only) vs trajectory-level skill-augmented GRPO (SkillRL) — hybrid?
- Online evolution: trigger SkillBank updates when Data Pool detects new failure patterns?

## Related

- [Comparison matrix](comparison.md)
- [SkillRL overview](../../topics/skill-rl/overview.md)
- [Claw-R1 overview](../../topics/claw-r1/overview.md)
