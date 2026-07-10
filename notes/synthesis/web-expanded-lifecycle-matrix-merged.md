---
id: N2026-07-08-WEB-LIFECYCLE
title: Web 扩展生命周期 Matrix — 合并版（公开证据 + L3 交叉核对）
date: 2026-07-08
tags: [lifecycle-matrix, web-research, merged, taichu-design, openclaw-rl]
status: active
evidence_level: L0+L3
source: public repo/docs (user extraction) + local L3 cross-check
related: [T007, N2026-07-08-WEB-DEEP, N2026-07-08-011]
summary: User expanded lifecycle overview matrix + quotes + TaiChu design; reconciled with 165-dim survey and 8 repo reports
---

# Web 扩展生命周期 Matrix — 合并版

> **来源 A**：公开 repo/docs 页面 evidence extraction（本文 §1–§6 主体）。  
> **来源 B**：本 workspace L3 本机源码（[survey-reports/](survey-reports/) · [agent-skill-architecture-survey-matrix.md](agent-skill-architecture-survey-matrix.md)）。  
> **合并规则**：保留 Web 表述 + **附录 B** 标 L3 修正；TaiChu 接缝以本机核实为准。

**相关文档**

| 文档 | 关系 |
|------|------|
| [agent-skill-architecture-survey-matrix.md](agent-skill-architecture-survey-matrix.md) | 165 维主仪器 |
| [survey-reports/README.md](survey-reports/README.md) | 8 仓 12 段报告 + evidence index |
| [web-deep-taichu-borrowing-guide.md](web-deep-taichu-borrowing-guide.md) | TaiChu 借鉴指南 |
| [taichu-p0-skill-compaction-spec.md](taichu-p0-skill-compaction-spec.md) | P0 实现 spec |

---

## 1. 总览 Matrix（Web 原版 + L3 修正列）

| Project | Skill 存储 | Exposed 给模型 | Discovered | Recommended | Dynamic / Per-turn | Used | Compact / Offload | Delete / Disable | Evolved | **L3 修正要点** |
|---------|-----------|---------------|------------|-------------|-------------------|------|-------------------|------------------|---------|----------------|
| **Codex** | `skills/<n>/SKILL.md` + scripts/refs/assets/agents | 初始 `name+description+path` | 目录扫描 + scopes | 显式 `/skills`/`$skill`；隐式 description | ★ progressive disclosure；选中后全文 | prompt + scripts | 2% ctx / 8K cap；truncate desc | 文件/配置 disable | skill-creator / Record&Replay；**无闭环** | L3 确认 `render.rs` 预算文案 · [codex.md](survey-reports/codex.md) |
| **OpenClaw** | 6 源 `SKILL.md` 优先级 merge | compact XML metadata → read tool | 多路径 + gating + allowlist | eligible list + **per-agent skillFilter** | session snapshot；watcher next-turn refresh | teach tools；lazy read | compact XML；`~/` path 压缩 | local/config；scanner quarantine | skill-workshop `agent_end`；**非仅 human** | L3：**workshop 源码** `extensions/skill-workshop/` · [openclaw.md](survey-reports/openclaw.md) |
| **Hermes** | `~/.hermes/skills/**/SKILL.md` | progressive disclosure | local + hub sync | `/skills`、`/<skill>` | on-demand `skill_view` | skill_manage CRUD | ContextCompressor；frozen index | agent **可 delete any** | skill_manage + bg review；GEPA 离线仓 | L3：issue [#55647](https://github.com/NousResearch/hermes-agent/issues/55647) patch 风险 · [hermes-agent.md](survey-reports/hermes-agent.md) |
| **GenericAgent** | memory `*_sop.md` tree | memory recall | L1 index → file_read | task similarity / related_sop | anchor prompt；非 per-turn registry | crystallized path | 6× token via reuse | 治理弱 | 成功任务 auto crystallize | L3：`ga.py:508` verified write · [genericagent.md](survey-reports/genericagent.md) |
| **OpenSquilla** | Skill + **MetaSkill** DAG | injector full/compact | 6-layer loader | **★ 每 turn RRF top-k** | pipeline `filter_skills` | meta_invoke workflow | per-turn rebuild；budget governor | **reject_proposal** + gates | auto_propose + 4-gate + runtime_e2e | L3：**强于 Web「unclear delete」** · [opensquilla.md](survey-reports/opensquilla.md) |
| **ZeroClaw** | workspace + **zeroclaw-skills** registry | **Full / Compact** injection | registry install + audit | user install/search | session-level | SkillToolHandler | auto_compact history | pin version；registry advisory | 进化弱；audit 强 | L3：主仓有 compact mode 非「无 progressive」 · [zeroclaw.md](survey-reports/zeroclaw.md) |
| **Claude (Yuyz0112)** | **非 skill runtime** | — | — | — | — | Task/SubAgent | **★ dirty context offload** | — | — | 仅 harness 洞察；[GitHub](https://github.com/Yuyz0112/claude-code-reverse) |
| **Claude Rev (oboard)** | ★ **完整 skill runtime** | 3-channel：listing / Skill tool / **invoked_skills** | 增量 listing per agentId | usage decay 7d | per-turn delta attachment | Skill tool + slash | **★ invoked_skills survives compact** | survey UI apply | skillImprovement 5-turn | L3：**必须单独列出** · [claude-code-rev.md](survey-reports/claude-code-rev.md) |
| **OpenClaw-RL** | trajectory/training signals | N/A | N/A | N/A | N/A | RL framework | async serve/train 解耦 | N/A | conv → PRM/judge/GRPO | **非 skill store** · [Gen-Verse/OpenClaw-RL](https://github.com/Gen-Verse/OpenClaw-RL) |
| **TaiChu** | canonical `skills/system/` + cloud catalog；目标 `.taichu/skills/` | XML + **每 turn user prefix** | session scan + Toollery | 建议 SkillRouter（◐ embedding） | ★ `# Available Skills` per turn | load_skill + **runs_on** | ❌ compact 丢 body；subagent relay | 建议 versioned store | trace→candidate→eval→publish | L3 接缝见 §4 · [taichu.md](survey-reports/taichu.md) |

---

## 2. Evidence / Quote（Web 提取 + 本机印证）

### Codex

官方：skill = reusable workflow；`SKILL.md` 必含 `name`/`description`；progressive disclosure；initial list ≤2% ctx 或 8000 chars。

> **"Codex loads the full `SKILL.md` instructions only when it decides to use a skill."**  
> — [OpenAI Developers — Agent Skills](https://developers.openai.com/codex/skills)

**L3 印证**：`codex-rs/core-skills/src/render.rs:27-43` 完整 progressive disclosure 指令；`render.rs:21` budget warning 常量。

### OpenClaw

Skill = YAML frontmatter markdown；6 源优先级；同名高优先级覆盖；session snapshot + mid-session refresh。

> **"When the same skill name appears in multiple places, the highest source wins."**  
> — [OpenClaw Skills docs](https://docs.openclaw.ai/tools/skills) · 本机 `docs/tools/skills.md:19-30`

**L3 追加**：location vs visibility 分离（docs:50-52）；`skill-workshop` *"Captures repeatable workflows as workspace skills, with pending review and safe writes"* — `extensions/skill-workshop/index.ts:13-14`。

### Hermes

On-demand knowledge docs；`~/.hermes/skills/`；agent 可 modify/delete。

> **"The agent can modify or delete any skill."**  
> — [Hermes Skills docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)

**L3 追加** — `skill_manager_tool.py:5-8`：

```python
"""Allows the agent to create, update, and delete skills, turning successful
approaches into reusable procedural knowledge."""
```

**L3 追加** — review prompt `run_agent.py:1773-1775`；风险 [issue #55647](https://github.com/NousResearch/hermes-agent/issues/55647)。

**离线进化**（Web L0，仓未 clone）：[hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) — DSPy/GEPA → eval → PR。

### GenericAgent

> **"automatically crystallizes the execution path into a reusable Skill."**  
> — [lsdefine/genericagent README](https://github.com/lsdefine/genericagent)

**L3 印证**：`README.md:38-40` *"don't preload skills, evolve them"*；`ga.py:508-523` `start_long_term_update`。

### OpenSquilla

MetaSkill = reusable task protocol。

> **"A MetaSkill preserves a way of doing high-value work."**  
> — [meta-skill-user-guide.md](https://github.com/opensquilla/opensquilla/blob/main/docs/features/meta-skill-user-guide.md)

**L3 追加**：`skills_filter.py:1` — *"Step 3: Gate skills deterministically, optionally filter by relevance, inject."*；`proposals_lib.py:425` `accept_proposal`。

### ZeroClaw

Registry 治理：pin version；install 前 audit。

> **"Run `zeroclaw skills audit` before installing a new skill."**  
> — [zeroclaw-labs/zeroclaw-skills](https://github.com/zeroclaw-labs/zeroclaw-skills)

**L3 追加**：`src/skills/audit.rs:16-20` zip-bomb 限制；registry **非** security boundary（README disclaimer）。

### Claude — 两个仓库

| 仓库 | Quote / 价值 |
|------|-------------|
| **Yuyz0112** | SubAgent 隔离 dirty context，主 context 只收 compact result — [claude-code-reverse](https://github.com/Yuyz0112/claude-code-reverse) |
| **oboard** | `compact.ts:1488-1492` — *"Creates an attachment for invoked skills to preserve their content across compaction"* |

### OpenClaw-RL

Conversation → training signals；serving / rollout / PRM / policy 四 loop 异步。

> — [Gen-Verse/OpenClaw-RL](https://github.com/Gen-Verse/OpenClaw-RL)

**定位**：RL harness layer；与 OpenClaw `openclaw-trajectory` JSONL 互补，**不是** SKILL.md lifecycle。

---

## 3. Skill Lifecycle 对比（Web + L3 合并）

| Stage | Codex | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | oboard Claude Rev | TaiChu 目标 |
|-------|-------|----------|--------|--------------|-------------|----------|-------------------|-------------|
| **Author** | human / skill-creator | human / workshop | human / hub / agent | agent crystallize | human/AI + auto_propose | community | skillify / human | human + agent candidate |
| **Store** | folder SKILL.md | 6-root merge | ~/.hermes/skills | memory SOP tree | 6-layer + proposals/ | workspace + registry | multi-root SKILL.md | `.taichu/skills` + manifest DB |
| **Discover** | scope scan | precedence + filter | dir scan | L1 index | **每 turn pipeline** | install + audit | incremental listing | SkillRegistry multi-root |
| **Expose** | name/desc/path | compact XML | metadata index | recalled title | injector compact/full | full/compact mode | 3-channel attachment | user prefix + XML |
| **Recommend** | description | allowlist | explicit/auto | similarity | **RRF top-k** | user choice | decay score | SkillRouter |
| **Load** | full after pick | read tool lazy | skill_view | file_read | skill_view / meta_invoke | read at location | Skill tool | load_skill + runs_on |
| **Use** | prompt+scripts | prompt+env | skill_manage | reuse path | MetaSkill DAG | tool bridge | prompt+tools | prompt+tools+workflow |
| **Observe** | dispatch trace | trajectory JSONL | JSONL+DB | model logs | decision log | OTel | session JSONL | **interaction_log** ★已有 |
| **Compact** | metadata budget | compact XML | compressor | history tags | per-turn rebuild | auto_compact | **invoked_skills ★** | reinject P0 |
| **Evolve** | creator/replay | workshop+scanner | manage+GEPA | auto SOP | gates+E2E | weak | survey UI | eval-gated PR |
| **Delete** | FS/config | FS+quarantine | agent delete | manual | **reject_proposal** | rm/pin | user delete | disable/archive/rollback |
| **Governance** | Guardian | allowlist+scanner | skills_guard ◐ | L0 SOP doc | **4-gate** | **audit ★** | survey gate | policy+approval |

---

## 4. TaiChu 设计建议（合并版）

### 4.1 目标六层（Web + L3 一致）

```text
SkillRegistry   → scan / precedence / metadata / version / trust_tier
SkillRouter     → per-turn / per-agent / per-subagent selection
SkillLoader     → progressive disclosure (name+description → full SKILL.md)
SkillTrace      → HookChain + interaction_log
SkillEvolution  → trace → candidate → eval → approval → publish
SkillGovernance → allow/deny tools / risk / owner / audit / rollback
```

### 4.2 真实接缝（L3 核实 — 修正 Web 写法）

| Web 材料写法 | **本机核实（2026-07-08）** | 证据 |
|-------------|---------------------------|------|
| `SessionOptions.extra_tool_factories` | → **`Runtime::add_tool_factory`** / `register_extra_tools` | `survey-methodology-and-repo-confirmation.md` |
| `ContextOptions.hook_chain` | → **`SessionOptions.transform_context`** + Toollery `before_prompt` | `api/mod.rs:674-694`, `tool_search_bridge.rs:370` |
| `preloaded_blocks` | ◐ 存在；skills 主路径是 **user prefix + load_skill** | `prompt_builder.rs`, `load_skill.rs` |
| `enable_interaction_log` | ★ **SkillTrace 落点** | interaction JSONL |
| `subagent_relay` | ★ 有；**缺** child skill preload / inherit | `manager.rs:1736-1796` |

### 4.3 P0–P3 落地（来自 8 份 survey report）

| P | 组件 | 借谁 | 文件 |
|---|------|------|------|
| **P0** | InvokedSkillRegistry + compact reinject | oboard Claude Rev | `compaction.rs` — [spec](taichu-p0-skill-compaction-spec.md) |
| **P0** | ChildSessionSpec.skills preload | oboard | `session/manager.rs` |
| **P1** | proposals/ + gates.json | OpenSquilla | new `~/.taichu/proposals/` |
| **P1** | skill_manage → **candidate only** | Hermes（加 read-before-write） | `builtintools/` |
| **P1** | audit + trust_tier | ZeroClaw | skill loader |
| **P2** | RRF SkillRouter | OpenSquilla | `tool_search_bridge.rs` |
| **P2** | SkillMiner | GenericAgent + interaction_log | async job |
| **P3** | MetaSkill DAG | OpenSquilla | new `meta/` |

---

## 5. 最应该借鉴的组合（Web + L3 分数）

| 来源 | 借什么 | 落地 | L3 分数 |
|------|--------|------|:-------:|
| Codex | progressive disclosure + description routing | SkillManifest.description | 7.2 |
| OpenClaw | 多路径 + per-agent visibility + trajectory | registry merge + JSONL schema | 8.0 |
| Hermes | skill_manage + review（**candidate only**） | async review + guard | 8.1 |
| GenericAgent | trajectory → skill | SkillMiner | 4.8 |
| OpenSquilla | MetaSkill + gates + RRF | proposals + router | **9.0** |
| ZeroClaw | audit / pin / trust | pre-load scan | 5.0 |
| **oboard Claude Rev** | invoked_skills + subagent preload | P0 compaction | 7.7 |
| Yuyz0112 | subagent context offload | relay 设计参考 | — |
| OpenClaw-RL | feedback → training signal | log → RL dataset | RL layer |
| **TaiChu 保留** | runs_on + per-turn user prefix | 已实现 | 5.0 |

---

## 6. 最终目标形态（一致）

```text
User Task
  ↓
SkillRouter (RRF + pinned + role filter)
  ↓
Per-turn selected skills (user prefix / compact expose)
  ↓
Main Agent + SubAgent complementary skill bundles
  ↓
Execution / tool / failure trace (interaction_log)
  ↓
Skill Miner (GenericAgent 思想 + OpenSquilla 共现)
  ↓
Candidate Skill / Candidate MetaSkill (~/.taichu/proposals/)
  ↓
Regression Eval + ZeroClaw-style Audit + OpenSquilla gates
  ↓
Human / Policy Approval (Hermes 教训：禁止无 gate 直写)
  ↓
Versioned Skill Store
  ↓
Next-turn Dynamic Loading + Claude Rev invoked_skills compact survival
```

> **TaiChu 不要只做 skills 目录；要做 Skill Lifecycle System。**

---

## 附录 A — 与 165 维 Matrix 映射

| 本文 §1 列 | Matrix sections |
|-----------|-----------------|
| Skill 存储 | §1 Data Model |
| Exposed / Discovered / Recommended | §2–§4 |
| Dynamic / Per-turn / Used | §5–§7 |
| Compact / Offload | §5–§6 |
| Delete / Evolved / Governance | §8–§11 |
| RL（OpenClaw-RL 行） | §15 |

Full instrument: [agent-skill-architecture-survey-matrix.md](agent-skill-architecture-survey-matrix.md)

---

## 附录 B — Web 表需修正项（L3）

| Web 结论 | L3 修正 |
|---------|---------|
| Claude Code Reverse = 无 skill | **拆两行**：Yuyz0112（viz/offload）+ **oboard（完整 runtime）** |
| OpenSquilla delete unclear | `reject_proposal` + managed delete + gates |
| OpenClaw evolve 偏 human only | `skill-workshop` auto policy + LLM reviewer |
| ZeroClaw 无 progressive disclosure | 主仓 Full/Compact injection mode |
| TaiChu `extra_tool_factories` / `hook_chain` | 见 §4.2 接缝表 |
| Hermes evolve 最强无保留 | 必须 candidate/PR + read-before-write（#55647） |
| 未单列 OpenClaw-RL | 已加第 9 行；trajectory 层非 skill store |

---

## 参考链接

- [1] https://developers.openai.com/codex/skills
- [2] https://docs.openclaw.ai/tools/skills
- [3] https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
- [4] https://github.com/NousResearch/hermes-agent-self-evolution
- [5] https://github.com/lsdefine/genericagent
- [6] https://github.com/opensquilla/opensquilla/blob/main/docs/features/meta-skill-user-guide.md
- [7] https://github.com/zeroclaw-labs/zeroclaw-skills
- [8] https://github.com/Yuyz0112/claude-code-reverse
- [9] https://github.com/Gen-Verse/OpenClaw-RL
- oboard https://github.com/oboard/claude-code-rev
- Hermes #55647 https://github.com/NousResearch/hermes-agent/issues/55647

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-08 | 摄入 Web 扩展 lifecycle matrix；与 L3 survey 合并 |
