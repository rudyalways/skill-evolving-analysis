---
id: N2026-07-08-007
title: 八仓库身份确认 + 源码调研框架（回应外部 AI 无法读本地路径）
date: 2026-07-08
tags: [oss-inventory, research-framework, source-analysis]
status: active
related: [N2026-07-08-006, N2026-07-08-005]
---

# 八仓库身份确认 + 源码调研框架

> **本机路径前缀**：`/Users/maybewu/Documents/Projects/`（不是 `/Users/x/`）  
> Cursor 环境可直接读源码；无需 zip / File Library。

---

## 一、身份确认（消除歧义）

| 你列的路径 | 本机实际路径 | 公开仓库 | 确认身份 |
|-----------|-------------|:--------:|----------|
| `oss/openclaw` | `.../oss/openclaw` | ✅ | **[openclaw/openclaw](https://github.com/openclaw/openclaw)** — Personal AI Assistant（🦞），**不是** OpenClaw-RL 论文项目 |
| `oss/experimental/claude-code-rev` | `.../oss/experimental/claude-code-rev` | ✅ | **[oboard/claude-code-rev](https://github.com/oboard/claude-code-rev)** — 社区从 source map 还原的 Claude Code，非 Anthropic 官方 |
| `drafts/zk/TaiChu` | `.../drafts/zk/TaiChu` | ❌ 私有 Gitea | **[taichu.fun/gitea/SystemAgentDev/TaiChu](https://taichu.fun/gitea/SystemAgentDev/TaiChu.git)** — 端云兼容 agent 主仓 |
| `oss/genericagent` | `.../oss/genericagent` | ✅ | **[lsdefine/genericagent](https://github.com/lsdefine/genericagent)** — 自标 "self-evolving" 极简 agent |
| `oss/codex` | `.../oss/codex` | ✅ | **[openai/codex](https://github.com/openai/codex)** — OpenAI 官方 Codex CLI (Rust) |
| `oss/opensquilla` | `.../oss/opensquilla` | ✅ | **[opensquilla/opensquilla](https://github.com/opensquilla/opensquilla)** — Token-efficient agent microkernel |
| `oss/zeroclaw` | `.../oss/zeroclaw` | ✅ | **[zeroclaw-labs/zeroclaw](https://github.com/zeroclaw-labs/zeroclaw)** — Rust 轻量 agent runtime |
| `oss/hermes-agent` | `.../oss/hermes-agent` | ✅ | **[nousresearch/hermes-agent](https://github.com/nousresearch/hermes-agent)** — Nous Research 自改进 agent |

### 常见混淆澄清

| 名字相似 | 本仓库是 | 不是 |
|---------|---------|------|
| openclaw | 个人 AI 助手 gateway | OpenClaw-RL (arXiv:2603.10165, Gen-Verse) |
| hermes-agent | NousResearch/hermes-agent | 其他 Hermes 相关小项目 |
| genericagent | lsdefine/genericagent | 无其他主流同名 |
| zeroclaw | zeroclaw-labs/zeroclaw | OpenClaw 内有一份 reference copy |

---

## 二、建议调研顺序（与外部建议一致，附本机状态）

| 优先级 | 仓库 | 理由 | 本机 HEAD 日期 |
|:------:|------|------|---------------|
| 1 | **codex** | 官方 CLI + memories 2-phase distill | 2026-06-07 |
| 2 | **openclaw** | 最大开源 harness 之一 + dreaming | 2026-04-27 |
| 3 | **hermes-agent** | 显式 `skill_manage` 自改进 | 2026-04-10 |
| 4 | **genericagent** | SOP 结晶 + morphling | 2026-06-29 |
| 5 | **zeroclaw** | 轻量 memory consolidation | 2026-03-04 |
| 6 | **opensquilla** | meta-skill + dream factory | 2026-07-01 |
| 7 | **claude-code-rev** | memdir + /dream 参考 | 2026-04-08 |
| 8 | **TaiChu** | 内部集成目标 | 2026-06-11 |

---

## 三、源码目录扫描（本机 find 结果）

| 目录模式 | openclaw | claude-rev | TaiChu | genericagent | codex | opensquilla | zeroclaw | hermes |
|----------|:--------:|:----------:|:------:|:------------:|:-----:|:-----------:|:--------:|:------:|
| `skills/` | ✅ 多处 | ✅ src/skills | ✅ 17+ canonical | ❌ | ✅ codex-rs | ✅ 91 SKILL | ✅ loader | ✅ 122 |
| `memory/` | ✅ memory-core | ✅ memdir | ⚠️ deploy only | ✅ **核心** | ✅ memories/ | ✅ dream/ | ✅ src/memory | ✅ plugins |
| `hooks/` | ✅ src/hooks | ✅ src/hooks | ✅ .cursor/.claude | ❌ | ✅ codex-rs | ✅ engine/hooks | ✅ src/hooks | ❌ |
| `reflection/` | ❌ | ❌ | ❌ | ⚠️ reflect/ | ❌ | ❌ | ❌ | ❌ |
| `evaluator/` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `benchmark/` | ⚠️ android | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `trainer/` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `workflow/` | ⚠️ prose ext | ❌ | ✅ agent-runtime | ❌ | ❌ | ⚠️ meta-DAG | ❌ | ❌ |
| `agent_loop/` | ⚠️ src/agents | ❌ | ⚠️ core | ✅ agent_loop.py | ❌ | ✅ engine | ✅ src/agent | ✅ run_agent.py |
| `planner/` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `experience/` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `trajectory/` | ✅ src/trajectory | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **SKILL.md** | 83 | 2 | 150* | 0 | 18 | 91 | 0 | 122 |

*TaiChu 150 含 `.agent-runtime` 快照重复；canonical ~17

---

## 四、横向对比表（调研维度 × 8 仓库）

图例：✅ 已实现 · ⚠️ 部分 · ❌ 无 · 📋 文档/样本

| 维度 | Codex | OpenClaw | Hermes | GenericAgent | ZeroClaw | OpenSquilla | Claude-Rev | TaiChu |
|------|:-----:|:--------:|:------:|:------------:|:--------:|:-----------:|:----------:|:------:|
| **Runtime Architecture** | Rust CLI | TS gateway + extensions | Python agent+gateway | Python ~3K LOC | Rust runtime | Python microkernel | TS restored CLI | Rust svc + Flutter |
| **Agent Loop** | codex-rs/core | src/agents | run_agent.py | agent_loop.py | src/agent | engine/ | src/cli | core/agent-session |
| **Harness** | ext/skills + hooks | src/ + extensions | agent/ + toolsets | ga.py | src/gateway | engine/hooks | shims + src | services/rust |
| **Skill 表示** | SKILL.md | SKILL.md | SKILL.md | L3 *_sop.md | SKILL.md (user) | SKILL.md + meta | SKILL.md | SKILL.md + system |
| **Skill 生命周期** | load/version API | ClawHub sync | skill_manage CRUD | morphling→SOP | workspace sync | proposals flow | skillImprovement | catalog+load_skill |
| **Skill 自动生成** | 📋 skill-creator | ⚠️ skill-creator | ✅ skill_manage | ✅ L3 结晶 | ❌ | ✅ meta-skill-creator | ⚠️ skillify | ❌ |
| **Skill 自动更新** | ❌ | ⚠️ Workshop | ✅ patch/write | ✅ start_long_term_update | ❌ | ✅ auto_propose | ⚠️ improvement | ❌ |
| **Skill 淘汰/Version** | version API | ❌ | delete skill | SOP archive | ❌ | proposal accept/reject | ❌ | ❌ |
| **Memory** | 2-phase memories | memory-core+dream | MEMORY.md+plugins | L1-L4 | consolidation cron | dream factory | memdir | compaction only |
| **Hooks** | codex-rs/hooks | src/hooks | cron/gateway | ❌ | src/hooks | engine/hooks | src/hooks | .cursor/.claude |
| **Reflection** | ❌ | compaction distill | memory nudge | reflect/scheduler | consolidation | session_flush | /dream | ❌ |
| **Self-evolution** | memory only | dream+distill | **skill_manage loop** | **morphling+SOP** | memory cron | **proposals+dream** | dream→mem | ❌ |
| **Evaluation** | eval-skills doc | qa/scenarios | tests/skills | ❌ | ❌ | skill linter | ❌ | ❌ |
| **Online Learning** | async memory write | dreaming phases | turn nudges | L4 archive cron | nightly job | dream pipeline | nightly dream | ❌ |

---

## 五、每个仓库要深入读的关键文件

### Codex — `oss/codex`
```
codex-rs/memories/          # 2-phase distill
codex-rs/ext/skills/        # skill loader
codex-rs/core/              # agent loop
.codex/skills/              # repo maintenance skills
```

### OpenClaw — `oss/openclaw`
```
extensions/memory-core/     # hybrid memory + promotion
src/memory/                 # dreaming, compaction-safeguard
skills/skill-creator/       # authoring
src/trajectory/             # trajectory handling
docs/concepts/dreaming.md
```

### Hermes — `oss/hermes-agent`
```
tools/skill_manager_tool.py # skill_manage CRUD
agent/memory_manager.py
run_agent.py                # nudges + skill review triggers
skills/
```

### GenericAgent — `oss/genericagent`
```
ga.py                       # start_long_term_update, morphling
memory/                     # L1-L4 + *_sop.md
reflect/scheduler.py
agent_loop.py
```

### OpenSquilla — `oss/opensquilla`
```
src/opensquilla/memory/dream/
src/opensquilla/skills/bundled/meta-skills/
docs/features/meta-skills.md
```

### ZeroClaw — `oss/zeroclaw`
```
src/cron/consolidation.rs
src/memory/
src/skills/
```

### Claude Code Rev — `oss/experimental/claude-code-rev`
```
src/memdir/
src/skills/bundled/
```

### TaiChu — `drafts/zk/TaiChu`
```
skills/system/                              # 17 device skills
services/rust/taichu-service/src/tools/a_system/
core/agent-session/src/compaction.rs
docs/architecture/skill-system-cross-repo-comparison.md  # ★ 已有 1000+ 行对标
```

---

## 六、与 SkillRL / Claw-R1 的关系（预判）

| 论文概念 | 最接近的开源实现 |
|---------|-----------------|
| Claw-R1 Step Data Pool | **codex** memories JSONL; openclaw trajectory; 无现成 middleware |
| SkillRL Trajectory→Skill | **genericagent** L3 SOP; **opensquilla** session_flush |
| SkillRL Failure lessons | openclaw dreaming; opensquilla repair queue |
| SkillRL Recursive SkillBank | **无完整开源对标** — 各 repo 只有片段 |
| SkillHone Version + decision history | opensquilla proposals; hermes skill_manage |
| Validation gate | opensquilla skill linter; codex eval-skills |

**Gap**：没有任何一个开源 repo 实现完整 `Step Trace → Skill Candidate → Eval → Versioned Library → GRPO` 闭环。

---

## 七、TaiChu 已有工作（不必从零开始）

`drafts/zk/TaiChu/docs/architecture/skill-system-cross-repo-comparison.md` 已包含：

- 八仓库对标总表（per-turn、compaction、自进化、Hub…）
- T0/T1/T2 调用栈约定
- TaiChu 短板：compaction 保护、SubAgent 技能传递、自进化门禁
- 优先借鉴：Hermes skill_view、OpenSquilla filter_skills、Claude-Rev invoked_skills

本 research workspace 应与之 **交叉引用**，专注 SkillRL/Claw-R1 论文栈 + 官方产品 gap。

---

## 八、下一步源码深挖（可在此 workspace 继续）

- [ ] Hermes: `skill_manage` 完整 action 流 + 是否有 eval gate
- [ ] GenericAgent: `start_long_term_update` vs SkillRL distill 对比
- [ ] OpenSquilla: meta-skill-creator proposal → accept 代码路径
- [ ] OpenClaw: dreaming → MEMORY.md promotion 触发条件
- [ ] Codex: memories consolidation template 与 Skill 边界
- [ ] TaiChu: `load_skill` → compaction 丢失问题复现路径
- [ ] 汇总成 canvas 横向对比表
