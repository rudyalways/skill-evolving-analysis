---
id: T007
title: Agent Skill Architecture Survey Matrix
date: 2026-07-08
tags: [survey-matrix, architecture, skill-data-model, lifecycle, evolution, governance, rl-readiness]
status: active
evidence_level: L3
related: [N2026-07-08-LIFECYCLE-MATRIX, N2026-07-08-010, N2026-07-08-009]
summary: 7 mega-categories, 15 sections, 165 dimensions × 8 frameworks — Agent Harness + Skill Architecture Survey
---

# Agent Skill Architecture Survey Matrix

> **Not a feature checklist** — a comparative architecture instrument for Agent Harness + Skill system design.  
> **Evidence**: L2–L3 local source (8 runtime repos) + L0 public docs/issues.  
> **Projects**: Codex · Claude Code Rev (oboard) · OpenClaw · Hermes · GenericAgent · OpenSquilla · ZeroClaw · TaiChu

## Seven mega-categories

| # | Mega-category | Sections | Dimensions |
|---|---------------|----------|:----------:|
| I | **Skill Data Model** | §1 | 14 |
| II | **Runtime** | §2–§7 Discovery, Exposure, Recommendation, Runtime, Offload, Usage | 68 |
| III | **Lifecycle** | §8 | 13 |
| IV | **Evolution & Quality** | §9–§10 | 29 |
| V | **Governance** | §11 | 12 |
| VI | **Agent Integration** | §12–§14 Relationship, Multi-Agent, Memory | 28 |
| VII | **RL Readiness** | §15 | 11 |
| | **Total** | **15 sections** | **165** |

### Cell legend

| Symbol | Meaning |
|:------:|---------|
| ★ | Strong / first-class / production path |
| ◐ | Partial / experimental / weak |
| · | Not present / out of scope |
| ❌ | Known gap or documented risk |
| — | N/A for this framework type |

Short text supplements symbols where architecture differs materially.

### Per-repo deliverable format

Each framework should eventually produce a **12-section survey report** (template: [`templates/survey-matrix-repo-report.md`](../templates/survey-matrix-repo-report.md)):

```text
1. Architecture  2. Skill Runtime  3. Skill Lifecycle  4. Skill Evolution
5. Multi-Agent Skill  6. Skill Governance  7. Harness Integration  8. RL Readiness
9. Borrow for TaiChu  10. Implement in TaiChu  11. Do NOT borrow  12. Score (1–10)
```

Worked examples: **all 8 repos** in [survey-reports/](survey-reports/) — see [README](survey-reports/README.md)

---

# I. Skill Data Model

## §1 — Skill representation & packaging

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Skill Unit** | SKILL.md dir | SKILL.md dir | SKILL.md file | SKILL.md dir | `*_sop.md` | SkillSpec + MetaSkill | SKILL.md/.toml | SKILL.md |
| **Storage Format** | MD + YAML FM | MD + YAML FM | MD + YAML FM | MD + YAML FM | MD SOP prose | MD + meta schema | MD/TOML | MD + YAML |
| **File Layout** | `skills/<n>/` + scripts/refs/assets/agents | project/user/bundled/plugin roots | multi-root merge | `~/.hermes/skills/<n>/` | `memory/` L0–L4 tree | 6-layer precedence dirs | `workspace/skills/` | `skills/system/<n>/` |
| **Metadata** | name, description req | frontmatter | frontmatter + location | frontmatter | L-tier tags | SkillSpec typed | version in manifest | runs_on, depends_on_tools |
| **Description** | ★ routing signal | trigger text | catalog desc | catalog desc | SOP title | trigger + description | summary line | XML description |
| **Parameters** | `agents/openai.yaml` | · | · | · | · | meta step params | `{placeholder}`→tool schema | · |
| **Scripts** | ★ `scripts/` | · | via references | ★ `scripts/` | · | ★ `skill_exec` entrypoint | shell bridge | · |
| **Assets** | ★ `assets/` | · | · | ★ `assets/` | · | · | · | · |
| **References** | ★ `references/` | · | lazy read path | ★ `references/` | · | · | · | · |
| **Examples** | · | · | · | templates/ | · | ★ `eval_prompts` fixtures | · | · |
| **Embedded Workflow** | · | · | · | · | plan.md checkpoint | ★ MetaSkill `composition_raw` | channel SOP | · |
| **Nested Skill** | · | · | · | · | ◐ L-tree parent/child | meta step→skill ref | · | · |
| **MetaSkill** | · | · | · | · | · | ★ DAG workflow type | · | ◐ roadmap P3 |
| **Version** | · | · | ◐ snapshot version# | ◐ manifest origin hash | · | ★ lockfile SHA256 | ◐ manifest field | · |

---

# II. Runtime

## §2 — Skill Discovery

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Discover Source** | FS scopes | multi-root scan | 6-source merge | `~/.hermes` scan | memory/ listing | 6-layer loader | workspace scan | canonical + cloud catalog |
| **Search Path** | User/Repo/System/Admin | project→user→bundled | workspace highest | single home dir | L1 index | WORKSPACE highest | `~/.zeroclaw/workspace` | system roots only |
| **Workspace Skill** | ★ repo `skills/` | ★ project dir | ★ `<ws>/skills` | · | · | ★ WORKSPACE layer | ★ workspace | · session isolated |
| **User Skill** | ★ User scope | ★ user dir | `~/.openclaw/skills` | ★ `~/.hermes` | memory/ user | PERSONAL layer | workspace | cloud sync |
| **Global Skill** | ★ System scope | bundled | managed + bundled | bundled sync | · | MANAGED | open-skills sync | 17 canonical |
| **Registry Skill** | · | · | ClawHub (external) | Hermes Hub | · | hub install | ★ zeroclaw-skills | · |
| **Remote Skill** | · | · | remote node refresh | · | · | · | · | ★ cloud catalog + device |
| **Generated Skill** | ◐ Record&Replay | ◐ skillify | workshop proposals | ★ agent-created | ★ crystallized SOP | proposals/ | · | · |
| **Bundled Skill** | ★ system | ★ bundled | ★ lowest priority | ★ skills_sync | seed SOPs | BUNDLED layer | bundled | ★ system/ |
| **Priority** | scope order | source order | ★ 6-level explicit | single tree | L-tier | ★ 6-level explicit | workspace over remote | canonical only |
| **Override** | higher scope wins | · | ★同名高优先级覆盖 | agent patch | file_patch | accept→MANAGED | · | · |
| **Shadow** | · | · | · | ◐ issue: symlink | · | · | · | · |
| **Conflict Resolution** | scope precedence | · | merge by name+priority | last write | manual | lock SHA pin | · | · |
| **Lazy Discovery** | watcher refresh | incremental listing | ★ snapshot at session start | index at session | on file_read | snapshot v11 cache | scan at load | scan at session |
| **File Watch** | ★ | · | ★ chokidar | · | · | · | ◐ sync interval | · |
| **Hot Reload** | ◐ watcher | ◐ delta listing | ★ next-turn refresh | · | · | pipeline rebuild | · | ◐ per-turn prefix |
| **Refresh Policy** | on change | per-turn delta | snapshot version bump | session frozen | reflect cron | **★ every turn** filter_skills | session | **★ every turn** user prefix |

## §3 — Skill Exposure

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Visible to LLM** | metadata block | listing attachment | metadata XML | metadata index | memory dir list | injector output | full or compact | XML + user prefix |
| **Visible to User** | TUI skill toggle | UI skill picker | config UI | CLI/Gateway | file tree | CLI proposals | audit cmd | Flutter catalog |
| **Hidden Skill** | disableModelInvocation equiv | · | ★ frontmatter hide | · | · | disabled gate | · | filter |
| **Progressive Disclosure** | ★ desc→full | ★ listing→tool | ★ catalog→read | ★ list→view | index→read | ★ compact→view | ★ compact mode | ★ catalog→load_skill |
| **Summary Only** | ★ initial catalog | listing metadata | compact XML | skills_list meta | L1 index | compact injector | compact summary | `# Available Skills` |
| **Full Prompt Loaded** | on @mention | Skill tool | read tool lazy | skill_view / --skills preload | file_read | skill_view / meta_invoke | always-flag full | load_skill body |
| **Description Only** | ★ default expose | ★ attachment | ★ default | ★ default | title only | compact mode | compact | ★ default |
| **Explicit Invocation** | ★ `/` `@skill` | ★ Skill tool slash | read tool | ★ `/<skill>` | file_read path | skill_view / `/meta` | read file | ★ load_skill |
| **Implicit Invocation** | ★ shell pattern match | · | · | ◐ auto from desc | related_sop hint | ◐ auto_trigger meta | · | ◐ Toollery decide |

## §4 — Skill Recommendation

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Trigger** | mention / shell | usage decay UI | · | slash / nudge | related_sop | **★ per-turn pipeline** | · | Toollery hook |
| **Description Match** | ◐ implicit | · | · | · | · | ◐ lexical leg | · | ◐ |
| **Embedding Match** | · | EXPERIMENTAL search | · | · | · | ★ semantic leg RRF | · | ◐ plugin slot |
| **LLM Decide** | model picks mention | · | · | review agent | agent picks SOP | Dream classify | · | NLU context |
| **Rule Based** | shell regex | bundled+MCP filter | skillFilter whitelist | · | · | pinned always | · | runs_on filter |
| **Task Pattern** | · | · | workshop regex | review prompt | goal mode | auto_propose chains | · | · |
| **Tool Pattern** | ★ implicit shell | · | · | · | tool in SOP | requires_tools gate | · | depends_on_tools soft |
| **History Pattern** | · | ★ 7d decay score | · | session_search FTS | access stats | Dream co-occurrence | · | · |
| **User Preference** | TUI enabled set | survey apply | agent config | · | · | · | · | device profile |
| **Frequency** | · | ★ decay ranking | · | · | ◐ access stats | trigger accuracy | · | · |
| **Ranking** | · budget truncate | ◐ decay sort | alpha + budget | · | ◐ stats | **★ RRF fusion** | · | ◐ embedding |
| **Multi Skill Ranking** | · | · | · | · | · | ★ top-k=5 | · | ◐ multi filter |
| **Budget Aware** | ★ 2% / 8K cap | attachment budget | 150 / 18K cap | size limit | anchor prompt | injector truncate | compact mode | · |

## §5 — Skill Runtime

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Per Turn Loading** | ★ mentioned only | ★ delta listing | ◐ snapshot reuse | · frozen index | · | **★ filter+inject** | · session | **★ user prefix** |
| **Per Session** | SkillsManager cache | sentSkillNames map | ★ snapshot | frozen prefix | anchor rebuild | snapshot cache | load at start | session scan |
| **Per Agent** | turn_skills config | per agentId map | ★ skillFilter | same index | · | agent FSM | · | session instance |
| **Per SubAgent** | ★ child turn_skills | ★ frontmatter preload | ◐ filter inherit | ◐ delegate | · | meta agent step | ◐ spawn | ❌ rescans only |
| **Dynamic Loading** | injection.rs | Skill tool | read tool | skill_view | file_read | skill_view | read at location | load_skill |
| **Dynamic Unloading** | not in turn | · | lazy default | · | anchor | compact injector | compact | ToolResult only |
| **Parallel Skills** | multi mention | multi invoked | multi read | multi view | · | meta parallel steps | · | multi load |
| **Skill Chain** | · | · | · | · | · | ★ MetaSkill steps | SOP chain | · |
| **Skill Graph** | · | · | · | · | · | ★ MetaOrchestrator DAG | · | · |
| **Skill Cache** | SkillsManager | sentSkillNames | snapshot prompt | frozen memory | working dict | schema v11 | registry | prefix cache |
| **Skill Context Budget** | ★ metadata cap | per-skill cap | char/skill cap | · | anchor | governor | compact/full | · |
| **Skill Compression** | truncate desc | compact attachment | ~/ path compress | · | history tags | compact injector | compact mode | · |
| **Skill Summarization** | compact hooks | · | compaction-safeguard | ContextCompressor | compress tags | session compact | auto_compact | ★ LLM compact |
| **Skill Pruning** | omit from catalog | · | binary search drop | · | · | gate disabled | · | skill_name_filter |

## §6 — Skill Offload

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Offload to SubAgent** | ★ Task spawn | ★ Task tool isolate | subagent session | ★ delegate_task | subprocess | meta agent step | SubAgentRegistry | run_subagent |
| **Offload to Tool** | read/MCP | Skill tool | read tool | skill_view | file_read | skill_exec | SkillToolHandler | load_skill |
| **Offload to Workflow** | update_plan | · | cron isolated | · | plan.md | ★ MetaSkill | channel SOP | · |
| **Offload to Memory** | generate_memories | TodoWrite JSON | memory search | MEMORY.md frozen | ★ L2/L3 SOP | Dream→MEMORY | fact extract | MEMORY.md |
| **Offload to MCP** | ★ MCP tools | MCP in search | MCP plugins | MCP tools | · | MCP | ★ MCP | MCP planned |
| **Offload to Human** | Guardian approval | ★ Survey UI | workshop pending | · | · | gate refuse | audit user | · |

## §7 — Skill Usage

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Direct Prompt** | ★ injected `<skill>` | Skill tool body | read→prompt | skill_view body | SOP text | skill_view | read content | load_skill result |
| **Tool Wrapper** | · | Skill as tool | · | skills as tools | · | skill_exec | SkillToolHandler | load_skill tool |
| **Code** | scripts/ | · | · | scripts/ | · | entrypoints | shell bridge | · |
| **Workflow** | agent_jobs | · | cron agent | · | morphling | ★ meta_invoke | · | · |
| **Planner** | ★ update_plan | TodoWrite | · | · | plan mode | meta steps | · | · |
| **SOP** | · | · | · | · | ★ primary form | · | ◐ | · |
| **Agent** | ★ multi_agents | ★ subagent | subagent | delegate | team BBS | meta agent | subagent spawn | subagent relay |
| **MCP** | ★ | bundled+MCP | plugins | ★ | · | ★ | ★ | ◐ |
| **Command** | ★ implicit shell | slash | slash | slash | · | CLI | zeroclaw CLI | device SkillLoad |

---

# III. Lifecycle

## §8 — Skill lifecycle stages

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Created By** | human / skill-creator | skillify / human | workshop / human | ★ agent skill_manage | ★ agent crystallize | auto_propose / meta-creator | human | human canonical |
| **Imported** | FS copy | project add | ClawHub / extraDirs | Hub install | · | hub install | open-skills sync | cloud deploy |
| **Generated** | Record&Replay | skillify session | workshop heuristic | background review | long_term_update | Dream / auto_propose | · | · |
| **Human Written** | ★ primary | ★ project skills | workspace files | bundled | seed SOPs | managed | user workspace | ★ 17 canonical |
| **AI Written** | · | ◐ patches | ◐ workshop apply | ★ skill_manage | ★ SOP write | proposals | · | · |
| **Reviewed** | Guardian (tools) | ★ Survey UI | LLM reviewer | bg review agent | L0 protocol | 4-gate + E2E | audit scan | · |
| **Approved** | TUI test / user | user survey | auto/manual policy | · agent self | agent self | gates.json pass | user audit | · |
| **Published** | FS write | apply patch | apply proposal | immediate write | file_patch | accept→MANAGED | load skill | canonical deploy |
| **Deprecated** | disable toggle | · | · | · | cleanup SOP | reject | · | · |
| **Disabled** | write_skill_enabled | · | disableModelInvocation | · | · | disabled gate | · | skill_name_filter |
| **Deleted** | FS delete | user delete | file delete | skill_manage delete | manual | reject + rm | rm dir | · |
| **Archived** | · | · | quarantine store | · | L4 sessions | proposals history | hygiene cron | JSONL log |
| **Rollback** | git / manual | · | · | · | · | · | · | ❌ needed |
| **Lifecycle Score** | 6/13 | 8/13 | 9/13 | 10/13 | 7/13 | **12/13** | 5/13 | 4/13 |

---

# IV. Evolution & Quality

## §9 — Skill Evolution

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Reflection** | ReviewTask code | ★ 5-turn hook | ◐ dreaming | ★ bg review | reflect cron | ★ Dream | loop detect | · |
| **Self Reflection** | · | skillImprovement | workshop self | ★ review prompt | goal mode | Dream LLM | · | · |
| **Teacher** | · | aux small model | LLM reviewer | review agent | · | E2E judge | · | · |
| **RL** | · | · | ◐ trajectory | ★ Atropos | · | · | · | · |
| **GRPO** | · | · | OpenClaw-RL ext | ◐ RL tool | · | · | · | · |
| **Preference** | · | survey accept | · | · | · | · | · | · |
| **Pairwise** | · | · | · | · | · | meta vs baseline | · | · |
| **Candidate** | · | JSON patches | ★ proposals store | direct create | SOP draft | ★ proposals/ | · | · |
| **Merge** | · | user apply | append/replace | patch | file_patch | accept_proposal | · | · |
| **Split** | · | · | · | · | · | · | · | · |
| **Rewrite** | manual | section patches | replace mode | edit | morphling | meta rewrite | · | · |
| **Summarize** | memories distill | · | · | · | · | Dream summary | fact extract | compact summarize |
| **Refactor** | · | · | · | · | · | meta-skill-creator | · | · |
| **Auto Patch** | · | ◐ after survey | ◐ auto policy | ★ skill_manage | ★ file_patch | after gates | · | · |
| **Auto Delete** | · | · | · | ★ skill_manage | · | reject | · | · |
| **Auto Version** | · | · | snapshot# | hash | · | lock SHA | field | · |

## §10 — Skill Quality

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Benchmark** | integration tests | · | qa-lab | · | model logs | trigger accuracy | · | bench plan |
| **Regression** | suite/skill_* | · | · | · | · | ★ eval_prompts | · | · |
| **Replay** | Record&Replay | session JSONL | trajectory | JSONL+DB | · | decision log | · | interaction_log |
| **Unit Test** | ★ Rust tests | · | · | · | · | pytest | audit tests | Rust tests |
| **Integration Test** | ★ extensive | · | e2e ext | · | · | runtime_e2e | · | ◐ |
| **Sandbox** | · | · | · | · | · | · | · | · |
| **Simulation** | TestCodex | · | · | Atropos env | · | · | · | · |
| **Online Eval** | analytics | usage decay | · | · | access stats | trigger acc | economic | · |
| **A/B** | · | · | · | · | · | ★ meta vs baseline | · | · |
| **Success Rate** | · | · | · | · | verify axiom | gate metrics | · | · |
| **Reward** | · | · | trajectory reward | RL reward | · | · | · | · |
| **Token Cost** | budget cap | attachment cap | char cap | · | ★ anchor | governor | compact | user prefix |
| **Latency** | · | SideQuery small | · | bg async | · | pipeline | · | · |

---

# V. Governance

## §11 — Skill Governance

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Permission** | TUI approval | project scope | agent config | · | · | policy chain | · | ToolDomains |
| **Capability** | tool allow | · | tool + read | toolsets | 9 atomic tools | requires_tools | tool schema | runs_on |
| **Risk** | ★ Guardian JSON | · | scanner quarantine | skills_guard | · | gates.json | audit patterns | · |
| **Signature** | · | · | · | · | · | lock SHA | · | · |
| **Trust Level** | Admin scope | project vs bundled | managed tiers | bundled vs user | · | MANAGED vs BUNDLED | registry disclaimer | canonical |
| **Audit** | · | · | skill-scanner | _security_scan | · | hub quarantine | ★ skills/audit.rs | · |
| **Provenance** | · | · | proposal metadata | origin hash | · | proposal source | sync source | cloud origin |
| **Registry** | · | · | ClawHub | Hermes Hub | · | hub | ★ zeroclaw-skills | skill_catalog.json |
| **Marketplace** | · | · | ★ ClawHub risk | Hub | · | hub | community | · |
| **Review** | Guardian | Survey UI | LLM reviewer | bg review | L0 SOP | 4-gate | CI structure | · |
| **Owner** | · | · | · | · | · | · | contributor | team curated |
| **License** | · | · | · | · | · | · | repo LICENSE | · |

---

# VI. Agent Integration

## §12 — Skill Relationship

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Parent Skill** | · | · | · | · | L-tree | · | · | · |
| **Child Skill** | · | · | · | · | nested SOP | step refs | · | · |
| **Meta Skill** | · | · | · | · | · | ★ MetaSkill type | · | P3 |
| **Composite Skill** | · | · | · | · | · | composition_raw | · | · |
| **Complementary Skill** | · | ◐ subagent preload | per-agent filter | delegate | · | meta multi-skill | · | ❌ |
| **Alternative Skill** | · | · | · | · | · | · | · | · |
| **Dependency** | · | · | · | · | · | requires_tools | · | depends_on_tools soft |
| **Skill Graph** | · | · | · | · | · | ★ MetaOrchestrator | · | · |
| **Skill DAG** | · | · | · | · | · | ★ meta steps | · | · |

## §13 — Multi-Agent Skill

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Shared Skill** | repo scope | project | shared managed | ~/.hermes | memory shared | MANAGED | workspace | canonical |
| **Private Skill** | user scope | user | per-agent ws | user created | user SOP | PERSONAL | · | device profile |
| **Per Agent Skill** | turn_skills | agentId map | ★ skillFilter | same index | · | FSM agent | · | session |
| **Per Role Skill** | · | subagent profile | agent list[] | · | · | meta roles | team topology | · |
| **Complementary Skill** | child subset | ★ preload list | filter diff | ◐ | · | DAG steps | · | ❌ |
| **Skill Negotiation** | · | · | · | · | BBS | · | · | · |
| **Skill Transfer** | · | tool result | summary | delegate summary | · | subagent report | · | relay |
| **Skill Borrow** | · | · | · | · | · | · | · | · |
| **Skill Broadcast** | · | · | · | · | · | · | · | cloud catalog |
| **Skill Isolation** | ★ child no parent skills | ★ sub context | subagent prompt | ★ delegate | subprocess | one-shot agent | registry | partial |

## §14 — Memory Integration

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Episodic** | thread history | session JSONL | trajectory | session DB | L4 sessions | pipeline log | history | JSONL |
| **Semantic** | memories config | · | memory search | MEMORY.md | L2 facts | hybrid chunks | facts | MEMORY.md |
| **Vector** | · | · | ◐ embedding | · | · | ★ hybrid | · | ◐ planned |
| **Graph** | · | · | · | · | · | meta DAG | · | · |
| **RAG** | · | · | ★ hybrid FTS+vec | FTS5 search | file_read | ★ retrieval | · | Toollery |
| **KV** | prefix cache | · | snapshot cache | ★ frozen prefix | anchor | per-turn inject | · | user prefix cache |
| **Summary** | compact | compact | compaction | compressor | compress | compact | auto_compact | ★ compact |
| **Reflection** | distill | skillImprove | dream | bg review | reflect | Dream | consolidation | · |
| **Long-term** | AGENTS.md | · | MEMORY.md | MEMORY.md | L3 SOP tree | Dream promote | memory hygiene | MEMORY.md |

---

# VII. RL Readiness

## §15 — RL Readiness (SkillRL / Claw-R1)

| Dimension | Codex | Claude Rev | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
|-----------|:-----:|:----------:|:--------:|:------:|:------------:|:-----------:|:--------:|:------:|
| **Step Trace** | ◐ dispatch trace | session steps | ★ trajectory metadata | JSONL steps | model log | ★ PipelineStepRecord | OTel | ◐ interaction_log |
| **Trajectory** | rollout | JSONL export | ★ openclaw-trajectory | Atropos traj | · | TraceContext | · | JSONL |
| **Tool Trace** | ★ tool_dispatch_trace | tool results | trajectory tools | tool log | tool log | decision log | tool log | interaction_log |
| **Reward** | · | · | ◐ trajectory reward | ★ env reward | · | · | · | · |
| **Verifier** | tests | · | qa-lab | env verify | VERIFY SOP | runtime_e2e | audit | · |
| **Replay** | Record&Replay | session replay | trajectory read | DB replay | · | decision replay | · | log replay |
| **Dataset** | · | · | trajectory export | RL datasets | · | · | · | · |
| **Offline RL** | · | · | ★ OpenClaw-RL repo | ★ Atropos | · | · | · | · |
| **Online RL** | · | · | · | rl_training_tool | · | · | · | · |
| **SkillRL Compatible** | ◐ traces only | ◐ traces | ◐ traj no SkillBank | ◐ closest | ◐ SOP mine | ◐ proposals | · | ◐ log only |
| **Claw-R1 Compatible** | ◐ | ◐ | ★ best OSS | ★ | · | ★ pipeline log | · | ◐ hooks |

---

# Aggregate scores (1–10)

| Framework | Data Model | Runtime | Lifecycle | Evolution | Governance | Agent Integ. | RL Ready | **Overall** |
|-----------|:----------:|:-------:|:---------:|:---------:|:----------:|:------------:|:--------:|:-----------:|
| **OpenSquilla** | 9 | 9 | 12 | 9 | 8 | 9 | 6 | **9.0** |
| **Hermes** | 8 | 8 | 10 | 9 | 5 | 7 | 8 | **8.1** |
| **OpenClaw** | 8 | 8 | 9 | 7 | 7 | 8 | 7 | **8.0** |
| **Claude Rev** | 7 | 9 | 8 | 7 | 6 | 9 | 4 | **7.7** |
| **Codex** | 9 | 8 | 6 | 3 | 8 | 7 | 4 | **7.2** |
| **TaiChu** | 6 | 7 | 4 | 1 | 3 | 5 | 3 | **5.0** |
| **ZeroClaw** | 6 | 5 | 5 | 2 | 7 | 4 | 2 | **5.0** |
| **GenericAgent** | 5 | 5 | 7 | 6 | 2 | 3 | 2 | **4.8** |

*Scores are qualitative rollup from matrix coverage; not benchmark metrics.*

---

# TaiChu synthesis (from matrix)

## Borrow (by mega-category)

| Category | Primary sources |
|----------|----------------|
| Data Model | Codex layout + OpenClaw multi-root + ZeroClaw trust metadata |
| Runtime | Codex progressive disclosure + OpenSquilla RRF + Claude incremental listing + **runs_on keep** |
| Lifecycle | OpenSquilla gates + Hermes CRUD (candidate only) + Claude invoked_skills |
| Evolution | OpenSquilla proposals + GenericAgent miner + Hermes review (with read-before-write) |
| Governance | ZeroClaw audit + OpenSquilla gates + Codex Guardian |
| Agent Integration | Claude subagent bundles + OpenSquilla MetaSkill + OpenClaw skillFilter |
| RL Readiness | OpenClaw trajectory + Claw-R1 step schema on interaction_log |

## Do NOT borrow

- Hermes direct production patch without gate
- OpenClaw marketplace trust model wholesale
- GenericAgent ungated crystallize
- ZeroClaw assumption that CI = security boundary

---

## Related documents

| Doc | Role |
|-----|------|
| [skill-lifecycle-full-matrix.md](skill-lifecycle-full-matrix.md) | Prior 9-stage condensed matrix |
| [skill-lifecycle-and-dynamic-loading-survey.md](skill-lifecycle-and-dynamic-loading-survey.md) | Per-repo L3 narrative evidence |
| [repos/*.md](repos/) | 20-dimension repo cards |
| [web-expanded-lifecycle-matrix-merged.md](web-expanded-lifecycle-matrix-merged.md) | **Web 扩展 lifecycle** 合并（公开 quotes + L3 修正） |
| [survey-reports/](survey-reports/) | **8 complete** 12-section reports + evidence index |
| [config/survey-matrix-dimensions.yaml](../config/survey-matrix-dimensions.yaml) | Machine-readable dimension index |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-07-08 | Initial 165-dimension Agent Skill Architecture Survey Matrix |
