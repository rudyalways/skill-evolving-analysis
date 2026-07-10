---
id: N2026-07-08-005
title: 官方产品 Skill 自进化 gap 分析（共识版）
date: 2026-07-08
tags: [official-product, skill-evolution, gap-analysis, synthesis]
status: active
related: [N2026-07-08-004, N2026-07-08-003, T005]
---

# 官方产品 Skill 自进化 gap 分析

## 短答案

**没有一家官方明确提出「Skill 自进化（Skill Self-Evolution）」作为产品能力或官方路线。**

但三家已经分别提供了组成 Skill 自进化闭环的**基础设施**，只是停留在 **Human-in-the-loop**，而不是论文里的 **Automatic Skill Evolution**。

---

## 总结表（修订版）

| 产品 | Skills | Memory | 自动修改 Skill | 自动评测 Skill | 官方提出 Skill Evolution? |
|------|:------:|:------:|:--------------:|:--------------:|:-------------------------:|
| Claude Code | ✅ 很强 | 部分 (CLAUDE.md 等) | ❌ | ❌ | ❌（路线图有暗示） |
| Codex | ✅ 很强 | ✅ Memories | ❌ | ⚠️ eval-skills 文档 | ❌ |
| Cursor | ✅ Skills + Rules | 部分 | ❌ | ❌ | ❌ |

> **修订说明**：Codex 2026 同时强推 **Skills + Memories**（互补，非替代）；Cursor 2.4 已支持 Agent Skills 标准，不只 Rules。

**共识**：官方目前都没有做到 SkillRL 那种 `Trajectory → Skill → Evaluation → Update Skill` 全自动闭环。

---

## 一、Claude Code

Skills 是一等公民：[Claude Code Skills Documentation](https://docs.anthropic.com/en/docs/claude-code/skills)

```
Skill = SKILL.md + scripts/ + references/
```

**Progressive Loading** — metadata 先进 context，命中后再加载全文。

### 官方支持的生命周期

```
Create Skill → Use Skill → Share Skill
     ↑
   Human 写
```

**没有**：`Trajectory → Generate Skill → Replace Skill`

Skill 生命周期仍然靠人维护。Anthropic 强调 Project / Team / Personal Skill 不断积累，但**没有说 Claude 自己修改 Skill**。

### 唯一暗示（路线图，非产品）

> "enable agents to create, edit, and evaluate Skills on their own"  
> — [Agent Skills engineering post](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

---

## 二、Codex

**修订**：Codex 并非「只有 Memory 没有 Skill」。官方 [Customization 文档](https://developers.openai.com/codex/concepts/customization) 明确列出互补四层：

| 层 | 用途 |
|----|------|
| `AGENTS.md` | 持久指令 |
| **Memories** | 从过往 thread 携带 ambient context（偏好、惯例） |
| **Skills** | 可复用 workflow（SKILL.md + scripts） |
| MCP | 外部系统 |

### Memories（Experience → Memory）

```
Experience → Memory → Future Tasks
```

- 默认关闭（EEA/UK/CH 需显式开启）
- 记住偏好、corrections、tech stack、repo conventions
- 背景异步生成，非 skill 文件

### Skills（Experience → Skill，但单向）

```
演示 / $skill-creator / Record & Replay → SKILL.md
```

- **不是**自动 library 更新 loop
- [eval-skills 博客](https://developers.openai.com/blog/eval-skills) 提供评测方法论，但无 auto-promotion

**判断**：Codex = **Memory Evolution（ambient）+ Skill Creation（manual/semi-auto）**，两者并行，都不是 SkillRL 式闭环。

---

## 三、Cursor

**修订**：Cursor 已有 **Agent Skills**（[changelog 2.4](https://cursor.com/changelog/2-4)、[dynamic context discovery](https://cursor.com/blog/dynamic-context-discovery)），与 Rules 并存：

| 机制 | 路径 | 特点 |
|------|------|------|
| Rules | `.cursor/rules` | 声明式、always-on 或 glob 触发 |
| Skills | `SKILL.md` (agentskills.io) | 程序性 how-to、动态发现 |

两者都是 **Human 编写、静态维护**。没有 Generate Rule / Update Rule / Auto Skill Evolution。

Cursor 官方重点在 **Harness 进化**（[Continually improving agent harness](https://cursor.com/blog/continually-improving-agent-harness)）：A/B、Keep Rate、平台级 prompt/tool 调优。

---

## 四、为什么官方都没做 Skill 自进化？

真正 Skill Evolution 意味着：

```
Rollout → Skill Candidate → 替换 Skill → 以后所有 Agent 都调用新 Skill
```

**企业风险极大**：

```
今天生成: "Always use git rebase"
明天发现: 团队禁止 rebase
→ 整个团队 agent 行为损坏
```

所以企业产品必然需要：

```
Candidate → Review → Approve → Deploy
```

和传统软件发布流程一样 — 这解释了 Human-in-the-loop 的产品选择。

---

## 五、官方架构 vs SkillRL 闭环

### 官方现状（静态扩展点）

```
Task → Agent → Skill / Memory / Hook / MCP → Result
                    ↑
                 全部静态，人工维护
```

### SkillRL 希望的闭环

```
Task → Trajectory → Reflection → Generate Skill
  → Evaluate → Version → Replace Skill → Next Task
                    ↑
                 完全自动（或 validation-gated）
```

**中间缺失层** — 也是论文价值所在。

---

## 六、社区 workaround（仍非 Skill 改 Skill）

Reddit / 社区常见模式：

```
Session 结束 → wrap-up skill → Review → Commit → Learn → Remember
```

或：Claude review mistakes → suggest memories → human confirm update

这些都是 **Skill 调用 Memory**，不是 **Skill 修改 Skill**。真正改 `SKILL.md` 仍需人工确认。

---

## 七、下一代 Agent Harness 方向（共识架构）

官方产品已具备四个组件：**Skills/Rules、Memory、Hooks、长期上下文**。

缺失的中间层：

```
               Runtime
                  │
                  ▼
           Step-level Trace          ← Claw-R1
                  │
                  ▼
            Reflection Agent
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
   Memory Candidate    Skill Candidate    ← SkillRL / Trace2Skill
        │                   │
        │             Regression / Eval    ← SkillOpt / SkillHone
        │                   │
        └─────────┬─────────┘
                  ▼
         Human Review (可选)              ← 企业必需
                  │
                  ▼
      Versioned Skills / Rules / Memory   ← SkillHone
                  │
                  ▼
          Automatic Retrieval               ← GoS / SkillRouter
```

### 缺失的四块（= 研究/产品机会）

1. **Skill Candidate 生成** — Trajectory → Skill
2. **自动回归测试 / Benchmark** — eval gate
3. **Skill 排名、版本管理与淘汰** — ELO / score / merge
4. **自动或半自动发布（Promotion）** — review → deploy

**核心判断**：把 Skills 从静态配置文件 → 持续学习、持续评测、持续版本化的**软件资产** — 这正是 SkillRL、SkillHone 等论文的方向，也是官方产品尚未闭合的 gap。

---

## Related

- [官方博客调研](official-blog-skill-evolution.md)
- [Skill 进化 taxonomy](skill-evolution-taxonomy.md)
- [Proposed 2027 architecture](proposed-skill-lifecycle-architecture.md)
