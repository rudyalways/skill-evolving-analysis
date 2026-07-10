---
id: N2026-07-08-004
title: 官方博客 Skill 自进化内容调研（Claude / Codex / Cursor）
date: 2026-07-08
tags: [industry-survey, official-blog, skill-evolution, claude-code, codex, cursor]
status: active
related: [N2026-07-08-002, N2026-07-08-003]
---

# 官方博客：是否有 Skill 自进化内容？

## 结论摘要

| 产品 | Skill 支持 | Skill **自进化**（官方） | 进化对象（官方实际在做） |
|------|-----------|------------------------|------------------------|
| **Claude Code / Anthropic** | ✅ 强 | ⚠️ **路线图有，产品未完全落地** | 人工/半自动迭代 + harness 进化 |
| **OpenAI Codex** | ✅ 强 | ⚠️ **Skill 创建有，自动进化 loop 偏 harness** | Record & Replay、Improvement Loop |
| **Cursor** | ✅ 支持标准 | ❌ **无 Skill 自进化产品** | **Harness 平台级进化** |

**一句话**：三家官方都在推 Skills，但 **Skill 全自动自进化** 目前主要是 **Anthropic 明确写进 future roadmap**；Codex 有 **skill 创建 + harness improvement loop**；Cursor 重点在 **harness 持续改进**，Skills 是静态加载/发现，不是自动演化 library。

---

## 1. Anthropic / Claude Code

### 有相关内容的官方来源

| 来源 | 链接 | 关于 Skill 自进化说了什么 |
|------|------|--------------------------|
| Agent Skills 工程文 | [anthropic.com/engineering/.../agent-skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) | **最明确**：future 希望 agent 自己 create/edit/evaluate skills |
| Introducing Agent Skills | [claude.com/blog/skills](https://claude.com/blog/skills) | skill-creator 交互式创建；org 级管理 |
| Building Agents with Skills | [claude.com/blog/building-agents-with-skills-...](https://claude.com/blog/building-agents-with-skills-equipping-agents-for-specialized-work) | Skills 与 MCP/harness 分工；开放标准 |
| Long-running harnesses | [anthropic.com/engineering/effective-harnesses-for-long-running-agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | **Harness 进化**（initializer + coding agent），非 SkillBank |
| Harness design long-running apps | [anthropic.com/engineering/harness-design-long-running-apps](https://www.anthropic.com/engineering/harness-design-long-running-apps) | planner-generator-**evaluator** 三 agent |

### 已落地 vs 路线图

**已落地（半自动，人 in the loop）**：
- `skill-creator` skill：Claude 引导你创建 SKILL.md
- 官方建议 workflow：
  > "Iterate with Claude: ask Claude to capture its successful approaches and common mistakes into reusable context and code within a skill. If it goes off track, ask it to self-reflect on what went wrong."
- Progressive disclosure 检索已有 skills

**明确路线图（尚未产品化）**：
> "Looking further ahead, we hope to **enable agents to create, edit, and evaluate Skills on their own**, letting them codify their own patterns of behavior into reusable capabilities."

**相关但非 Skill 自进化**：
- Long-running harness = session 间 artifact 传递（progress file, git commits）
- Evaluator agent = harness 层验证，不是 Skill Library 递归更新

### 判断

Anthropic 是三家里面 **唯一在官方 engineering 文里明确写 "agents create/edit/evaluate skills on their own"** 的。但当前产品是 **人工观察 → 让 Claude 帮你改 skill**，不是 SkillRL 那种自动 SkillBank co-evolve。

---

## 2. OpenAI Codex

### 有相关内容的官方来源

| 来源 | 链接 | 关于 Skill 自进化说了什么 |
|------|------|--------------------------|
| Agent Skills 文档 | [developers.openai.com/codex/skills](https://developers.openai.com/codex/skills) | Skills 标准、$skill-creator、Record & Replay |
| Record & Replay | [developers.openai.com/codex/record-and-replay](https://developers.openai.com/codex/record-and-replay) | **演示 → 自动生成 skill**（一次性创建） |
| Introducing Codex app | [openai.com/index/introducing-the-codex-app](https://openai.com/index/introducing-the-codex-app/) | Skills + Automations；内部数百 skills |
| Changelog | [developers.openai.com/codex/changelog](https://developers.openai.com/codex/changelog) | Agent skills、Record & Replay 上线 |
| Agent Improvement Loop | [cookbook/.../agent_improvement_loop](https://developers.openai.com/cookbook/examples/agents_sdk/agent_improvement_loop) | Traces → Evals → **Harness 改进 handoff** |
| Testing Skills with Evals | [developers.openai.com/blog/eval-skills](https://developers.openai.com/blog/eval-skills) | **Skill 评测**方法论，非自动进化 |
| Self-Evolving Agents cookbook | [cookbook/.../autonomous_agent_retraining](https://developers.openai.com/cookbook/examples/partners/self_evolving_agents/autonomous_agent_retraining) | Prompt/harness 优化 loop（LLM-as-judge） |
| Iterate on difficult problems | [developers.openai.com/codex/use-cases/iterate-on-difficult-problems](https://developers.openai.com/codex/use-cases/iterate-on-difficult-problems) | Eval 驱动迭代修复 loop |

### 已落地 vs 未落地

**Skill 相关已落地**：
- `$skill-creator`：交互式生成 SKILL.md
- **Record & Replay**：macOS 上演示工作流 → Codex draft skill → 可 refine
- Skills 自动检测文件变更（需 restart）
- Eval skills：用 `codex exec --json` 对 skill 行为做 deterministic checks

**Improvement Loop 已落地（但进化的是 Harness，不是 Skill Library）**：
```
Traces → Human/LLM feedback → Promptfoo evals → HALO optimization → codex_handoff.md → Codex 改 harness
```
官方 cookbook 明确说进化的是 "prompt, tools, routing rules, output requirements, validation checks" — **当前 agent harness**。

**没有官方博客说**：
- Skill Library 自动递归更新
- 失败 trajectory 自动 distill 成 skill 并入库
- Skill version chain (V1→V2→V3) 产品化

### 判断

Codex 官方 content 最接近 "skill 自进化" 的是 **Record & Replay（experience → skill 单向蒸馏）** 和 **eval-skills（评测 skill）**。完整的 **closed-loop skill library evolution** 在官方文档里 **没有作为产品 feature 推出**，Improvement Loop 主要面向 harness。

---

## 3. Cursor

### 有相关内容的官方来源

| 来源 | 链接 | 关于 Skill 自进化说了什么 |
|------|------|--------------------------|
| Continually improving harness | [cursor.com/blog/continually-improving-agent-harness](https://cursor.com/blog/continually-improving-agent-harness) | **Harness 进化**（A/B、Keep Rate、evals） |
| Dynamic context discovery | [cursor.com/blog/dynamic-context-discovery](https://cursor.com/blog/dynamic-context-discovery) | 支持 Agent Skills **开放标准 + 动态检索** |
| Changelog 2.4 | [cursor.com/changelog/2-4](https://cursor.com/changelog/2-4) | Skills 支持（SKILL.md、slash command） |
| Long-running agents | [cursor.com/blog/long-running-agents](https://cursor.com/blog/long-running-agents) | 长时 agent harness research preview |

### Skills 相关内容

**Dynamic context discovery 博客 §3**：
- 支持 Agent Skills 开放标准
- name/description 作为 static context
- Agent 用 grep / semantic search **动态发现** relevant skills
- Skills 可 bundle scripts

**Changelog 2.4**：
- "Agents can discover and apply skills"
- 用户手动定义 `SKILL.md`
- Skills vs Rules：更适合 procedural "how-to"

### Harness 进化（有，但不是 Skill）

**Continually improving agent harness** 详细描述：
- CursorBench + 在线 A/B 实验
- Keep Rate（agent 生成代码留存率）
- LLM 读用户回复判断满意度
- 工具错误分类 + anomaly detection
- **Weekly Automation 用 skill 查 logs 开 ticket** — 这是 *使用* skill 做内部运维，不是 *进化* skill library

### 判断

Cursor 官方博客 **没有任何 "skill self-evolution" 或 "skill library grows automatically" 的表述**。进化的是 **平台 harness**（prompt、tools、context engineering），Skills 是用户/团队提供的 **静态可发现资产**。

---

## 4. 横向对比：官方到底在进化什么？

```
                    Claude          Codex           Cursor
                    ──────          ─────           ──────
Skill 格式/标准      ✅ 制定者        ✅ 采用          ✅ 采用
Skill 创建           ✅ skill-creator ✅ R&R + creator  ✅ 手动 SKILL.md
Skill 评测           ⚠️ 建议人工观察   ✅ eval-skills    ❌ 未提
Skill 自动进化        📋 路线图        ❌ 未产品化       ❌ 未提
Harness 进化         ✅ 长时 harness   ✅ Improvement Loop ✅ 核心重点
Weight 进化          ❌               ⚠️ cookbook 示例   ✅ Tab RL 信号
```

---

## 5. 与学术/开源的 gap

官方博客描述的 maturity：

| 能力 | 官方产品 | 学术/开源 |
|------|---------|----------|
| Trajectory → Skill distill | Record & Replay, 人工 iterate | SkillRL, Trace2Skill |
| Failure → Skill | 人工 self-reflect | SkillRL, HarnessFix |
| Skill Revision (V1→Vn) | 人工 edit SKILL.md | SkillHone |
| Validation gate | eval-skills (Codex) | SkillOpt, EvoSkills |
| Skill Graph retrieval | progressive disclosure | Graph of Skills, SkillRouter |
| Closed-loop Skill Library | **未产品化** | SkillRL recursive evolution |

**Gap 正是研究机会**：官方提供了 Skill **格式 + 创建 + 检索 + 评测** 的基础设施，但 **Skill Library 持续自进化闭环** 仍主要在论文/开源（SkillRL、SkillHone、Trace2Skill、Memento-Skills）里。

---

## References

- Anthropic Agent Skills: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Claude blog Skills: https://claude.com/blog/skills
- Codex Skills: https://developers.openai.com/codex/skills
- Codex Record & Replay: https://developers.openai.com/codex/record-and-replay
- Codex Agent Improvement Loop: https://developers.openai.com/cookbook/examples/agents_sdk/agent_improvement_loop
- Codex eval-skills: https://developers.openai.com/blog/eval-skills
- Cursor harness blog: https://cursor.com/blog/continually-improving-agent-harness
- Cursor dynamic context: https://cursor.com/blog/dynamic-context-discovery
- Cursor changelog 2.4: https://cursor.com/changelog/2-4
