---
id: T005
title: Proposed 2026–2027 Online Skill Lifecycle Architecture
date: 2026-07-08
tags: [architecture, skill-evolution, claw-r1, skillrl, synthesis]
status: draft
related: [T001, T002, T003, N2026-07-08-003]
---

# Proposed Architecture: Online Skill Lifecycle (2026–2027)

> Skill 不是静态 Prompt，而是可评测、可版本化、可路由、可淘汰、可持续演化的软件资产。

## Architecture diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        AGENT RUNTIME                              │
│  LLM + Harness (prompt, tools, routing, recovery)               │
└────────────────────────────┬─────────────────────────────────────┘
                             │ every action
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  L0: STEP-LEVEL TRACE CAPTURE                    [Claw-R1]       │
│  Gateway → {state, action, reward, tool, metadata, timestamp}  │
│  Data Pool: query, filter, version, quality-label              │
└────────────────────────────┬─────────────────────────────────────┘
                             │ step streams / assembled trajectories
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  L1: EXPERIENCE MINING                                            │
│  ┌─────────────────────┐    ┌─────────────────────┐              │
│  │  Failure Mining      │    │  Success Mining      │              │
│  │  - timeout patterns  │    │  - strategic patterns│              │
│  │  - wrong tool choice │    │  - efficient paths   │              │
│  │  - captcha/block     │    │  - verification flow │              │
│  └──────────┬──────────┘    └──────────┬──────────┘              │
│             └────────────┬───────────────┘                        │
│                          ▼                                        │
│              Skill Candidate Pool                                 │
│              (prompt / code / workflow variants)                  │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  L2: VALIDATION & SELECTION                                       │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Auto Practice / Regression Tests          [SkillHone]       │ │
│  │ - role-separated opt/eval subagents                         │ │
│  │ - practice probes with redacted evidence                    │ │
│  │ - held-out validation gate                [SkillOpt]        │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Pairwise Ranking / A-B Evaluation                           │ │
│  │ - ELO among skill candidates                                │ │
│  │ - benchmark tournament                  [EvoSkills]           │ │
│  └─────────────────────────────────────────────────────────────┘ │
└────────────────────────────┬─────────────────────────────────────┘
                             │ accepted skills only
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  L3: VERSIONED SKILL LIBRARY                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ General Skills (cross-task heuristics)     [SkillRL S_g]   │ │
│  │ Task-Specific Skills (domain tactics)      [SkillRL S_k]   │ │
│  │ Program Skills (executable code)           [Voyager]        │ │
│  │ Workflow Skills (DAG graphs)               [ComfyClaw]      │ │
│  │ Decision History (diagnosis→revision)      [SkillHone]      │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  Retirement: score threshold · ELO · embedding merge · archive  │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  L4: GRAPH RETRIEVAL & ROUTING                                    │
│  Skill Graph (dependencies, workflow chains)    [Graph of Skills] │
│  Scale routing (80K+ pool)                      [SkillRouter]     │
│  Progressive disclosure (L0→L4 context depth)   [skill-graph]     │
└────────────────────────────┬─────────────────────────────────────┘
                             │ retrieved skill bundle
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  L5: AGENT EXECUTION (with skill-augmented context)               │
│  Policy conditions on: general skills + retrieved task skills     │
│  Optional: GRPO policy update              [SkillRL]              │
└────────────────────────────┬─────────────────────────────────────┘
                             │ runtime metrics
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  L6: HARNESS CO-EVOLUTION                                         │
│  Harness flaw attribution (ETCLOVG)           [HarnessFix]        │
│  Harness component edit + regression          [Self-Harness, AHE] │
│  Skill revision harness                       [SkillHone]         │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             └──────────────► back to L0 (closed loop)
```

## Layer responsibilities

| Layer | Question it answers | Key systems |
|-------|-------------------|-------------|
| L0 | 数据从哪来、怎么管？ | Claw-R1 |
| L1 | 从经验中提取什么？ | SkillRL distill, HarnessFix mining |
| L2 | 怎么保证 skill 质量？ | SkillOpt, SkillHone, EvoSkills |
| L3 | 怎么组织和版本化？ | SkillRL SkillBank, SkillHone history |
| L4 | 怎么高效检索？ | Graph of Skills, SkillRouter |
| L5 | 怎么用于执行和学习？ | SkillRL GRPO, any agent runtime |
| L6 | Harness 本身怎么进化？ | Self-Harness, HarnessFix, AHE |

## Design principles

1. **Step-level first** — 不要等完整 trajectory 才处理；Claw-R1 的 step 粒度支持 failure mining at the wrong step
2. **Failure ≥ Success** — 失败 lesson 和成功 pattern 同等重要（SkillRL 已验证）
3. **Validation before store** — 没有 gate 的 skill library 会退化（SkillOpt 52/52 cells 证明 gate 的价值）
4. **Version, don't overwrite** — SkillHone 的 decision history 避免重复犯错
5. **Graph, not list** — 100+ skills 时 flat retrieval 不够（SkillRouter @ 80K scale）
6. **Harness co-evolve** — Skill 优化不够，harness 层也要一起改（2026 共识）

## Open design decisions

- [ ] Trajectory builder: Claw-R1 extension vs SkillRL preprocessor?
- [ ] Skill artifacts back into Data Pool as new asset type?
- [ ] Online vs batch evolution frequency
- [ ] Human-in-the-loop approval (ComfyClaw model) vs fully automatic
- [ ] Unified skill schema: Anthropic SKILL.md vs SkillRL prompt-heuristic vs Voyager code

## Implementation phases

| Phase | Scope | Dependencies |
|-------|-------|-------------|
| P0 | Claw-R1 Data Pool + basic step capture | Claw-R1 repo |
| P1 | Failure/success mining → skill candidates | SkillRL distillation prompts |
| P2 | Validation gate (held-out + practice probes) | SkillOpt / SkillHone patterns |
| P3 | Versioned SkillBank + graph retrieval | SkillRL + Graph of Skills |
| P4 | GRPO co-evolution loop | SkillRL training |
| P5 | Harness co-evolution | HarnessFix / Self-Harness |

## Related

- [Skill evolution taxonomy](skill-evolution-taxonomy.md)
- [Combined pipeline (Claw-R1 + SkillRL)](combined-pipeline.md)
