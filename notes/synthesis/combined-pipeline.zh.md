---
id: T003-zh
title: 组合流水线 — Claw-R1 + SkillRL
date: 2026-07-08
tags: [skillrl, claw-r1, synthesis, architecture, zh]
status: active
lang: zh
related: [T003]
---

# 组合流水线：Claw-R1 + SkillRL

全栈 Agentic RL — 基础设施（数据）+ 算法（学习）。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                      Claw-R1                            │
│              （数据生命周期层）                            │
├─────────────────────────────────────────────────────────┤
│   Agents → Gateway → Step Data Pool → Trajectory Builder│
└──────┼──────────────────────────────────────────────────┘
       ▼
┌─────────────────────────────────────────────────────────┐
│                      SkillRL                            │
│              （学习算法层）                                │
├─────────────────────────────────────────────────────────┤
│   Trajectory → Teacher LLM → SkillBank → GRPO → Policy  │
│   新数据 ─────────────────────────────────→ 回到 Claw-R1 │
└─────────────────────────────────────────────────────────┘
```

## 分工

| 层次 | 系统 | 职责 |
|------|------|------|
| 采集 | Claw-R1 Gateway | 从异构 Agent 捕获每一步 |
| 存储 | Claw-R1 Data Pool | 版本化、过滤、标注、查询 step 记录 |
| 组装 | Trajectory Builder | 将 step 组成可训练轨迹 |
| 抽象 | SkillRL 蒸馏 | 轨迹 → 紧凑 Skill + 失败教训 |
| 记忆 | SkillRL SkillBank | 分层、可检索 Skill 库 |
| 优化 | SkillRL GRPO | Skill 增强上下文下的策略更新 |
| 进化 | SkillRL 递归循环 | SkillBank 与策略协同进化 |
| 反馈 | Claw-R1 | 改进策略的新 rollout 回到 Data Pool |

## 为何这一组合有效

1. **Claw-R1 解决 SkillRL 默认假设的数据问题** — step 级多样成功/失败轨迹。
2. **SkillRL 解决 Claw-R1 不做的压缩问题** — 原始 step 无限增长；SkillBank 蒸馏为可复用 Skill。
3. **失败处理互补** — Claw-R1 记录/查询失败 step；SkillRL 蒸馏为策略上下文中的失败教训。
4. **两者均兼容 GRPO** — Claw-R1 TrainingBackend 可服务 GRPO batch；SkillRL 带 Skill 增强消费。

## 开放设计问题

- Trajectory Builder 放在 Claw-R1 扩展还是 SkillRL 预处理？
- Skill 是否作为新资产类型写回 Data Pool？
- Step 级训练 vs 轨迹级 Skill 增强 GRPO — 混合？
- 在线进化：Data Pool 发现新失败模式时触发 SkillBank 更新？

## 相关

- [对比分析](comparison.md)
- [SkillRL 概览](../../topics/skill-rl/overview.md)
- [Claw-R1 概览](../../topics/claw-r1/overview.md)
