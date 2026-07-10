---
id: T007-zh
title: Agent Skill 架构调研矩阵
date: 2026-07-08
tags: [survey-matrix, architecture, zh]
status: active
lang: zh
related: [T007]
summary: 7 大类、15 节、165 维 × 8 框架 — Agent Harness + Skill 架构调研
---

# Agent Skill 架构调研矩阵

> **不是功能清单** — Agent Harness + Skill 系统设计的**横向架构调研工具** for Agent Harness + Skill system design.  
> **证据**： L2–L3 local source (8 runtime repos) + L0 public docs/issues.  
> **项目**： Codex · Claude Code Rev (oboard) · OpenClaw · Hermes · GenericAgent · OpenSquilla · ZeroClaw · TaiChu

## 七大类

| # | 大类 | 章节 | 维度数 |
|---|---------------|----------|:----------:|
| I | **Skill 数据模型** | §1 | 14 |
| II | **运行时** | §2–§7 发现、暴露、推荐、运行时、卸载、使用 | 68 |
| III | **生命周期** | §8 | 13 |
| IV | **进化与质量** | §9–§10 | 29 |
| V | **治理** | §11 | 12 |
| VI | **Agent 集成** | §12–§14 关系、多 Agent、记忆 | 28 |
| VII | **RL 就绪度** | §15 | 11 |
| | **合计** | **15 节** | **165** |

### 单元格图例

| 符号 | 含义 |
|:------:|---------|
| ★ | 强 / 一等公民 / 生产路径 |
| ◐ | 部分 / 实验 / 弱 |
| · | 无 / 不在范围 |
| ❌ | 已知缺口或文档化风险 |
| — | 该框架类型不适用 |

架构差异显著处用短文本补充符号。

### 各仓库交付格式

每个框架应产出 **12 节调研报告** (template: [`templates/survey-matrix-repo-report.md`](../templates/survey-matrix-repo-report.md)):

```text
1. Architecture  2. Skill Runtime  3. Skill Lifecycle  4. Skill Evolution
5. Multi-Agent Skill  6. Skill Governance  7. Harness Integration  8. RL Readiness
9. Borrow for TaiChu  10. Implement in TaiChu  11. Do NOT borrow  12. Score (1–10)
```

完整示例： **all 8 repos** in [survey-reports/](survey-reports/) — see [README](survey-reports/README.md)

---

# I. Skill 数据模型

## §1 — Skill 表示与打包

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Skill 单元** (Skill Unit) | SKILL.md dir | SKILL.md dir | SKILL.md file | SKILL.md dir | `*_sop.md` | SkillSpec + MetaSkill | SKILL.md/.toml | SKILL.md |
| **存储格式** (Storage Format) | MD + YAML FM | MD + YAML FM | MD + YAML FM | MD + YAML FM | MD SOP prose | MD + meta schema | MD/TOML | MD + YAML |
| **文件布局** (File Layout) | `skills/<n>/` + scripts/refs/assets/agents | project/user/bundled/plugin roots | 多根目录合并 | `~/.hermes/skills/<n>/` | `memory/` L0–L4 tree | 六层优先级目录 | `workspace/skills/` | `skills/system/<n>/` |
| **元数据** (Metadata) | name, description req | frontmatter | frontmatter + location | frontmatter | L-tier tags | SkillSpec typed | version in manifest | runs_on, depends_on_tools |
| **描述** (Description) | ★ routing signal | trigger text | catalog desc | catalog desc | SOP title | trigger + description | summary line | XML description |
| **参数** (Parameters) | `agents/openai.yaml` | · | · | · | · | meta step params | `{placeholder}`→tool schema | · |
| **脚本** (Scripts) | ★ `scripts/` | · | via references | ★ `scripts/` | · | ★ `skill_exec` entrypoint | shell bridge | · |
| **资产** (Assets) | ★ `assets/` | · | · | ★ `assets/` | · | · | · | · |
| **引用** (References) | ★ `references/` | · | lazy read path | ★ `references/` | · | · | · | · |
| **示例** (Examples) | · | · | · | templates/ | · | ★ `eval_prompts` fixtures | · | · |
| **内嵌工作流** (Embedded Workflow) | · | · | · | · | plan.md checkpoint | ★ MetaSkill `composition_raw` | channel SOP | · |
| **嵌套 Skill** (Nested Skill) | · | · | · | · | ◐ L-tree parent/child | meta step→skill ref | · | · |
| **MetaSkill 工作流** (MetaSkill) | · | · | · | · | · | ★ DAG workflow type | · | ◐ roadmap P3 |
| **版本** (Version) | · | · | ◐ snapshot version# | ◐ manifest origin hash | · | ★ lockfile SHA256 | ◐ manifest field | · |

---

# II. 运行时

## §2 — Skill 发现

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **发现来源** (Discover Source) | 文件系统作用域 | 多根目录扫描 | 六源合并 | `~/.hermes` scan | memory/ listing | 六层加载器 | workspace scan | canonical + cloud catalog |
| **搜索路径** (Search Path) | User/Repo/System/Admin | project→user→bundled | workspace highest | 单一主目录 | L1 index | WORKSPACE highest | `~/.zeroclaw/workspace` | 仅 system 根 |
| **工作区 Skill** (Workspace Skill) | ★ repo `skills/` | ★ project dir | ★ `<ws>/skills` | · | · | ★ WORKSPACE layer | ★ workspace | · session isolated |
| **用户 Skill** (User Skill) | ★ User scope | ★ user dir | `~/.openclaw/skills` | ★ `~/.hermes` | memory/ user | PERSONAL layer | workspace | cloud sync |
| **全局 Skill** (Global Skill) | ★ System scope | bundled | managed + bundled | bundled sync | · | MANAGED | open-skills sync | 17 canonical |
| **注册表 Skill** (Registry Skill) | · | · | ClawHub (external) | Hermes Hub | · | hub install | ★ zeroclaw-skills | · |
| **远程 Skill** (Remote Skill) | · | · | remote node refresh | · | · | · | · | ★ cloud catalog + device |
| **生成 Skill** (Generated Skill) | ◐ Record&Replay | ◐ skillify | workshop proposals | ★ agent-created | ★ crystallized SOP | proposals/ | · | · |
| **内置 Skill** (Bundled Skill) | ★ system | ★ bundled | ★ lowest priority | ★ skills_sync | 种子 SOP | BUNDLED layer | bundled | ★ system/ |
| **优先级** (Priority) | 作用域顺序 | 源顺序 | ★ 6-level explicit | 单一目录树 | L-tier | ★ 6-level explicit | workspace over remote | canonical only |
| **覆盖** (Override) | 高作用域优先 | · | ★同名高优先级覆盖 | agent patch | file_patch | accept→MANAGED | · | · |
| **影子/遮蔽** (Shadow) | · | · | · | ◐ issue: symlink | · | · | · | · |
| **冲突解决** (Conflict Resolution) | 作用域优先级 | · | 按名+优先级合并 | 后写胜出 | manual | lock SHA pin | · | · |
| **懒发现** (Lazy Discovery) | watcher refresh | incremental listing | ★ snapshot at session start | index at session | on file_read | snapshot v11 cache | scan at load | scan at session |
| **文件监听** (File Watch) | ★ | · | ★ chokidar | · | · | · | ◐ sync interval | · |
| **热重载** (Hot Reload) | ◐ watcher | ◐ delta listing | ★ next-turn refresh | · | · | pipeline rebuild | · | ◐ per-turn prefix |
| **刷新策略** (Refresh Policy) | 变更时 | 每轮增量 | snapshot version bump | session frozen | reflect cron | **★ every turn** filter_skills | session | **★ every turn** user prefix |

## §3 — Skill 暴露

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **LLM 可见** (Visible to LLM) | metadata block | listing attachment | metadata XML | metadata index | memory dir list | injector output | full or compact | XML + user prefix |
| **用户可见** (Visible to User) | TUI skill toggle | UI skill picker | config UI | CLI/Gateway | file tree | CLI proposals | audit cmd | Flutter catalog |
| **隐藏 Skill** (Hidden Skill) | disableModelInvocation equiv | · | ★ frontmatter hide | · | · | disabled gate | · | filter |
| **渐进披露** (Progressive Disclosure) | ★ desc→full | ★ listing→tool | ★ catalog→read | ★ list→view | index→read | ★ compact→view | ★ compact mode | ★ catalog→load_skill |
| **仅摘要** (Summary Only) | ★ initial catalog | listing metadata | compact XML | skills_list meta | L1 index | compact injector | compact summary | `# Available Skills` |
| **完整 Prompt 加载** (Full Prompt Loaded) | on @mention | Skill tool | read tool lazy | skill_view / --skills preload | file_read | skill_view / meta_invoke | always-flag full | load_skill body |
| **仅描述** (Description Only) | ★ default expose | ★ attachment | ★ default | ★ default | title only | compact mode | compact | ★ default |
| **显式调用** (Explicit Invocation) | ★ `/` `@skill` | ★ Skill tool slash | read tool | ★ `/<skill>` | file_read path | skill_view / `/meta` | read file | ★ load_skill |
| **隐式调用** (Implicit Invocation) | ★ shell pattern match | · | · | ◐ auto from desc | related_sop hint | ◐ auto_trigger meta | · | ◐ Toollery decide |

## §4 — Skill 推荐

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **触发** (Trigger) | mention / shell | usage decay UI | · | slash / nudge | related_sop | **★ per-turn pipeline** | · | Toollery hook |
| **描述匹配** (Description Match) | ◐ implicit | · | · | · | · | ◐ lexical leg | · | ◐ |
| **向量匹配** (Embedding Match) | · | EXPERIMENTAL search | · | · | · | ★ semantic leg RRF | · | ◐ plugin slot |
| **LLM 决策** (LLM Decide) | model picks mention | · | · | review agent | agent picks SOP | Dream classify | · | NLU context |
| **规则驱动** (Rule Based) | shell regex | bundled+MCP filter | skillFilter whitelist | · | · | pinned always | · | runs_on filter |
| **任务模式** (Task Pattern) | · | · | workshop regex | review prompt | goal mode | auto_propose chains | · | · |
| **工具模式** (Tool Pattern) | ★ implicit shell | · | · | · | tool in SOP | requires_tools gate | · | depends_on_tools soft |
| **历史模式** (History Pattern) | · | ★ 7d decay score | · | session_search FTS | access stats | Dream co-occurrence | · | · |
| **用户偏好** (User Preference) | TUI enabled set | survey apply | agent config | · | · | · | · | device profile |
| **频率** (Frequency) | · | ★ decay ranking | · | · | ◐ access stats | trigger accuracy | · | · |
| **排序** (Ranking) | · budget truncate | ◐ decay sort | alpha + budget | · | ◐ stats | **★ RRF fusion** | · | ◐ embedding |
| **多 Skill 排序** (Multi Skill Ranking) | · | · | · | · | · | ★ top-k=5 | · | ◐ multi filter |
| **预算感知** (Budget Aware) | ★ 2% / 8K cap | attachment budget | 150 / 18K cap | size limit | anchor prompt | injector truncate | compact mode | · |

## §5 — Skill 运行时

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **每轮加载** (Per Turn Loading) | ★ mentioned only | ★ delta listing | ◐ snapshot reuse | · frozen index | · | **★ filter+inject** | · session | **★ user prefix** |
| **每 Session** (Per Session) | SkillsManager cache | sentSkillNames map | ★ snapshot | frozen prefix | anchor rebuild | snapshot cache | load at start | session scan |
| **每 Agent** (Per Agent) | turn_skills config | per agentId map | ★ skillFilter | same index | · | agent FSM | · | session instance |
| **每 SubAgent** (Per SubAgent) | ★ child turn_skills | ★ frontmatter preload | ◐ filter inherit | ◐ delegate | · | meta agent step | ◐ spawn | ❌ rescans only |
| **动态加载** (Dynamic Loading) | injection.rs | Skill tool | read tool | skill_view | file_read | skill_view | read at location | load_skill |
| **动态卸载** (Dynamic Unloading) | not in turn | · | lazy default | · | anchor | compact injector | compact | ToolResult only |
| **并行 Skill** (Parallel Skills) | multi mention | multi invoked | multi read | multi view | · | meta parallel steps | · | multi load |
| **Skill 链** (Skill Chain) | · | · | · | · | · | ★ MetaSkill steps | SOP chain | · |
| **Skill 图** (Skill Graph) | · | · | · | · | · | ★ MetaOrchestrator DAG | · | · |
| **Skill 缓存** (Skill Cache) | SkillsManager | sentSkillNames | snapshot prompt | frozen memory | working dict | schema v11 | registry | prefix cache |
| **Skill 上下文预算** (Skill Context Budget) | ★ metadata cap | per-skill cap | char/skill cap | · | anchor | governor | compact/full | · |
| **Skill 压缩** (Skill Compression) | truncate desc | compact attachment | ~/ path compress | · | history tags | compact injector | compact mode | · |
| **Skill 摘要** (Skill Summarization) | compact hooks | · | compaction-safeguard | ContextCompressor | compress tags | session compact | auto_compact | ★ LLM compact |
| **Skill 剪枝** (Skill Pruning) | omit from catalog | · | binary search drop | · | · | gate disabled | · | skill_name_filter |

## §6 — Skill 卸载

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **卸载到 SubAgent** (Offload to SubAgent) | ★ Task spawn | ★ Task tool isolate | subagent session | ★ delegate_task | subprocess | meta agent step | SubAgentRegistry | run_subagent |
| **卸载到 Tool** (Offload to Tool) | read/MCP | Skill tool | read tool | skill_view | file_read | skill_exec | SkillToolHandler | load_skill |
| **卸载到工作流** (Offload to Workflow) | update_plan | · | cron isolated | · | plan.md | ★ MetaSkill | channel SOP | · |
| **卸载到记忆** (Offload to Memory) | generate_memories | TodoWrite JSON | memory search | MEMORY.md frozen | ★ L2/L3 SOP | Dream→MEMORY | fact extract | MEMORY.md |
| **卸载到 MCP** (Offload to MCP) | ★ MCP tools | MCP in search | MCP plugins | MCP tools | · | MCP | ★ MCP | MCP planned |
| **卸载到人工** (Offload to Human) | Guardian approval | ★ Survey UI | workshop pending | · | · | gate refuse | audit user | · |

## §7 — Skill 使用

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **直接 Prompt** (Direct Prompt) | ★ injected `<skill>` | Skill tool body | read→prompt | skill_view body | SOP text | skill_view | read content | load_skill result |
| **Tool 包装** (Tool Wrapper) | · | Skill as tool | · | skills as tools | · | skill_exec | SkillToolHandler | load_skill tool |
| **代码** (Code) | scripts/ | · | · | scripts/ | · | entrypoints | shell bridge | · |
| **工作流** (Workflow) | agent_jobs | · | cron agent | · | morphling | ★ meta_invoke | · | · |
| **规划器** (Planner) | ★ update_plan | TodoWrite | · | · | plan mode | meta steps | · | · |
| **标准作业程序** (SOP) | · | · | · | · | ★ primary form | · | ◐ | · |
| **Agent 执行体** (Agent) | ★ multi_agents | ★ subagent | subagent | delegate | team BBS | meta agent | subagent spawn | subagent relay |
| **MCP 协议** (MCP) | ★ | bundled+MCP | plugins | ★ | · | ★ | ★ | ◐ |
| **命令** (Command) | ★ implicit shell | slash | slash | slash | · | CLI | zeroclaw CLI | device SkillLoad |

---

# III. 生命周期

## §8 — Skill 生命周期阶段

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **创建者** (Created By) | human / skill-creator | skillify / human | workshop / human | ★ agent skill_manage | ★ agent crystallize | auto_propose / meta-creator | human | human canonical |
| **导入** (Imported) | FS copy | project add | ClawHub / extraDirs | Hub install | · | hub install | open-skills sync | cloud deploy |
| **生成** (Generated) | Record&Replay | skillify session | workshop heuristic | background review | long_term_update | Dream / auto_propose | · | · |
| **人工编写** (Human Written) | ★ primary | ★ project skills | workspace files | bundled | 种子 SOP | managed | user workspace | ★ 17 canonical |
| **AI 编写** (AI Written) | · | ◐ patches | ◐ workshop apply | ★ skill_manage | ★ SOP write | proposals | · | · |
| **已评审** (Reviewed) | Guardian (tools) | ★ Survey UI | LLM reviewer | bg review agent | L0 protocol | 4-gate + E2E | audit scan | · |
| **已批准** (Approved) | TUI test / user | user survey | auto/manual policy | · agent self | agent self | gates.json pass | user audit | · |
| **已发布** (Published) | FS write | apply patch | apply proposal | immediate write | file_patch | accept→MANAGED | load skill | canonical deploy |
| **已弃用** (Deprecated) | disable toggle | · | · | · | cleanup SOP | reject | · | · |
| **已禁用** (Disabled) | write_skill_enabled | · | disableModelInvocation | · | · | disabled gate | · | skill_name_filter |
| **已删除** (Deleted) | FS delete | user delete | file delete | skill_manage delete | manual | reject + rm | rm dir | · |
| **已归档** (Archived) | · | · | quarantine store | · | L4 sessions | proposals history | hygiene cron | JSONL log |
| **回滚** (Rollback) | git / manual | · | · | · | · | · | · | ❌ needed |
| **生命周期得分** (Lifecycle Score) | 6/13 | 8/13 | 9/13 | 10/13 | 7/13 | **12/13** | 5/13 | 4/13 |

---

# IV. 进化与质量

## §9 — Skill 进化

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **反思** (Reflection) | ReviewTask code | ★ 5-turn hook | ◐ dreaming | ★ bg review | reflect cron | ★ Dream | loop detect | · |
| **自反思** (Self Reflection) | · | skillImprovement | workshop self | ★ review prompt | goal mode | Dream LLM | · | · |
| **教师模型** (Teacher) | · | aux small model | LLM reviewer | review agent | · | E2E judge | · | · |
| **强化学习** (RL) | · | · | ◐ trajectory | ★ Atropos | · | · | · | · |
| **GRPO 算法** (GRPO) | · | · | OpenClaw-RL ext | ◐ RL tool | · | · | · | · |
| **偏好** (Preference) | · | survey accept | · | · | · | · | · | · |
| **成对比较** (Pairwise) | · | · | · | · | · | meta vs baseline | · | · |
| **候选** (Candidate) | · | JSON patches | ★ proposals store | direct create | SOP draft | ★ proposals/ | · | · |
| **合并** (Merge) | · | user apply | append/replace | patch | file_patch | accept_proposal | · | · |
| **拆分** (Split) | · | · | · | · | · | · | · | · |
| **重写** (Rewrite) | manual | section patches | replace mode | edit | morphling | meta rewrite | · | · |
| **摘要化** (Summarize) | memories distill | · | · | · | · | Dream summary | fact extract | compact summarize |
| **重构** (Refactor) | · | · | · | · | · | meta-skill-creator | · | · |
| **自动 Patch** (Auto Patch) | · | ◐ after survey | ◐ auto policy | ★ skill_manage | ★ file_patch | after gates | · | · |
| **自动删除** (Auto Delete) | · | · | · | ★ skill_manage | · | reject | · | · |
| **自动版本** (Auto Version) | · | · | snapshot# | hash | · | lock SHA | field | · |

## §10 — Skill 质量

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **基准测试** (Benchmark) | integration tests | · | qa-lab | · | model logs | trigger accuracy | · | bench plan |
| **回归测试** (Regression) | suite/skill_* | · | · | · | · | ★ eval_prompts | · | · |
| **回放** (Replay) | Record&Replay | session JSONL | trajectory | JSONL+DB | · | decision log | · | interaction_log |
| **单元测试** (Unit Test) | ★ Rust tests | · | · | · | · | pytest | audit tests | Rust tests |
| **集成测试** (Integration Test) | ★ extensive | · | e2e ext | · | · | runtime_e2e | · | ◐ |
| **沙箱** (Sandbox) | · | · | · | · | · | · | · | · |
| **仿真** (Simulation) | TestCodex | · | · | Atropos env | · | · | · | · |
| **在线评估** (Online Eval) | analytics | usage decay | · | · | access stats | trigger acc | economic | · |
| **A/B 测试** (A/B) | · | · | · | · | · | ★ meta vs baseline | · | · |
| **成功率** (Success Rate) | · | · | · | · | verify axiom | gate metrics | · | · |
| **奖励** (Reward) | · | · | trajectory reward | RL reward | · | · | · | · |
| **Token 成本** (Token Cost) | budget cap | attachment cap | char cap | · | ★ anchor | governor | compact | user prefix |
| **延迟** (Latency) | · | SideQuery small | · | bg async | · | pipeline | · | · |

---

# V. 治理

## §11 — Skill 治理

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **权限** (Permission) | TUI approval | project scope | agent config | · | · | policy chain | · | ToolDomains |
| **能力** (Capability) | tool allow | · | tool + read | toolsets | 9 atomic tools | requires_tools | tool schema | runs_on |
| **风险** (Risk) | ★ Guardian JSON | · | scanner quarantine | skills_guard | · | gates.json | audit patterns | · |
| **签名** (Signature) | · | · | · | · | · | lock SHA | · | · |
| **信任等级** (Trust Level) | Admin scope | project vs bundled | managed tiers | bundled vs user | · | MANAGED vs BUNDLED | registry disclaimer | canonical |
| **审计** (Audit) | · | · | skill-scanner | _security_scan | · | hub quarantine | ★ skills/audit.rs | · |
| **溯源** (Provenance) | · | · | proposal metadata | origin hash | · | proposal source | sync source | cloud origin |
| **注册表** (Registry) | · | · | ClawHub | Hermes Hub | · | hub | ★ zeroclaw-skills | skill_catalog.json |
| **市场** (Marketplace) | · | · | ★ ClawHub risk | Hub | · | hub | community | · |
| **评审** (Review) | Guardian | Survey UI | LLM reviewer | bg review | L0 SOP | 4-gate | CI structure | · |
| **所有者** (Owner) | · | · | · | · | · | · | contributor | team curated |
| **许可证** (License) | · | · | · | · | · | · | repo LICENSE | · |

---

# VI. Agent 集成

## §12 — Skill 关系

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **父 Skill** (Parent Skill) | · | · | · | · | L-tree | · | · | · |
| **子 Skill** (Child Skill) | · | · | · | · | nested SOP | step refs | · | · |
| **Meta Skill 类型** (Meta Skill) | · | · | · | · | · | ★ MetaSkill type | · | P3 |
| **组合 Skill** (Composite Skill) | · | · | · | · | · | composition_raw | · | · |
| **互补 Skill** (Complementary Skill) | · | ◐ subagent preload | per-agent filter | delegate | · | meta multi-skill | · | ❌ |
| **替代 Skill** (Alternative Skill) | · | · | · | · | · | · | · | · |
| **依赖** (Dependency) | · | · | · | · | · | requires_tools | · | depends_on_tools soft |
| **Skill 图** (Skill Graph) | · | · | · | · | · | ★ MetaOrchestrator | · | · |
| **Skill 有向无环图** (Skill DAG) | · | · | · | · | · | ★ meta steps | · | · |

## §13 — 多 Agent Skill

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **共享 Skill** (Shared Skill) | repo scope | project | shared managed | ~/.hermes | memory shared | MANAGED | workspace | canonical |
| **私有 Skill** (Private Skill) | user scope | user | per-agent ws | user created | user SOP | PERSONAL | · | device profile |
| **每 Agent Skill** (Per Agent Skill) | turn_skills | agentId map | ★ skillFilter | same index | · | FSM agent | · | session |
| **每角色 Skill** (Per Role Skill) | · | subagent profile | agent list[] | · | · | meta roles | team topology | · |
| **互补 Skill** (Complementary Skill) | child subset | ★ preload list | filter diff | ◐ | · | DAG steps | · | ❌ |
| **Skill 协商** (Skill Negotiation) | · | · | · | · | BBS | · | · | · |
| **Skill 传递** (Skill Transfer) | · | tool result | summary | delegate summary | · | subagent report | · | relay |
| **Skill 借用** (Skill Borrow) | · | · | · | · | · | · | · | · |
| **Skill 广播** (Skill Broadcast) | · | · | · | · | · | · | · | cloud catalog |
| **Skill 隔离** (Skill Isolation) | ★ child no parent skills | ★ sub context | subagent prompt | ★ delegate | subprocess | one-shot agent | registry | partial |

## §14 — 记忆集成

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **情节记忆** (Episodic) | thread history | session JSONL | trajectory | session DB | L4 sessions | pipeline log | history | JSONL |
| **语义记忆** (Semantic) | memories config | · | memory search | MEMORY.md | L2 facts | hybrid chunks | facts | MEMORY.md |
| **向量** (Vector) | · | · | ◐ embedding | · | · | ★ hybrid | · | ◐ planned |
| **图** (Graph) | · | · | · | · | · | meta DAG | · | · |
| **检索增强生成** (RAG) | · | · | ★ hybrid FTS+vec | FTS5 search | file_read | ★ retrieval | · | Toollery |
| **KV 缓存** (KV) | prefix cache | · | snapshot cache | ★ frozen prefix | anchor | 每轮注入 | · | user prefix cache |
| **摘要** (Summary) | compact | compact | compaction | compressor | compress | compact | auto_compact | ★ compact |
| **反思** (Reflection) | distill | skillImprove | dream | bg review | reflect | Dream | consolidation | · |
| **长期记忆** (Long-term) | AGENTS.md | · | MEMORY.md | MEMORY.md | L3 SOP tree | Dream promote | memory hygiene | MEMORY.md |

---

# VII. RL 就绪度

## §15 — RL 就绪度（SkillRL / Claw-R1）

| 维度 | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Step 轨迹** (Step Trace) | ◐ dispatch trace | session steps | ★ trajectory metadata | JSONL steps | model log | ★ PipelineStepRecord | OTel | ◐ interaction_log |
| **轨迹** (Trajectory) | rollout | JSONL export | ★ openclaw-trajectory | Atropos traj | · | TraceContext | · | JSONL |
| **Tool 轨迹** (Tool Trace) | ★ tool_dispatch_trace | tool results | trajectory tools | tool log | tool log | decision log | tool log | interaction_log |
| **奖励** (Reward) | · | · | ◐ trajectory reward | ★ env reward | · | · | · | · |
| **验证器** (Verifier) | tests | · | qa-lab | env verify | VERIFY SOP | runtime_e2e | audit | · |
| **回放** (Replay) | Record&Replay | session replay | trajectory read | DB replay | · | decision replay | · | log replay |
| **数据集** (Dataset) | · | · | trajectory export | RL datasets | · | · | · | · |
| **离线 RL** (Offline RL) | · | · | ★ OpenClaw-RL repo | ★ Atropos | · | · | · | · |
| **在线 RL** (Online RL) | · | · | · | rl_training_tool | · | · | · | · |
| **SkillRL 兼容** (SkillRL Compatible) | ◐ traces only | ◐ traces | ◐ traj no SkillBank | ◐ closest | ◐ SOP mine | ◐ proposals | · | ◐ log only |
| **Claw-R1 兼容** (Claw-R1 Compatible) | ◐ | ◐ | ★ best OSS | ★ | · | ★ pipeline log | · | ◐ hooks |

---

# 综合评分（1–10）

| 框架 | 数据模型 | 运行时 | 生命周期 | 进化 | 治理 | Agent 集成 | RL 就绪 | **总分** |
|-----------|:----------:|:-------:|:---------:|:---------:|:----------:|:------------:|:--------:|:-----------:|
| **OpenSquilla** | 9 | 9 | 12 | 9 | 8 | 9 | 6 | **9.0** |
| **Hermes** | 8 | 8 | 10 | 9 | 5 | 7 | 8 | **8.1** |
| **OpenClaw** | 8 | 8 | 9 | 7 | 7 | 8 | 7 | **8.0** |
| **Claude Rev** | 7 | 9 | 8 | 7 | 6 | 9 | 4 | **7.7** |
| **Codex** | 9 | 8 | 6 | 3 | 8 | 7 | 4 | **7.2** |
| **TaiChu** | 6 | 7 | 4 | 1 | 3 | 5 | 3 | **5.0** |
| **ZeroClaw** | 6 | 5 | 5 | 2 | 7 | 4 | 2 | **5.0** |
| **GenericAgent** | 5 | 5 | 7 | 6 | 2 | 3 | 2 | **4.8** |

*评分为矩阵覆盖度的定性汇总，非 benchmark 指标。*

---

# TaiChu 综合结论（来自矩阵）

## 可借鉴（按大类）

| 类别 | 主要来源 |
|----------|----------------|
| 数据模型 | Codex layout + OpenClaw multi-root + ZeroClaw trust metadata |
| 运行时 | Codex progressive disclosure + OpenSquilla RRF + Claude incremental listing + **runs_on keep** |
| 生命周期 | OpenSquilla gates + Hermes CRUD (candidate only) + Claude invoked_skills |
| 进化 | OpenSquilla proposals + GenericAgent miner + Hermes review (with read-before-write) |
| 治理 | ZeroClaw audit + OpenSquilla gates + Codex Guardian |
| Agent 集成 | Claude subagent bundles + OpenSquilla MetaSkill + OpenClaw skillFilter |
| RL 就绪度 | OpenClaw trajectory + Claw-R1 step schema on interaction_log |

## 不应借鉴

- Hermes direct production patch without gate
- OpenClaw marketplace trust model wholesale
- GenericAgent ungated crystallize
- ZeroClaw assumption that CI = security boundary

---

## 相关文档

| 文档 | 作用 |
|-----|------|
| [skill-lifecycle-full-matrix.md](skill-lifecycle-full-matrix.md) | 9 阶段精简矩阵 |
| [skill-lifecycle-and-dynamic-loading-survey.md](skill-lifecycle-and-dynamic-loading-survey.md) | 各仓库 L3 叙事证据 |
| [repos/*.md](repos/) | 20 维仓库卡片 |
| [web-expanded-lifecycle-matrix-merged.md](web-expanded-lifecycle-matrix-merged.md) | **Web 扩展 lifecycle** 合并（公开 quotes + L3 修正） |
| [survey-reports/](survey-reports/) | **8 complete** 12-section reports + evidence index |
| [config/survey-matrix-dimensions.yaml](../config/survey-matrix-dimensions.yaml) | Machine-readable dimension index |

---

## 变更记录

| 日期 | 变更 |
|------|--------|
| 2026-07-08 | 首版 165 维 Agent Skill 架构调研矩阵 |
