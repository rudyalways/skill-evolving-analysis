---
id: N2026-07-08-011
title: 调研口径 + Repo 确认 + 证据等级 + TaiChu 接缝映射
date: 2026-07-08
tags: [methodology, repo-inventory, evidence-level, taichu-integration]
status: active
related: [N2026-07-08-010, N2026-07-08-009]
---

# 调研口径 + Repo 确认

> **诚实声明**：截至 2026-07-08，本 workspace **未**对任一 repo 做「全库逐文件读完」。  
> 已完成的是 **L1–L2 证据**（关键路径 grep + 核心模块精读）；后续按 repo **逐个 L3 深挖**。

---

## 一、证据等级（固定口径）

| 等级 | 名称 | 含义 | 本调研现状 |
|:----:|------|------|-----------|
| **L0** | README / 文档 | 官方描述、博客 | 全部 8+1 已读 |
| **L1** | 第一层源码 | 目录结构 + 关键词 grep + 入口文件 | **8 runtime repo 已完成** |
| **L2** | 模块精读 | Skill/memory/harness 核心文件 20–80 行上下文 | **8 runtime repo 部分完成**（见下表） |
| **L3** | 深读 | 单 repo 全链路走读（agent loop → compact → evolve） | **排队中，按 repo 逐个** |
| **L4** | 交叉验证 | 测试、CHANGELOG、设计 doc 与实现对照 | 未系统做 |

**对外表述应写**：「基于 L1–L2 源码证据的对比调研，L3 深读进行中」—— **不要**写「已彻底读完源码」。

---

## 二、Repo 确认（本机实测 remote）

### 2.1 已 clone 且 remote 已验证

| 项目 | GitHub | 本机路径 | HEAD 日期 | 角色 |
|------|--------|---------|-----------|------|
| **OpenClaw** | [openclaw/openclaw](https://github.com/openclaw/openclaw) | `oss/openclaw` | 2026-04-27 | Gateway + skill ecosystem + skill-workshop |
| **OpenClaw-RL** | [Gen-Verse/OpenClaw-RL](https://github.com/Gen-Verse/OpenClaw-RL) | `oss/openclaw-rl` | 2026-04-21 | **RL 训练层**（≠ openclaw 主仓） |
| **claude-code-rev** | [oboard/claude-code-rev](https://github.com/oboard/claude-code-rev) | `oss/experimental/claude-code-rev` | 2026-04-08 | **完整 agent runtime** 社区还原 |
| **GenericAgent** | [lsdefine/genericagent](https://github.com/lsdefine/genericagent) | `oss/genericagent` | 2026-06-29 | SOP-as-skill 自进化 |
| **Codex** | [openai/codex](https://github.com/openai/codex) | `oss/codex` | 2026-06-07 | 官方 Rust CLI harness |
| **OpenSquilla** | [opensquilla/opensquilla](https://github.com/opensquilla/opensquilla) | `oss/opensquilla` | 2026-07-01 | Token-efficient agent + proposals |
| **ZeroClaw** | [zeroclaw-labs/zeroclaw](https://github.com/zeroclaw-labs/zeroclaw) | `oss/zeroclaw` | 2026-03-04 | 轻量 Rust runtime |
| **Hermes Agent** | [nousresearch/hermes-agent](https://github.com/nousresearch/hermes-agent) | `oss/hermes-agent` | 2026-04-10 | skill_manage + RL env |
| **TaiChu** | taichu.fun Gitea（私有） | `drafts/zk/TaiChu` | 2026-06-11 | 端云集成目标 |

### 2.2 常见混淆 — 必须纠正

| 名字 | 是什么 | 不是什么 |
|------|--------|---------|
| **openclaw** | 个人 AI 助手 gateway | OpenClaw-RL 论文/训练项目 |
| **OpenClaw-RL** | Gen-Verse RL 插件 + 训练脚本 | openclaw 内置 skill 进化 |
| **oboard/claude-code-rev** | source-map **完整 runtime** 还原（query/compact/skills） | Yuyz0112 的工具 |
| **Yuyz0112/claude-code-reverse** | **LLM API 交互可视化**工具 | agent skill runtime；**本机未 clone** |
| **Claw-R1** (arXiv:2606.09138) | 论文：step-level middleware | 上述任一 GitHub repo 名 |

### 2.3 尚未 clone（可选扩展）

| 项目 | GitHub | 说明 |
|------|--------|------|
| **ZeroClaw Skills** | [zeroclaw-labs/zeroclaw-skills](https://github.com/zeroclaw-labs/zeroclaw-skills) | 社区 skill registry；ZeroClaw 主仓有 sync 逻辑，registry 仓 **L3 时再 clone** |
| **Yuyz0112/claude-code-reverse** | 见上 | 若只关心 API 抓包可视化才需要；**skill 调研优先 oboard/claude-code-rev** |

### 2.4 Codex 官方 repo

已确认：**[openai/codex](https://github.com/openai/codex)** — Rust monorepo `codex-rs/`。

---

## 三、固定调研维度（与用户表对齐）

每个 repo L3 深读时填同一张表：

| 维度 | 要查什么 | L2 已有结论摘要 |
|------|---------|----------------|
| **per-turn skill** | 每轮 catalog 是否变化 | OpenSquilla ★；TaiChu user prefix ★；Claude incremental ★ |
| **dynamic loading** | body 按需加载 | 全员 lazy/progressive；TaiChu `load_skill` |
| **subagent complementary skills** | 子 agent 独立 skill set | Claude frontmatter preload ★；Codex child turn_skills；TaiChu ❌ |
| **storage** | 文件/registry/DB 布局 | 见 [skill-lifecycle survey](skill-lifecycle-and-dynamic-loading-survey.md) |
| **expose / discover** | prompt / CLI / hub | 各仓不同 |
| **recommend** | retrieval / router | OpenSquilla RRF ★；Claude decay；TaiChu Toollery |
| **offload / compact** | 压缩后 skill 是否存活 | Claude `invoked_skills` ★；TaiChu ❌ gap |
| **delete / evolve** | 退役 + 自进化闭环 | OpenSquilla gates；Hermes skill_manage；OpenClaw workshop |
| **自进化** | trace→candidate→eval→deploy | 无单仓全闭环；见下节 |

---

## 四、Skill 自进化强度 — 修正版（L1–L2 证据）

| 项目 | 强度 | L2 结论（源码，非 README） |
|------|:----:|---------------------------|
| **OpenSquilla** | **高（skill 文件）** | `proposals_lib` + 4-gate + `auto_propose` + Dream — **比 README 描述的「router flywheel」更完整** |
| **Hermes** | **高** | `skill_manage` CRUD + `_spawn_background_review` — 闭环在 runtime，无 proposal gate |
| **OpenClaw** | **中高** | `extensions/skill-workshop/`：`agent_end` → heuristic/LLM → proposal → scanner → apply |
| **GenericAgent** | **中高（SOP 哲学）** | `start_long_term_update` + L3 SOP；**非 SKILL.md 标准** |
| **Claude-code-rev** | **中** | `skillImprovement` 5-turn + survey UI；`invoked_skills` compact 存活 |
| **OpenClaw-RL** | **高（模型 RL）** | feedback → trajectory → GRPO/OPD；**不写 SKILL.md** |
| **OpenClaw（主仓）** | 中 | skill 生态 + workshop；非 GRPO |
| **ZeroClaw** | 低–中 | audit + open-skills sync；**无 auto-create** |
| **Codex** | 低（刻意） | skill 基础设施；memories/harness 进化，非 skill library |
| **TaiChu** | **无** | load/catalog 强；evolution 未实现 |

**Yuyz0112/claude-code-reverse** 不在上表 — 不是 skill runtime。

---

## 五、L3 深读排队（建议顺序）

| 序 | Repo | 优先文件 | 产出 |
|:--:|------|---------|------|
| 1 | **TaiChu** | `compaction.rs`, `load_skill.rs`, `session/mod.rs`, `tool_search_bridge.rs`, `api/mod.rs` | P0 实现 spec |
| 2 | **Claude-code-rev** | `compact/compact.ts`, `skillImprovement.ts`, `runAgent.ts`, `attachments.ts` | invoked_skills 移植设计 |
| 3 | **OpenSquilla** | `skills_filter.py`, `proposals_lib.py`, `runtime_e2e.py`, `meta/orchestrator.py` | gate 模板 |
| 4 | **Hermes** | `run_agent.py` (review), `skill_manager_tool.py` | CRUD + review 移植 |
| 5 | **OpenClaw** | `skill-workshop/`, `skills/workspace.ts`, `trajectory/` | workshop + trace |
| 6 | **OpenClaw-RL** | `extensions/rl-training-headers`, training scripts | RL 接缝（非 skill 文件） |
| 7 | **Codex** | `core-skills/`, `hook_runtime.rs`, `skills.rs` | hooks + implicit invoke |
| 8 | **ZeroClaw** | `skills/mod.rs`, `loop_/detection.rs` | audit + loop detect |
| 9 | **GenericAgent** | `ga.py`, `memory_management_sop.md` | L0 SOP 协议 |
| 10 | **zeroclaw-skills** | clone 后 | registry 格式 |

---

## 六、TaiChu 接缝映射（源码核实）

用户提出的 `SessionOptions.extra_tools / hook_chain` — **与当前代码略有出入**，以下为本机 **实际接缝**：

### 6.1 已有（可直接挂 Skill 生命周期）

| 接缝 | 位置 | 用途 |
|------|------|------|
| **`SessionOptions.transform_context`** | `agent-framework/src/session/mod.rs:257-280` | **Per-turn** 注入 `# Available Skills`、turn_reminder；不改 SDK transcript |
| **`disable_workspace_skill_scan`** | 同上 :244-256 | A-system 避免 dual skill registry |
| **`set_skill_name_filter`** | `agent-session/src/session.rs` | Toollery per-turn 收窄 skill |
| **`ToolleryHook before_prompt`** | `agent-plugin/src/tool_search_bridge.rs:370-382` | decide → skill_filter + active_tools |
| **`load_skill` tool** | `builtintools/src/skill/load_skill.rs` | 按需 body + runs_on 路由 |
| **`interaction_log`** | session handle | turn-level trace（SkillCandidate 输入） |
| **`register_extra_tools`** | `agent-session/src/session.rs:884+` | 运行时合并新 tool（含未来 skill_manage） |
| **`Runtime::add_tool_factory`** | `core-architecture.md` | **Host 工具注册**（`extra_tool_factories` 已从 SessionOptions 迁到 Runtime，见 `docs/guides/sdk-integration.md:575`） |

### 6.2 命名对照（文档 vs crate）

| 用户/文档说法 | 本机 crate/符号 |
|--------------|----------------|
| `fast_agent-session` | `core/agent-session`（FFI 导出 `fast_agent_create_session`） |
| `fast_agent-agent` | `core/agent-loop` + `core/agent-framework` |
| `taichu-core-sdk` | `core/taichu-core-sdk` |
| `SessionOptions.hook_chain` | **无此字段**；workflow 有 `hook_chain_trace.jsonl`（issue-366 diagnostics）；等效 hook 为 **`transform_context`** + **Toollery `before_prompt`** + extension hooks 设计 doc |
| `ContextOptions` | 分散在 `SessionOptions` + `PromptBuilderContext` |
| `extra_tool_factories` | **`Runtime::add_tool_factory`**（非 SessionOptions） |

### 6.3 建议落地的 Skill 生命周期（映射到真实接缝）

```text
agent-loop turn complete
  ↓
interaction_log JSONL          ← 已有
  ↓
[NEW] SkillEvolutionHook       ← 挂 SessionOptions 扩展或 service 层 async task
  ↓  (借 Hermes _spawn_background_review)
[NEW] SkillCandidateStore      ← ~/.taichu/proposals/  (借 OpenSquilla proposals_lib)
  ↓
[NEW] SkillEvaluator           ← regression + gates.json
  ↓
[NEW] skill_manage tool        ← register_extra_tools / add_tool_factory
  ↓
canonical skills/ + MANAGED    ← 现有 load_skill roots
  ↓
transform_context              ← per-turn # Available Skills 动态列表
  ↓
load_skill → exec_cli          ← 现有端云链
```

**Compaction 补强**（P0，借 Claude Rev）：

```text
load_skill ToolResult
  ↓
[NEW] InvokedSkillRegistry     ← session state
  ↓
compaction.rs summarize
  ↓
[NEW] re-inject invoked_skills attachment  ← transform_context 或 transcript repair
```

---

## 七、与 OpenClaw-RL / Claw-R1 / SkillRL 的关系

| 层 | Repo / 论文 | TaiChu 借什么 |
|----|------------|--------------|
| **Step trace** | Claw-R1 论文；OpenClaw trajectory；OpenSquilla trace |  enrich interaction_log schema |
| **Skill file evolution** | OpenSquilla + Hermes + OpenClaw workshop | proposals + skill_manage |
| **Model RL** | OpenClaw-RL；Hermes Atropos；SkillRL 论文 | 独立训练管线，非 skill MD 写入 |
| **Compact survival** | Claude-code-rev | invoked_skills |

OpenClaw-RL **应单独 L3**，不要与 openclaw skill-workshop 混为一谈。

---

## 八、本 workspace 已有产出索引

| 文档 | 证据等级 | 内容 |
|------|---------|------|
| [eight-repo-source-analysis-framework.md](eight-repo-source-analysis-framework.md) | L0–L1 | 身份确认 |
| [eight-repo-deep-source-analysis.md](eight-repo-deep-source-analysis.md) | L1–L2 | 7 维 × 8 仓 |
| [eight-repo-comprehensive-survey.md](eight-repo-comprehensive-survey.md) | L1–L2 | 20 维矩阵 |
| [skill-lifecycle-and-dynamic-loading-survey.md](skill-lifecycle-and-dynamic-loading-survey.md) | L2 | per-turn / subagent / 生命周期 |
| **本文** | 元数据 | 口径 + repo 确认 + TaiChu 接缝 |

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-08 | 初版：证据等级、repo 纠正、TaiChu 接缝核实、L3 排队 |
