---
id: N2026-07-08-LIFECYCLE-MATRIX
title: Skill 全生命周期矩阵 — 八仓 × 九阶段
date: 2026-07-08
tags: [lifecycle, matrix, store, expose, discover, recommend, offload, compact, delete, evolve, comparison]
status: active
evidence_level: L3
related: [N2026-07-08-010, N2026-07-08-009, N2026-07-08-WEB-DEEP, N2026-07-08-L3]
summary: Wide comparison table — Store/Expose/Discover/Recommend/Offload/Use/Compact/Delete/Evolve/Lifecycle per framework
---

# Skill 全生命周期矩阵 — 八仓 × 九阶段

> **证据**：本机 L2–L3 源码（见 [`skill-lifecycle-and-dynamic-loading-survey.md`](skill-lifecycle-and-dynamic-loading-survey.md)）。  
> **生命周期模型**：`Store → Expose → Discover → Recommend → Offload → Use → Compact → Delete → Evolve`  
> **图例**：★ 明确实现 | ◐ 部分 | · 无 | ❌ 已知缺口

**Claude 条目** = **oboard/claude-code-rev**（skill runtime），非 Yuyz0112 可视化工具。

---

## 1. 主矩阵（九阶段 × 八项目）

| 项目 | **Store** | **Expose** | **Discover** | **Recommend** | **Offload** | **Use (Load)** | **Compact** | **Delete** | **Evolve** | **Lifecycle 完整度** |
|------|-----------|------------|--------------|---------------|-------------|----------------|-------------|------------|------------|---------------------|
| **Codex** | `skills/<name>/SKILL.md` + scripts/refs/assets/agents；User/Repo/System/Admin scopes；FS 为真相 | Metadata block `AvailableSkillsInstructions`；2% ctx / 8K char budget 截断 | File watcher 刷新；TUI toggle；`@skill-name` explicit mention | · 无 ranking；全量 metadata 字母序 + budget 截断 | 未 mention 的 skill **不进当 turn**；body 从未预载 | **Explicit**：`build_skill_injections()` 全文注入 user fragment；**Implicit**：shell 命令 pattern 自动 invoke | Pre/post compact hooks；**无** invoked_skills 附件；`Polluted` memory 标记 | 用户删 FS 文件；TUI `write_skill_enabled` 开关 | · 刻意不做闭环；`skill-creator` 样本 + Record & Replay 人工路径 | **6/9** — 标准+披露强；缺 Recommend/Evolve/Compact-skill |
| **OpenClaw** | 6 源 merge + 优先级覆盖：extra < bundled < managed < `~/.agents` < project/.agents < workspace/skills；`~/.openclaw/skills` managed | Prompt 仅 **metadata XML**（name/desc/location）；`~/` path 压缩；150 skill / 18K char 上限 → compact XML → binary search | Session snapshot + version；chokidar watcher；**per-agent skillFilter** 白名单 | · 字母序 + count/char budget；**无** embedding/RRF | Lazy 设计：body **永不进 catalog prompt**；靠 read tool 按需 | Model **read tool** 读 `SKILL.md`；`disableModelInvocation` 可隐藏 | compaction-safeguard 总结对话；**不**保留 invoked skills；skill-workshop 与 compact 并行 | 删 workspace 文件；workshop tool 管 proposals；scanner **quarantine** 危险项 | **skill-workshop**：`agent_end` → regex+LLM reviewer → proposals → scanner → append/replace（auto/manual） | **8/9** — 缺 per-turn Recommend；Compact-skill 弱 |
| **Hermes** | `~/.hermes/skills/{name}/SKILL.md` + refs/scripts/assets；bundled manifest hash sync | System prompt **metadata index**；progressive disclosure 三层 | `skills_list` tool；`/<skill>` slash；CLI `--skills` session preload 全文 | · 全量 index 在 prompt（size limit）；**无** RRF | Body 经 `skill_view` 按需；index frozen 保 prefix cache | `skill_view(name, file_path?)`；prompt 鼓励使用中 patch | `ContextCompressor` prune+summarize；**无** invoked_skills | `skill_manage(delete)`；`_security_scan_skill` 写后扫描 | **最强 runtime**：nudge + `_spawn_background_review` → `skill_manage` create/patch/edit/delete；`skills_guard`；**无** proposal queue / read-before-write（issue 风险） | **8/9** — 缺 Recommend gate；Evolve 激进无硬门禁 |
| **GenericAgent** | **非 SKILL.md**：`memory/*_sop.md` + L1 index + L2 facts + L4 sessions | System 列 memory 目录；每 10 turn `get_global_memory()`；anchor prompt 仅最新 user msg | Agent 读 L1 index → `file_read` SOP；`working['related_sop']` 提示 | ◐ `file_access_stats.json` 弱频率 | Anchor 重建 working memory；SOP body 非常驻 | `file_read` 加载 SOP；plan mode 强制 plan.md | `compress_history_tags` 截断 thinking/tool；**无** skill 保护 | `file_patch` / 手动；`memory_cleanup_sop.md` | ◐ `start_long_term_update` 验证成功才写 L2/L3；`/morphling` SOP 结晶；**无** gate/proposal | **5/9** — 理念强（Mine→Evolve）；标准 skill 生命周期弱 |
| **OpenSquilla** | 6 层：EXTRA < BUNDLED < MANAGED < PERSONAL < PROJECT < WORKSPACE；proposals `~/.opensquilla/proposals/` | `SkillInjector`：full / **compact**（仅 name+location）/ budget truncate | Session snapshot v11；pipeline **`filter_skills` 每 turn** | **★ HybridRetriever** lexical+semantic RRF top-k(5)；pinned `always`/meta 绕过 | Compact injector = body offload；full 才带 description | `skill_view`；`meta_invoke` DAG；`skill_exec` CLI entry | Session compact；skills 块 **per-turn 可重建**（pipeline 重跑 filter）；history 持久 injection | `reject_proposal`；managed 文件级删除；hub quarantine | **★ 产品化**：`auto_propose` → gates.json → 4-gate + `runtime_e2e` judge → `accept_proposal` → MANAGED；Dream hook | **9/9** — 最全；MetaSkill 为 workflow 层扩展 |
| **ZeroClaw** | `~/.zeroclaw/workspace/skills/` SKILL.md/toml；open-skills repo sync；**zeroclaw-skills** registry（CI 结构扫描） | **Full** vs **Compact** injection mode；`always` 在 compact 下仍全文 | `load_skills_with_config` workspace scan | · 无 retriever | Compact：summary + on-demand read | Compact 读 location；`SkillToolHandler` placeholder→native tool | `auto_compact_history` + fact extraction；**无** invoked_skills | 用户删目录；hygiene cron 归档 memory | · **Audit only**（zip-bomb, traversal, injection patterns）；nightly **memory** 合并非 skill | **5/9** — 治理/Store 强；Evolve/Recommend 弱 |
| **Claude Rev** (oboard) | Multi-source：project/user/bundled/plugin `loadSkillsDir` | **三通道**：skill_listing attachment / Skill tool / **invoked_skills** post-compact | **★ 增量 listing**：`sentSkillNames` per agentId；resume 只发 delta | ◐ `skillUsageTracking` 7-day decay 排序 UI；EXPERIMENTAL_SKILL_SEARCH | Listing 仅 metadata；body 经 Skill tool | Skill tool + slash → `addInvokedSkill()` 注册 STATE | **★ `invoked_skills` attachment** survives compaction；per-skill + total budget；most-recent-first | 删 project skill；skillImprovement survey 选择性 apply | **skillImprovement** 每 5 turn → JSON patches → **Survey UI** gate；**skillify** 会话→新 skill | **8/9** — Compact/Evolve 领先；缺 formal proposal store |
| **TaiChu** | 17 canonical `skills/system/{name}/SKILL.md`；用户 runtime meta_data；session **不**扫 workspace | `<local/cloud_skills>` XML system；**每 turn user prefix** `# Available Skills`（cache-friendly） | Session `load_skills_from_dirs`；cloud `skill_catalog.json`；Toollery `before_prompt` filter | ◐ Toollery embedding search（optional）；**无** usage decay | Catalog 在 user prefix；body 在 ToolResult | **`load_skill`** + **runs_on** 端云路由 + `remote_delegation` | ❌ `compaction.rs` 纯 summarize；**无** invoked_skills reinject（**P0 缺口**） | · 无 agent CRUD；canonical 人工 curated | · 无 runtime evolve；roadmap proposals store | **5/9** — Store/Expose/Use/Discover 强；Compact/Evolve/Delete 缺口 |

---

## 2. 生命周期阶段定义（列说明）

| 列 | 含义 | 典型实现模式 |
|----|------|-------------|
| **Store** | 磁盘布局、多源优先级、managed/bundled/registry | OpenClaw 6 源 merge；OpenSquilla 6 层；Codex scope layers |
| **Expose** | 注入 prompt 的元数据形态与 token 预算 | Codex 2% budget；OpenClaw XML metadata；TaiChu user prefix |
| **Discover** | 模型如何知道有哪些 skill 存在 | Hermes `skills_list`；Claude 增量 attachment；OpenSquilla 每 turn pipeline |
| **Recommend** | 按 task/query/usage 筛选 top-k | OpenSquilla RRF ★；Codex implicit description match ◐；Claude decay ◐ |
| **Offload** | 从 context 移除 body，仅保留 metadata | 全员 progressive disclosure；OpenSquilla compact injector |
| **Use (Load)** | 拉取全文并执行 | `load_skill` / `skill_view` / read tool / `@mention` injection |
| **Compact** | 长会话压缩后 skill 是否存活 | **仅 Claude Rev** invoked_skills ★；TaiChu ❌ |
| **Delete** | 退役、归档、禁用 | Hermes `skill_manage(delete)`；OpenSquilla `reject_proposal` |
| **Evolve** | 轨迹→候选→评估→写入闭环 | OpenSquilla gates ★；Hermes CRUD ★；OpenClaw workshop ★ |
| **Lifecycle 完整度** | 九阶段中有明确实现的阶段数（满分 9） | OpenSquilla 9/9；TaiChu 5/9 |

---

## 3. 扩展列：Per-turn · Subagent · Scope · Governance

| 项目 | **Per-turn catalog** | **Subagent skills** | **Scope / Priority** | **Governance / Gate** |
|------|---------------------|---------------------|----------------------|----------------------|
| **Codex** | ◐ 仅 **mentioned** skills 注入当 turn | ★ child `turn_skills` 独立 enable 集；**不含** parent skills block | User/Repo/System/Admin scopes | Guardian JSON risk；TUI approval test |
| **OpenClaw** | ◐ snapshot 复用；watcher bump 才刷新 | ★ per-agent **skillFilter**；subagent 缩减 system prompt | 6 源 location precedence + agent visibility | skill-scanner quarantine；workshop pending/auto |
| **Hermes** | · index session-frozen；review 是 post-turn 异步 | ◐ delegate 隔离 context；**无** skill preload 参数 | 单主目录 `~/.hermes/skills` | `skills_guard` scan；**无** critical-skill lock（issue） |
| **GenericAgent** | · anchor + related_sop 提示 | · subprocess workers 非 skill bundle | memory/ 扁平 SOP tree | L0 SOP 协议；无 formal gate |
| **OpenSquilla** | **★ pipeline `filter_skills` 每 turn** | ◐ MetaOrchestrator DAG 组合；非 frontmatter preload | 6 层 + pinned always | **4-gate** + runtime_e2e + gates.json |
| **ZeroClaw** | · session 级 injection | ◐ SubAgentRegistry；**无** skill 参数 | workspace + registry sync | `skills/audit.rs`；registry **非** security boundary |
| **Claude Rev** | **★ 增量 skill_listing attachment** | **★ frontmatter `skills:[]` preload**；per-agent `sentSkillNames` | project/user/bundled/plugin | skillImprovement **Survey UI**；user apply |
| **TaiChu** | **★ `# Available Skills` user prefix 每 turn** | ❌ 子 session rescans canonical；**不继承** parent invoked | canonical + cloud catalog；**runs_on** 端云 | · 待建 trust_tier / proposal gates |

---

## 4. 按阶段横向排名（谁做得最好）

| 阶段 | 领先实现 | 次优 | TaiChu 现状 / 应借 |
|------|---------|------|-------------------|
| **Store** | OpenClaw（多源+priority+visibility） | OpenSquilla 6 层 + proposals | canonical 强；缺 user/workspace 多源 merge |
| **Expose** | Codex（budget+progressive disclosure 文档化） | TaiChu user prefix（cache-friendly） | 保留 user prefix；补 metadata budget |
| **Discover** | OpenSquilla（每 turn pipeline） | Claude Rev 增量 listing | Toollery filter ◐；补 delta listing |
| **Recommend** | **OpenSquilla RRF** | Codex implicit + Claude decay | Toollery embedding ◐ → 接 RRF |
| **Offload** | OpenClaw lazy + OpenSquilla compact injector | Codex per-turn mention-only | 已有 progressive disclosure |
| **Use** | TaiChu **runs_on** 端云 | Hermes skill_view + Codex implicit | **保留** load_skill wire |
| **Compact** | **Claude Rev invoked_skills** | OpenSquilla per-turn rebuild | **❌ P0** — 借 oboard |
| **Delete** | Hermes skill_manage + OpenSquilla reject | OpenClaw quarantine | 待建 agent CRUD + policy |
| **Evolve** | OpenSquilla gates + Hermes CRUD + OpenClaw workshop | Claude Rev survey UI | Candidate/PR 模式；不直改生产 |

---

## 5. 生命周期流水线覆盖（Claw-R1 × SkillRL 视角）

```text
Store → Expose → Discover → Recommend → Offload → Use → [Trace] → Compact → Delete → Evolve
                                              ↑
                                    Claw-R1 step trace / TaiChu interaction_log
                                              ↓
                                    GenericAgent Mine / Hermes review / OpenSquilla auto_propose
```

| 流水线段 | 最强片段组合 |
|---------|-------------|
| Trace | OpenClaw trajectory JSONL + TaiChu `interaction_log` |
| Mine | GenericAgent crystallize + SkillRL 思想 |
| Propose | Hermes `skill_manage` + OpenSquilla `proposals/` |
| Evaluate | OpenSquilla 4-gate + `runtime_e2e` |
| Publish | OpenSquilla `accept_proposal` + ZeroClaw audit |
| Runtime | Codex progressive disclosure + OpenClaw scope + TaiChu runs_on |
| Survive compact | **Claude Rev invoked_skills**（TaiChu P0） |

---

## 6. TaiChu 目标生命周期（九阶段目标态）

| 阶段 | 当前 | P0 | P1 | P2 |
|------|------|----|----|-----|
| Store | canonical + cloud | + workspace `/.taichu/skills` | 6 层 merge 对齐 OpenClaw | versioned manifest |
| Expose | user prefix + XML | + metadata budget cap | compact expose mode | |
| Discover | scan + Toollery | + incremental delta listing | | |
| Recommend | embedding ◐ | | RRF + pinned always | usage decay |
| Offload | progressive | 保持 | | |
| Use | load_skill ★ | 保持 runs_on | implicit trigger (Codex) | |
| Compact | ❌ | **InvokedSkillRegistry + reinject** | | |
| Delete | · | | skill_manage equivalent | reject/archive |
| Evolve | · | | proposals + gates (OpenSquilla) | background review (Hermes) w/ read-before-write |

Spec：[taichu-p0-skill-compaction-spec.md](taichu-p0-skill-compaction-spec.md) · 借鉴：[web-deep-taichu-borrowing-guide.md](web-deep-taichu-borrowing-guide.md)

---

## 7. 与旧表关系

| 文档 | 关系 |
|------|------|
| [skill-lifecycle-and-dynamic-loading-survey.md](skill-lifecycle-and-dynamic-loading-survey.md) | 本矩阵的 **逐仓长文** 证据来源 |
| [agent-skill-architecture-survey-matrix.md](agent-skill-architecture-survey-matrix.md) | **主调研仪器** — 165 维 × 7 大类 |
| [survey-reports/](survey-reports/) | 每仓 12 段调研报告 |
| [eight-repo-comprehensive-survey.md](eight-repo-comprehensive-survey.md) | 20 维度 + 流水线 8 段 |
| [web-deep-taichu-borrowing-guide.md](web-deep-taichu-borrowing-guide.md) §1 简表 | 已被本文 **取代/扩展** |

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-08 | 初版：九阶段 × 八项目主矩阵 + 扩展列 + TaiChu 目标态 |
| 2026-07-08 | 被 agent-skill-architecture-survey-matrix.md (165 dim) 吸纳为 condensed view |
