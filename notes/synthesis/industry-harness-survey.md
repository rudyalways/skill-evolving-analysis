---
id: N2026-07-08-002
title: 业界 Agent Harness 调研 — 自进化与 Skill 自进化
date: 2026-07-08
tags: [industry-survey, harness, skill-evolution, self-evolving, synthesis]
status: active
related: [T001, T002, N2026-07-08-001]
---

# 业界 Agent Harness 调研：自进化是如何做的，特别是 Skill 自进化

## 1. 先厘清：什么是 Agent Harness

Agent Harness 是把 LLM **变成可用 Agent 的控制层**，包括：

- Prompt / system instructions
- Tool schema & routing
- Planning / recovery / retry logic
- Subagent orchestration
- **Skills**（可复用流程包）
- Memory / context management

业界共识（2025–2026）：**Agent 性能 = Base Model × Harness**。同一模型换不同 harness，差距可达 20–40pp（Terminal-Bench、SWE-bench 等 benchmark 已反复验证）。

---

## 2. 自进化的三层 × 三时域框架

参考 [Xinming Tu 的 3×3 矩阵](https://xinmingtu.cn/blog/2026/self-evolving-agents/)，自进化状态可以落在三个 **substrate（载体）** 和三个 **persistence horizon（持久性）** 的交叉点上：

### 三个载体（What evolves）

| 层 | 载体 | 例子 | 成本 | 持久性 |
|----|------|------|------|--------|
| L1 | **External Files** | Skills、memory、CLAUDE.md、脚本 | 低 | 可编辑、可审计 |
| L2 | **Agent Harness** | Prompt、tool policy、workflow、recovery | 中 | 需重新部署/加载 |
| L3 | **Model Weights** | SFT/RL 后的 checkpoint | 高 | 最 durable |

**关键边界**：Skill 文件开始时是 L1（外部文件），一旦被 runtime 发现、加载、路由，就**变成 L2（harness 逻辑）**。

### 三个时域（When persists）

| 时域 | 含义 | Skill 相关例子 |
|------|------|----------------|
| **Single Session** | 单次任务内适应 | 动态编排、scratchpad、runtime 合成 tool |
| **Across Sessions** | 跨会话持久 | Skill library、Record & Replay、SkillBank |
| **Across Users** | 群体级进化 | 平台默认 harness 升级、skill marketplace |

**Skill 自进化主要发生在 L1 × Across Sessions**，部分系统会进一步编译到 L2 或蒸馏到 L3。

---

## 3. Skill 自进化的六种范式

### 范式 A：人工编写 → 语义发现（工业基线）

**代表**：Anthropic Agent Skills、OpenAI Codex Skills、Cursor

```
SKILL.md (name + description) → Agent 语义匹配 → 按需加载完整指令
```

- **格式**：`SKILL.md` + 可选 scripts/references（[agentskills.io](https://agentskills.io) 开放标准，16+ 工具兼容）
- **进化方式**：**人工迭代** — 观察 agent 使用 skill 的行为，修改 description/instructions
- **Anthropic 路线图**：*"enable agents to create, edit, and evaluate Skills on their own"* — 尚未完全自动化
- **特点**：Progressive disclosure（先加载 ~100 token metadata，命中后再加载全文）

### 范式 B：演示 → 自动生成 Skill（Record & Replay）

**代表**：OpenAI Codex Record & Replay

```
用户演示工作流 → Codex 观察 → 自动生成 SKILL.md → 未来复用
```

- **进化触发**：用户主动录制
- **进化粒度**：一次演示 → 一个 skill
- **本质**：Experience → Skill 的单向蒸馏，**无自动 refinement loop**

### 范式 C：轨迹蒸馏 → Skill Library（RL / Teacher 驱动）

**代表**：SkillRL、ExpeL、Voyager

| 系统 | 蒸馏物 | 进化机制 |
|------|--------|----------|
| **Voyager** (2023) | 可执行 code skills | 成功轨迹 → 新 skill 入库 → 检索复用 |
| **ExpeL** (2024) | Natural-language insights | 成功/失败轨迹 → 提取 rules → ICL 检索 |
| **SkillRL** (2026) | 分层 SkillBank | Teacher 蒸馏 + GRPO + **递归进化** |

**SkillRL 的递归进化 loop**（与本项目核心相关）：

```
Policy → Rollout → Teacher 蒸馏(success/failure)
    → SkillBank 更新 → GRPO → 更强 Policy → 更好轨迹 → 更好 Skills → ...
```

- 成功 → strategic patterns
- 失败 → failure lessons（不是丢弃）
- 验证 epoch 触发：弱类别 → 分析 gap → 新增/精炼 skill

### 范式 D：Skill 文档作为可训练参数（Text-Space Optimization）

**代表**：Microsoft SkillOpt

```
Frozen target model + skill document
    → Rollout → Optimizer model 提出 edit (add/delete/replace)
    → Validation gate（必须严格优于 held-out）
    → 接受 → best_skill.md
```

- **核心创新**：把 skill 当 **trainable parameter**，模型权重 frozen
- **训练纪律**：textual learning rate（edit budget）、rejected-edit buffer、epoch-wise slow update
- **部署产物**：300–2000 token 的 `best_skill.md`，零额外 inference cost
- **52/52 cells best or tied-best**（6 benchmarks × 7 models × 3 harnesses）

与 SkillRL 对比：SkillOpt 优化**单个 skill 文档**；SkillRL 维护**分层 skill library** 并 co-evolve with policy。

### 范式 E：Read-Execute-Reflect-Write（部署时自修复）

**代表**：Memento-Skills、AutoSkill

**Memento-Skills** loop：

```
Read (检索/生成 skill)
  → Execute
  → Reflect (失败归因 → 定位弱 skill)
  → Write (修复 skill 写回 library)
```

- Skill 是 **first-class capability unit**（不仅是 prompt，含 code + prompts）
- Behaviour-aligned contrastive router 选择 skill
- 模型 frozen，skill library 持续读写

**AutoSkill**：

- 从对话/交互中自动抽象 skill → 标准化 `SKILL.md`
- 跨 session 注入相关 skill，**无需 retrain model**
- 面向个性化偏好（写作风格、机构规范等）

### 范式 F：Co-Evolutionary Skill Generation（生成器 + 验证器共进化）

**代表**：EvoSkills

```
Skill Generator ←→ Surrogate Verifier (共进化)
    ↓
Ground-truth oracle (opaque pass/fail)
    ↓
Multi-file skill package
```

- 解决 **human-machine cognitive misalignment**（人类写的 skill 有时反而降低 agent 性能）
- 5 轮进化后 surpass human-curated skills on SkillsBench (+40.5pp)
- Surrogate Verifier 合成测试用例，无需 ground-truth 内容访问

---

## 4. 非 Skill 层的 Harness 自进化

Skill 只是 harness 自进化的一部分。业界还有：

### Harness 代码/配置自进化

| 系统 | 机制 | 提升 |
|------|------|------|
| **Self-Harness** | Weakness Mining → Harness Proposal → Validation | 40.5%→61.9% (Terminal-Bench) |
| **AHE** (Agentic Harness Engineering) | 三支柱 observability + 可 falsifiable edit contract | 69.7%→77.0% |
| **Meta-Harness** | Outer-loop 搜索 harness code | +7.7pt, 4× fewer tokens |
| **HarnessX** | Processor 组合搜索 + RL bridge | Harness evolution + Model evolution 双 loop |

共同模式：

```
Execution traces → 分析失败模式 → 提出 harness 修改 → 回归验证 → 接受/拒绝
```

### Memory Skill 自进化（Meta-Memory）

**MemSkill** — 进化的不是 memory content，而是 **memory skills**（如何提取、整合、遗忘）：

- Skill-conditioned memory construction
- Hard case mining → refine/propose memory skills
- 跨 dataset、跨 model transfer

### Policy + Experience 自进化（Weight 层）

| 系统 | 机制 |
|------|------|
| **AgentEvolver** | Self-questioning + Self-navigating + Self-attributing |
| **OpenClaw-RL** | Next-state signal → Binary RL + OPD |
| **HarnessX Model Evolution** | Reward-annotated trajectories → VERL RL |

---

## 5. 工业界产品矩阵

| 产品 | Skill 支持 | 自进化方式 | 进化层 |
|------|-----------|-----------|--------|
| **Claude Code** | Agent Skills 标准 | 人工 + `/loop` 动态编排；平台级 harness 升级 | L1 + L2 |
| **OpenAI Codex** | Skills + Record & Replay | 演示→skill；插件 marketplace | L1 |
| **Cursor** | `.cursor/skills/` + rules | Tab accept/edit → RL signal；人工 skill 迭代 | L1 + L3 |
| **OpenHands** | Persistent skill install | 跨 session enable/disable | L1 |
| **HarnessX** | Processor bundles | 自动 harness search + RL | L2 + L3 |

**平台级 flywheel**（Across Users）：

```
Aggregate failure logs → 识别结构性瓶颈 → 升级默认 harness
→ 所有用户继承（plan mode、/loop、tool schema 改进等）
```

---

## 6. Skill 自进化技术谱系

```
                    人工程度
                       ↑
    Anthropic Skills ──┤
    Codex R&R ────────┤
                       │
    AutoSkill ─────────┤
    Memento-Skills ────┤  ← Read-Execute-Reflect-Write
                       │
    SkillOpt ──────────┤  ← Text-space optimization (validation gate)
                       │
    SkillRL ───────────┤  ← RL + recursive SkillBank co-evolution
    ExpeL / Voyager ───┤  ← Trajectory distillation
                       │
    EvoSkills ─────────┤  ← Co-evolutionary generation
                       ↓
                    自动化程度
```

### 进化信号来源

| 信号 | 使用者 |
|------|--------|
| 成功轨迹 | SkillRL, Voyager, ExpeL |
| 失败轨迹 | SkillRL (failure lessons), Memento (reflect) |
| 用户演示 | Codex R&R |
| 用户对话/偏好 | AutoSkill |
| 验证集分数 | SkillOpt |
| Surrogate 测试 | EvoSkills |
| Next-state 反馈 | OpenClaw-RL (weight 层，非 skill) |

### 进化产物形态

| 形态 | 系统 |
|------|------|
| 单个 `best_skill.md` | SkillOpt |
| 分层 SkillBank (general + task-specific) | SkillRL |
| Multi-file skill package | EvoSkills, Anthropic Skills |
| 可执行 code skill | Voyager |
| NL insights/rules | ExpeL |
| Memory operation skills | MemSkill |

---

## 7. 与本项目（SkillRL + Claw-R1）的关系

```
┌─────────────────────────────────────────────────────────┐
│  Claw-R1 — 数据层                                        │
│  Gateway → Step Data Pool → 可查询、可筛选的 step 资产    │
└────────────────────────┬────────────────────────────────┘
                         │ trajectories
                         ▼
┌─────────────────────────────────────────────────────────┐
│  SkillRL — 算法层                                        │
│  蒸馏 → SkillBank → GRPO → 递归进化                      │
└────────────────────────┬────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
     SkillOpt       EvoSkills     Memento-Skills
   (单 skill 优化)  (多文件生成)   (部署时修复)
```

- **Claw-R1** 对应业界 "Feature Store / Data Lake for agents" — 解决 **数据从哪来、怎么管**
- **SkillRL** 对应 "Experience → Skill distillation + RL" — 解决 **怎么从经验中学**
- 工业界大多停在 **范式 A/B**（人工 skill + 演示录制），学术前沿正在推进 **范式 C–F**

---

## 8. 趋势判断

1. **Skill 格式标准化** — Agent Skills 开放标准（2025.12）已成事实标准，skill 成为跨平台可移植资产
2. **Skill 从静态到可训练** — SkillOpt 证明 skill 文档可以像 weight 一样优化；SkillRL 证明 skill library 可以与 policy co-evolve
3. **Harness 自进化独立成赛道** — Self-Harness、AHE、Meta-Harness、HarnessX 表明 harness engineering 本身可被自动化
4. **数据基础设施觉醒** — Claw-R1、OpenClaw-RL、slime 等表明 agent RL 首先是 data problem
5. **三层协同** — 未来系统 likely 是 L1(skill files) + L2(harness) + L3(weights) 同时进化，而非只改一层
6. **Human-machine misalignment** — EvoSkills 揭示人类写的 skill 不一定适合 agent；自动进化可能优于人工

## 9. 待深入调研

- [ ] SkillsBench benchmark 详细结果对比
- [ ] SkillOpt vs SkillRL 在同一 benchmark 的直接对比
- [ ] Cursor / Claude Code 是否有未公开的 skill auto-evolution 能力
- [ ] Claw-R1 Data Pool 能否直接 feed SkillRL distillation pipeline
- [ ] MemSkill 的 memory skill 与 SkillRL 的 task skill 能否统一抽象

## References

- Anthropic Agent Skills: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Agent Skills Standard: https://agentskills.io
- SkillRL: arXiv:2602.08234
- Claw-R1: arXiv:2606.09138
- SkillOpt: Microsoft Research / github.com/microsoft/SkillOpt
- EvoSkills: arXiv:2604.01687
- Memento-Skills: arXiv:2603.18743
- AutoSkill: arXiv:2603.01145
- Self-Harness: arXiv:2606.09498
- AHE: arXiv:2604.25850
- Meta-Harness: arXiv:2603.28052
- HarnessX: github.com/Darwin-Agent/HarnessX
- AgentEvolver: github.com/modelscope/AgentEvolver
- MemSkill: github.com/ViktorAxelsen/MemSkill
- 3×3 Framework: https://xinmingtu.cn/blog/2026/self-evolving-agents/
