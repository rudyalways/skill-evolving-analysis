---
id: N2026-07-08-013
title: L3 深度源码分析 — 八仓 Skill 全生命周期（合并版）
date: 2026-07-08
tags: [L3-analysis, skill-lifecycle, self-evolution, comprehensive]
status: active
related: [N2026-07-08-012, N2026-07-08-010, N2026-07-08-011]
evidence_level: L3
---

# L3 深度源码分析 — 八仓 Skill 全生命周期

> **证据等级**：L3 — 核心模块全文精读（非全库逐行）。  
> **方法**：本机 clone + 子模块走读；`hermes-agent-self-evolution` / `zeroclaw-skills` 因网络未 clone，用 README Web 补证。  
> **维度**：Store → Expose → Discover → Recommend → Load → Per-turn → Offload → Compact → Delete → Evolve → Subagent

---

## 总览：谁在哪一层最强

| 能力层 | #1 | #2 | #3 |
|--------|----|----|-----|
| **在线 skill CRUD** | Hermes `skill_manage` | OpenSquilla accept | OpenClaw workshop |
| **候选→Gate→晋升** | OpenSquilla 5-gate | OpenClaw scanner+pending | — |
| **Per-turn catalog** | OpenSquilla pipeline | Claude Rev listing delta | TaiChu user prefix |
| **Per-turn body inject** | Codex `$mention` | Claude meta user msg | Hermes skill_view |
| **Compaction 保 skill** | Claude `invoked_skills` | — | — |
| **Subagent skill bundle** | Claude frontmatter preload | Codex child turn_skills | OpenSquilla meta DAG |
| **离线演化 (GEPA)** | hermes-self-evolution | — | — |
| **RL trace export** | OpenClaw trajectory | Hermes Atropos | — |
| **端云 skill 路由** | TaiChu `runs_on` | — | — |

---

# 1. Hermes Agent (+ Self-Evolution 生态)

**路径**：`oss/hermes-agent` | **L3 精读**：`skill_manager_tool.py`, `skills_tool.py`, `run_agent.py`, `skills_guard.py`, `delegate_tool.py`

## 生命周期

| 阶段 | 实现 | 证据 |
|------|------|------|
| **Store** | `~/.hermes/skills/` 唯一真相；bundled→sync；hub→quarantine→scan→install | `skills_sync.py:155-280`, `skills_hub.py:307-374` |
| **Expose** | `<available_skills>` index + `SKILLS_GUIDANCE` + slash `/skill-name` | `prompt_builder.py:525-742` |
| **Discover** | 三层 progressive：list metadata → view body → view reference | `skills_tool.py:719-1056` |
| **Recommend** | Prompt 驱动 + iteration nudge（非 embedding） | `prompt_builder.py:720-732`, `run_agent.py:9604-9610` |
| **Load** | `skill_view` / CLI `--skills` preload / slash 注入全文 | `cli.py:9101-9113`, `skill_commands.py:291-327` |
| **Per-turn** | Index session-frozen；`_iters_since_skill` 累计 | `run_agent.py:7464-7468`, `7244-7247` |
| **Offload** | 大 skill_view → `maybe_persist_tool_result`  spill 到沙箱文件 | `tool_result_storage.py:9-22` |
| **Compact** | 通用 history 压缩；**skill body 可被 summarize 掉**，需重调 skill_view | `context_compressor.py` |
| **Delete** | `skill_manage(delete)` → `shutil.rmtree`；sync 尊重用户删除 | `skill_manager_tool.py:455-472` |
| **Evolve** | ① inline patch ② nudge→`_spawn_background_review` ③ hub/bundled hash sync | `run_agent.py:1768-1896` |

## 自进化（在线）

```text
每 ~10 tool iterations 无 skill_manage
  → _spawn_background_review(review_skills=True)
  → fork quiet AIAgent + _SKILL_REVIEW_PROMPT
  → skill_manage create/edit/patch → ~/.hermes/skills/
  → skills_guard scan → clear_skills_system_prompt_cache
```

## 自进化（离线）— `hermes-agent-self-evolution` [Web L0]

```text
Read SKILL.md → synthetic/sessiondb eval dataset
  → GEPA optimizer + execution traces
  → candidate variants
  → gates: pytest 100% + size ≤15KB + semantic preservation
  → Best variant → PR（永不 direct commit）
```

Phase 1 skill 文件已实现；Phase 2-5 tool desc / system prompt / code / continuous 计划中。

## Subagent

- `delegate_task`：**不 block** skills toolset
- **无 skill preload**；child 仅 `ephemeral_system_prompt`（goal/context）
- **已知 bug**：background review agent **未继承** parent `enabled_toolsets`（`run_agent.py:1822-1828`）

## 安全

`skills_guard.py`：builtin/trusted/community/agent-created 四级；80+ regex + 结构检查。

## TaiChu 借鉴

| 借什么 | 怎么落 |
|--------|--------|
| `skill_manage` CRUD API | `add_tool_factory` 注册 Rust tool |
| `_spawn_background_review` | post-turn async task |
| `skills_guard` | community skill 上设备前扫描 |
| GEPA 离线 PR | Phase 2：`evolution/` 子模块，只开 PR 不改 canonical |

---

# 2. OpenSquilla

**路径**：`oss/opensquilla` | **L3 精读**：`proposals_lib.py`, `skills_filter.py`, `injector.py`, `auto_propose.py`, `runtime_e2e.py`, `meta/orchestrator.py`

## 生命周期

| 阶段 | 实现 |
|------|------|
| **Store** | BUNDLED → MANAGED (`~/.opensquilla/skills/`) + PROPOSALS (`proposals/<8-hex>/`) |
| **Expose** | `SkillInjector` → `<available_skills>` XML（**仅 catalog**） |
| **Discover** | 每 turn pipeline `filter_skills` |
| **Recommend** | **HybridRetriever** lexical+semantic RRF，`top_k` 默认 5；`always`+meta_match **pinned 绕过检索** |
| **Load** | `skill_view(name)` 按需全文；`meta_invoke` 跑 DAG |
| **Per-turn** | **最强**：`meta_resolution` → gate → retrieve → inject，每 turn 重跑 |
| **Offload** | compact injector 即 offload body |
| **Compact** | skills 块 per-turn 可重建；history 持久 skills context |
| **Delete** | `reject_proposal` rmtree；`disable_auto_enabled_skill` 退回 proposals |
| **Evolve** | **最完整 gate 管道**（见下） |

## 自进化闭环（源码证实）

```text
collect_invoked_skills(turn_segments)     # runtime.py:250
  ↓
DecisionEntry.skills_invoked → decisions.jsonl
  ↓
aggregate_co_occurrences (skill 共现链)
  ↓
auto_propose (cron | dream hook)
  ↓
MetaOrchestrator(meta-skill-creator)
  ↓
proposals/<id>/SKILL.md + gates.json
  ↓
5 gates: lint | smoke | collision | risk | acceptance_compare | runtime_e2e
  ↓
accept_proposal → MANAGED (或 auto_enable if low risk)
```

`runtime_e2e`：candidate meta route vs **no-meta baseline** + LLM judge。

## Subagent / MetaSkill

- **MetaOrchestrator DAG**：`agent` | `skill_exec` | `tool_call` | `llm_classify` | `user_input`
- 子 agent **strip `meta_invoke`** 防嵌套
- `yield_skill_view_preface` 在 sub-agent step 前调真实 `skill_view`
- **不是** frontmatter preload list — 是 **组合编排**

## 设计不变量

1. Catalog ≠ content（injector vs skill_view）
2. Meta trigger 是 **soft hint**，LLM 决定 `meta_invoke`
3. Degraded smoke **blocks auto-enable**
4. `OPENSQUILLA_AUTO_PROPOSE_DISABLED=1` kill switch

## TaiChu 借鉴

| 借什么 | 怎么落 |
|--------|--------|
| `proposals_lib` 原子写 + gates.json | `~/.taichu/proposals/` |
| `skills_filter` pinned + RRF | 扩展 Toollery `decide` |
| `runtime_e2e` judge | skill 晋升前 A/B |
| MetaSkill DAG | P3，单 skill 生命周期稳定后 |

---

# 3. OpenClaw

**路径**：`oss/openclaw` | **L3 精读**：`skill-workshop/`, `skills/workspace.ts`, `agent-filter.ts`, `refresh-state.ts`, `trajectory/`

## 生命周期

| 阶段 | 实现 |
|------|------|
| **Store** | 6 源 merge，workspace 最高优先级 |
| **Expose** | XML catalog + "Use **read** tool to load" |
| **Discover** | chokidar + snapshot version |
| **Recommend** | 字母序 + char budget；**无 embedding** |
| **Load** | Lazy read `SKILL.md` |
| **Per-turn** | `ensureSkillSnapshot`：version 或 skillFilter 变则 refresh |
| **Offload** | Body 从未进 prompt（by design） |
| **Compact** | compaction-safeguard 总结对话；**不**保 invoked skills |
| **Delete** | 用户删文件；workshop quarantine |
| **Evolve** | **skill-workshop**（非仅 marketplace） |

## Skill Workshop 三入口

| 入口 | 触发 |
|------|------|
| Heuristic | `agent_end` success → regex 用户纠正语 |
| LLM reviewer | 15 turns 或 8 tool calls → 隔离 sub-run（tools disabled） |
| `skill_workshop` tool | suggest/apply/reject |

写入 **仅** `<workspace>/skills`；scanner critical → quarantine；apply 后 `bumpSkillsSnapshotVersion`。

## Subagent

- **无 parent→child skill 继承**
- `resolveEffectiveAgentSkillFilter(targetAgentId)` 决定 child catalog
- 跨 agent spawn 用 **target workspace**，非 caller workspace

## Trajectory（RL 就绪）

`trace.metadata` 含 `snapshotVersion`, `skillFilter`, `skillsPrompt`, entries — NDJSON 默认开启。

## Dreaming vs Skills

| | Skills | Dreaming |
|---|--------|----------|
| 内容 | 程序性 workflow | 事实/偏好 |
| 存储 | SKILL.md | MEMORY.md |
| 晋升 | scanner + approval | minScore + recall 阈值 |

## TaiChu 借鉴

| 借什么 | 怎么落 |
|--------|--------|
| snapshot version + watcher | skill catalog 版本号 |
| workshop proposal→quarantine→apply | 进化侧车 |
| trajectory schema | interaction_log  enrich |

---

# 4. Claude Code Rev (oboard)

**路径**：`oss/experimental/claude-code-rev` | **L3 精读**：`compact.ts`, `skillImprovement.ts`, `state.ts`, `runAgent.ts`, `attachments.ts`

## 生命周期亮点

| 阶段 | 实现 |
|------|------|
| **Per-turn listing** | `getSkillListingAttachments` — per-`agentId` delta，initial vs dynamic |
| **Invocation** | `addInvokedSkill` → composite key `${agentId}:${skillName}` |
| **Inject band** | Skill content 作为 **meta user message**（非 tool result） |
| **Compact** | **`invoked_skills` attachment** — 5K/skill, 25K total, most-recent-first |
| **Resume** | `restoreSkillStateFromMessages` 从 transcript 恢复 registry |
| **Evolve** | `skillImprovement` 每 5 user turns + survey UI gate |
| **Ranking** | `skillUsageTracking` 7-day half-life decay |

## Subagent preload

```typescript
// runAgent.ts:577-646
agentDefinition.skills ?? []  → 并发 load → initialMessages meta user
```

**Gap**：preload 不一定调用 `addInvokedSkill` — compact 保护可能不覆盖 preload-only。

## TaiChu P0（~300-500 LOC）

1. `InvokedSkillRegistry` in `agent-session`
2. `load_skill` success → `record_invoked_skill`
3. `compaction.rs` post-summarize → reinject attachment
4. `ChildSessionSpec.skills: Vec<String>` preload

---

# 5. TaiChu（私有）

**路径**：`drafts/zk/TaiChu` | **L3 精读**：`load_skill.rs`, `compaction.rs`, `session/mod.rs`, `tool_search_bridge.rs`, `api/mod.rs`, `manager.rs`

## 已有优势

- **`runs_on` + `remote_delegation`** — 八仓最全端云路由
- **Per-turn `# Available Skills`** user prefix — 不 bust system cache
- **`transform_context`** — turn_reminder + skills + NLU
- **Toollery `before_prompt`** — `skill_filter` per turn
- **`load_skill` 双维度 wire** — LLM snake_case / device PascalCase

## 关键缺口（文档已承认）

```64:66:drafts/zk/TaiChu/docs/capabilities/context-and-skills.md
load_skill 结果作为普通 ToolResult 进入会话，compaction 后可能被摘要或截断
```

- 无 `InvokedSkillRegistry`
- 无 post-compact reinjection
- 无 `profile.skills` child preload
- 无 skill evolution runtime

## 真实接缝（非 hook_chain / extra_tool_factories）

| 接缝 | 文件 |
|------|------|
| Per-turn inject | `SessionOptions.transform_context` |
| Per-turn filter | `set_skill_name_filter` + Toollery |
| Tool 注册 | `Runtime::add_tool_factory` |
| Trace | `interaction_log` JSONL |
| Compact | `compaction.rs` |

---

# 6. Codex

**L3 精读**：`core-skills/manager.rs`, `injection.rs`, `core/src/skills.rs`, `hook_runtime.rs`

- **Per-turn**：仅 **explicit `$skill-name`** 注入全文
- **Implicit**：shell 命令匹配 skill script path → telemetry
- **Subagent**：`SubagentStart/Stop` hooks；child **不含** parent skills instructions（by design）
- **Evolve**：无；filesystem 人工管理
- **强项**：typed hooks、Guardian、config-layer skill cache

---

# 7. GenericAgent

**L3 精读**：`ga.py`, `memory_management_sop.md`, `morphling_sop.md`, `reflect/scheduler.py`

- **Skill = L3 SOP**，非 SKILL.md
- **_axiom**：「No Execution, No Memory」
- **Per-turn**：anchor prompt 重建 working memory；每 10 turn 注入 L1 index
- **Evolve**：`start_long_term_update` + scheduler + morphling/Goal Hive
- **治理最弱**：无 proposal/gate/version
- **哲学最强**：适合借 L0 SOP 协议，**不可**照搬全自动固化

---

# 8. ZeroClaw

**L3 精读**：`skills/mod.rs`, `audit.rs`, `consolidation.rs`

- **Full vs Compact** injection mode（compact = lazy read）
- **`always`** flag 在 compact 下仍注入全文
- **audit.rs**：symlink/zip-bomb/prompt-injection 静态扫描
- **consolidation cron** 3AM — **memory only**，不改 skill 文件
- **zeroclaw-skills** registry 仓未 clone（DNS 失败）

---

# 9. OpenClaw-RL（独立仓）

**路径**：`oss/openclaw-rl` | **角色**：conversation feedback → trajectories → GRPO/OPD

- **不写 SKILL.md**
- 与 openclaw `skill-workshop` **正交**
- TaiChu 若做 SkillRL：trajectory 接缝在 interaction_log + OpenClaw-RL plugin

---

# 10. 跨仓对比矩阵（L3）

## Per-turn / Dynamic / Subagent

| 项目 | Per-turn catalog | Dynamic body | Subagent skills |
|------|:----------------:|:------------:|:---------------:|
| OpenSquilla | ★★★ pipeline+RRF | skill_view | Meta DAG 组合 |
| Claude Rev | ★★★ listing delta | Skill tool/meta msg | ★★ frontmatter preload |
| TaiChu | ★★★ user prefix | load_skill | ❌ rescans only |
| Codex | ★★ $mention only | per-turn inject | child turn_skills 独立 |
| OpenClaw | ★★ snapshot refresh | read tool lazy | agent skillFilter |
| Hermes | ★ session frozen | skill_view | delegate 无 preload |
| ZeroClaw | ★ session | compact→read | spawn 无 skill param |
| GenericAgent | · | file_read SOP | subprocess BBS |

## Compact 保 skill

| 项目 | 机制 |
|------|------|
| **Claude Rev** | `invoked_skills` attachment 25K budget |
| Hermes | 无 — 重调 skill_view |
| OpenSquilla | per-turn 重建 catalog |
| OpenClaw | lazy catalog 仍在 snapshot |
| TaiChu | **❌ ToolResult 可被 summarize** |
| Codex | 未 mention 的不注入 |
| 其他 | 无专门机制 |

## 自进化闭环完整度

| 项目 | Trace | Candidate | Eval | Deploy | Online metrics |
|------|:-----:|:---------:|:----:|:------:|:--------------:|
| OpenSquilla | ★ decision log | ★ proposals | ★ 5-gate+E2E | ★ accept | trigger_accuracy |
| Hermes online | ★ JSONL | ◐ agent create | ◐ guard | ★ skill_manage | · |
| Hermes offline | sessiondb | ★ GEPA | ★ pytest+size | PR only | · |
| OpenClaw workshop | ★ trajectory | ★ store | ◐ scanner | apply/quarantine | qa-lab |
| Claude Rev | session | ◐ JSON patches | survey UI | user apply | ★ usage decay |
| GenericAgent | L4 logs | ◐ L3 SOP | L0 protocol | file_patch | access stats |
| TaiChu | ◐ interaction_log | ❌ | ❌ | ❌ | ❌ |

---

# 11. TaiChu 推荐架构（L3 定稿）

```text
┌─────────────────────────────────────────────────────────────┐
│  EXISTING: interaction_log + transform_context + load_skill │
│           + Toollery decide + runs_on routing                │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  P0: InvokedSkillRegistry (Claude Rev)                       │
│      compaction reinject + resume restore                      │
│      ChildSessionSpec.skills preload                           │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  P1: skill_manage tool (Hermes) + post-turn ReviewAgent      │
│      proposals/ + gates.json (OpenSquilla)                     │
│      skills_guard / audit (Hermes + ZeroClaw)                  │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  P2: HybridRetriever top-k (OpenSquilla) via Toollery        │
│      usage decay ranking (Claude Rev)                          │
│      trajectory schema enrich (OpenClaw)                       │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  P3: MetaSkill DAG (OpenSquilla)                             │
│      GEPA offline PR (hermes-self-evolution)                   │
│      OpenClaw-RL trajectory export (SkillRL 实验)            │
└─────────────────────────────────────────────────────────────┘
```

**原则**：Skill = 软件资产。在线只写 **proposals**；canonical 晋升需 **gate**；离线 GEPA 只开 **PR**。

---

# 12. 分仓 L3 详文索引

| 仓库 | 独立 L3 章节位置 |
|------|-----------------|
| Hermes | 本文 §1 + subagent report `289a5d5b` |
| OpenSquilla | 本文 §2 + subagent report `704b2caf` |
| OpenClaw | 本文 §3 + subagent report `a8c9c500` |
| Claude Rev + TaiChu | 本文 §4-5 + subagent report `ca91a057` |
| Codex / GA / ZeroClaw | 本文 §6-8 + subagent report `56b9de73` |

完整子报告可请求导出为 `notes/synthesis/l3/{repo}.md` 分拆文件。

---

# 13. 待 L4 / 未验证项

| 项 | 状态 |
|----|------|
| `hermes-agent-self-evolution` 源码走读 | 仅 README Web |
| `zeroclaw-skills` registry schema | clone 失败 |
| OpenClaw-RL training loop 全读 | 仅 README |
| Hermes background review toolset bug | L3 已记录，待 fix 验证 |
| Claude preload vs addInvokedSkill gap | L3 已记录 |
| TaiChu P0 实现 | 设计完成，未编码 |

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-08 | L3 合并版：四路 subagent 深读 + Web GEPA 补证 |
