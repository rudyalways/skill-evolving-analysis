---
id: N2026-07-08-010
title: 八仓库 Skill 生命周期 + 动态加载 + 自进化 源码对照
date: 2026-07-08
tags: [skill-lifecycle, per-turn-skills, subagent-skills, self-evolution, taichu-borrow]
status: active
related: [N2026-07-08-009, N2026-07-08-008]
---

# Skill 生命周期 + 动态加载 + 自进化 — 八仓库源码对照

> 基于本机源码逐项核对，非 README 摘要。  
> 重点回答：**per-turn skill**、**dynamic loading**、**subagent complementary skills**、**自进化**、**TaiChu 可借鉴项**。

---

## 速查：谁支持什么？

> **完整生命周期矩阵**（Store / Expose / Discover / Recommend / Offload / Use / Compact / Delete / Evolve）：**[skill-lifecycle-full-matrix.md](skill-lifecycle-full-matrix.md)**  
> **165 维架构调研矩阵**：**[agent-skill-architecture-survey-matrix.md](agent-skill-architecture-survey-matrix.md)**

| 能力 | OpenClaw | Hermes | Codex | OpenSquilla | GenericAgent | ZeroClaw | Claude Rev | TaiChu |
|------|:--------:|:------:|:-----:|:-----------:|:------------:|:--------:|:----------:|:------:|
| **Per-turn skill 列表变化** | ◐ 增量 attachment 式 | · | ◐ turn 注入 | **★** pipeline 每 turn | · | · | **★** 增量 listing | **★** user prefix |
| **Dynamic body load** | ★ read tool | ★ skill_view | ★ @mention 注入 | ★ skill_view | ★ file_read SOP | ★ read file | ★ Skill tool | ★ load_skill |
| **Per-turn 检索/推荐** | · | · | · | **★** RRF top-k | · | · | ◐ skill search | ◐ Toollery |
| **Subagent 专属 skills** | ★ agent skillFilter | ◐ preload CLI | ★ child turn_skills | ◐ meta DAG 子步 | ◐ subprocess | ◐ spawn | **★** frontmatter preload | · 仅 rescans |
| **Compaction 保 skill** | ◐ post-compact context | ◐ compressor | ◐ compact hooks | ◐ history 持久 skills ctx | · | ◐ auto_compact | **★** invoked_skills | **❌ 缺口** |
| **自进化闭环** | ★ skill-workshop | ★ skill_manage+review | · | ★ proposals+auto_propose | ◐ L3 SOP 结晶 | · | ★ skillImprovement | · |

图例：★ 明确代码路径 | ◐ 部分 | · 无 | ❌ 已知 bug/缺口

---

## 统一生命周期模型（本文用词）

```text
Store → Expose → Discover → Recommend → Load/Use → Offload → Compact → Delete → Evolve
```

| 阶段 | 含义 |
|------|------|
| **Store** | 磁盘布局、层级、managed vs bundled |
| **Expose** | 注入 system/user prompt 的元数据 |
| **Discover** | 模型如何知道有哪些 skill |
| **Recommend** | 按 query/usage 筛选 top-k |
| **Load/Use** | 拉取全文并执行 |
| **Offload** | 从 context 移除/仅保留 metadata |
| **Compact** | 长会话压缩后 skill 是否存活 |
| **Delete** | 退役/移除 |
| **Evolve** | 自进化（轨迹→候选→gate→写入） |

---

# 1. OpenClaw

**路径**：`/Users/maybewu/Documents/Projects/oss/openclaw`

### Store
6 源 merge，后者覆盖同名：`extra < bundled < managed < ~/.agents/skills < project/.agents/skills < workspace/skills`（`src/agents/skills/workspace.ts:579-597`）。Managed 在 `~/.openclaw/skills`（CONFIG_DIR）。

### Expose
- Prompt 仅 **metadata**（name/description/location XML），指令："Use the **read tool** to load a skill's file"（`skill-contract.ts:44-50`）。
- **Compact 路径**：`~/` 前缀压缩 location 省 token（`workspace.ts:68-85`）。
- 预算：`maxSkillsInPrompt=150`，`maxSkillsPromptChars=18000`；超限 → compact XML（去 description）→ binary search 截断（`workspace.ts`）。

### Discover
- Session 启动 scan + **snapshot version**（`refresh-state.ts`）；chokidar 监听变更。
- **Per-agent skillFilter**：`resolveEffectiveAgentSkillFilter()` — 配置 `agents.list[].skills` 白名单（`agent-filter.ts:24-36`）。

### Recommend
- **无 embedding 排序**；merge 后按字母序，再 count/char budget 截断。
- Memory hybrid search **不**用于 skills。

### Load / Use
- **Lazy**：模型用 read tool 读 `SKILL.md`。
- `disableModelInvocation` frontmatter 可隐藏于 catalog。

### Per-turn / Dynamic
- **Snapshot 缓存**：`resolveSkillsPromptForRun()` 复用 snapshot prompt，非每 turn 重扫（`workspace.ts`）。
- **Subagent**：继承 agent skillFilter + 独立 session snapshot（`cron/isolated-agent/skills-snapshot.ts` 版本校验）。
- 非严格 "每 turn 换 skill 列表"；靠 snapshot 版本 bump 触发刷新。

### Offload
- Body 从未进 prompt（lazy 设计即 offload）。

### Compact
- **compaction-safeguard** 总结对话，**不**专门保留 invoked skills（与 Claude Rev 不同）。
- Skill-workshop 在 `agent_end` 捕获轨迹写 skill，与 compact 并行。

### Delete
- 用户删 workspace 文件；skill-workshop `skill_workshop` tool 可管理 proposals。
- Scanner **quarantine** 危险 proposal（`workshop.ts`）。

### Evolve（自进化）
**extensions/skill-workshop/** — 最完整 OpenClaw 进化路径：

| 机制 | 代码 |
|------|------|
| 触发 | `agent_end` hook，成功 run 后（`index.ts:48-52`） |
| 启发式 | `createProposalFromMessages()` regex 信号（`signals.ts`） |
| LLM 审查 | `reviewTranscriptForProposal()` 独立 reviewer session（`reviewer.ts`） |
| 存储 | proposals：`pending/applied/quarantined`（`store.ts`） |
| 写入 | `create/append/replace` + atomic temp→rename（`skills.ts`） |
| Gate | `scanSkillContent()` critical → quarantine（`workshop.ts:54-61`） |
| 自动合并 | `approvalPolicy: "auto"` 时直接 `applyProposalToWorkspace` |

### Subagent complementary skills
- **Per-agent skillFilter** 配置不同 skill 集合（`agent-filter.ts`）。
- Subagent 用缩减 system prompt（`subagent-system-prompt.ts`），非 frontmatter `skills:` 预加载。
- 无 "父 session invoked + 子 agent 专属" 组合模型。

### 其他创新
- Trajectory JSONL `openclaw-trajectory`（RL 数据出口）。
- Context engine `assemble/afterTurn/compact` 插件 API。
- Plugin harness 可替换 Pi runtime。

### TaiChu 可借鉴
1. **Lazy catalog + read/load_skill** — 已有 load_skill，可对齐 XML 格式与 home path 压缩。
2. **skill-workshop 模式** — `agent_end` → proposal store → scanner → apply；落 Taichu compaction 之后。
3. **Per-agent skillFilter** — 映射 TaiChu subagent profile + Toollery filter。
4. **Trajectory export** — interaction JSONL 已有，可对齐 schema。

---

# 2. Hermes Agent

**路径**：`/Users/maybewu/Documents/Projects/oss/hermes-agent`

### Store
`~/.hermes/skills/{name}/SKILL.md` + references/templates/scripts/assets（`skill_manager_tool.py:22-32`）。Bundled 经 `skills_sync.py` manifest hash 同步，保留用户编辑。

### Expose
- System prompt：`build_skills_system_prompt()` 注入 **metadata index**（`prompt_builder.py`）。
- Progressive disclosure 三层：list metadata → view body → view references。

### Discover
- `skills_list` tool；CLI/Gateway `/skill-name` slash（`skill_commands.py`）。
- Session **preload**：`--skills hermes-agent-dev,github-auth` 启动时预加载全文（`cli.py:8999,9016`）。

### Recommend
- 无 RRF/embedding；全量 index 在 prompt（有 size limit）。

### Load / Use
- `skill_view(name, file_path?)` 按需加载（`skills_tool.py:52-54`）。
- Prompt 鼓励使用中 patch 过时 skill（`prompt_builder.py:164-171`）。

### Per-turn / Dynamic
- **非 per-turn 换 catalog**；index 在 session 前缀（frozen snapshot 保 cache）。
- **Background skill review** 每 ~10 tool iterations 触发（`run_agent.py:9604-9610`），fork quiet agent 写 skill — **turn 后异步**，非 prompt 内动态换 skill。

### Offload
- Body 通过 skill_view 按需；不在 prefix 常驻。

### Compact
- `ContextCompressor`  prune tool outputs + LLM summarize；**无 invoked_skills 附件**。
- Frozen memory snapshot 与 skills index 分离。

### Delete
- `skill_manage(action="delete")` 移除用户 skill（`skill_manager_tool.py`）。
- `_security_scan_skill()` 写后扫描。

### Evolve（自进化）
**最强 runtime CRUD + 软闭环**：

```python
# run_agent.py:1768-1776 — 后台 review prompt
"If a relevant skill already exists, update it with what you learned.
 Otherwise, create a new skill if the approach is reusable."
```

| 阶段 | 实现 |
|------|------|
| 触发 | `_skill_nudge_interval` + post-turn `_spawn_background_review` |
| 检测 | LLM 判断 trial-and-error / 用户期望 |
| 写入 | `skill_manage` create/edit/patch/delete/write_file |
| Gate | `skills_guard` 安全扫描 |
| 合并 | patch 级局部更新，无 proposal queue |

### Subagent complementary skills
- `delegate_task` .spawn child AIAgent，**隔离 context**，父见 summary（`delegate_tool.py`）。
- **无** `load_skills=[]` 参数；子 agent 继承 toolsets 子集，skills 靠同一 index + skill_view。
- CLI `--skills` preload 是 **session 级**，非 delegate 级。

### 其他创新
- Frozen MEMORY.md snapshot + API-time injection（prefix cache）。
- FTS5 session_search + 辅助 LLM 摘要跨 session 召回。
- Atropos RL env + `rl_training_tool` — skill 轨迹可进训练管线。

### TaiChu 可借鉴
1. **P0**：`_spawn_background_review` + `skill_manage` 移植为 Rust tool + async task。
2. **Frozen catalog + load_skill 按需** — 与 TaiChu A-system user prefix 兼容。
3. **skills_guard** — community skill 上设备前扫描。
4. **RL**：若做 SkillRL，Hermes Atropos 接口最直接。

---

# 3. Codex (OpenAI)

**路径**：`/Users/maybewu/Documents/Projects/oss/codex`

### Store
Scopes：User / Repo / System / Admin + plugin roots（`core-skills/loader.rs:107-125`）。Filesystem 为真相。

### Expose
- `AvailableSkillsInstructions` metadata block（`available_skills_instructions.rs`）。
- **Metadata budget** — 超限截断（`core-skills/manager.rs`）。

### Discover
- File watcher 刷新；TUI skill toggle/approval。
- `@skill-name` explicit mention（`mention_syntax::TOOL_MENTION_SIGIL`）。

### Recommend
- 无 retrieval ranking。

### Load / Use
- **Explicit**：`build_skill_injections()` 读全文注入 `<skill>` user fragment（`injection.rs:57-80`）。
- **Implicit**：shell 命令匹配 skill → `maybe_emit_implicit_skill_invocation()`（`core/src/skills.rs:48-95`）。

### Per-turn / Dynamic
- **Per-turn injection**：仅 **mentioned** skills 注入当 turn user messages（`injection.rs`）。
- `SkillsManager` 按 cwd + config-layer key 缓存。
- **Child session**：`turn_skills.outcome.is_skill_enabled()` — 子 thread 独立 skill 开关（`session/tests.rs:4337`）。

### Offload
- 未 mention 的 skill 不进当 turn context。

### Compact
- Pre/post compact hooks（`hook_runtime.rs`）；**无 invoked_skills 专用附件**。
- `ThreadMemoryMode::Polluted` 标记外部 context 污染 memory。

### Delete
- 用户删文件；TUI `write_skill_enabled` 配置切换。

### Evolve（自进化）
- **刻意不做**。Sample `skill-creator/SKILL.md` 指导人工创建 + subagent 验证。
- Memories 2-phase distill 服务 **memory**，非 skill library。

### Subagent complementary skills
- MultiAgent v2 spawn；child **不含** parent skills instructions（测试断言 `!body_contains_text("<skills_instructions>")`，`subagent_notifications.rs:1180`）。
- Child 可 **enable 不同 skill subset** via `turn_skills`（`core-skills/manager_tests.rs:805`）。
- 子 agent 技能集与父 ** deliberately decoupled**。

### 其他创新
- **Guardian** 二级审批 JSON risk assessment。
- Typed hooks：block / rewrite / inject additional context。
- Tool dispatch trace for rollout debugging。

### TaiChu 可借鉴
1. **Per-turn 仅注入 invoked/mentioned skills** — 减 token。
2. **Implicit invocation** — CLI 命令 pattern → 自动 load_skill。
3. **Child turn_skills 独立 enable 集** — subagent profile.skills + filter。
4. **Hook runtime** — Agent Hook Gateway 设计可对齐。

---

# 4. OpenSquilla

**路径**：`/Users/maybewu/Documents/Projects/oss/opensquilla`

### Store
6 层：`EXTRA < BUNDLED < MANAGED < PERSONAL < PROJECT < WORKSPACE`（`skills/loader.py`）。Proposals 在 `~/.opensquilla/proposals/{8-hex}/`；accept 后 → `~/.opensquilla/skills/`。

### Expose
`SkillInjector`：`inject_full` / `inject_compact` / budget truncate（`skills/injector.py`）。Compact 模式：**仅 name+location**，正文靠 `skill_view`。

### Discover
- Session 加载全量 snapshot（schema v11 cache）。
- Pipeline step `filter_skills` **每 turn 运行**（`engine/steps/skills_filter.py:107`）。

### Recommend（★ 最强）
当 `filter_enabled=True`：
- **HybridRetriever**：lexical + semantic RRF，`top_k` 默认 5（`skills_filter.py:220-225`）。
- **Pinned skills**：`always`、meta_match、pinned_skills **绕过检索**（:162-188）。
- 发布 `filtered_skill_ids` 到 decision log 可观测。

### Load / Use
- `skill_view(name)` 加载正文。
- **Meta-skills**：`meta_invoke(name)` 跑 DAG，**不**对 meta 调 skill_view（`injector.py:40-49`）。
- `skill_exec` entrypoint — CLI skill 无 sub-agent（meta orchestrator）。

### Per-turn / Dynamic（★）
**明确 per-turn pipeline**：
1. Gate（eligibility, requires_tools, disabled）
2. Retrieve top-k（可选）
3. Inject 到 system 或 **user_message**（`injection_mode`，:255-260）
4. Skills context **persisted per-turn in history** for KV-cache（agent.py ~1862-1868，subagent 报告）

Subagent：`collect_invoked_skills(turn_segments)` 记录本 turn 实际 skill_view 解析名（`runtime.py:250`）。

### Offload
- Compact injector 即 offload body；full 模式才带 description。

### Compact
- Session compaction；skills 块设计为 **per-turn 可重建**（pipeline 重跑 filter）。
- 无 Claude 式 invoked_skills attachment；靠 **history 中 persisted skills injection**。

### Delete
- `reject_proposal()`；managed skill 文件级删除。
- Hub install quarantine scan。

### Evolve（自进化）（★ 产品化最完整）
| 阶段 | 实现 |
|------|------|
| 候选 | `auto_propose` 决策日志共现链 → meta-skill-creator DAG |
| 存储 | `atomic_write_proposal()` + gates.json |
| 评估 | 4-gate：`evaluate_proposal_gates` + `runtime_e2e` meta vs baseline judge |
| 晋升 | `accept_proposal()` → MANAGED（gates 未过 refuse） |
| Dream 联动 | Dream 完成后 hook 触发 auto_propose |

### Subagent complementary skills
- **MetaOrchestrator DAG**：一步 `skill_exec`、一步 `agent`、一步 `tool_call` — **组合多 skill 工作流**（`meta/orchestrator.py`）。
- 子 agent 一步一 skill，非 frontmatter preload list。
- Meta-skill **manual-only** 默认（`/meta`）；`auto_trigger=true` 才进 catalog。

### 其他创新
- Decision log + `skills_invoked` 遥测。
- Squilla Router LightGBM 模型路由（非 skill RL）。
- `eval_prompts` in SkillSpec 回归夹具。

### TaiChu 可借鉴
1. **P1**：`proposals_lib` + gates.json 整套。
2. **Per-turn HybridRetriever + pinned** — Toollery `before_prompt` 已有 filter hook（`tool_search_bridge.rs:370-373`），可接 embedding。
3. **collect_invoked_skills** — interaction log 已有，补结构化字段。
4. **runtime_e2e judge** — skill 晋升前 A/B meta vs baseline。
5. **injection_mode=user_message** — 与 TaiChu `# Available Skills` user prefix **同哲学**。

---

# 5. GenericAgent

**路径**：`/Users/maybewu/Documents/Projects/oss/genericagent`

### Store
**非 SKILL.md** — `memory/*_sop.md` + L1 index + L2 facts + L4 sessions（`memory/memory_management_sop.md`）。

### Expose
- System prompt 列 memory 目录；`get_global_memory()` 每 10 turn 注入（`ga.py:569`）。
- **Anchor prompt** 重建 working memory，**仅最新 user message 送 API**（`ga.py:539-549`）。

### Discover
- Agent 读 L1 index → `file_read` 相关 SOP。
- `working['related_sop']` 提示重读（`ga.py:547`）。

### Recommend
- `file_access_stats.json` 记录访问频率（弱 ranking）。
- 无 embedding。

### Load / Use
- `file_read(path)` 加载 SOP 全文。
- Plan mode 强制读 plan.md checkpoint。

### Per-turn / Dynamic
- **无 skill catalog per turn**；靠 anchor + related_sop 提示。
- Reflect scheduler 外部脚本周期性注入任务（`reflect/scheduler.py`）。

### Compact
- `compress_history_tags` 截断旧 message 中 thinking/tool blocks（`llmcore.py`）。
- **无 skill 保护**。

### Delete
- `file_patch` / 手动删 SOP；`memory_cleanup_sop.md` 指南。

### Evolve（自进化）
- **`start_long_term_update`**：agent 自触发，仅 **验证成功** 的信息写 L2/L3（`ga.py:508-523`）。
- **`/morphling`**：Goal Hive 长程 SOP 结晶（`morphling_sop.md`）。
- **无** proposal/gate；哲学是 **SOP-as-skill**。

### Subagent
- Agent team BBS + checklist subprocess workers — **非** skill preload。

### TaiChu 可借鉴
1. **L0 memory_management_sop** — skill 更新协议文档。
2. **Action-verified axiom** — 只写验证成功的 skill 条目。
3. **Reflect scheduler** — HarmonyOS 健康检查 cron。
4. **Anchor prompt** — 降 API history 成本（移动端友好）。

---

# 6. ZeroClaw

**路径**：`/Users/maybewu/Documents/Projects/oss/zeroclaw`

### Store
`~/.zeroclaw/workspace/skills/{name}/SKILL.md` 或 `SKILL.toml`；open-skills repo 周期 sync（`skills/mod.rs`）。

### Expose
`prompt_injection_mode`：**Full**（预加载 instructions+tools）vs **Compact**（summary + on-demand read）（`skills/mod.rs:800-814`）。`always` flag 在 compact 下仍注入全文。

### Discover
- `load_skills_with_config` scan workspace。
- 无 per-turn retriever。

### Recommend
- 无。

### Load / Use
- Compact：read skill file at `location`。
- **SkillToolHandler**：`{placeholder}` shell → native tool schema 桥接。

### Per-turn / Dynamic
- Session 级 injection；**无 per-turn filter**。
- Subagent_spawn 背景 agent — 独立 registry，**无 skill 参数**。

### Compact
- `auto_compact_history` + fact extraction（`loop_/history.rs`）。
- 无 invoked_skills。

### Delete
- 用户删目录；hygiene cron 归档 memory。

### Evolve
- **Audit only**（zip-bomb, path traversal, prompt injection patterns — `skills/audit.rs`）。
- Nightly consolidation **memory**，非 skill（`cron/consolidation.rs`）。

### Subagent
- `SubAgentRegistry` + team topology 预算（Single/LeadSubagent/StarTeam/MeshTeam）。
- 无 complementary skill list API。

### TaiChu 可借鉴
1. **Loop detection** — tool 停滞 warn→stop（`loop_/detection.rs`）。
2. **Skill audit** before device load。
3. **Compact vs Full injection mode** 配置化。
4. **Subagent registry** 并发限制模式。

---

# 7. Claude Code Rev

**路径**：`/Users/maybewu/Documents/Projects/oss/experimental/claude-code-rev`

### Store
Multi-source：`loadSkillsDir.ts`；project/user/bundled/plugin。

### Expose
**三通道模型**（attachments.ts + SkillTool）：
1. **skill_listing** — 增量 attachment 每 agentId
2. **Skill tool** / `/skill-name` slash
3. **invoked_skills** — post-compact 附件

### Discover
- **Per-turn incremental listing**：`getSkillListingAttachments()` — 只发 **尚未 sent** 的 skills（`attachments.ts:2717-2734`）。
- `sentSkillNames` Map per `agentId`。
- Skill search 实验特性：subagent turn-0 仅 bundled+MCP（`filterToBundledAndMcp`，:2651-2697）。

### Recommend
- **skillUsageTracking.ts**：7-day half-life decay score 排序 UI/建议。
- EXPERIMENTAL_SKILL_SEARCH 长尾走 discovery 非 listing。

### Load / Use
- Skill tool → `addInvokedSkill()` 注册到 `STATE.invokedSkills`（bootstrap/state.ts）。
- Slash command 同样 register。

### Per-turn / Dynamic（★）
- **Dynamic attachment batch**："Sending N skills via attachment (initial|dynamic)"（:2732-2734）。
- Resume 路径：标记已有 skill 为 sent，只 delta 新 skill（:2709-2714）。
- **Per-subagent** `sentSkillNames` 隔离（:2699-2704）。

### Compact（★ 业界最佳实践之一）
`createSkillAttachmentIfNeeded()`（compact.ts:1494-1534）：
- 按 agentId 过滤 invoked skills
- **Most-recent-first** 排序
- Per-skill token cap + total budget
- 生成 `type: 'invoked_skills'` attachment **survives compaction**

### Delete
- 用户删 project skill；skillImprovement survey 选择性 apply。

### Evolve（自进化）
**skillImprovement.ts**：
- 每 **5 user turns** post-sampling hook
- 仅 **project-scoped invoked skills**
- Aux small/fast model → JSON `{section, change, reason}[]`
- **SkillImprovementSurvey UI** 用户 gate 后 `applySkillImprovement`
- **skillify** bundled skill：会话→新 skill 工作流

### Subagent complementary skills（★）
`runAgent.ts:577-639`：
- Agent frontmatter **`skills: [name, ...]`** → preload 全文到 initialMessages
- 并发 load + UI metadata
- **注意**：preload ≠ `addInvokedSkill` — compact 保护可能不覆盖 preload-only skills（comparison doc 已知 gap）

Skill search 为 subagent 专门缩小 listing（bundled+MCP）避免 200+ skills 截断。

### TaiChu 可借鉴（P0）
1. **`invoked_skills` post-compaction attachment** — 直接移植到 `compaction.rs`。
2. **Per-turn incremental skill listing** — 对齐 `# Available Skills` user prefix delta。
3. **SubAgent profile.skills preload** — `ChildSessionSpec` 扩展。
4. **skillImprovement 5-turn + SideQuery 小模型** — 对齐 big-small-model-collaboration.md。
5. **Usage decay ranking** — Flutter skill picker。

---

# 8. TaiChu（私有）

**路径**：`/Users/maybewu/Documents/Projects/drafts/zk/TaiChu`

### Store
17 canonical：`skills/system/{name}/SKILL.md`；用户 runtime skills 在 meta_data 路径（`load_skill.rs:30-34`）。Session workspace **隔离**，不搜 workspace 内 skill（:46-47）。

### Expose
- **System prompt**：`<local_skills>` / `<cloud_skills>` XML（`prompt_builder.rs`）。
- **A-system 端云**：每 turn **user message prefix** `# Available Skills`（`api/mod.rs:674-694`）— **故意不进 system prompt 保 cache**（transient.rs 注释）。

### Discover
- Session 启动 `load_skills_from_dirs` scan。
- Cloud catalog + device sync（Flutter）；`skill_catalog.json`。
- **Toollery `before_prompt`**：`tool_search decide` → `apply.skill_filter`（`tool_search_bridge.rs:370-373`）— **per-turn 动态 filter**，session 级 `set_skill_name_filter`。

### Recommend
- Toollery embedding search（optional plugin slot）。
- 无 usage decay。

### Load / Use
- **`load_skill(name|file_path)`** — 读 canonical root；**runs_on** 不匹配 → `remote_delegation: true` 提示云端执行（`load_skill.rs:110-132`）。
- `depends_on_tools` 仅 soft text，**无 hard gate**（comparison doc L965）。

### Per-turn / Dynamic（★ partial）
- **`# Available Skills` 每 turn 由 NLU/context 传入** — 真正 per-turn catalog（`render_available_skills_prefix`）。
- **`skill_name_filter`**：Toollery 可收窄本 turn 可见 skills（`session.rs:1038-1039, 2089-2091`）。
- **`disable_workspace_skill_scan`**：A-system caller 避免 system 双份 skills（`session/mod.rs:244-256`）。

### Offload
- Catalog 在 user prefix；body 在 ToolResult，**compaction 可丢 body**（已知 gap）。

### Compact（❌ 关键缺口）
`compaction.rs` 纯 LLM summarize — **无 invoked_skills 重注入**（`context-and-skills.md:64-68`）。load_skill ToolResult 可能被 summarize 掉。

### Delete
- 无 agent CRUD；canonical 人工 curated。

### Evolve
- **全无 runtime**；roadmap P2 proposals store（comparison doc L978-985）。

### Subagent complementary skills（❌）
`build_child_session_prompt()`（manager.rs:1736-1796）：
- 子 session **rescans canonical roots**
- **不继承** parent invoked skills
- **无** `profile.skills: [...]` preload
- `disable_workspace_skill_scan: false` 固定

### TaiChu 独有创新（值得保留）
- **runs_on + remote_delegation** — 八仓中最完整端云 skill 路由。
- **双维度 wire**：LLM `load_skill` / device `SkillLoad`（a_system/tools.rs）。
- **Per-turn user prefix skills** — cache-friendly，与 OpenSquilla user_message injection 同族。
- **Toollery before_prompt** — 已有 per-turn skill_filter 钩子。

---

# 跨仓：自进化（自进化）机制对照

| 项目 | 触发 | 检测 | 候选 | 评估 | 写入 | 人工 gate |
|------|------|------|------|------|------|-----------|
| **OpenClaw** | agent_end | regex + LLM reviewer | skill-workshop store | skill-scanner | append/replace | pending/auto policy |
| **Hermes** | nudge + post-turn | LLM review prompt | 直接 create | skills_guard | skill_manage patch | 无（agent 自决） |
| **Codex** | 无 | — | skill-creator 文档 | subagent 验证指南 | 人工 FS | 用户 |
| **OpenSquilla** | auto_propose + Dream | 共现链 + Dream signal | proposals/ | 4-gate + E2E judge | accept→MANAGED | gates.json |
| **GenericAgent** | start_long_term_update | agent 自判 | L3 SOP 文件 | L0 SOP 协议 | file_patch | agent 自决 |
| **ZeroClaw** | 无 | — | — | audit | — | — |
| **Claude Rev** | 每 5 turn | invoked project skills | JSON patches | survey UI | applySkillImprovement | **用户 survey** |
| **TaiChu** | 无 | — | — | — | — | — |

---

# TaiChu 集成方案（How）

## Phase 0 — 保现有优势
- 保留 **runs_on + load_skill wire + per-turn user prefix**。
- 保留 **Toollery before_prompt skill_filter**。

## Phase 1 — 补 lifecycle 缺口（2-4 周可落地）

| 借谁 | 做什么 | 落点 |
|------|--------|------|
| Claude Rev | `InvokedSkillRegistry` + post-compact attachment | `agent-session/compaction.rs`, session state |
| Claude Rev | `ChildSessionSpec.skills: Vec<String>` preload metadata | `session/manager.rs`, subagent profiles |
| Hermes | `skill_manage` equivalent tool (create/patch/delete) | `builtintools/` + security scan |
| Hermes | `_spawn_background_review` after turn | async task in session handle |

## Phase 2 — 进化闭环（4-8 周）

| 借谁 | 做什么 | 落点 |
|------|--------|------|
| OpenSquilla | `proposals/` + gates.json + accept | `~/.taichu/proposals/` |
| OpenSquilla | HybridRetriever top-k + pinned always | extend Toollery decide |
| OpenClaw | Trajectory/step JSONL export | interaction_log schema |
| Claude Rev | skillImprovement 5-turn SideQuery | big-small-model-collaboration |

## Phase 3 — 高级（可选）

| 借谁 | 做什么 |
|------|--------|
| OpenSquilla | meta-skill DAG |
| Hermes | Atropos env for SkillRL experiments |
| GenericAgent | L0 skill-update SOP markdown |

### 建议数据结构（TaiChu）

```text
~/.taichu/
├── skills/              # MANAGED（accept 后）
├── proposals/{id}/      # SKILL.md + gates.json
└── state/
    └── invoked_skills.json   # session → [{name, path, invoked_at}]
```

### Compaction 伪代码（借 Claude Rev）

```rust
// After summarize old messages:
if let Some(skills) = session.invoked_skills.for_agent(agent_id) {
    messages.push(rebuild_invoked_skills_attachment(skills, budget));
}
```

---

# 结论

1. **Per-turn skill catalog**：OpenSquilla pipeline + TaiChu A-system user prefix + Claude Rev incremental attachment — 三种成熟模式；TaiChu 已在 user prefix 领先，缺 **delta/dynamic** 与 **invoked tracking**。

2. **Dynamic body load**：全员 progressive disclosure；TaiChu `load_skill` + runs_on 最强。

3. **Subagent complementary skills**：Claude Rev frontmatter preload + Codex child turn_skills 最清晰；OpenSquilla meta DAG 适合 **组合** 非 **preload**；TaiChu **全缺**。

4. **Compaction skill survival**：**仅 Claude Rev** 有完整 `invoked_skills` — TaiChu **P0**。

5. **自进化**：OpenSquilla（gate）+ Hermes（CRUD）+ OpenClaw（workshop）+ Claude Rev（UI survey）各擅一段；TaiChu 应 **Hermes 运行时 + OpenSquilla gate + Claude compact** 三板斧。

---

## 源码索引

| 主题 | 文件 |
|------|------|
| TaiChu per-turn prefix | `taichu-service/src/api/mod.rs:674-694` |
| TaiChu load_skill + runs_on | `builtintools/src/skill/load_skill.rs` |
| TaiChu tool filter | `agent-plugin/src/tool_search_bridge.rs:370-382` |
| TaiChu compact gap | `agent-session/src/compaction.rs` |
| OpenSquilla per-turn filter | `engine/steps/skills_filter.py` |
| OpenClaw lazy + workshop | `skill-contract.ts`, `skill-workshop/index.ts` |
| Hermes review + manage | `run_agent.py:1753-1830`, `skill_manager_tool.py` |
| Claude invoked_skills | `compact/compact.ts:1494-1534` |
| Claude subagent preload | `AgentTool/runAgent.ts:577-639` |
| Claude skillImprovement | `hooks/skillImprovement.ts` |
