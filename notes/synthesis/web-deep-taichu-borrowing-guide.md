---
id: N2026-07-08-WEB-DEEP
title: Web 深度版 — 八仓横向结论与 TaiChu 借鉴指南
date: 2026-07-08
tags: [web-research, taichu, borrowing-guide, codex, openclaw, hermes, opensquilla, zeroclaw, genericagent, lifecycle]
status: processed
evidence_level: L0
source: public GitHub / official docs / issues (no local clone access)
related: [N2026-07-08-015, N2026-07-08-L3, N2026-07-08-P0, T005]
summary: Public-source deep analysis of skill systems + TaiChu three-layer recommendation; reconciled with local L3 in appendix
---

# Web 深度版 — 八仓横向结论与 TaiChu 借鉴指南

> **证据来源**：公开 GitHub / 官方文档 / issue 页面（**无本机 clone 访问**）。  
> **交叉核对**：见文末 [附录：与本机 L3 交叉核对](#附录与本机-l3-交叉核对)。  
> **相关**：[`web-vs-local-reconciliation.md`](web-vs-local-reconciliation.md) · [`l3-comprehensive-skill-analysis.md`](l3-comprehensive-skill-analysis.md) · [`taichu-p0-skill-compaction-spec.md`](taichu-p0-skill-compaction-spec.md)

---

## 0. 总体判断

**最值得 TaiChu 借鉴的是：**

```text
Codex / OpenClaw / Hermes 的 SKILL.md 标准化
+
OpenClaw 的多来源加载、优先级、per-agent visibility
+
Codex 的 progressive disclosure + description-based implicit trigger
+
Hermes 的 skill_manage / agent-created skills / background self-improvement
+
OpenSquilla 的 MetaSkill = workflow-level skill
+
ZeroClaw 的 registry/audit/security governance
+
GenericAgent 的 task → execution path → reusable skill 思想
```

但真正做到「安全、工程化、可上线」的 **Skill 自进化**，目前没有一个项目完全成熟。Hermes 最激进，但 issue 里也暴露了自修改 skill 的安全和一致性问题，例如 background review 可能在未读取当前 `SKILL.md` 的情况下 patch skill，导致内容被错误删除；也有 issue 要求防止 agent 修改 critical skills。([GitHub #55647](https://github.com/NousResearch/hermes-agent/issues/55647))

---

## 1. 横向结论表

> **完整九阶段矩阵**（Store / Expose / Discover / Recommend / Offload / Use / Compact / Delete / Evolve）：见 **[skill-lifecycle-full-matrix.md](skill-lifecycle-full-matrix.md)**。  
> **165 维架构调研矩阵**（7 大类）：见 **[agent-skill-architecture-survey-matrix.md](agent-skill-architecture-survey-matrix.md)**。下表为简版。

| 项目 | Skill 存储 | 动态加载 | Per-turn skill | 子 Agent skill | 自进化 | 工程成熟度 |
|------|-----------|---------|----------------|---------------|--------|-----------|
| **Codex** | `skills/<name>/SKILL.md` + scripts/references/assets | 强，progressive disclosure | 支持 implicit/explicit activation | 可能通过 agents/openai.yaml 扩展，但不是核心 | Record & Replay 可生成 skill，但不是闭环自进化 | 高 |
| **OpenClaw** | 多来源 `SKILL.md` | 中强，session snapshot + watcher refresh | session snapshot，下一 turn 可刷新 | 明确 per-agent/workspace/personal/shared skills | agent-drafted proposals，但偏人工 approve | 中高 |
| **Hermes** | `~/.hermes/skills/**/SKILL.md` | 强，on-demand / progressive disclosure | 支持 `/skills`、`/<skill>`、自动选择 | 有 delegate/subagent，但 skill isolation 还不完整 | 最强，`skill_manage` 可 create/patch/edit/delete | 激进但风险高 |
| **GenericAgent** | memory/SOP/skill tree | 更像 recall，不是标准 skill loader | 任务后复用 | 弱 | 强理念：每次任务 crystallize 成 Skill | 简洁但治理弱 |
| **OpenSquilla** | Skill + MetaSkill docs/workflow | 中强 | router/turn-loop 相关 | MetaSkill 可编排 tools/skills/sub-agents | `meta-skill-creator`，偏 proposal | 设计优秀 |
| **ZeroClaw** | registry + `SKILL.md` | install/audit/use | 更偏 registry/runtime | SOP/tool/channel 更强 | 弱，偏安全治理 | 安全治理值得借 |
| **claude-code-reverse** | 不是 skill runtime | 无 | 无 | 重点是 Task/Sub Agent 分析 | 无 | 用来学习 Claude Code harness 思路 |
| **TaiChu** | 建议 `.taichu/skills/**/SKILL.md` + metadata store | 可借 hooks/session factory 实现 | 可实现 | 可结合 subagent relay | 待实现 | 接缝很好 |

---

## 2. Codex：标准化 skill + progressive disclosure，适合作为 TaiChu 基线

Codex 官方文档已经把 Agent Skills 做成正式能力：skill 是目录，包含 `SKILL.md`，可带 `scripts/`、`references/`、`assets/`、`agents/openai.yaml`；`SKILL.md` 必须包含 `name` 和 `description`。([OpenAI Developers — Agent Skills](https://developers.openai.com/codex/skills))

最关键的是 **progressive disclosure**：

```text
初始上下文：
  name + description + file path

真正使用时：
  读取完整 SKILL.md
```

Codex 还限制初始 skill list 的上下文预算：最多 2% context window，未知窗口时最多 8000 字符；如果 skill 太多，先缩短 description，再可能省略部分 skill。

Codex 的触发方式有两种：

```text
explicit:
  /skills
  $ mention skill

implicit:
  根据 description 自动选择
```

这点对 TaiChu 很重要：**description 不是文档字段，而是 routing signal**。

Codex 也有 skill creation 入口：`$skill-creator`，并且支持 Record & Replay：记录 workflow、检查步骤、草拟 reusable skill。

### TaiChu 应借什么

TaiChu 的第一版 skill runtime 应直接采用：

```text
.taichu/skills/<skill-name>/
  SKILL.md
  scripts/
  references/
  assets/
  agents/
```

并要求 frontmatter：

```yaml
name: rust-test-debugger
description: Use when cargo test fails and the task is to diagnose Rust test failure, inspect logs, minimize repro, and propose patch.
version: 0.1.0
owner: team-or-user
allowed_tools:
  - read_file
  - grep
  - bash
risk_level: medium
```

**重点：description 要为 router 写，不是给人看的。**

---

## 3. OpenClaw：多来源 skill loading / priority / per-agent visibility 做得最好

OpenClaw 文档明确说明 skill 是带 YAML frontmatter 的 markdown instruction file，用于教 agent 如何以及何时使用工具。它从多个来源加载 skill，并按优先级覆盖。([openclaw/docs/tools/skills.md](https://github.com/openclaw/openclaw/blob/main/docs/tools/skills.md))

加载优先级是：

```text
1. <workspace>/skills
2. <workspace>/.agents/skills
3. ~/.agents/skills
4. ~/.openclaw/skills
5. bundled skills
6. skills.load.extraDirs + plugin skills
```

同名 skill 由高优先级覆盖低优先级。

OpenClaw 还明确区分 **location precedence** 和 **agent visibility**。多 agent 场景下，每个 agent 有自己的 workspace，可以使用 per-agent、project-agent、personal-agent、shared managed、extra dirs 等不同作用域。

这是 TaiChu 非常应该借鉴的地方。因为 TaiChu 有 subagent / relay / runtime tool factories 的设计，天然会遇到：

```text
主 Agent 可见的 skill
子 Agent 可见的 skill
项目级 skill
用户级 skill
系统级 skill
临时任务 skill
```

OpenClaw 还做了 session snapshot：session 开始时 snapshot eligible skills，后续 turn 复用；但如果 watcher 检测到 `SKILL.md` 变化，或远程节点连接，下一 turn 可以刷新。

### TaiChu 应借什么

TaiChu 的 skill scope 可以这样设计：

```text
Priority 1: <workspace>/.taichu/skills
Priority 2: <workspace>/.agents/skills
Priority 3: ~/.taichu/skills
Priority 4: ~/.agents/skills
Priority 5: managed registry skills
Priority 6: bundled skills
Priority 7: plugin-provided skills
```

再加一个 allowlist：

```yaml
agent_profiles:
  coding_agent:
    allowed_skills:
      - rust-debug
      - git-safety
      - test-repair

  review_agent:
    allowed_skills:
      - code-review
      - security-review
      - diff-analysis

  skill_evolver:
    allowed_skills:
      - skill-authoring
      - regression-eval
```

**关键点：skill 是否存在、skill 优先级、skill 对哪个 agent 可见，是三件事，不要混在一起。**

---

## 4. Hermes：最接近真正 Skill 自进化，但也暴露最多风险

Hermes 的 skill 文档说明：skills 是 on-demand knowledge documents，使用 progressive disclosure 减少 token；所有 skills 都在 `~/.hermes/skills/`，这是 primary source of truth；bundled、hub-installed、agent-created skills 都会放这里；并且 agent 可以修改或删除任意 skill。([hermes-agent skills docs](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md))

这就是它最激进的地方：

```text
Agent 不只是用 skill
Agent 可以创建 / 修改 / 删除 skill
```

Hermes 还有 `skill_manage`，相关 issue 显示它支持 create/patch/edit/delete；同时也暴露出一致性问题：有 issue 说 `skill_manage` 应该和 `skill_view` / `skills_list` 使用同一 discovery path；还有 issue 说 `skill_manage` 报告创建成功但磁盘上没写出 `SKILL.md`。([GitHub #54195](https://github.com/NousResearch/hermes-agent/issues/54195))

最有价值的 Hermes 经验不是「让 agent 随便改 skill」，而是它证明了一个完整闭环的必要组件：

```text
skill_list
skill_view
skill_manage
background_review
progressive disclosure
agent-created skills
```

同时它也证明了危险点：

```text
没有 read-before-write 会 hallucinate patch
没有 critical skill protection 会破坏治理 skill
没有 on-disk verification 会造成 session 内假成功
没有 shadowing 防护会绕过 readonly external skill
```

Hermes issue 中明确提到 background self-improvement review turn 可以调用 `skill_manage(patch)`，但如果没先读当前 skill，会基于 transcript 幻觉式 patch，甚至删除大量现有内容。([GitHub #55647](https://github.com/NousResearch/hermes-agent/issues/55647))

### TaiChu 应借什么

TaiChu 可以借 Hermes 的能力，但要加硬约束：

```text
skill_manage(action=patch)
  必须先 skill_view 当前版本
  必须提交 unified diff
  必须做 schema validation
  必须写临时 candidate
  必须 run eval
  必须 produce before/after summary
  高风险 skill 必须 human approve
```

不要让 agent 直接写生产 skill。应该是：

```text
Agent proposes
System validates
Eval scores
Policy gates
Human approves if needed
Then deploy
```

---

## 5. GenericAgent：最纯粹的「任务路径固化为 skill」思想

GenericAgent README 明确说它是 minimal self-evolving autonomous agent framework，核心约 3K 行、9 个 atomic tools、约 100 行 agent loop；设计哲学是「不预加载 skills，而是 evolve them」。每次解决新任务后，会把 execution path 自动 crystallize 成 reusable Skill，长期形成 personal skill tree。([lsdefine/genericagent](https://github.com/lsdefine/genericagent))

这代表一种和 Codex/OpenClaw/Hermes 不同的路线：

```text
Codex / OpenClaw / Hermes:
  skills are authored packages

GenericAgent:
  skills are crystallized execution paths
```

这更接近 SkillRL 的精神：从 trajectory 中抽取 reusable abstraction。

但它的问题是：如果缺少评测和治理，crystallized skill 很容易把偶然经验、环境特定路径、错误 workaround 固化下来。

### TaiChu 应借什么

TaiChu 应借 GenericAgent 的 **Skill Miner** 思想：

```text
task
  ↓
trajectory
  ↓
success/failure analysis
  ↓
candidate skill
```

但不要借它的「直接沉淀到可用 skill」。TaiChu 应该加：

```text
candidate skill
  ↓
deduplicate
  ↓
generalize
  ↓
regression test
  ↓
risk gate
  ↓
versioned publish
```

也就是说：

```text
GenericAgent = skill 自进化的灵感
Hermes = skill 自修改的 runtime
Codex/OpenClaw = skill packaging/loading standard
ZeroClaw = security governance
OpenSquilla = workflow-level MetaSkill
```

---

## 6. OpenSquilla：MetaSkill 是 TaiChu 最应该吸收的抽象

OpenSquilla 的 MetaSkill 定义很清楚：Meta-skills package repeatable multi-step work as reusable, inspectable workflows；适合需要多个 normal skill、tool、checkpoint、final synthesis pass 的任务。([OpenSquilla Meta-Skills](https://www.opensquilla.ai/docs/features/meta-skills/))

它区分：

```text
Skill:
  one focused task pattern / instruction set / script / tool helper

MetaSkill:
  reusable workflow made of multiple steps / skills / checks / outputs
```

这对 TaiChu 很关键。因为「Skill 自进化」如果只停留在 prompt 片段，会很快失控。真正可工程化的是：

```text
procedure
  + preconditions
  + steps
  + tool permissions
  + checkpoints
  + expected artifacts
  + eval criteria
```

这其实就是 MetaSkill。

OpenSquilla 还内置 `meta-skill-creator`，用于把重复的多 skill 协作模式变成新的 MetaSkill proposals。

### TaiChu 应借什么

TaiChu 可以把 skill 分两层：

```text
AtomicSkill:
  单一能力
  例如：cargo-test-debug, git-safety-check, web-search-verify

MetaSkill:
  workflow 编排
  例如：implement-feature-with-tests
```

MetaSkill 示例：

```yaml
name: implement-feature-with-tests
description: Use for code changes requiring implementation, tests, and verification.
steps:
  - skill: repo-understanding
  - skill: implementation-plan
  - skill: edit-code
  - checkpoint: compile
  - skill: test-repair
  - checkpoint: regression
  - skill: final-summary
subagents:
  reviewer:
    skills:
      - code-review
      - security-review
outputs:
  - patch
  - test_report
  - risk_summary
```

这样 TaiChu 的 skill evolution 可以分层演进：

```text
AtomicSkill evolution:
  改某个调试步骤

MetaSkill evolution:
  改整个工作流拓扑
```

---

## 7. ZeroClaw：Skill registry 安全治理值得直接照搬

ZeroClaw 主项目是 Rust agent runtime，强调本地运行、工具、channel、provider、MCP 等。([zeroclaw-labs/zeroclaw](https://github.com/zeroclaw-labs/zeroclaw))

更重要的是 `zeroclaw-skills` registry：它明确说 registry 不是 vetted security boundary；CI 只做结构验证、secret detection、dangerous regex、file-policy checks；用户仍需要自己 `zeroclaw skills audit <name>` 并阅读 `SKILL.md`。([zeroclaw-labs/zeroclaw-skills](https://github.com/zeroclaw-labs/zeroclaw-skills))

这非常现实。

OpenClaw 生态也被安全报道指出过 skill marketplace 风险：恶意 skill 会伪装成正常扩展，诱导 agent 或用户执行恶意脚本；安全问题集中在 local file / network / command execution 权限和第三方 skill 未充分 sandbox。([The Verge](https://www.theverge.com/news/874011/openclaw-ai-skill-clawhub-extensions-security-nightmare))

### TaiChu 应借什么

TaiChu 的 skill store 必须是安全对象，而不是普通 markdown：

```yaml
name: github-pr-review
version: 0.2.1
source: workspace | user | registry | generated | bundled
owner: andy
trust_tier: bundled | team | personal | generated | community
risk_level: low | medium | high | critical
allowed_tools:
  - read_file
  - grep
  - git_diff
denied_tools:
  - shell_network
  - write_sensitive_file
requires_approval:
  - bash
  - network
  - modify_skill
mutable_by_agent: false
```

对自进化生成的 skill，默认：

```text
trust_tier = generated
mutable_by_agent = false after publish
requires_human_approval = true
```

否则会出现 Hermes issue 中那类「agent 把 governance skill 改坏」的问题。([GitHub #25083](https://github.com/NousResearch/hermes-agent/issues/25083))

---

## 8. Claude Code Reverse：重点不是 skill，而是 subagent context offload

`claude-code-reverse` 不是 skill runtime，而是可视化 Claude Code LLM interactions 的工具。它的价值在于揭示 Claude Code 的 harness 模式。

它记录的 Task/Sub Agent workflow 是：

```text
Main Agent
  ↓
通过 Task Tool 启动 Sub Agent
  ↓
把独立任务抽取成 sub context 初始 prompt
  ↓
Sub Agent 完成后把最终结果作为 tool result 返回 main context
```

这个设计的价值是隔离 dirty context：例如代码搜索过程中产生大量无关文件读取，这些上下文留在 subagent，主上下文只保留最终摘要。([Yuyz0112/claude-code-reverse](https://github.com/Yuyz0112/claude-code-reverse))

它还提到 TodoWrite 会写 JSON 到 `~/.claude/todos/`，作为当前 conversation 的短期 memory；system reminder 会动态加载最新 Todo list。

### TaiChu 应借什么

Skill 和 subagent 应该结合：

```text
Main Agent:
  only sees task-level MetaSkill

Sub Agent:
  sees specialized AtomicSkills

Main context:
  only receives compact result
```

比如：

```text
主 Agent:
  MetaSkill = implement-feature-with-tests

子 Agent A:
  skills = repo-search, symbol-trace

子 Agent B:
  skills = rust-test-debug, cargo-error-minimize

子 Agent C:
  skills = review-diff, security-check
```

这就是 **complementary skills for subagents**。它不应该是所有 agent 共享同一个 skill list，而是：

```text
task decomposition
  ↓
subagent role
  ↓
skill bundle selection
  ↓
subagent isolated execution
  ↓
compact return
```

---

## 9. Skill 生命周期完整模型

TaiChu 最终应该实现的是这张生命周期表：

| 阶段 | 作用 | 来源项目可借鉴 |
|------|------|---------------|
| Discover | 找到所有 skills | OpenClaw multi-root loading |
| Expose | 暴露 name/description/path | Codex progressive disclosure |
| Recommend | 按 task 推荐 skill | Codex implicit trigger / router |
| Load | 读取完整 SKILL.md | Codex/Hermes |
| Execute | 按 skill 指令执行 | 全部 |
| Trace | 记录 turn/tool/failure | Claw-R1 思想 + TaiChu hooks |
| Mine | 从 trajectory 提取 candidate | GenericAgent / SkillRL |
| Propose | 生成 skill patch/new skill | Hermes skill_manage |
| Evaluate | regression/eval/score | Hermes self-evolution / GEPA 思想 |
| Approve | 人审/策略门禁 | ZeroClaw governance |
| Publish | 写入 versioned store | OpenClaw/ZeroClaw |
| Monitor | 统计使用率/成功率 | TaiChu 自建 |
| Compact | 压缩 description / references | Codex/OpenClaw |
| Delete | 删除/归档/禁用 | Hermes/ZeroClaw |
| Rollback | 回滚版本 | TaiChu 必须补 |

---

## 10. TaiChu 推荐实现：三层 skill 系统

### Layer 1：Skill Registry

```rust
struct SkillManifest {
    name: String,
    description: String,
    version: SemVer,
    source: SkillSource,
    scope: SkillScope,
    trust_tier: TrustTier,
    risk_level: RiskLevel,
    allowed_tools: Vec<String>,
    denied_tools: Vec<String>,
    mutable_by_agent: bool,
    requires_approval: Vec<ApprovalKind>,
}
```

### Layer 2：Skill Router

输入：

```text
task
session state
agent role
available tools
risk policy
context budget
```

输出：

```text
selected skill summaries
full SKILL.md for activated skills
subagent skill bundles
```

Router 必须支持：

```text
explicit:
  /skill rust-debug

implicit:
  task matches description

role-based:
  reviewer agent only gets review skills

budget-based:
  initial skill list capped
```

### Layer 3：Skill Evolution

```text
SessionHook / ToolHook
  ↓
TraceCollector
  ↓
FailureMiner / SuccessMiner
  ↓
SkillCandidateGenerator
  ↓
Deduper
  ↓
Evaluator
  ↓
PolicyGate
  ↓
SkillPublisher
```

TaiChu 已有 hooks、session options、extra tool factories、context options，这些就是落点。资料里显示 `SessionOptions` 已有 `extra_tools`、`extra_tool_factories`、`enable_interaction_log`，`ContextOptions` 有 `hook_chain`，这些适合接入 trace capture 与 dynamic skill/tool 注入。

---

## 11. 自进化不要直接在线更新：推荐 Candidate/PR 模式

最安全的 TaiChu 自进化闭环：

```text
Online execution
  ↓
collect traces
  ↓
offline miner generates candidate skill
  ↓
candidate saved under:
    .taichu/skill-candidates/<id>/
  ↓
run regression harness
  ↓
score:
    success_rate_delta
    token_delta
    latency_delta
    tool_error_delta
    safety_risk
  ↓
if good:
    open PR / human approve
  ↓
publish to:
    .taichu/skills/<name>/SKILL.md
```

不要直接：

```text
background agent
  ↓
patch production SKILL.md
```

Hermes 的 issue 已经说明这个路径很危险。([GitHub #55647](https://github.com/NousResearch/hermes-agent/issues/55647))

---

## 12. 最终建议：TaiChu 应该借鉴谁的哪一部分

| 借鉴对象 | 借什么 | 不借什么 |
|---------|--------|---------|
| Codex | SKILL.md 标准、progressive disclosure、implicit trigger、Record & Replay | 不要只做手工 skill creator |
| OpenClaw | 多来源加载、优先级、per-agent visibility、session snapshot、watch refresh | 不要照搬 marketplace 风险 |
| Hermes | `skill_manage`、agent-created skills、background review、skill self-improvement | 不要让 agent 无门禁修改 critical skills |
| GenericAgent | trajectory → reusable skill | 不要无评测直接固化 |
| OpenSquilla | MetaSkill = workflow-level skill | 不要把 workflow 写成散 prompt |
| ZeroClaw | registry/audit/trust tier/security | 不要相信 CI 扫描就是安全边界 |
| Claude Code Reverse | subagent context offload | 不要把所有 skill 暴露给所有 subagent |

### 一句话结论

TaiChu 最优路线不是简单做一个 `skills/` 目录，而是做：

```text
Versioned Skill Registry
+
Per-turn Skill Router
+
Subagent-specific Skill Bundles
+
Trace-driven Skill Candidate Mining
+
Eval-gated Skill Evolution
+
Security/Approval Governance
```

也就是把 skill 当成 **可评测、可审计、可版本化、可回滚的软件资产**，而不是 prompt 片段。

---

## 附录：与本机 L3 交叉核对

> 本 workspace 有本机 clone 的 L3 源码证据。以下修正/补充 Web 版结论。

### A. 必须修正：两个不同的「claude-code-reverse」

| 仓库 | 实际是什么 | 对 TaiChu 的价值 |
|------|-----------|-----------------|
| **Yuyz0112/claude-code-reverse** | LLM 交互可视化工具 | Subagent Task 模式、TodoWrite 模式（Web 文 §8 引用的是这个） |
| **oboard/claude-code-rev**（本机 `oss/experimental/claude-code-rev`） | **完整 skill runtime + harness** | `invoked_skills` compaction 存活、`skillImprovement` 5-turn、subagent frontmatter preload |

**Web 文 §1 表将 claude-code-reverse 标为「不是 skill runtime」——对 Yuyz0112 正确，但会漏掉 oboard 仓。** 本机 L3 证据表明 oboard 应单独列入借鉴表：

| 借鉴对象 | 额外应借（本机 L3） |
|---------|-------------------|
| **oboard/claude-code-rev** | compaction 后 reinject invoked skills；5-turn skill improvement；`ChildSessionSpec` skill preload |

见 [`repos/claude-code-rev.md`](repos/claude-code-rev.md) · [`taichu-p0-skill-compaction-spec.md`](taichu-p0-skill-compaction-spec.md)。

### B. OpenClaw 自进化 — Web 偏保守，本机更强

Web 表写「agent-drafted proposals，偏人工 approve」。本机 L3 发现 **`extensions/skill-workshop/`** 在 `agent_end` 有 heuristic + LLM reviewer → apply 管道，不仅是 marketplace。强度仍低于 OpenSquilla 5-gate，但应上调。

### C. OpenSquilla — Web 偏设计文档，本机有完整代码

本机 L3：`proposals_lib.py`（accept + gates）、`skills_filter.py`（**每 turn RRF**）、`auto_propose.py`、`runtime_e2e.py`。MetaSkill 不仅是文档抽象，有 `meta/orchestrator.py` DAG 编排。

### D. TaiChu 接缝名修正（§10）

| Web 文写法 | 本机核实 |
|-----------|---------|
| `SessionOptions.extra_tool_factories` | → **`Runtime::add_tool_factory`** / `register_extra_tools` |
| `ContextOptions.hook_chain` | → **`SessionOptions.transform_context`** + Toollery `before_prompt` |
| `set_skill_name_filter` | ✅ 正确，per-turn filter |

### E. 合并后的「借鉴谁」表（Web + L3）

在 §12 基础上 **增加一行**：

| 借鉴对象 | 借什么 | 不借什么 |
|---------|--------|---------|
| **oboard/claude-code-rev** | `invoked_skills` compaction survival、skillImprovement、subagent skill preload | 不要与 Yuyz0112 可视化工具混淆 |

### F. 合并后的生命周期表补充

| 阶段 | 本机 L3 额外证据 |
|------|-----------------|
| Compact | **仅 oboard** 有 `invoked_skills` 附件；TaiChu **P0 缺口** |
| Recommend | OpenSquilla **每 turn RRF** 强于 Codex 静态 list |
| Propose | OpenSquilla **5-gate** + OpenClaw **skill-workshop** 双路径 |

### G. 证据等级

| 本文 | 等级 |
|------|------|
| §0–§12 主体 | **L0**（公开 docs/issue） |
| 本附录 | **L3**（本机源码交叉） |

完整合并排序见 [`web-vs-local-reconciliation.md`](web-vs-local-reconciliation.md) · [`l3-comprehensive-skill-analysis.md`](l3-comprehensive-skill-analysis.md)。

---

## 参考链接

- [Hermes #55647 — skill_manage patches hallucinate](https://github.com/NousResearch/hermes-agent/issues/55647)
- [OpenAI Codex Agent Skills](https://developers.openai.com/codex/skills)
- [OpenClaw skills.md](https://github.com/openclaw/openclaw/blob/main/docs/tools/skills.md)
- [Hermes skills docs](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md)
- [Hermes #54195 — skill_manage symlink](https://github.com/NousResearch/hermes-agent/issues/54195)
- [GenericAgent](https://github.com/lsdefine/genericagent)
- [OpenSquilla Meta-Skills](https://www.opensquilla.ai/docs/features/meta-skills/)
- [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw)
- [zeroclaw-skills registry](https://github.com/zeroclaw-labs/zeroclaw-skills)
- [The Verge — OpenClaw skill security](https://www.theverge.com/news/874011/openclaw-ai-skill-clawhub-extensions-security-nightmare)
- [Hermes #25083 — critical skill protection](https://github.com/NousResearch/hermes-agent/issues/25083)
- [Yuyz0112/claude-code-reverse](https://github.com/Yuyz0112/claude-code-reverse)（可视化；≠ oboard/claude-code-rev）
