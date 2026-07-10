---
id: N2026-07-08-012
title: 外部 Web 调研 vs 本机 L2 源码 — 交叉核对
date: 2026-07-08
tags: [reconciliation, web-vs-local, skill-evolution-ranking]
status: active
related: [N2026-07-08-011, N2026-07-08-010]
---

# 外部 Web 调研 vs 本机 L2 源码 — 交叉核对

> **背景**：另一路调研无法 `git clone`（DNS 失败），用 GitHub 网页/issue/docs 做第一轮。  
> **本 workspace**：本机已 clone 8 runtime repo + OpenClaw-RL，完成 **L1–L2 源码精读**（非全库 L3）。  
> **本文**：合并两路结论，标出 **一致 / 需修正 / 仅 Web 可证**。

---

## 一、Skill 自进化强度 — 合并排序

| 秩 | 项目 | Web 调研 | 本机 L2 源码 | **合并结论** |
|:--:|------|---------|-------------|-------------|
| 1 | **Hermes 生态** | Hermes + `hermes-agent-self-evolution` (GEPA/DSPy) | `skill_manage` + `_spawn_background_review`（`run_agent.py`）；self-evolution **仓未 clone** | **#1 不变**：在线 CRUD（本机已证）+ 离线演化器（Web/issue，待 clone 验 L3） |
| 2 | **OpenSquilla** | MetaSkill + meta-skill-creator | `proposals_lib` 4-gate + `auto_propose` + per-turn RRF（`skills_filter.py`） | **应上调至 #2**：不仅是 MetaSkill 文档，有 **完整 proposal→accept 代码** |
| 3 | **GenericAgent** | crystallize 理念最强 | `start_long_term_update` + L3 SOP（`ga.py:508`）；无 gate | **#3 不变**：哲学强，工程治理弱 |
| 4 | **OpenClaw** | marketplace，自进化弱 | **`skill-workshop`** `agent_end` heuristic/LLM→apply（`extensions/skill-workshop/index.ts`） | **应上调**：非仅 ClawHub；有 **runtime workshop**，弱于 OpenSquilla gate |
| 5 | **Claude-code-rev (oboard)** | *(Web 表未单列，把 Yuyz0112 当 claude)* | `invoked_skills` compact + `skillImprovement` 5-turn | **本机独有 #5**：Web 若只看 Yuyz0112 会 **漏掉** oboard 完整 runtime |
| 6 | **ZeroClaw** | registry 治理强，进化弱 | `skills/audit.rs` + version field；无 auto-create | **一致** |
| 7 | **Codex** | 无一等 skill 进化 | 确认：filesystem + sample skill-creator | **一致** |
| 8 | **TaiChu** | 缺 lifecycle | load_skill + transform_context；无 evolve | **一致** |

**不纳入 skill-runtime 对比**：`Yuyz0112/claude-code-reverse`（API 可视化）、`Gen-Verse/OpenClaw-RL`（模型 RL，非 SKILL.md）。

---

## 二、核心对比表 — 逐格核对

| 维度 | Web 说法 | 本机 L2 修正 |
|------|---------|-------------|
| **Hermes per-turn** | `/skills` 自动触发有问题 (issue) | Catalog **session-frozen**；进化靠 **post-turn review**，非 per-turn 换列表 |
| **Hermes dynamic load** | Progressive disclosure ✅ | 确认：`skills_list` / `skill_view`（`skills_tool.py`） |
| **Hermes subagent** | delegate 有 context 过大 issue | 确认：无 skill preload 参数 |
| **Hermes evolve** | skill_manage + review ✅ | 确认：`skill_manager_tool.py` + `run_agent.py:9604-9632` |
| **OpenSquilla per-turn** | CLI `opensquilla skills` | **更强**：pipeline `filter_skills()` **每 turn** RRF top-k（`skills_filter.py:107-260`） |
| **OpenSquilla evolve** | meta-skill-creator | **更强**：`proposals_lib.accept_proposal` + gates.json + `runtime_e2e` judge |
| **OpenClaw per-turn** | 注入不稳定 (issue) | Snapshot 缓存 + lazy read；workshop 在 **agent_end** 非 per-turn catalog |
| **OpenClaw evolve** | Skill Workshop / marketplace | **skill-workshop 源码存在**：非纯 marketplace |
| **ZeroClaw storage** | registry.json + SKILL.md | 主仓 `skills/mod.rs` workspace + open-skills sync；**zeroclaw-skills 仓 clone 失败**（DNS） |
| **Codex** | 无一等 skill 进化 | 确认；hooks/guardian 强 |
| **TaiChu** | hooks/session/tool factory 接缝 | **修正接缝名**（见下节） |

---

## 三、Web 调研中 **值得采纳** 且本机可落地的点

### 3.1 Hermes + `hermes-agent-self-evolution` 双层架构

| 层 | 仓 | 模式 | TaiChu 建议 |
|----|-----|------|------------|
| **在线** | hermes-agent | runtime `skill_manage` + background review | P1：post-turn async + CRUD tool |
| **离线** | hermes-agent-self-evolution | DSPy/GEPA → eval → PR | P2：**不要在线直改生产 skill**；trace → eval cases → mutate → regression → PR |

本机 **未 clone** `hermes-agent-self-evolution`；Web README 描述与 Hermes 文档中的 DSPy **bundled skill** 一致，但 GEPA 演化器需 **L3 clone 后验**。

### 3.2 OpenSquilla MetaSkill — Web 与本机一致

MetaSkill = task protocol DAG（本机：`meta/orchestrator.py`）。TaiChu 建议：

```text
Skill      = 单 procedure (SKILL.md + load_skill)
MetaSkill  = 多 step + checks + subagent routing (P3，单 skill 生命周期稳定后)
```

### 3.3 ZeroClaw 治理 frontmatter — 部分本机已证

本机 `zeroclaw/src/skills/mod.rs` 有 `version` 字段 + `audit.rs`（zip-bomb、path traversal、prompt injection patterns）。Web 提到的 `permissions/risk_level` 在 **zeroclaw-skills registry 仓**（未 clone）；TaiChu 可 **先借 audit.rs 模式**，frontmatter schema 自定。

### 3.4 GenericAgent — Web 警告正确

「全自动固化」必须加 candidate→eval→approve（本机：无 proposal，仅 L0 SOP 协议）。

---

## 四、Web 调研中 **需修正** 的点

| Web 结论 | 修正依据 |
|---------|---------|
| OpenClaw 自进化弱 | 本机有 `skill-workshop` 完整 `agent_end` 管道 |
| OpenSquilla 偏 router flywheel | 本机有 **4-gate proposals**，强度应仅次于 Hermes |
| claude-code-reverse 不是 harness | **对 Yuyz0112**；**错若泛指 oboard/claude-code-rev** — 本机有完整 harness + skillImprovement |
| TaiChu 用 `SessionOptions.extra_tool_factories` | 已迁到 **`Runtime::add_tool_factory`**（`sdk-integration.md:575`） |
| TaiChu 用 `ContextOptions.hook_chain` | 实为 **`SessionOptions.transform_context`** + **Toollery before_prompt** |

---

## 五、TaiChu 推荐架构 — 合并版（软件资产管理）

```text
Turn Trace (interaction_log — 已有)
        ↓
Skill Miner [NEW]          ← 借 Hermes review prompt
        ↓
Skill Candidate Store      ← 借 OpenSquilla proposals/ + gates.json
        ↓
Static Checks              ← 借 ZeroClaw audit + Hermes skills_guard
        ↓
Regression Harness [NEW]
        ↓
Human / Policy Gate        ← 借 Claude survey UI 或 offline PR (GEPA)
        ↓
Versioned Store ~/.taichu/skills/
        ↓
Skill Router               ← 借 OpenSquilla RRF / Toollery decide (已有 partial)
        ↓
Per-turn Loading           ← transform_context # Available Skills (已有)
        ↓
Subagent Skill Bundle      ← 借 Claude profile.skills preload (缺失)
        ↓
Compaction Survival        ← 借 Claude invoked_skills (缺失, P0)
```

### 真实接缝（本机核实）

| 组件 | TaiChu 落点 |
|------|------------|
| Trace | `interaction_log` JSONL |
| Per-turn inject | `SessionOptions.transform_context` |
| Per-turn filter | `set_skill_name_filter` + Toollery `before_prompt` |
| Load body | `load_skill` + `runs_on` |
| Add tools | `Runtime::add_tool_factory` / `register_extra_tools` |
| Compact | `agent-session/src/compaction.rs` — **待加 invoked_skills** |

---

## 六、证据来源矩阵

| 项目 | Web 调研 | 本机 L2 | 待 L3 |
|------|:--------:|:-------:|:-----:|
| Hermes main | ✅ README/issue | ✅ 源码 | review 全路径 |
| hermes-self-evolution | ✅ README | ❌ 未 clone | **需 clone** |
| OpenSquilla | ✅ docs | ✅ proposals/filter | runtime_e2e 全流程 |
| OpenClaw | ✅ issue | ✅ skill-workshop | workshop.ts 全读 |
| oboard/claude-code-rev | ❌ 未区分 | ✅ compact/skillImprovement | attachments 全读 |
| zeroclaw-skills | ✅ README | ❌ clone 超时 | registry schema |
| TaiChu | 材料 | ✅ core 部分 | P0 spec |

---

## 七、对用户的行动建议

1. **采纳 Web 排序框架**，但把 **OpenSquilla 上调、OpenClaw 上调、oboard/claude-code-rev 单独列出**。
2. **Hermes 生态 = 两仓**：在线 hermes-agent（本机已证）+ 离线 self-evolution（待 clone）。
3. **TaiChu 先做离线 PR 模式**（Web 建议正确），在线只写 **candidate/proposal**，不直写 canonical。
4. 本 workspace 下一步：**TaiChu P0 spec** 或 **clone hermes-agent-self-evolution**（网络恢复时）。

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-08 | Web 调研与本机 L2 交叉核对 |
| 2026-07-08 | 新增 Web 深度版 TaiChu 借鉴指南（L0）+ L3 附录核对 → [web-deep-taichu-borrowing-guide.md](web-deep-taichu-borrowing-guide.md) |
