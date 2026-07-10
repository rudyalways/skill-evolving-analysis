---
id: N2026-07-08-009
title: 八仓库综合架构调研（20 维度 × 8 项目）
date: 2026-07-08
tags: [comprehensive-survey, oss-inventory, skill-evolution, harness]
status: active
related: [N2026-07-08-008, N2026-07-08-007]
---

# 八仓库综合架构调研

> **方法**：本机全量源码访问（`/Users/maybewu/Documents/Projects/`），非 GitHub 网页增量阅读。  
> **Claude Code 逆向**：确认为 **[oboard/claude-code-rev](https://github.com/oboard/claude-code-rev)**（社区 source-map 还原，非 Anthropic 官方）。  
> **TaiChu**：私有 Gitea，路径 `drafts/zk/TaiChu`。  
> **Cursor**：非开源，本调研不含源码级分析（仅官方 blog 结论见 `official-product-gap-consensus.md`）。

---

## 文档结构

| 文件 | 内容 |
|------|------|
| 本文 | 总览矩阵、Skill Evolution 流水线、评级、TaiChu 集成优先级 |
| [repos/openclaw.md](repos/openclaw.md) | OpenClaw 20 维度详析 |
| [repos/hermes-agent.md](repos/hermes-agent.md) | Hermes 20 维度详析 |
| [repos/codex.md](repos/codex.md) | Codex 20 维度详析 |
| [repos/opensquilla.md](repos/opensquilla.md) | OpenSquilla 20 维度详析 |
| [repos/genericagent.md](repos/genericagent.md) | GenericAgent 20 维度详析 |
| [repos/zeroclaw.md](repos/zeroclaw.md) | ZeroClaw 20 维度详析 |
| [repos/claude-code-rev.md](repos/claude-code-rev.md) | Claude Code Rev 20 维度详析 |
| [repos/taichu.md](repos/taichu.md) | TaiChu 20 维度详析 |

---

## 一、总览对比矩阵

### 1.1 核心能力（★ = 强 / ◐ = 部分 / · = 无）

| Project | Skills | Memory | Reflection | Skill Evolution | Harness | Workflow | RL Ready | 综合 |
|---------|:------:|:------:|:----------:|:---------------:|:-------:|:--------:|:--------:|:----:|
| **OpenClaw** | ★★★ | ★★★ | ★★ | ★★★ | ★★★ | ★★ | ◐ | **A** |
| **Hermes** | ★★★ | ★★★ | ★★ | ★★★ | ★★★ | ★★ | ★★★ | **A+** |
| **Codex** | ★★★ | ★★ | ★ | · | ★★★ | ★★ | ◐ | **A-** |
| **OpenSquilla** | ★★★ | ★★★ | ★★ | ★★★ | ★★★ | ★★★ | ◐ | **A+** |
| **GenericAgent** | ◐ | ★★ | ★★ | · | ◐ | ★★ | · | **B** |
| **ZeroClaw** | ★★ | ★★★ | ◐ | · | ★★ | ★★ | · | **B+** |
| **Claude Code Rev** | ★★★ | ★★★ | ★★ | ★★ | ★★★ | ★★ | · | **A** |
| **TaiChu** | ★★★ | ◐ | · | · | ★★ | · | · | **B+** |

*TaiChu Skills/Harness 强在端云执行与 catalog；Evolution/Reflection 为明确缺口。*

### 1.2 Skill Evolution 专项矩阵

| Project | 表示 | 加载 | 自动生成 | 自动更新 | 版本 | 排序 | 候选池 | 自动合并 | Gate |
|---------|:----:|:----:|:--------:|:--------:|:----:|:----:|:------:|:--------:|:----:|
| OpenClaw | SKILL.md | lazy+snapshot | skill-workshop | append/replace | snapshot# | · | proposals | auto policy | scanner |
| Hermes | SKILL.md | progressive | background review | skill_manage | manifest hash | · | · | · | skills_guard |
| Codex | SKILL.md | metadata budget | skill-creator 样本 | 文件系统 | · | · | · | · | approval test |
| OpenSquilla | SKILL.md+meta | 6-layer+RRF | auto_propose | accept_proposal | lock SHA | RRF+Dream | proposals | accept | 4-gate |
| GenericAgent | *_sop.md | on-demand read | · | file_patch | · | access stats | · | · | · |
| ZeroClaw | SKILL.md/toml | workspace sync | · | · | manifest field | · | · | · | audit |
| Claude Rev | SKILL.md | 3-channel | skillify | skillImprovement | · | decay 7d | · | user apply | survey UI |
| TaiChu | SKILL.md | catalog+load_skill | · | · | · | · | · | · | · |

---

## 二、Skill Evolution 流水线覆盖

```text
Trajectory → Reflection → Skill Candidate → Evaluation → Version → Deployment → Runtime Retrieval → Online Metrics
```

| Stage | OpenClaw | Hermes | Codex | OpenSquilla | GenericAgent | ZeroClaw | Claude Rev | TaiChu |
|-------|:--------:|:------:|:-----:|:-----------:|:------------:|:--------:|:----------:|:------:|
| **Trajectory** | ★ JSONL trace | ★ JSONL+DB | ◐ dispatch trace | ★ pipeline log | ◐ model logs | ◐ OTel | ★ session JSONL | ◐ interaction JSONL |
| **Reflection** | ◐ dreaming/MS Teams | ★ bg review | · | ★ Dream | ◐ goal mode | ◐ loop detect | ★ skillImprovement | · |
| **Skill Candidate** | ★ proposals | ◐ agent create | · | ★ proposals | · | · | ★ JSON patches | · |
| **Evaluation** | ◐ scanner | ◐ guard | ◐ approval | ★ 4-gate+E2E | ◐ VERIFY | ◐ audit | ◐ survey | · |
| **Version** | ◐ snapshot# | ◐ origin hash | · | ★ lock SHA | · | ◐ field | · | · |
| **Deployment** | ★ auto/manual | ★ skill_manage | ◐ FS | ★ accept | ◐ file_patch | ◐ load | ◐ user apply | ★ load_skill |
| **Runtime Retrieval** | ◐ lazy read | ★ skill_view | ★ @mention | ★ RRF | ◐ file_read | ◐ inject | ★ 3-channel | ★ runs_on |
| **Online Metrics** | ◐ qa-lab | · | ◐ analytics | ◐ trigger acc | ◐ access stats | ◐ economic | ★ usage decay | · |

**唯一接近全链路的组合**（无单仓实现）：

```
OpenClaw trajectory + OpenSquilla gates + Hermes skill_manage + Claude Rev invoked_skills compaction
```

---

## 三、Harness + Skill Evolution 研究问题速查

| Topic | 最强实现 | 关键路径 |
|-------|---------|---------|
| Skill 表示 | 通用 SKILL.md；GenericAgent 用 L3 SOP | `skill-contract.ts`, `ga.py` memory/ |
| Skill Loading | OpenClaw lazy+snapshot；OpenSquilla 6-layer+RRF | `workspace.ts`, `skills/retrieval/` |
| Skill Evolution | OpenSquilla proposals；OpenClaw skill-workshop；Hermes skill_manage | 见上表 |
| Reflection 时机 | Hermes post-turn；Claude Rev 每 5 turn；OpenSquilla Dream cron | `run_agent.py:9622`, `skillImprovement.ts` |
| Memory 类型 | OpenClaw/OpenSquilla hybrid FTS+vector；GenericAgent L1–L4 | `memory-search.ts`, `memory/` |
| Harness 扩展 | OpenClaw plugin harness；Codex typed hooks；OpenSquilla stage harness | `harness/types.ts`, `hook_runtime.rs` |
| Evaluation | OpenSquilla runtime_e2e judge；OpenClaw qa-lab | `runtime_e2e.py`, `qa-lab/` |
| Self-play | 全无 | — |
| RL readiness | **Hermes** Atropos+RL tool；OpenClaw trajectory export | `hermes_base_env.py`, `trajectory/` |
| Step-level traces | OpenClaw `openclaw-trajectory`；OpenSquilla `TraceContext` | `trajectory/runtime.ts` |
| Skill versioning | OpenSquilla lock SHA；OpenClaw snapshot version | `hub/lockfile.py`, `refresh-state.ts` |
| Skill ranking | OpenSquilla RRF；Claude Rev decay；OpenClaw memory ranking only | `fusion.py`, `skillUsageTracking.ts` |
| Candidate skills | OpenSquilla proposals；OpenClaw skill-workshop store | `proposals_lib.py`, `skill-workshop/store.ts` |
| Automatic merge | OpenSquilla accept；OpenClaw auto policy；Hermes patch | `accept_proposal`, `workshop.ts` |

---

## 四、各仓一句话定位

| Repo | 定位 |
|------|------|
| **OpenClaw** | 最大开源 multi-channel gateway；memory dreaming + **skill-workshop** 进化；trajectory JSONL |
| **Hermes** | 唯一内置 **RL/Atropos** 路径 + **skill_manage** 运行时 CRUD + 后台 review |
| **Codex** | 官方生产级 Rust harness；typed hooks + Guardian；skills 故意不做自进化 |
| **OpenSquilla** | **Skill evolution 产品化最完整**：proposals + 4-gate + Dream + meta-skill DAG |
| **GenericAgent** | 极简 self-evolving；L1–L4 SOP 记忆哲学；无 SKILL.md 标准 |
| **ZeroClaw** | Rust 轻量 runtime；loop detection + subagent registry；skill 仅 audit/load |
| **Claude Code Rev** | 逆向参考：**invoked_skills compaction 存活** + skillImprovement 5-turn 循环 |
| **TaiChu** | 端云 skill 执行最强（runs_on + load_skill wire）；evolution 全缺 |

---

## 五、TaiChu 集成路线图（源码证据优先级）

| P | 来源 | 能力 | TaiChu 落点 |
|---|------|------|------------|
| **P0** | Claude Rev | `invoked_skills` post-compaction 重注入 | `compaction.rs` + session state |
| **P0** | Hermes | `_spawn_background_review` + `skill_manage` | taichu-service tools |
| **P0** | Claude Rev | SubAgent `profile.skills` preload | `session/manager.rs` |
| **P1** | OpenSquilla | `proposals_lib` + gates.json | `~/.taichu/proposals/` |
| **P1** | OpenClaw | trajectory JSONL export | agent_loop observability |
| **P1** | Claude Rev | usage decay ranking | Flutter skill UI |
| **P2** | OpenSquilla | Dream signal classification | memory promotion |
| **P2** | GenericAgent | L0 memory_management_sop | skill update protocol |
| **P2** | ZeroClaw | loop detection | device automation safety |
| **P3** | OpenSquilla | meta-skill DAG | 单 skill 生命周期稳定后 |

---

## 六、与 SkillRL / Claw-R1 的关系

| 论文层 | 八仓库最强覆盖 | 仍缺 |
|--------|--------------|------|
| **Claw-R1 Gateway** | OpenClaw, OpenSquilla, TaiChu | Step RPC 统一 export |
| **Claw-R1 Step Pool** | OpenClaw trajectory, OpenSquilla trace | 无训练用 middleware |
| **SkillRL SkillBank** | Hermes/OpenSquilla managed dirs | embedding retrieval + success rate |
| **SkillRL Failure mining** | GenericAgent L3, Hermes review prompt | structured failure tags |
| **SkillRL GRPO** | Hermes RL tool only | 无 in-repo trainer |
| **SkillRL Validation** | OpenSquilla 4-gate | automated benchmark on skill |

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-08 | 初版：20 维度调研框架 + 8 项目矩阵 + 流水线覆盖 + TaiChu 路线图 |
