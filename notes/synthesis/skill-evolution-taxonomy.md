---
id: N2026-07-08-003
title: Skill 自进化技术路线全景（2025–2026）
date: 2026-07-08
tags: [skill-evolution, taxonomy, synthesis, harness, architecture]
status: active
related: [T001, T002, T003, T004, N2026-07-08-001, N2026-07-08-002]
---

# Skill 自进化技术路线全景（2025–2026）

> 过去一年 Agent 研究的明显趋势：**自进化越来越不是更新模型参数，而是更新 Harness、Skill、Memory、Workflow。** 其中 **Skill Evolution** 是最成熟、最一致的方向。

---

## 一、Skill 自进化到底在进化什么？

很多人理解成：

```
Task → Trajectory → 保存下来
```

**现在不是。**

更准确的是：

```
Task → Experience → Skill → Skill Library → Retriever → 以后 Agent 调用
```

真正进化的是 **Skill Library**，而不是模型参数。

```
LLM + Agent Harness + Skill Library
         ↑                    ↑
      相对固定           持续成长
```

---

## 二、六条进化路线

```
                    Self Evolution
                         │
────────────────────────────────────────
Trajectory │ Skill │ Workflow │ Harness │ Tool │ Weight
                         │
              真正成熟的是 Skill Evolution
              Weight Evolution 很少在线发生
```

### 路线 1：Trajectory → Skill（目前主流）

**代表**：Voyager · SkillRL · Trace2Skill · Memento-Skills · SkillHone

**共同思想**：不是保存 Trajectory，而是 **Distill**。

```
Agent: Search → Read → Compare → Answer

变成 Skill:
"When comparing APIs:
 1. Search official docs
 2. Compare versions
 3. Verify examples"

Trajectory 消失，留下 Skill。
```

**标准流程**：

```
Rollout → Trajectory → Teacher LLM → Skill Distillation → Skill Library
```

| 系统 | 特点 | arXiv |
|------|------|-------|
| Voyager (2023) | 可执行 code skill 入库 | — |
| SkillRL (2026) | 分层 SkillBank + GRPO 递归共进化 | 2602.08234 |
| Trace2Skill (2026) | 并行 analyst → 无冲突合并 skill directory | 2603.25158 |
| Memento-Skills (2026) | Read-Execute-Reflect-Write | 2603.18743 |
| SkillHone (2026) | Persistent decision history + 版本化 revision | 2606.08671 |

**优点**：非常小 · 容易 retrieve · 容易泛化

---

### 路线 2：Failure → Skill（近一年越来越火）

**代表**：SkillRL · HarnessFix · SkillHone

**思想**：不要只保存成功经验，**更应该保存失败**。

```
失败: Tool timeout → Retry → Retry → Fail
变成 Skill: "Never retry; use backup API"

失败: Browser → Captcha → Stop
变成 Skill: "Switch to search API"
```

| 系统 | 失败处理方式 |
|------|-------------|
| SkillRL | Teacher 合成 failure lessons（非丢弃失败轨迹） |
| HarnessFix | HTIR 归因 → ETCLOVG 层 scoped repair | arXiv:2606.06324 |
| SkillHone | 诊断 + 候选 revision + practice probe 验证 |

**失败通常比成功更有价值** — 边界条件、反模式、recovery 策略。

---

### 路线 3：Skill Revision（Skill 持续修改，2026 兴起）

不是 Skill V1 一直保存，而是：

```
Skill V1 → Run → Feedback → Skill V2 → Run → Feedback → Skill V3
```

Skill 成为 **Version**，越来越长、越来越成熟。

```
"Search docs"
  → "Search official docs; if unavailable, search github issues"
```

**代表**：SkillHone — 记录 `(diagnosis, revision, evidence, outcome)` 决策历史，跨 session 持续 refinement，避免重复犯错。

与 SkillOpt 的区别：SkillOpt 优化单个 `best_skill.md`；SkillHone 维护完整 revision history + evaluation assets。

---

### 路线 4：Skill Graph（从 List 到 Graph）

以前：

```
Skill1, Skill2, Skill3  (flat list)
```

现在：

```
Skill A → Skill B → Skill C     (dependency)
Search → Read → Summarize → Verify  (workflow chain)
```

**Graph Retrieval** — 只加载相关子图，而非整个 library。

| 系统 | 机制 | arXiv |
|------|------|-------|
| Graph of Skills | 离线建 skill graph，dependency-aware rerank | 2604.05333 |
| SkillRouter | 80K skill pool，bi-encoder + cross-encoder rerank | 2603.22455 |
| SkillFlow (benchmark) | Lifelong skill discovery & evolution benchmark | 2604.17308 |
| GraSP | Graph-Structured Skill Compositions | 2604.17870 |
| SkillGraph | Self-evolving multi-agent collaboration + graph topology | 2604.17503 |

---

### 路线 5：Program Skill（Code，不是 Prompt）

**代表**：Voyager · Inducing Programmatic Skills

```
以前: "Search docs" (prompt)
后来: def search_docs(): ... (code)
```

**优势**：速度快 · 可 debug · 可测试 · 可 version

Agent 直接调用函数，而非每次重新推理 procedure。

---

### 路线 6：Workflow Skill（Skill = Workflow Graph）

**代表**：ComfyClaw · SkillFlow (executor)

Skill 不再是一句 Prompt，而是 **整个 Workflow**：

```
Browser → Search → Read → Verify → Summarize = 一个 Skill
```

| 系统 | 说明 | arXiv |
|------|------|-------|
| ComfyClaw | ComfyUI workflow 作为 typed graph edit + VLM verifier + skill library | 2607.01709 |
| SkillFlow | YAML DAG executor，human-in-the-loop checkpoints | (engine, not paper) |

ComfyClaw 的 skill evolution：clustering traces → propose skill mutations → validate → 加入 library。

---

## 三、Skill 是怎么产生的？（四种方法）

| 方法 | 流程 | 代表 |
|------|------|------|
| **Distillation** | Trajectory → Teacher LLM → Skill | SkillRL, Trace2Skill |
| **Reflection** | Trajectory → Reflection → Lesson → Skill | Reflexion, Memento-Skills |
| **RL** | Skill 作为 policy 输入；好保留、差删除 | SkillRL (GRPO + SkillBank co-evolve) |
| **Search** | 多 Skill 候选 → Benchmark → Choose best | SkillOpt, EvoSkills, Harness 论文 increasingly |

---

## 四、Skill 如何更新？（标准闭环）

几乎所有论文都经历：

```
Collect → Extract → Validate → Store → Retrieve → Execute → Collect
```

展开：

```
Task → Trajectory → Skill Candidate → Offline Evaluation
  → Accepted Skill → Skill Library → Retriever → Agent → New Tasks
         ↑                                              │
         └──────────────── Rollout ─────────────────────┘
```

**Validation gate 是共识** — SkillOpt（held-out 必须严格更好）、SkillHone（practice probe）、EvoSkills（surrogate verifier + oracle）。

---

## 五、Skill 如何淘汰？

| 策略 | 机制 | 采用者 |
|------|------|--------|
| **Score** | success rate / usage / reward，低分删除 | SkillRL (validation epoch 触发) |
| **ELO** | Skill pairwise 对战，留胜率高的 |  increasingly popular |
| **Embedding Merge** | 相似 skill 自动合并 | "Search docs" + "Search official docs" |
| **Version** | 不覆盖，V1→V2→V3 链式保留 | SkillHone (persistent decision history) |

---

## 六、2026 最大趋势：Harness × Skill 联合进化

以前：

```
LLM → Trajectory → Skill
```

现在：

```
LLM → Harness → Trajectory → Skill → Harness Update + Skill Update
```

| 系统 | 进化什么 | arXiv |
|------|---------|-------|
| Self-Harness | Harness 自身（weakness mining → proposal → validation） | 2606.09498 |
| AHE | Harness 组件（observability-driven edit contract） | 2604.25850 |
| HarnessFix | Harness flaws（ETCLOVG 层归因 + scoped repair） | 2606.06324 |
| Meta-Harness | Harness code outer-loop search | 2603.28052 |
| HarnessX | Processor 组合 + Model evolution 双 loop | GitHub |
| SkillHone | Skill revision harness（role-separated opt/eval） | 2606.08671 |
| ComfyClaw | Workflow harness + skill library 共进化 | 2607.01709 |

**Skill 和 Harness 的边界在模糊** — Skill 文件加载进 runtime 后就是 harness 逻辑。

---

## 七、六条路线 × 四条产线 对照表

| | Distillation | Reflection | RL | Search |
|---|:---:|:---:|:---:|:---:|
| Trajectory→Skill | SkillRL, Trace2Skill | — | SkillRL | — |
| Failure→Skill | SkillRL | Memento | — | HarnessFix |
| Skill Revision | — | SkillHone | SkillOpt | SkillHone |
| Skill Graph | GoS, SkillRouter | — | — | SkillRouter |
| Program Skill | Voyager | — | — | — |
| Workflow Skill | ComfyClaw | ComfyClaw | — | — |

---

## 八、2026–2027 推荐架构：在线 Skill 生命周期

相比目前论文大多仍采用 `Trajectory → LLM Distill → Skill`，更有潜力的是 **持续在线的 Skill 生命周期**：

```
                Agent Runtime
                     │
                     ▼
              Step-level Trace          ← Claw-R1
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
 Failure Mining             Success Mining    ← SkillRL
        │                         │
        └────────────┬────────────┘
                     ▼
             Skill Candidate Pool
                     │
      Auto Practice / Regression Tests      ← SkillHone, SkillOpt
                     │
      Pairwise Ranking / A-B Evaluation     ← ELO / Search
                     │
            Versioned Skill Library         ← SkillHone
                     │
      Graph Retrieval + Skill Routing       ← GoS, SkillRouter
                     │
              Next Agent Execution
                     │
          Runtime Metrics Feedback
                     └──────────────►（继续闭环）
```

### 融合的研究路线

| 组件 | 来源 |
|------|------|
| Step-level 数据管理 | Claw-R1 (Gateway + Data Pool) |
| Trajectory → Skill 蒸馏 | SkillRL, Trace2Skill |
| Failure Mining | SkillRL, HarnessFix |
| Versioned Skills | SkillHone |
| Graph/Router 检索 | Graph of Skills, SkillFlow, SkillRouter |
| Harness 自进化 | Self-Harness, AHE, HarnessFix |
| Validation gate | SkillOpt, EvoSkills |
| Workflow Skill | ComfyClaw |

### 核心思想

> **Skill 不再是静态 Prompt，而是可评测、可版本化、可路由、可淘汰、可持续演化的软件资产。**

这也是当前 Agent Harness 研究正在快速汇聚的方向。

---

## 九、与 Claw-R1 + SkillRL 的定位

```
┌─────────────────────────────────────────────────────────┐
│  Layer 0: Claw-R1 — Step-level Data Infrastructure      │
│  Gateway → Data Pool → queryable step assets            │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  Layer 1: Skill Lifecycle Engine (proposed)             │
│  Mining → Candidate → Validate → Version → Graph        │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  Layer 2: SkillRL — Distillation + RL co-evolution      │
│  Teacher distill → SkillBank → GRPO → recursive update  │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  Layer 3: Harness co-evolution                          │
│  Self-Harness / HarnessFix / SkillHone                  │
└─────────────────────────────────────────────────────────┘
```

Claw-R1 提供 **数据燃料**；SkillRL 提供 **蒸馏+RL 算法**；上层还需要 SkillHone 式的 versioning、GoS 式的 graph retrieval、SkillOpt 式的 validation gate — 这才是完整 stack。

---

## 十、Paper Index（本 taxonomy 涉及）

| Short | Title | arXiv | Route |
|-------|-------|-------|-------|
| SkillRL | Recursive Skill-Augmented RL | 2602.08234 | T→S, Failure, RL |
| Claw-R1 | Step-Level Data Middleware | 2606.09138 | Infrastructure |
| Trace2Skill | Trajectory-Local Lessons | 2603.25158 | T→S |
| SkillHone | Persistent Decision History | 2606.08671 | Revision, Harness×Skill |
| SkillOpt | Skills as Trainable Parameters | — | Search/Validate |
| EvoSkills | Co-Evolutionary Verification | 2604.01687 | Search |
| Memento-Skills | Let Agents Design Agents | 2603.18743 | Reflection |
| HarnessFix | Diagnosing Harness Flaws | 2606.06324 | Failure→Harness |
| Graph of Skills | Dependency-Aware Retrieval | 2604.05333 | Graph |
| SkillRouter | Routing at Scale (80K) | 2603.22455 | Graph/Router |
| ComfyClaw | Workflow Skill Evolution | 2607.01709 | Workflow |
| Self-Harness | Harnesses Improve Themselves | 2606.09498 | Harness |
| AHE | Observability-Driven Harness Evolution | 2604.25850 | Harness |
| AutoSkill | Lifelong Skill Self-Evolution | 2603.01145 | Distillation |

Full list: [DataArcTech/Awesome-Agent-Skill-Papers](https://github.com/DataArcTech/Awesome-Agent-Skill-Papers)

---

## Related

- [Industry harness survey](industry-harness-survey.md)
- [SkillRL vs Claw-R1 comparison](comparison.md)
- [Combined pipeline](combined-pipeline.md)
- [Proposed 2027 architecture](proposed-skill-lifecycle-architecture.md)
