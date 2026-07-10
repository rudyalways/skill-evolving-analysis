---
id: N2026-07-08-001-zh
title: SkillRL 与 Claw-R1 — 跨论文对比
date: 2026-07-08
tags: [skillrl, claw-r1, synthesis, zh]
status: active
lang: zh
related: [T001, T002, T003]
---

# SkillRL 与 Claw-R1

这两篇论文针对 **Agent RL 技术栈的不同层次**，**互补而非竞争**。

| 论文 | 焦点 | 层次 |
|------|------|------|
| [SkillRL](../../topics/skill-rl/overview.md) | 策略如何从经验中学习 | RL 算法 / 训练方法 |
| [Claw-R1](../../topics/claw-r1/overview.md) | 如何采集、管理 Agent 交互数据并输入 RL | 基础设施 / 数据系统 |

---

## 1. SkillRL

**论文：** [SkillRL: Evolving Agents via Recursive Skill-Augmented Reinforcement Learning](https://arxiv.org/abs/2602.08234)（2026）

### 动机

多数 LLM Agent 呈 episodic 行为——每个任务几乎独立。现有记忆方法保存原始轨迹：冗长、噪声大、难检索、难泛化。

**核心问题：** 能否将轨迹转化为可复用 Skill？

### 核心思想 — SkillBank

不再存储 `Observation → Action → ...`，而是存储紧凑 Skill：

> 「搜索网页时，先找官方来源，再对比，最后验证。」

### 流水线

```
Environment → Rollouts → Teacher LLM → Skill 蒸馏 → SkillBank
    → 检索 Skill → Policy → GRPO → 更优策略
    → 新轨迹 → 更新 SkillBank
```

最后一步是关键：**SkillBank 与策略协同进化**。

### 经验蒸馏

- **成功** → 正向 Skill（策略 + 适用场景）
- **失败** → 失败教训（不丢弃）

### 与 Claw-R1 的关系

SkillRL 假设已有高质量 step-level 轨迹。Claw-R1 提供这一数据层。

---

## 2. Claw-R1

**论文：** [Claw-R1: ...](https://arxiv.org/abs/2606.09138)（2026）

### 动机

Agent 交互数据分散在日志、trace、会话中，难以系统化用于 RL 训练。

### 核心思想 — Data Pool

Gateway 中间件，将每步交互结构化为可查询记录（Replay Buffer++）。

### 特点

- **Step-level** 粒度（非整段 trajectory）
- **算法无关**（不绑定 GRPO / PPO）
- **可查询**（按失败、工具、任务类型过滤）

---

## 3. 组合架构

```
用户任务 → Claw-R1 Gateway（采集 step 数据）
         → Data Pool（存储 + 查询）
         → SkillRL（蒸馏 Skill + GRPO 训练）
         → 更强策略 → 回到 Gateway 部署
```

详见 [组合流水线](./combined-pipeline.md)。

---

## 4. 并排对比

| 维度 | SkillRL | Claw-R1 |
|------|---------|---------|
| 主要贡献 | RL + Skill 学习 | 数据中间件 |
| 是否使用 RL | 是（GRPO） | 否（算法无关） |
| 存储内容 | Skill | Step 记录 |
| 焦点 | 更好的策略学习 | 更好的数据生命周期 |
| 失败处理 | 蒸馏失败教训 | 记录供后续查询 |

---

## 5. 对 TaiChu 的启示

- **SkillRL 层：** SkillBank 抽象、递归进化、失败挖掘 → 在线 Skill 质量提升
- **Claw-R1 层：** step-level 轨迹归档 → 为离线 RL / 蒸馏提供燃料
- **本地 L3 差距：** TaiChu 有 `load_skill` 与 progressive disclosure，缺 post-compaction  reinject（P0 见 [TaiChu P0 规范](./taichu-p0-skill-compaction-spec.md)）
