# Skill 自进化 — 用户原始请求归档（Raw Requests Archive）
> **目的：** 完整保留本工作线相关 Cursor 会话中的 **用户原始请求**（raw `user_query`），便于路线图溯源与评审对照。  
> **来源：** Cursor agent transcripts（本地）+ 当前会话补录。  
> **最近刷新：** 2026-07-14  
> **关联：** [路线图 v1.2](../../zk/TaiChu/docs/architecture/skill-self-evolution-roadmap.md) · workspace `skill-evolving-analysis`

## 会话索引

| Transcript ID | 标题提示 | 请求数 |
|------------|--------------------|--------|
| `98132ca9` | [Skill 调研与 TaiChu 路线图](98132ca9-6424-4168-a38f-f9493b440c76) | 96 |
| `4008ce97` | [Prompt / 八仓对照碎片](4008ce97-b5a7-4b5f-ad32-87177431ba63) | 3 |
| `e6cc5cc2` | [检索 roadmap 相关会话](e6cc5cc2-8439-4051-ab37-f5ad3f1e19b5) | 3 |
| `current-session` | 本会话续写（transcript 可能尚未落盘的补录） | 2 |

## 主题标签图例

| Tag | 含义 |
|-----|------|
| `papers-rl` | 论文 / Skill RL / Claw RL |
| `survey-industry` | 业界 harness / skill 自进化调研 |
| `repo-discovery` | 开源仓发现与深挖 |
| `matrix-survey` | Skill Architecture Survey Matrix |
| `html-ui` | 调研站 / deck HTML / i18n / UX |
| `privacy-isolation` | 用户隔离 / 端侧 / 端云 |
| `roadmap-m1-m6` | TaiChu 3–6 月路线图与里程碑 |
| `decoupling-flags` | 解耦 / Standalone / Borrowed-from |
| `session-scope` | Session vs 跨 Session / 在线单 session |
| `calling-points` | 调用点 / hook / plugin / async |
| `no-modify-tools` | 不修改现有 builtintools |
| `taichu-code-analysis` | TaiChu 现有 skill 链路代码分析 |
| `claude-hermes-m1` | Claude 每5轮 / Hermes nudge → M1 |
| `docs-meta` | 文档元数据 / v1 / SSOT |
| `co-improve` | 端云·端端共进化 |
| `trigger-adapter` | 触发策略 × 适配器 |
| `github-push` | 推送 GitHub |
| `store-persist` | 落盘 store/ |
| `meta-archive` | 本归档请求 |
| `other` | 未自动归类 |

## 设计决策脉络（从原始请求抽取）

按时间压缩成「用户坚持要写进文档/实现」的硬要求，原文见下方完整清单：

1. 先调研论文 + 八仓 skill 自进化，再落地 TaiChu。
2. Survey matrix 要覆盖存储/暴露/发现/推荐/使用/压缩/删除/演化…并有证据。
3. 用户隔离 / 端侧进化 / **无八仓自动端云 sync** 要标清；后又要求承认 TaiChu **可做**共进化（M7+）。
4. 3–6 月路线图；M1 须借齐八仓（尤四仓）；解耦 + standalone + flag。
5. Session vs 跨 Session；**在线 + 单 Session 自进化进 M1**。
6. 三层：Tool → 委托 Agent → 多 Agent；`skill_evo`；调用点 hook/plugin/async。
7. **不修改现有 tools**；用统一 `skill_evo` 覆盖八仓进化 tool 语义。
8. 先分析 TaiChu 现码；附录补 compaction / in-ram / 触发路径。
9. Claude 每5轮、Hermes nudge+子Agent、`InRamSnapshot` → **M1 非 M3**。
10. 文档元数据 v1；子规格可拆；触发策略×适配器；共进化附录 I。

---


## 分阶段速查（请求编号）

| 阶段 | 大约编号 | 焦点 |
|------|----------|------|
| 论文 / 行业趋势 | `98132` R001–R007 | SkillRL / ClawRL；自进化趋势 |
| 八仓发现与深挖 | R008–R025 | clone/读码；Survey Matrix |
| 调研站 HTML/UX | R026–R068 | deck、i18n、隔离/端侧标注、push |
| TaiChu 路线图成型 | R069–R088 | 3–6月、解耦、M1 八仓、调用点、不改现有 tool、现码分析 |
| 附录 H / CP-06/07→M1 | R089–R091 | compaction、in-ram、Claude/Hermes 归 M1 |
| 文档定稿与扩展 | R092–R096 + `current-session` | v1 元数据、共进化、触发适配器、归档 |

Cursor transcript 主会话：[Skill 调研与 TaiChu 路线图](98132ca9-6424-4168-a38f-f9493b440c76)


## 完整原始请求清单

### `98132ca9` · R001

**Tags:** `papers-rl`

````text
explain two papers: skill rl, claw rl
````

### `98132ca9` · R002

**Tags:** `html-ui`

````text
create .md and html or dir structure for a deep research topic, there will be a lot of data coming in, keep them stored
````

### `98132ca9` · R003

**Tags:** `papers-rl`, `matrix-survey`, `docs-meta`

````text
These two papers target different layers of the agent RL stack:

Paper	Focus	Layer
SkillRL: Evolving Agents via Recursive Skill-Augmented Reinforcement Learning	How the policy learns from experience	RL algorithm / training method
Claw-R1: A Step-Level Data Middleware System for Agentic Reinforcement Learning	How agent interaction data is collected, managed, and fed into RL	Infrastructure / data system

They are actually complementary rather than competing.

1. SkillRL

Paper

SkillRL: Evolving Agents via Recursive Skill-Augmented Reinforcement Learning (2026)
Motivation

Most LLM agents today behave like this:

Task 1
   ↓
trajectory

Task 2
   ↓
trajectory

Task 3
   ↓
trajectory

Every task is almost independent.

Existing "memory" methods simply save trajectories:

database
----------
task A trajectory
task B trajectory
task C trajectory

Problems:

trajectories are long
noisy
redundant
hard to retrieve
don't generalize

The authors ask:

Can we convert trajectories into reusable skills?

Main idea

Instead of storing

Observation
Action
Observation
Action
...

store

Skill:
"When searching webpages,
first identify official sources,
then compare,
then verify."

This is much shorter.

They call this

SkillBank

Pipeline

The whole pipeline is roughly

Environment

↓

Rollouts

↓

Successful trajectories
Failed trajectories

↓

Teacher LLM

↓

Skill distillation

↓

SkillBank

↓

Retrieve skills

↓

Policy

↓

GRPO

↓

Better policy

↓

New trajectories

↓

Update SkillBank

Notice the last arrow.

The SkillBank is not fixed.

It evolves together with the policy.

Experience Distillation

Instead of

Trajectory

step1
step2
step3
...
step50

Teacher LLM summarizes

Skill

Applicable:
Searching APIs

Strategy:
Search official docs first

Failure:
Do not trust cached pages

This becomes reusable.

They also learn from failures

Unlike many previous papers that discard failed rollouts,

they keep

Success
↓

Positive skill

Failure
↓

Failure lesson

Example

Instead of

50-step failed trajectory

store

Failure lesson:

Do not search StackOverflow before
official documentation.

This dramatically compresses context.

Hierarchical SkillBank

They divide skills into two levels.

General skills

Reason before acting

Verify answer

Search official docs

Task-specific skills

ALFWorld

Always open cabinet
before checking drawer

or

WebShop

Check product variants
before buying
Adaptive retrieval

Given a task

Buy shoes

retrieve

General

Verify inventory

Task-specific

Compare shoe sizes

instead of dumping every previous trajectory.

Recursive Evolution

This is probably the most interesting contribution.

Instead of

Policy

↓

RL

↓

Done

they do

Policy

↓

Collect trajectories

↓

Generate skills

↓

Update SkillBank

↓

Policy learns

↓

Collect better trajectories

↓

Generate better skills

↓

...

Policy and SkillBank co-evolve recursively.

RL Objective

Interestingly,

the RL algorithm itself is not novel.

They use

GRPO

Policy

↓

Sample rollouts

↓

Reward

↓

GRPO update

The novelty is adding

SkillBank

+

Recursive skill evolution

around GRPO.

Advantages

Compared with trajectory memory:

Pros

much shorter context
reusable
transferable
better generalization
learns from failures
hierarchical retrieval

Cons

requires teacher LLM
skill extraction quality matters
skill retrieval becomes another optimization problem
2. Claw-R1

Paper:

Claw-R1: A Step-Level Data Middleware System for Agentic Reinforcement Learning (2026).

This paper is not proposing a new RL algorithm.

Instead, it asks:

How do we manage millions of agent interaction steps?

Imagine OpenAI training an agent.

There are

10000 agents

↓

millions of steps

↓

training

Current systems often treat interactions as temporary logs.

stdout

↓

deleted

Claw-R1 says:

Treat interactions like structured datasets.

Core Architecture
Agent

↓

Gateway Server

↓

Step records

↓

Data Pool

↓

RL Trainer
Gateway Server

All agent requests pass through a unified gateway.

Instead of

Agent

↓

LLM

they have

Agent

↓

Gateway

↓

LLM

The gateway automatically records

prompt
response
reward
tool calls
metadata
timestamps
Step-Level Data

Instead of storing only

Trajectory

they store

Step 1

State

Action

Reward

Prompt ID

Response ID

Every step becomes an independent data asset.

For example

Episode

Step1

Search

reward 0

Step2

Read webpage

reward 1

Step3

Answer

reward 1

Each is queryable.

Data Pool

Think of

Replay Buffer++

Traditional replay buffer

Trajectory

Claw Data Pool

Step

↓

Metadata

↓

Filtering

↓

Versioning

↓

Quality labels

↓

Training readiness

You can ask

Show

all failed search steps

reward < 0

tool = browser

or

Show

all tool-use mistakes

This is extremely useful for debugging.

Why step-level?

Suppose one trajectory has

20 steps

19 correct

1 wrong

Trajectory-level storage loses granularity.

Step-level lets you train

only

the wrong step.
Training

The trainer later selects

Step

↓

Batch

↓

GRPO

or

PPO

or

DPO

or

other RL

Claw itself does not care which algorithm you use. It is a middleware layer that prepares data for downstream RL.

Why it matters

Agent RL is becoming a data engineering problem.

The paper argues that we need infrastructure analogous to:

Feature Stores in recommendation systems
Data Lakes for analytics
Experience Replay Buffers in classical RL

but designed specifically for LLM agents.

SkillRL vs. Claw-R1
Aspect	SkillRL	Claw-R1
Main contribution	RL algorithm + skill learning	Data middleware
Uses RL	Yes (GRPO)	No (algorithm-agnostic)
Stores	Skills	Step records
Main abstraction	SkillBank	Data Pool
Focus	Better policy learning	Better data lifecycle
Learns from failures	Yes (distills failure lessons)	Records failures for later use
Training improvement	Direct	Indirect (through better data management)
How they fit together

They can be combined into a single pipeline:

                Claw-R1
──────────────────────────────────

Agents
   │
   ▼
Gateway
   │
   ▼
Step Data Pool
   │
   ▼
Trajectory Builder
   │
──────────────────────────────────
                │
                ▼
             SkillRL
──────────────────────────────────

Trajectory

↓

Teacher LLM

↓

Skill Distillation

↓

SkillBank

↓

Retrieve Skills

↓

GRPO

↓

Updated Policy

↓

More Agent Data

↓

Back to Claw-R1

In this architecture:

Claw-R1 provides a high-quality, queryable stream of step-level interaction data.
SkillRL consumes those trajectories, distills them into reusable skills, updates the policy with GRPO, and recursively evolves the SkillBank.

One manages the data lifecycle, while the other improves the learning algorithm. Together they represent a full-stack approach to agentic RL: infrastructure plus policy optimization.
````

### `98132ca9` · R004

**Tags:** `survey-industry`

````text
业界的agent harness调研： 自进化是如何做的， 特别是skill自进化
````

### `98132ca9` · R005

**Tags:** `papers-rl`, `survey-industry`, `docs-meta`

````text
过去一年（尤其是 2025–2026）的 Agent 研究，一个非常明显的趋势就是：

Agent 的自进化（Self-evolution）越来越不是更新模型参数，而是更新 Harness、Skill、Memory、Workflow。

如果专门聚焦 Skill 自进化（Skill Evolution），目前业界已经逐渐形成了比较一致的技术路线。

一、Skill 自进化到底在进化什么？

很多人理解成：

Task
↓

Trajectory

↓

保存下来

其实现在不是。

更准确的是：

Task

↓

Experience

↓

Skill

↓

Skill Library

↓

Retriever

↓

以后Agent调用

真正进化的是：

Skill Library

而不是模型参数。

可以理解成：

LLM
+
Agent Harness
+
Skill Library

其中只有 Skill Library 在持续成长。

二、业界目前基本可以分成六条路线

我一般会把它们画成：

                Self Evolution

                     │

────────────────────────────────────────

Trajectory

Skill

Workflow

Harness

Tool

Weight

其中

真正成熟的是

Skill Evolution

Weight Evolution（模型更新）反而很少在线发生。

第一类：Trajectory → Skill（目前主流）

代表：

Voyager
SkillRL
Trace2Skill
Memento-Skills
SkillHone

共同思想：

不是保存Trajectory，

而是Distill。

例如

Agent执行

Search

↓

Read

↓

Compare

↓

Answer

变成

Skill:

When comparing APIs:

1 Search official docs

2 Compare versions

3 Verify examples

Trajectory消失。

留下Skill。

这是目前最主流路线。

流程：

Rollout

↓

Trajectory

↓

Teacher LLM

↓

Skill Distillation

↓

Skill Library

优点

非常小

容易retrieve

容易泛化

第二类：Failure → Skill

这个近一年越来越火。

代表：

SkillRL

HarnessFix

SkillHone

思想：

不要保存成功经验。

更应该保存失败。

例如

失败：

Tool timeout

↓

Retry

↓

Retry

↓

Fail

变成

Skill

Never retry

Use backup API

或者

Browser

↓

Captcha

↓

Stop

Skill

Switch to search API

失败通常比成功更有价值。

第三类：Skill Revision（Skill持续修改）

这类开始出现于2026。

不是

Skill V1

一直保存。

而是

Skill V1

↓

Run

↓

Feedback

↓

Skill V2

↓

Run

↓

Feedback

↓

Skill V3

Skill成为Version。

例如

Search docs

后来变成

Search official docs

↓

If unavailable

↓

Search github issues

Skill越来越长。

越来越成熟。

代表：

SkillHone。

第四类：Skill Graph

以前：

List

Skill1

Skill2

Skill3

现在越来越多工作变成：

Skill A

↓

Skill B

↓

Skill C

或者

Search

↓

Read

↓

Summarize

↓

Verify

Skill之间有依赖。

Graph Retrieval。

代表：

Graph of Skills

SkillFlow

SkillRouter。

第五类：Program Skill

代表：

Voyager

Inducing Programmatic Skills

不是Prompt。

而是Code。

例如

以前：

Search docs

后来

Skill变成

def search_docs():

...

以后Agent直接调用。

优势：

速度快。

可以debug。

可以测试。

可以version。

第六类：Workflow Skill

今年开始越来越明显。

Skill已经不是一句Prompt。

而是Workflow。

例如

Browser

↓

Search

↓

Read

↓

Verify

↓

Summarize

整个Workflow

就是Skill。

COMFYCLAW就是这样。

Skill其实是Workflow Graph。

三、Skill 是怎么产生的？

目前大概四种。

方法1 Distillation

最常见。

Trajectory

↓

Teacher LLM

↓

Skill

SkillRL

Trace2Skill

都是这样。

方法2 Reflection
Trajectory

↓

Reflection

↓

Lesson Learned

↓

Skill

类似

Reflexion。

方法3 RL

Skill

作为Policy输入。

好的Skill

保留。

差Skill

删除。

SkillRL属于这一类。

方法4 Search

多个Skill

一起测试。

留下最好的。

像

Skill A

Skill B

Skill C

↓

Benchmark

↓

Choose

越来越多Harness论文采用。

四、Skill 如何更新？

几乎所有论文都会经历：

Collect

↓

Extract

↓

Validate

↓

Store

↓

Retrieve

↓

Execute

↓

Collect

形成闭环。

即

Rollout

↓

Skill

↓

Agent

↓

Rollout

如果展开：

Task

↓

Trajectory

↓

Skill Candidate

↓

Offline Evaluation

↓

Accepted Skill

↓

Skill Library

↓

Retriever

↓

Agent

↓

New Tasks
五、Skill 如何淘汰？

目前有几种策略：

1. Score

每个Skill

维护

success rate

usage

reward

低分删除。

2. ELO

越来越流行。

Skill之间Pairwise。

例如

Skill A

vs

Skill B

留下胜率高的。

3. Embedding Merge

相似Skill

自动Merge。

例如

Search docs

Search official docs

合并。

4. Version

Skill

不是覆盖。

而是

V1

↓

V2

↓

V3

SkillHone就是典型。

六、目前最大的研究方向：Harness × Skill 联合进化

2026 年开始，一个新的趋势已经非常明显：

以前：

LLM

↓

Trajectory

↓

Skill

现在：

LLM

↓

Harness

↓

Trajectory

↓

Skill

↓

Harness Update

↓

Skill Update

Harness 和 Skill 一起进化。代表性工作包括 Self-Harness、Harness 演化能力分析、Adaptive Auto-Harness 等。

我认为未来（2026–2027）最值得做的 Skill 自进化架构

相比目前论文大多仍采用

Trajectory
    ↓
LLM Distill
    ↓
Skill

我认为更有潜力的是一个持续在线的 Skill 生命周期：

                Agent Runtime
                     │
                     ▼
              Step-level Trace
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
 Failure Mining             Success Mining
        │                         │
        └────────────┬────────────┘
                     ▼
             Skill Candidate Pool
                     │
      Auto Practice / Regression Tests
                     │
      Pairwise Ranking / A-B Evaluation
                     │
            Versioned Skill Library
                     │
      Graph Retrieval + Skill Routing
                     │
              Next Agent Execution
                     │
          Runtime Metrics Feedback
                     └──────────────►（继续闭环）

这个架构融合了当前多条研究路线：

Step-level 数据管理（类似 Claw-R1）
Trajectory → Skill 蒸馏（SkillRL、Trace2Skill）
Failure Mining（SkillRL、HarnessFix）
Versioned Skills（SkillHone）
Graph/Router 检索（SkillFlow、Graph of Skills、SkillRouter）
Harness 自进化（Self-Harness、Adaptive Auto-Harness）

核心思想是：Skill 不再是静态 Prompt，而是一个可评测、可版本化、可路由、可淘汰、可持续演化的软件资产。这也是当前 Agent Harness 研究正在快速汇聚的方向。
````

### `98132ca9` · R006

**Tags:** `other`

````text
claude code, codex, cursor等官方博客，是否有skill自进化内容
````

### `98132ca9` · R007

**Tags:** `papers-rl`, `calling-points`

````text
短答案：

没有一家官方明确提出过「Skill 自进化（Skill Self-Evolution）」作为产品能力或官方路线。

但是三家（Claude Code、Codex、Cursor）实际上已经分别提供了组成 Skill 自进化闭环的基础设施，只是停留在 Human-in-the-loop，而不是论文里的 Automatic Skill Evolution。

下面分别分析。

总结
产品	Skills	Memory	自动修改Skill	自动评测	官方提出Skill Evolution?
Claude Code	✅ 很强	部分	❌	❌	没有
Codex	⚠️(Prompt/Memory)	✅	❌	❌	没有
Cursor	⚠️ Rules	部分	❌	❌	没有

所以：

官方目前都没有做到 SkillRL 那种 "Trajectory → Skill → Evaluation → Update Skill"。

一、Claude Code

官方文档已经正式把 Skills 做成了一等公民。

官方文档：

Claude Code Skills

Claude Code Skills Documentation

Skills 本质就是

Skill

SKILL.md

+

scripts

+

references

例如

review-pr

SKILL.md

scripts/

examples/

模型需要的时候自动加载。

官方称之为

Progressive Loading

不是一次把所有skills塞进去。

官方支持什么？

支持：

Create Skill

↓

Use Skill

↓

Share Skill

官方文档介绍的是：

Human

↓

Write Skill

↓

Claude使用

没有：

Trajectory

↓

Generate Skill

↓

Replace Skill

所以

Skill生命周期仍然靠人维护。

有没有暗示Self-improving？

有一点点。

Anthropic一直强调：

Skill应该越来越多。

例如：

Project Skill

Team Skill

Personal Skill

不断积累。

但是

官方没有说：

Claude自己修改Skill。

这是社区最希望的功能。

二、Codex

官方路线明显不同。

Codex没有强调Skill。

而强调

Memory。

最近更新里面增加：

Memory

remember

preferences

corrections

personal info

以及

reuse conversations

还有

scheduled tasks

官方方向更接近：

Experience

↓

Memory

↓

Future Tasks

而不是

Experience

↓

Skill

所以Codex目前更像：

Memory Evolution。

不是Skill Evolution。

三、Cursor

Cursor没有Skill。

更像：

Rule。

例如：

.cursor/rules

或者

Project Rules

User Rules

Auto Rules

这些都是

Instruction。

Cursor官方一直强调：

```text
Project Context

Workspace Context

Rules

没有：

Generate New Rule

也没有：

Update Rule

因此

Rule也是人工维护。

四、为什么官方都没有做 Skill 自进化？

原因其实很现实。

真正Skill Evolution意味着：

Rollout

↓

Skill Candidate

↓

替换Skill

↓

以后所有Agent都会调用

风险非常大。

例如：

今天生成

Always use git rebase

明天发现：

团队禁止rebase。

整个团队都坏了。

所以企业产品一定需要：

Candidate

↓

Review

↓

Approve

↓

Deploy

这和传统软件发布流程很像。

五、官方真正做的是什么？

如果把Claude Code画出来：

Task

↓

Claude

↓

Skill

↓

Hook

↓

Memory

↓

MCP

↓

Result

其中

Skill

Memory

Hook

MCP

都是扩展点。

但是：

这些扩展点都是静态。

SkillRL论文希望的是：

Task

↓

Trajectory

↓

Reflection

↓

Generate Skill

↓

Evaluate

↓

Version

↓

Replace Skill

↓

Next Task

这是一个完全闭环。

官方目前没有。

六、社区已经开始自己做了

虽然官方没有，

但是社区已经大量开始。

例如reddit有人做：

wrap-up Skill

↓

Session结束

↓

Review

↓

Commit

↓

Learn

↓

Remember

甚至：

Claude

↓

Review mistakes

↓

Suggest new memories

↓

Update

不过：

这些都是

Skill调用Memory

不是

Skill修改Skill。

真正修改

SKILL.md

仍然需要人工确认。

我认为下一代 Agent Harness 的方向

如果把 SkillRL 的思想和 Claude Code/Codex/Cursor 的产品形态结合起来，一个比较自然的演进方向会是：

               Runtime
                  │
                  ▼
           Step-level Trace
                  │
                  ▼
            Reflection Agent
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
   Memory Candidate    Skill Candidate
        │                   │
        │             Regression / Eval
        │                   │
        └─────────┬─────────┘
                  ▼
         Human Review (可选)
                  │
                  ▼
      Versioned Skills / Rules / Memory
                  │
                  ▼
          Automatic Retrieval

也就是说，官方产品已经具备了四个关键组件：Skills（或 Rules）、Memory、Hooks、长期上下文。目前缺失的是中间这一层：

Skill Candidate 生成（Trajectory → Skill）
自动回归测试 / Benchmark
Skill 排名、版本管理与淘汰
自动或半自动发布（Promotion）

这一层正是近年来 SkillRL、SkillHone 等论文关注的核心，也是我认为未来 Agent Harness 最有价值的演进方向：把 Skills 从静态配置文件演化为持续学习、持续评测、持续版本化的软件资产。
````

### `98132ca9` · R008

**Tags:** `repo-discovery`, `claude-hermes-m1`

````text
查看开源项目, find their repos first: 
1. /Users/x/Documents/Projects/oss/openclaw
2. /Users/x/Documents/Projects/oss/experimental/claude-code-rev
3. /Users/x/Documents/Projects/drafts/zk/TaiChu
4. /Users/x/Documents/Projects/oss/genericagent
5. /Users/x/Documents/Projects/oss/codex
6. /Users/x/Documents/Projects/oss/opensquilla
7. /Users/x/Documents/Projects/oss/zeroclaw
8. /Users/x/Documents/Projects/oss/hermes-agent  (x -> maybe on my mac here)
````

### `98132ca9` · R009

**Tags:** `papers-rl`, `calling-points`, `claude-hermes-m1`

````text
我无法直接访问你本机上的这些路径（例如 /Users/x/...），所以不能直接读取这些仓库。

不过我可以先识别哪些是公开仓库、哪些大概率是本地私有项目。

路径	是否能找到公开仓库	备注
/Users/x/Documents/Projects/oss/openclaw	很可能可以	存在多个名为 openclaw 的项目，需要确认是哪一个（MIT/OpenClaw RL？还是其他）
/Users/x/Documents/Projects/oss/experimental/claude-code-rev	未发现官方仓库	看起来像本地 reverse engineering 项目
/Users/x/Documents/Projects/drafts/zk/TaiChu	大概率私有	我在你的文件库中能看到大量 TaiChu 文档，涉及 xy-taichu/TaiChu、taichu-sdk、taichu-core-sdk 等内容，说明你之前分析过这个仓库。
/Users/x/Documents/Projects/oss/genericagent	不确定	有多个同名项目
/Users/x/Documents/Projects/oss/codex	可以	OpenAI 官方 Codex CLI 开源仓库
/Users/x/Documents/Projects/oss/opensquilla	不确定	没有广为人知的同名项目
/Users/x/Documents/Projects/oss/zeroclaw	不确定	看起来像实验项目
/Users/x/Documents/Projects/oss/hermes-agent	有多个	存在多个 Hermes Agent 相关仓库，需要确认具体是哪一个
我建议的调研流程

针对你想研究 Agent Harness / Skill 自进化，建议按下面顺序：

OpenAI Codex（官方）
OpenClaw（MIT/OpenClaw RL）
Hermes Agent
GenericAgent
ZeroClaw
OpenSquilla
Claude Code Reverse（如果是社区 reverse）
TaiChu（你们内部）

然后我会统一抽取每个仓库：

Runtime Architecture
Agent Loop
Harness
Skill
Memory
Hooks
Workflow
Session
Evaluation
Reflection
Self-evolution
Auto Skill
Prompt Generation
Tool Learning
Benchmark
Online Learning

最后整理成一张横向对比表。

建议不要只看 README，而是深入源码，重点找：

skills/
memory/
hooks/
reflection/
self_improve/
evaluator/
benchmark/
trainer/
workflow/
agent_loop/
planner/
experience/
trajectory/

这样更容易定位是否真正实现了 Skill 自进化。

如果你希望我直接分析源码，请提供其中一种方式：

给我 GitHub 仓库链接（推荐）。
把这些仓库上传到 ChatGPT File Library。
把它们打包成 zip 上传。

我会逐个深入源码分析，重点回答：

Skill 是如何表示的？
Skill 生命周期如何管理？
是否支持 Skill 自动生成？
是否支持 Skill 自动更新？
是否支持 Skill 淘汰 / 排序 / Version？
Harness 是否参与自进化？
与 SkillRL / Claw-R1 的设计有何异同？
````

### `98132ca9` · R010

**Tags:** `other`

````text
do it for me. only taichu is private, all others are open source
````

### `98132ca9` · R011

**Tags:** `other`

````text
do it for me. only taichu is private, all others are open source
````

### `98132ca9` · R012

**Tags:** `repo-discovery`, `matrix-survey`, `calling-points`, `claude-hermes-m1`

````text
Yes. I can do that.

However, this is **not a single-response task**. Reading the source code of **7+ agent frameworks** is roughly equivalent to reviewing **hundreds of thousands of lines of code**. A high-quality analysis will likely take **20–40 pages**.

## My proposed deliverables

For each repository I'll analyze:

1. Overall architecture
2. Agent loop
3. Harness design
4. Session lifecycle
5. Memory system
6. Skills
7. Workflow / Planner
8. Reflection
9. Self-improvement
10. Skill evolution
11. Prompt generation
12. Evaluation / benchmark
13. Hooks
14. Context management
15. Tool system
16. Multi-agent
17. Training / RL related components
18. Interesting implementation ideas
19. Weaknesses
20. Ideas applicable to TaiChu

---

## Repositories

I'll cover:

* OpenClaw (official) [GitHub repository](https://github.com/openclaw/openclaw?utm_source=chatgpt.com)
* Claude Code reverse-engineering project (if you tell me the exact GitHub repo; there are multiple community reverse-engineering repos)
* TaiChu (your private repository, based on what we've already discussed and the documents in your library) 
* GenericAgent
* Codex (OpenAI)
* OpenSquilla
* ZeroClaw
* Hermes Agent (Nous Research) [GitHub repository](https://github.com/nousresearch/hermes-agent?utm_source=chatgpt.com)

---

## Especially for your current research

Since you've recently been focusing on **Harness + Skill Evolution + RL**, I'll additionally extract:

| Topic             | Questions I'll answer                                 |
| ----------------- | ----------------------------------------------------- |
| Skill             | How are skills represented? Markdown? Code? Workflow? |
| Skill Loading     | Static, lazy, retrieval-based?                        |
| Skill Evolution   | Manual? Reflection? Automatic?                        |
| Reflection        | When does it run? Every task? End of session?         |
| Memory            | Episodic / semantic / vector / graph                  |
| Harness           | Extensible? Hook points? Runtime abstraction?         |
| Evaluation        | Online? Offline? Regression?                          |
| Self-play         | Supported?                                            |
| RL readiness      | Can it generate training traces?                      |
| Step-level traces | Available?                                            |
| Skill versioning  | Yes / No                                              |
| Skill ranking     | Yes / No                                              |
| Candidate skills  | Yes / No                                              |
| Automatic merge   | Yes / No                                              |

---

## Final comparison

I'll produce a large comparison matrix like:

| Project     | Skills | Memory | Reflection | Skill Evolution | Harness | Workflow | RL Ready | Rating |
| ----------- | ------ | ------ | ---------- | --------------- | ------- | -------- | -------- | ------ |
| OpenClaw    |        |        |            |                 |         |          |          |        |
| Hermes      |        |        |            |                 |         |          |          |        |
| Codex       |        |        |            |                 |         |          |          |        |
| Claude Code |        |        |            |                 |         |          |          |        |
| Cursor      |        |        |            |                 |         |          |          |        |
| TaiChu      |        |        |            |                 |         |          |          |        |

and another table specifically for **Skill Evolution**:

```text
Trajectory
      ↓
Reflection
      ↓
Skill Candidate
      ↓
Evaluation
      ↓
Version
      ↓
Deployment
      ↓
Runtime Retrieval
      ↓
Online Metrics
```

showing which projects implement each stage.

---

## One issue before I start

I **can** browse and analyze public repositories, but I **can't automatically clone and recursively inspect entire GitHub repositories** in one shot through the chat interface. The web interface is suitable for reading selected files and documentation, not performing a full repository crawl across hundreds of source files.

To produce the level of analysis you're asking for, the practical options are:

1. **Best option:** you provide local access (e.g. a ZIP of the repositories or a workspace), and I'll inspect every relevant source file.
2. **Public repos:** I can analyze them incrementally from GitHub, one repository at a time, using their source and documentation.
3. **TaiChu:** I can use the documents you've already shared plus any additional internal materials you provide.

I recommend the second approach for the public projects and then merging everything into a single comprehensive survey centered on **Agent Harness** and **Skill Self-Evolution**.
````

### `98132ca9` · R013

**Tags:** `matrix-survey`, `decoupling-flags`

````text
sure. and please consider these: 
which one supports per turn skill, or dynamic skill loading, or complementary skills for subagents?  any other innovation? what TaiChu can borrow from? how?  how skills are stored, exposed, discovered, recommended, offload, used, compact, delete, evolved for each of them.

how 自进化  related feature is supported etc.

read the code thoroughly before answering for each of them.
````

### `98132ca9` · R014

**Tags:** `papers-rl`, `calling-points`, `claude-hermes-m1`, `docs-meta`

````text
可以。我先确认公开 repo，并把调研口径固定下来。当前不能说“已彻底读完源码”；我能确认的是 repo 与第一层 evidence，后续应逐个 repo 深挖源码文件。

## Repo 确认

| 项目              | Repo                                                                                                                                            |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| OpenClaw        | `openclaw/openclaw` ([GitHub][1])                                                                                                               |
| OpenClaw-RL     | `Gen-Verse/OpenClaw-RL` ([GitHub][2])                                                                                                           |
| claude-code-rev | `Yuyz0112/claude-code-reverse` ([GitHub][3])                                                                                                    |
| GenericAgent    | `lsdefine/genericagent` ([GitHub][4])                                                                                                           |
| Codex           | 需要单独确认官方 repo 名称                                                                                                                                |
| OpenSquilla     | `opensquilla/opensquilla` ([GitHub][5])                                                                                                         |
| ZeroClaw        | `zeroclaw-labs/zeroclaw` ([GitHub][6])                                                                                                          |
| ZeroClaw Skills | `zeroclaw-labs/zeroclaw-skills` ([GitHub][7])                                                                                                   |
| Hermes Agent    | `NousResearch/hermes-agent` ([GitHub][8])                                                                                                       |
| TaiChu          | 私有，只能基于你给过的材料；已有材料显示 TaiChu 有 `taichu-sdk`、`taichu-core-sdk`、`fast_agent-session`、`fast_agent-agent`、hooks、SessionOptions、ExtraToolFactory 等结构。 |

## 初步判断：谁最像 Skill 自进化

| 项目                      | Skill 自进化强度 | 初步结论                                                                                                               |
| ----------------------- | ----------: | ------------------------------------------------------------------------------------------------------------------ |
| **Hermes Agent**        |           高 | 明确声称 closed learning loop、experience → skill、skills during use self-improve、past conversation search。([GitHub][8]) |
| **GenericAgent**        |           高 | 明确主张“don’t preload skills, evolve them”，任务完成后 crystallize 为 Skill，写入 memory layer。([GitHub][4])                    |
| **OpenClaw-RL**         |   高，但偏模型/RL | 重点不是 skill 文件，而是 conversation feedback → trajectories → PRM/judge → GRPO/OPD training signal。([GitHub][2])         |
| **OpenClaw**            |           中 | 有 workspace skills、bundled/managed/workspace skills、多 agent routing；更像 skill ecosystem，不一定是自动进化。([GitHub][1])      |
| **ZeroClaw**            |           中 | 有 SOP engine、skill registry、audit/install/version pin；偏“技能市场+SOP+安全治理”。([GitHub][6])                               |
| **OpenSquilla**         |           中 | 重点是 routing/memory/token efficiency；有 MetaSkill 文档和 migration skills，但自进化更像 router/data flywheel。([GitHub][5])     |
| **claude-code-reverse** |           低 | 这是分析 Claude Code LLM API 交互的 reverse 工具，不是 agent skill runtime。([GitHub][3])                                       |

## 下一步我会按这个表读源码

| 维度                            | 要查什么                                                          |
| ----------------------------- | ------------------------------------------------------------- |
| per-turn skill                | 每轮是否动态选择/注入 skill                                             |
| dynamic loading               | skill 是否按需加载，而不是全量进 prompt                                    |
| subagent complementary skills | 子 agent 是否有独立 skill set / routing / workspace                 |
| storage                       | `SKILL.md`、memory DB、TOML、registry、vector index、SQLite        |
| exposed/discovered            | CLI `/skills`、hub、registry、metadata、frontmatter               |
| recommended                   | 是否有推荐器 / retrieval / router                                   |
| offload/compact               | skill/memory/context 如何压缩、摘要、降级                               |
| delete/evolve                 | 是否有删除、版本、ranking、audit、promotion                              |
| 自进化                           | trajectory/reflection → candidate → eval → commit/deploy 是否闭环 |

## 对 TaiChu 的初步可借鉴方向

最值得借的是三层设计：

```text
Runtime Trace
  ↓
Skill Candidate / Memory Candidate
  ↓
Eval + Human Review + Versioned Deployment
```

对应到 TaiChu，可以落在：

```text
fast_agent-agent / session trace
  ↓
SessionHook / HookChain 捕获 turn-level 事件
  ↓
SkillCandidateStore
  ↓
SkillEvaluator / Regression Harness
  ↓
workspace skills 或 .taichu/skills
  ↓
SessionOptions.extra_tool_factories / ContextOptions.hook_chain 动态注入
```

TaiChu 现有 `SessionOptions.extra_tools`、`extra_tool_factories`、`ContextOptions.hook_chain`、`AppOptions.runtime_extra_tool_factories` 已经是很好的接缝；缺的是 **Skill 生命周期层**：发现、候选、评测、版本、启用、禁用、回滚。

[1]: https://github.com/openclaw/openclaw "GitHub - openclaw/openclaw: Your own personal AI assistant. Any OS. Any Platform. The lobster way.  · GitHub"
[2]: https://github.com/Gen-Verse/OpenClaw-RL "GitHub - Gen-Verse/OpenClaw-RL: OpenClaw-RL: Train any agent simply by talking · GitHub"
[3]: https://github.com/Yuyz0112/claude-code-reverse "GitHub - Yuyz0112/claude-code-reverse: A Tool to Visualize Claude Code's LLM Interactions · GitHub"
[4]: https://github.com/lsdefine/genericagent "GitHub - lsdefine/GenericAgent: Self-evolving agent: grows skill tree from 3.3K-line seed, achieving full system control with 6x less token consumption · GitHub"
[5]: https://github.com/opensquilla/opensquilla "GitHub - opensquilla/opensquilla: OpenSquilla — Token-Efficient AI Agent with same budget, higher intelligence density · GitHub"
[6]: https://github.com/zeroclaw-labs/zeroclaw "GitHub - zeroclaw-labs/zeroclaw: Fast, small, and fully autonomous AI personal assistant infrastructure, any OS, any platform — deploy anywhere, swap anything  · GitHub"
[7]: https://github.com/zeroclaw-labs/zeroclaw-skills "GitHub - zeroclaw-labs/zeroclaw-skills: Official skill registry for ZeroClaw — community-contributed AI agent skills, tools, and workflows · GitHub"
[8]: https://github.com/nousresearch/hermes-agent "GitHub - NousResearch/hermes-agent: The agent that grows with you · GitHub"
````

### `98132ca9` · R015

**Tags:** `repo-discovery`

````text
fetch the code, read the code thoroughly and do in-depth analysis
````

### `98132ca9` · R016

**Tags:** `other`

````text
Briefly inform the user about the task result and perform any follow-up actions (if needed). If there's no follow-ups needed, don't explicitly say that.
````

### `98132ca9` · R017

**Tags:** `repo-discovery`, `matrix-survey`, `calling-points`, `claude-hermes-m1`

````text
我无法从这里 `git clone` GitHub（运行环境 DNS 解析失败），所以我不能诚实地说“已经完整 clone 并读完全部源码”。我改用 GitHub/文档/issue 的源码页面做第一轮源码级调研。结论如下。

## 第一结论

**Skill 自进化强度排序：**

1. **Hermes Agent + hermes-agent-self-evolution**：最完整，已经有 `skill_manage`、后台 review agent、技能生成/修改/删除、外部 GEPA/DSPy 演化仓库。
2. **GenericAgent**：理念最极端，强调“每次任务沉淀为 Skill”，但更像 memory/SOP/code crystallization，不是严谨的版本化 skill pipeline。
3. **OpenSquilla**：MetaSkill 设计很有价值，强调 reusable / auditable / improvable task protocols；偏 harness-native data flywheel。
4. **OpenClaw**：skill ecosystem 成熟，但更多是 marketplace / slash command / static skill loading；自进化较弱。
5. **ZeroClaw**：skill registry、安全、权限、版本 pin 更完整；自进化弱。
6. **Codex**：官方 repo 更偏 coding agent runtime，没有公开一等 Skill 自进化系统。
7. **claude-code-reverse**：不是 agent harness，本质是 reverse 工具，不是 skill 自进化项目。

## 核心对比

| 项目           | per-turn skill                                     | dynamic loading                                             | subagent complementary skills              | storage                                 | evolve/delete                                                        |
| ------------ | -------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------ | --------------------------------------- | -------------------------------------------------------------------- |
| Hermes       | 支持 `/skills`、`/<skill>`，但 issue 显示自动触发仍有问题         | Progressive disclosure / skill view / skill manager         | 有 `delegate_task`，但子 agent context 过大是已知问题 | `~/.hermes/skills/**/SKILL.md`          | `skill_manage` 可 create/patch/edit/delete，甚至后台 review agent 可改 skill |
| GenericAgent | 任务后固化 Skill，下次直接 recall                            | 更像 memory recall，不是显式 per-turn skill registry               | 未见强子 agent skill 隔离                        | memory layer + SOP/code                 | 自动 crystallize，但缺少严格审核/版本治理                                          |
| OpenSquilla  | CLI 有 `opensquilla skills`，MetaSkill 可组织多 skill    | 有 MetaSkill task-protocol 层                                 | MetaSkill 可组合 skills/tools/sub-agents      | bundled SKILL.md + MetaSkill docs       | `meta-skill-creator`，AI-assisted evolve，但强调 review                   |
| OpenClaw     | 有 slash skill / available_skills，但很多 issue 指出注入不稳定 | 支持 bundled/managed/workspace/extraDirs，但 session cache 问题明显 | 有 coding-agent / sessions_spawn 方向         | `SKILL.md` + ClawHub                    | 主要靠 marketplace/Skill Workshop，不是自动进化                                |
| ZeroClaw     | `zeroclaw skills install/audit`                    | registry install + audit                                    | SOP engine 更强于 skill evolution             | registry.json + `skills/*/SKILL.md`     | 删除/归档/版本 pin，偏治理                                                     |
| Codex        | 未见一等 Skill                                         | 主要是 AGENTS.md/config/MCP/hooks                              | 多 agent/parallel MCP 相关，不是 skill-specific  | config + project instructions           | 没有公开 skill evolution                                                 |
| TaiChu       | 目前可借助 hooks/session/tool factory 做                 | 有良好接缝                                                       | 可做 subagent relay + skill set              | 建议 `.taichu/skills/**/SKILL.md` + store | 缺 Skill lifecycle 层                                                  |

## 对 TaiChu 最值得借鉴的设计

**1. 借 Hermes 的 Skill 生命周期层**

Hermes 明确有 built-in learning loop：从经验创建 skills、使用中改进、nudging persist knowledge、搜索历史会话；README 也列出 `/skills`、`/<skill-name>`，以及 OpenClaw migration 会导入 skills 到 `~/.hermes/skills/openclaw-imports/`。([GitHub][1]) ([GitHub][1])

TaiChu 可以落成：

```text
SessionHook 捕获 turn / tool / failure trace
  ↓
SkillCandidateStore
  ↓
SkillReviewAgent
  ↓
SkillEvaluator
  ↓
.taichu/skills/<name>/SKILL.md
  ↓
per-turn skill index 注入
```

TaiChu 已有 `SessionOptions.extra_tools / extra_tool_factories`、`ContextOptions.hook_chain`、`AppOptions.runtime_extra_tool_factories`，这些正好是 skill runtime 的接缝。

**2. 借 Hermes Self-Evolution 的“离线演化器”**

`hermes-agent-self-evolution` 用 DSPy + GEPA 自动 evolve skills、tool descriptions、system prompts、code；流程是：读取当前 skill/prompt/tool → 生成 eval dataset → GEPA optimizer + execution traces → candidate variants → tests/benchmarks/size gates → best variant → PR。([GitHub][2])

TaiChu 应该先做 **离线 PR 模式**，不要直接在线改生产 skill：

```text
trace DB
  ↓
generate eval cases
  ↓
mutate SKILL.md
  ↓
run regression harness
  ↓
score
  ↓
open PR / human approve
```

**3. 借 OpenSquilla 的 MetaSkill**

OpenSquilla 把 MetaSkill 定义为由 steps / skills / checks / outputs 组成的 reusable workflow，不是新 execution atom，而是组织已有 tools、skills、LLM calls、sub-agents 的 task protocol。([GitHub][3]) ([GitHub][4])

TaiChu 可做两层：

```text
Skill = 单个 procedure / instruction / tool wrapper
MetaSkill = 多 step workflow + checks + subagent routing
```

这比只做 `SKILL.md` 更适合 agent harness。

**4. 借 ZeroClaw 的安全治理**

ZeroClaw skill registry 要求 `SKILL.md` frontmatter，包含 name、description、version、author、license、category、permissions；并明确 registry 不是安全边界，CI 只做结构验证/secret/dangerous regex/file-policy scans；用户应 `skills audit`，可 pin 版本，恶意 skill 会从 registry 删除并归档。([GitHub][5])

TaiChu 应该内建：

```yaml
name:
version:
permissions:
risk_level:
owner:
source:
allowed_tools:
requires_approval:
```

**5. 不要照搬 GenericAgent 的“全自动固化”**

GenericAgent 的理念是“不预置技能，靠进化获得能力”，每次任务完成后把执行路径 crystallize 成 Skill，写入 memory layer，下次直接 recall。([GitHub][6])

这个思想适合个人 agent，但对 TaiChu 这种工程 harness，必须加：

```text
candidate → eval → approve → deploy → monitor → rollback
```

否则 skill drift / prompt injection / 错误 SOP 会长期污染系统。

## TaiChu 推荐架构

```text
Turn Trace / Tool Trace / Failure Trace
        ↓
Skill Miner
        ↓
Skill Candidate
        ↓
Static Checks
        ↓
Regression Harness
        ↓
Human / Policy Gate
        ↓
Versioned Skill Store
        ↓
Skill Router
        ↓
Per-turn Dynamic Skill Loading
        ↓
Subagent-specific Skill Bundle
```

最关键的是：**不要把 Skill 当 prompt 文件；要当软件资产管理。**
也就是：可搜索、可推荐、可版本化、可删除、可 compact、可 offload、可回滚、可审计、可评测。

[1]: https://github.com/nousresearch/hermes-agent "GitHub - NousResearch/hermes-agent: The agent that grows with you · GitHub"
[2]: https://github.com/NousResearch/hermes-agent-self-evolution "GitHub - NousResearch/hermes-agent-self-evolution: ⚒ Evolutionary self-improvement for Hermes Agent — optimize skills, prompts, and code using DSPy + GEPA · GitHub"
[3]: https://github.com/opensquilla/opensquilla/blob/main/docs/features/meta-skills.md?utm_source=chatgpt.com "opensquilla/docs/features/meta-skills.md at main"
[4]: https://github.com/opensquilla/opensquilla/blob/main/docs/features/meta-skill-user-guide.md?utm_source=chatgpt.com "opensquilla/docs/features/meta-skill-user-guide.md at main"
[5]: https://github.com/zeroclaw-labs/zeroclaw-skills "GitHub - zeroclaw-labs/zeroclaw-skills: Official skill registry for ZeroClaw — community-contributed AI agent skills, tools, and workflows · GitHub"
[6]: https://github.com/lsdefine/genericagent "GitHub - lsdefine/GenericAgent: Self-evolving agent: grows skill tree from 3.3K-line seed, achieving full system control with 6x less token consumption · GitHub"
````

### `98132ca9` · R018

**Tags:** `repo-discovery`

````text
do more in-depth and thorough analysis etc.
````

### `98132ca9` · R019

**Tags:** `store-persist`

````text
record all previous content and future content to store/disk/file system.
````

### `98132ca9` · R020

**Tags:** `store-persist`

````text
record all previous content and future content to store/disk/file system.
````

### `98132ca9` · R021

**Tags:** `papers-rl`, `repo-discovery`, `html-ui`, `roadmap-m1-m6`, `calling-points`, `claude-hermes-m1`, `docs-meta`

````text
下面是更深入版结论。注意：我没有本机路径访问权，不能直接读你本地 clone；以下基于公开 GitHub/官方文档/issue 页面做源码与设计证据分析。

# 0. 总体判断

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

但真正做到“安全、工程化、可上线”的 **Skill 自进化**，目前没有一个项目完全成熟。Hermes 最激进，但 issue 里也暴露了自修改 skill 的安全和一致性问题，例如 background review 可能在未读取当前 `SKILL.md` 的情况下 patch skill，导致内容被错误删除；也有 issue 要求防止 agent 修改 critical skills。([GitHub][1])

---

# 1. 横向结论表

| 项目                      | Skill 存储                                             | 动态加载                                  | Per-turn skill                  | 子 Agent skill                                 | 自进化                                          | 工程成熟度                       |
| ----------------------- | ---------------------------------------------------- | ------------------------------------- | ------------------------------- | --------------------------------------------- | -------------------------------------------- | --------------------------- |
| **Codex**               | `skills/<name>/SKILL.md` + scripts/references/assets | 强，progressive disclosure              | 支持 implicit/explicit activation | 可能通过 agents/openai.yaml 扩展，但不是核心              | Record & Replay 可生成 skill，但不是闭环自进化           | 高                           |
| **OpenClaw**            | 多来源 `SKILL.md`                                       | 中强，session snapshot + watcher refresh | session snapshot，下一 turn 可刷新    | 明确 per-agent/workspace/personal/shared skills | agent-drafted proposals，但偏人工 approve         | 中高                          |
| **Hermes**              | `~/.hermes/skills/**/SKILL.md`                       | 强，on-demand / progressive disclosure  | 支持 `/skills`、`/<skill>`、自动选择    | 有 delegate/subagent，但 skill isolation 还不完整    | 最强，`skill_manage` 可 create/patch/edit/delete | 激进但风险高                      |
| **GenericAgent**        | memory/SOP/skill tree                                | 更像 recall，不是标准 skill loader           | 任务后复用                           | 弱                                             | 强理念：每次任务 crystallize 成 Skill                 | 简洁但治理弱                      |
| **OpenSquilla**         | Skill + MetaSkill docs/workflow                      | 中强                                    | router/turn-loop 相关             | MetaSkill 可编排 tools/skills/sub-agents         | `meta-skill-creator`，偏 proposal              | 设计优秀                        |
| **ZeroClaw**            | registry + `SKILL.md`                                | install/audit/use                     | 更偏 registry/runtime             | SOP/tool/channel 更强                           | 弱，偏安全治理                                      | 安全治理值得借                     |
| **claude-code-reverse** | 不是 skill runtime                                     | 无                                     | 无                               | 重点是 Task/Sub Agent 分析                         | 无                                            | 用来学习 Claude Code harness 思路 |
| **TaiChu**              | 建议 `.taichu/skills/**/SKILL.md` + metadata store     | 可借 hooks/session factory 实现           | 可实现                             | 可结合 subagent relay                            | 待实现                                          | 接缝很好                        |

---

# 2. Codex：标准化 skill + progressive disclosure，适合作为 TaiChu 基线

Codex 官方文档已经把 Agent Skills 做成正式能力：skill 是目录，包含 `SKILL.md`，可带 `scripts/`、`references/`、`assets/`、`agents/openai.yaml`；`SKILL.md` 必须包含 `name` 和 `description`。([OpenAI Developers][2])

最关键的是 **progressive disclosure**：

```text
初始上下文：
  name + description + file path

真正使用时：
  读取完整 SKILL.md
```

Codex 还限制初始 skill list 的上下文预算：最多 2% context window，未知窗口时最多 8000 字符；如果 skill 太多，先缩短 description，再可能省略部分 skill。([OpenAI Developers][2])

Codex 的触发方式有两种：

```text
explicit:
  /skills
  $ mention skill

implicit:
  根据 description 自动选择
```

这点对 TaiChu 很重要：**description 不是文档字段，而是 routing signal**。([OpenAI Developers][2])

Codex 也有 skill creation 入口：`$skill-creator`，并且支持 Record & Replay：记录 workflow、检查步骤、草拟 reusable skill。([OpenAI Developers][2])

## TaiChu 应借什么

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

# 3. OpenClaw：多来源 skill loading / priority / per-agent visibility 做得最好

OpenClaw 文档明确说明 skill 是带 YAML frontmatter 的 markdown instruction file，用于教 agent 如何以及何时使用工具。它从多个来源加载 skill，并按优先级覆盖。([GitHub][3])

加载优先级是：

```text
1. <workspace>/skills
2. <workspace>/.agents/skills
3. ~/.agents/skills
4. ~/.openclaw/skills
5. bundled skills
6. skills.load.extraDirs + plugin skills
```

同名 skill 由高优先级覆盖低优先级。([GitHub][3])

OpenClaw 还明确区分 **location precedence** 和 **agent visibility**。多 agent 场景下，每个 agent 有自己的 workspace，可以使用 per-agent、project-agent、personal-agent、shared managed、extra dirs 等不同作用域。([GitHub][3])

这是 TaiChu 非常应该借鉴的地方。因为 TaiChu 有 subagent / relay / runtime tool factories 的设计，天然会遇到：

```text
主 Agent 可见的 skill
子 Agent 可见的 skill
项目级 skill
用户级 skill
系统级 skill
临时任务 skill
```

OpenClaw 还做了 session snapshot：session 开始时 snapshot eligible skills，后续 turn 复用；但如果 watcher 检测到 `SKILL.md` 变化，或远程节点连接，下一 turn 可以刷新。([GitHub][3])

## TaiChu 应借什么

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

# 4. Hermes：最接近真正 Skill 自进化，但也暴露最多风险

Hermes 的 skill 文档说明：skills 是 on-demand knowledge documents，使用 progressive disclosure 减少 token；所有 skills 都在 `~/.hermes/skills/`，这是 primary source of truth；bundled、hub-installed、agent-created skills 都会放这里；并且 agent 可以修改或删除任意 skill。([GitHub][4])

这就是它最激进的地方：

```text
Agent 不只是用 skill
Agent 可以创建 / 修改 / 删除 skill
```

Hermes 还有 `skill_manage`，相关 issue 显示它支持 create/patch/edit/delete；同时也暴露出一致性问题：有 issue 说 `skill_manage` 应该和 `skill_view` / `skills_list` 使用同一 discovery path；还有 issue 说 `skill_manage` 报告创建成功但磁盘上没写出 `SKILL.md`。([GitHub][5])

最有价值的 Hermes 经验不是“让 agent 随便改 skill”，而是它证明了一个完整闭环的必要组件：

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

Hermes issue 中明确提到 background self-improvement review turn 可以调用 `skill_manage(patch)`，但如果没先读当前 skill，会基于 transcript 幻觉式 patch，甚至删除大量现有内容。([GitHub][1])

## TaiChu 应借什么

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

# 5. GenericAgent：最纯粹的“任务路径固化为 skill”思想

GenericAgent README 明确说它是 minimal self-evolving autonomous agent framework，核心约 3K 行、9 个 atomic tools、约 100 行 agent loop；设计哲学是“不预加载 skills，而是 evolve them”。每次解决新任务后，会把 execution path 自动 crystallize 成 reusable Skill，长期形成 personal skill tree。([GitHub][6])

这代表一种和 Codex/OpenClaw/Hermes 不同的路线：

```text
Codex / OpenClaw / Hermes:
  skills are authored packages

GenericAgent:
  skills are crystallized execution paths
```

这更接近 SkillRL 的精神：从 trajectory 中抽取 reusable abstraction。

但它的问题是：如果缺少评测和治理，crystallized skill 很容易把偶然经验、环境特定路径、错误 workaround 固化下来。

## TaiChu 应借什么

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

但不要借它的“直接沉淀到可用 skill”。TaiChu 应该加：

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

# 6. OpenSquilla：MetaSkill 是 TaiChu 最应该吸收的抽象

OpenSquilla 的 MetaSkill 定义很清楚：Meta-skills package repeatable multi-step work as reusable, inspectable workflows；适合需要多个 normal skill、tool、checkpoint、final synthesis pass 的任务。([OpenSquilla][7])

它区分：

```text
Skill:
  one focused task pattern / instruction set / script / tool helper

MetaSkill:
  reusable workflow made of multiple steps / skills / checks / outputs
```

这对 TaiChu 很关键。因为“Skill 自进化”如果只停留在 prompt 片段，会很快失控。真正可工程化的是：

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

OpenSquilla 还内置 `meta-skill-creator`，用于把重复的多 skill 协作模式变成新的 MetaSkill proposals。([OpenSquilla][7])

## TaiChu 应借什么

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

# 7. ZeroClaw：Skill registry 安全治理值得直接照搬

ZeroClaw 主项目是 Rust agent runtime，强调本地运行、工具、channel、provider、MCP 等。([GitHub][8])

更重要的是 `zeroclaw-skills` registry：它明确说 registry 不是 vetted security boundary；CI 只做结构验证、secret detection、dangerous regex、file-policy checks；用户仍需要自己 `zeroclaw skills audit <name>` 并阅读 `SKILL.md`。([GitHub][9])

这非常现实。

OpenClaw 生态也被安全报道指出过 skill marketplace 风险：恶意 skill 会伪装成正常扩展，诱导 agent 或用户执行恶意脚本；安全问题集中在 local file / network / command execution 权限和第三方 skill 未充分 sandbox。([The Verge][10])

## TaiChu 应借什么

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

否则会出现 Hermes issue 中那类“agent 把 governance skill 改坏”的问题。([GitHub][11])

---

# 8. Claude Code Reverse：重点不是 skill，而是 subagent context offload

`claude-code-reverse` 不是 skill runtime，而是可视化 Claude Code LLM interactions 的工具。它的价值在于揭示 Claude Code 的 harness 模式。

它记录的 Task/Sub Agent workflow 是：

```text
Main Agent
  ↓
通过 Task Tool 启动 Sub Agent
  ↓
把独立任务抽取成 sub context 初始 pro

…[truncated at 12000 chars; full text in transcript]…

````

### `98132ca9` · R022

**Tags:** `matrix-survey`

````text
the table should have more columns to cover: how skills are stored, exposed, discovered, recommended, offload, used, compact, delete, evolved for each of them, lifecycle of skill etc.
````

### `98132ca9` · R023

**Tags:** `papers-rl`, `survey-industry`, `matrix-survey`, `decoupling-flags`, `claude-hermes-m1`, `docs-meta`

````text
我建议把它提升成一个**Agent Skill Architecture Survey Matrix**，而不是简单的 feature table。

目前业界论文和项目关注点都不同，所以如果只有 5~10 列，很难真正比较。建议拆成 **Skill Data Model → Runtime → Lifecycle → Evolution → Governance → Agent Integration → RL Readiness** 七大类，大约 **60~80 个维度**。

---

# 1. Skill Data Model（Skill 本身）

| Column            | Codex | Claude Code | OpenClaw | Hermes | GenericAgent | OpenSquilla | ZeroClaw | TaiChu |
| ----------------- | ----- | ----------- | -------- | ------ | ------------ | ----------- | -------- | ------ |
| Skill Unit        |       |             |          |        |              |             |          |        |
| Storage Format    |       |             |          |        |              |             |          |        |
| File Layout       |       |             |          |        |              |             |          |        |
| Metadata          |       |             |          |        |              |             |          |        |
| Description       |       |             |          |        |              |             |          |        |
| Parameters        |       |             |          |        |              |             |          |        |
| Scripts           |       |             |          |        |              |             |          |        |
| Assets            |       |             |          |        |              |             |          |        |
| References        |       |             |          |        |              |             |          |        |
| Examples          |       |             |          |        |              |             |          |        |
| Embedded Workflow |       |             |          |        |              |             |          |        |
| Nested Skill      |       |             |          |        |              |             |          |        |
| MetaSkill         |       |             |          |        |              |             |          |        |
| Version           |       |             |          |        |              |             |          |        |

---

# 2. Skill Discovery

这是很多项目差异最大的地方。

| Column              | ... |
| ------------------- | --- |
| Discover Source     |     |
| Search Path         |     |
| Workspace Skill     |     |
| User Skill          |     |
| Global Skill        |     |
| Registry Skill      |     |
| Remote Skill        |     |
| Generated Skill     |     |
| Bundled Skill       |     |
| Priority            |     |
| Override            |     |
| Shadow              |     |
| Conflict Resolution |     |
| Lazy Discovery      |     |
| File Watch          |     |
| Hot Reload          |     |
| Refresh Policy      |     |

例如：

OpenClaw

```text
workspace

↓

personal

↓

managed

↓

bundled
```

Codex

```text
workspace only
```

Hermes

```text
~/.hermes/skills
```

等等。

---

# 3. Skill Exposure

不是所有Skill都会暴露给LLM。

应该单独一栏。

| Column                 |
| ---------------------- |
| Visible to LLM         |
| Visible to User        |
| Hidden Skill           |
| Progressive Disclosure |
| Summary Only           |
| Full Prompt Loaded     |
| Description Only       |
| Explicit Invocation    |
| Implicit Invocation    |

例如

Codex

一开始

```text
description
```

真正调用

```text
SKILL.md
```

---

# 4. Skill Recommendation

这一块目前论文很少讲。

但是Agent最重要。

| Column              |
| ------------------- |
| Trigger             |
| Description Match   |
| Embedding Match     |
| LLM Decide          |
| Rule Based          |
| Task Pattern        |
| Tool Pattern        |
| History Pattern     |
| User Preference     |
| Frequency           |
| Ranking             |
| Multi Skill Ranking |
| Budget Aware        |

例如

```text
Task

↓

Top5 Skills

↓

LLM Select
```

---

# 5. Skill Runtime

真正Agent Loop里面。

| Column               |
| -------------------- |
| Per Turn Loading     |
| Per Session          |
| Per Agent            |
| Per SubAgent         |
| Dynamic Loading      |
| Dynamic Unloading    |
| Parallel Skills      |
| Skill Chain          |
| Skill Graph          |
| Skill Cache          |
| Skill Context Budget |
| Skill Compression    |
| Skill Summarization  |
| Skill Pruning        |

例如

Hermes

progressive loading

Codex

per turn

OpenClaw

session snapshot

等等。

---

# 6. Skill Offload

这一块目前几乎没人系统总结。

其实特别重要。

| Column              |
| ------------------- |
| Offload to SubAgent |
| Offload to Tool     |
| Offload to Workflow |
| Offload to Memory   |
| Offload to MCP      |
| Offload to Human    |

例如

```text
Skill

↓

SubAgent
```

或者

```text
Skill

↓

Workflow
```

---

# 7. Skill Usage

| Column        |
| ------------- |
| Direct Prompt |
| Tool Wrapper  |
| Code          |
| Workflow      |
| Planner       |
| SOP           |
| Agent         |
| MCP           |
| Command       |

---

# 8. Skill Lifecycle

我觉得这一张最重要。

```text
Author

↓

Store

↓

Discover

↓

Expose

↓

Recommend

↓

Retrieve

↓

Load

↓

Execute

↓

Observe

↓

Evaluate

↓

Improve

↓

Publish

↓

Retire

↓

Archive

↓

Delete
```

然后每一个节点都有对应列。

| Column        |
| ------------- |
| Created By    |
| Imported      |
| Generated     |
| Human Written |
| AI Written    |
| Reviewed      |
| Approved      |
| Published     |
| Deprecated    |
| Disabled      |
| Deleted       |
| Archived      |
| Rollback      |

---

# 9. Skill Evolution

也是重点。

| Column          |
| --------------- |
| Reflection      |
| Self Reflection |
| Teacher         |
| RL              |
| GRPO            |
| Preference      |
| Pairwise        |
| Candidate       |
| Merge           |
| Split           |
| Rewrite         |
| Summarize       |
| Refactor        |
| Auto Patch      |
| Auto Delete     |
| Auto Version    |

例如

Hermes

Auto Patch

OpenClaw

Manual

等等。

---

# 10. Skill Quality

| Column           |
| ---------------- |
| Benchmark        |
| Regression       |
| Replay           |
| Unit Test        |
| Integration Test |
| Sandbox          |
| Simulation       |
| Online Eval      |
| A/B              |
| Success Rate     |
| Reward           |
| Token Cost       |
| Latency          |

---

# 11. Skill Governance

企业非常重要。

| Column      |
| ----------- |
| Permission  |
| Capability  |
| Risk        |
| Signature   |
| Trust Level |
| Audit       |
| Provenance  |
| Registry    |
| Marketplace |
| Review      |
| Owner       |
| License     |

---

# 12. Skill Relationship

论文基本没人总结。

其实非常重要。

| Column              |
| ------------------- |
| Parent Skill        |
| Child Skill         |
| Meta Skill          |
| Composite Skill     |
| Complementary Skill |
| Alternative Skill   |
| Dependency          |
| Skill Graph         |
| Skill DAG           |

例如

```text
Planning

↓

Coding

↓

Testing

↓

Review
```

---

# 13. Multi-Agent Skill

这是未来方向。

| Column              |
| ------------------- |
| Shared Skill        |
| Private Skill       |
| Per Agent Skill     |
| Per Role Skill      |
| Complementary Skill |
| Skill Negotiation   |
| Skill Transfer      |
| Skill Borrow        |
| Skill Broadcast     |
| Skill Isolation     |

例如

```text
Planner

Planning Skill

Coder

Coding Skill

Reviewer

Review Skill
```

---

# 14. Memory Integration

很多项目Skill和Memory越来越融合。

| Column     |
| ---------- |
| Episodic   |
| Semantic   |
| Vector     |
| Graph      |
| RAG        |
| KV         |
| Summary    |
| Reflection |
| Long-term  |

---

# 15. RL Readiness

这是你最近一直研究的。

| Column             |
| ------------------ |
| Step Trace         |
| Trajectory         |
| Tool Trace         |
| Reward             |
| Verifier           |
| Replay             |
| Dataset            |
| Offline RL         |
| Online RL          |
| SkillRL Compatible |
| ClawRL Compatible  |

---

# 我建议最终的调研报告

不要只是"谁支持什么"。

而是每个Repo最后统一输出：

```text
1. Architecture

2. Skill Runtime

3. Skill Lifecycle

4. Skill Evolution

5. Multi-Agent Skill

6. Skill Governance

7. Harness Integration

8. RL Readiness

9. TaiChu可以借什么

10. TaiChu如何实现

11. 不应该借什么

12. 我的评价（1~10）
```

这样最终形成的就不是一个普通的开源调研，而是一份**Agent Harness + Skill Architecture Survey**。

对于你正在设计的 TaiChu，这种维度也足够支撑后续的 Skill Runtime、Skill Evolution、Harness、RL 和 Multi-Agent 架构设计。
````

### `98132ca9` · R024

**Tags:** `other`

````text
sure, do it. cover all of them and also give evidence/url/quote etc.
````

### `98132ca9` · R025

**Tags:** `papers-rl`, `matrix-survey`, `html-ui`, `calling-points`, `claude-hermes-m1`, `docs-meta`

````text
下面是扩展后的 **Skill Architecture Survey Matrix**。我把“skill 生命周期”拆成存储、暴露、发现、推荐、加载、使用、压缩/offload、删除、演化、治理、RL readiness。

> Evidence 说明：我基于公开 repo/docs 页面做源码/文档级 evidence extraction；TaiChu 基于你文件库里的架构材料。

## 1. 总览 Matrix

| Project                 | Skill 存储                                                                                             | Exposed 给模型                                      | Discovered 如何发现                                   | Recommended 如何推荐                             | Dynamic / Per-turn loading                                            | Used 如何使用                                         | Compact / Offload                                                             | Delete / Disable                                                | Evolved 如何进化                                                                        |
| ----------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------- | -------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| **Codex**               | `skills/<name>/SKILL.md` + `scripts/ references/ assets/ agents/openai.yaml`                         | 初始只暴露 `name + description + path`                | skill 目录扫描                                        | 显式 `/skills` / `$skill`；隐式按 `description` 匹配 | 是，progressive disclosure；选中后读完整 `SKILL.md`                            | prompt workflow + scripts/assets                  | 初始 skill list 限 2% context 或 8000 chars；多时 shorten descriptions / omit skills | 未看到自动 delete；通过文件/插件管理                                          | 有 `$skill-creator` / Record & Replay，但不是完整自动闭环                                      |
| **OpenClaw**            | 多来源 `SKILL.md`：workspace、`.agents/skills`、`~/.agents/skills`、`~/.openclaw/skills`、bundled、extra dirs | 编译成 compact XML block 注入 system prompt           | 多路径优先级扫描 + gating + allowlist + binary/env filter | 由有效 skill list + agent allowlist 决定          | session snapshot；`SKILL.md` watcher 或 remote node 可 next turn refresh | teach agent how/when to use tools；可注入 env/API key | compact XML；session snapshot；per-agent/shared visibility                      | local override / config allowlist / managed skills；未见强自动 delete | Skill Workshop 可 review/approve agent-drafted proposals；偏 human-in-loop             |
| **Hermes Agent**        | `~/.hermes/skills/**/SKILL.md`；bundled/hub/agent-created 都复制到这里                                      | progressive disclosure；on-demand load            | 本地 skills dir + external dirs                     | `/skills`、`/<skill>`、agent 自动选择              | 是，on-demand                                                           | skill knowledge doc；agent 可调用 skill_manage        | progressive disclosure；历史/skill 可按需加载                                         | agent 可 modify/delete any skill                                 | 最激进：`skill_manage` + background review；外部 self-evolution repo 用 DSPy/GEPA 优化 skills |
| **GenericAgent**        | memory layer / personal skill tree；不是标准 `SKILL.md` 为主                                                | 从 memory recall skill                            | 通过历史任务沉淀的 skill tree                              | 下次任务直接 recall 相似 execution path              | 更像 memory retrieval；不强调 per-turn registry                             | execution path crystallized into reusable skill   | 目标是 6x token reduction；通过 skill reuse 减少探索                                    | 未看到强治理/删除机制                                                     | 每次成功任务自动 crystallize 为 Skill                                                        |
| **OpenSquilla**         | Skills + MetaSkills；MetaSkill 是 task protocol 文档/工作流                                                 | 可显式 launch；auditable/improvable protocol         | CLI/docs/skills system；MetaSkill creator          | MetaSkill 把复杂任务封装为 reusable protocol         | 更偏 workflow-level explicit launch                                     | 组合 tools / skills / checks / outputs              | token-efficient microkernel + model router；MetaSkill 避免每次从零规划                 | 未看到完整 delete 治理                                                 | MetaSkill 可 AI-assisted author/revise/compose；偏 proposal/review                     |
| **ZeroClaw**            | registry repo + `skills/*/SKILL.md`                                                                  | 安装后进入 runtime                                    | registry install；用户 audit                         | registry/search/install                      | 依赖安装后的 runtime                                                        | skills/tools/workflows                            | 无明显 progressive disclosure 细节；重点是 audit/pin                                   | 可 pin version；registry 可下架/安全公告                                 | 自进化弱；issue 中有 autonomous skill creation 需求                                          |
| **Claude Code Reverse** | 不是 skill runtime；有 Todo JSON memory                                                                  | 无一等 skill evidence                               | 无                                                 | 无                                            | 无                                                                     | Task/SubAgent 工具                                  | SubAgent 隔离 dirty context，只回传 compact result                                  | 无                                                               | 无；但 subagent offload 很值得借                                                           |
| **OpenClaw-RL**         | 不是 skill store；存 conversation/trajectory/training signals                                            | 不适用                                              | 不适用                                               | 不适用                                          | 不适用                                                                   | RL training framework                             | async serving/training 解耦                                                     | 不适用                                                             | conversation feedback → PRM/judge/OPD/GRPO 等训练信号                                    |
| **TaiChu**              | 目前材料显示 session/tool/hook 接缝；建议 `.taichu/skills/**/SKILL.md` + registry DB                            | 可通过 `preloaded_blocks` / system prompt / hook 注入 | 可基于 workspace/profile/session manager             | 建议 SkillRouter                               | 可通过 hooks + `extra_tool_factories` 实现 per-turn/per-agent              | skill prompt + tool factory + MetaSkill workflow  | subagent relay + JSONL trace + compact summary                                | 建议 versioned store + disable/archive/delete                     | 建议 trace → candidate → eval → approve → publish                                     |

## 2. Evidence / Quote

### Codex

Codex 官方明确说 skill 是 reusable workflow；目录结构包含 `SKILL.md`、`scripts/`、`references/`、`assets/`、`agents/openai.yaml`，`SKILL.md` 必须有 `name` 和 `description`。它的 progressive disclosure 是：启动时只放 name/description/path；决定使用后才读完整 `SKILL.md`。官方还说 initial skill list 最多占 2% context 或 8000 字符，过多时会缩短 description 或省略部分 skill。([OpenAI Developers][1])

关键 quote：**“Codex loads the full `SKILL.md` instructions only when it decides to use a skill.”** ([OpenAI Developers][1])

### OpenClaw

OpenClaw skill 是带 YAML frontmatter 的 markdown instruction file；加载顺序是 workspace skills、project agent skills、personal agent skills、managed/local skills、bundled skills、extra dirs/plugin skills，同名 skill 高优先级覆盖低优先级。OpenClaw 在 agent run 开始时读取 metadata、应用 gating/allowlists/config overrides，然后把 eligible skills 编译成 compact XML block 注入 system prompt。([OpenClaw][2])

关键 quote：**“When the same skill name appears in multiple places, the highest source wins.”** ([OpenClaw][2])

它还有 session snapshot + mid-session refresh：session 开始时 snapshot eligible skills，`SKILL.md` watcher 检测变化或 remote node 连接后，下一 turn 刷新。([OpenClaw][2])

### Hermes Agent

Hermes 把 skills 定义为 on-demand knowledge documents，使用 progressive disclosure。所有 skills 都在 `~/.hermes/skills/`，bundled、hub-installed、agent-created skills 都放这里，并且 agent 可以 modify/delete any skill。([Hermes Agent][3])

关键 quote：**“The agent can modify or delete any skill.”** ([Hermes Agent][3])

Hermes 的 self-evolution repo 更进一步：用 DSPy + GEPA 自动优化 skills、tool descriptions、system prompts、code；流程是 read current skill → generate eval dataset → GEPA optimizer + execution traces → candidate variants → evaluate → constraint gates → best variant → PR。([GitHub][4])

### GenericAgent

GenericAgent 的核心 claim 是：每次解决新任务后自动把 execution path crystallize 成 reusable Skill，长期形成 personal skill tree。([GitHub][5])

关键 quote：**“automatically crystallizes the execution path into a reusable Skill.”** ([GitHub][5])

### OpenSquilla

OpenSquilla 的 MetaSkill 不是普通 prompt，而是 reusable、explicitly launchable、auditable、improvable task protocol。它的定位很接近 workflow-level skill。([GitHub][6])

关键 quote：**“A MetaSkill preserves a way of doing high-value work.”** ([GitHub][6])

### ZeroClaw

ZeroClaw skill registry 更偏治理：建议用户 pin skill version，安装前运行 `zeroclaw skills audit`，并关注 Security advisories。([GitHub][7])

关键 quote：**“Run `zeroclaw skills audit` before installing a new skill.”** ([GitHub][7])

### Claude Code Reverse

`claude-code-reverse` 不是 skill runtime，但揭示了重要的 offload 模式：Sub Agent 从 main context 抽取任务，独立执行，最后只把结果作为 tool result 返回；这样可以把“dirty context”隔离在 sub context，主 context 只保留小结果。([GitHub][8])

### OpenClaw-RL

OpenClaw-RL 不是 skill lifecycle 系统，而是 RL harness：它把 everyday conversations 转成 personalized AI agent 的训练信号；serving、rollout collection、PRM/judge evaluation、policy training 四个 loop 异步解耦。([GitHub][9])

## 3. Skill Lifecycle 对比

| Lifecycle Stage | Codex                            | OpenClaw                        | Hermes                      | GenericAgent      | OpenSquilla                 | ZeroClaw            | TaiChu 建议                  |
| --------------- | -------------------------------- | ------------------------------- | --------------------------- | ----------------- | --------------------------- | ------------------- | -------------------------- |
| Author          | human / skill-creator            | human / workshop proposal       | human / hub / agent-created | agent from task   | human/AI-assisted MetaSkill | community           | human + agent candidate    |
| Store           | folder `SKILL.md`                | multi-root `SKILL.md`           | `~/.hermes/skills`          | memory/skill tree | skill/metaskill docs        | registry            | `.taichu/skills` + DB      |
| Discover        | installed skill list             | precedence scan                 | local/external dirs         | memory recall     | CLI/docs/router             | registry install    | SkillRegistry scan         |
| Expose          | name/description/path            | compact XML                     | progressive disclosure      | recalled memory   | explicit protocol           | installed skill     | summary block              |
| Recommend       | description match                | eligible list + allowlist       | auto + explicit command     | task similarity   | explicit launch / creator   | user install/audit  | SkillRouter                |
| Load            | full `SKILL.md` after activation | prompt catalog/session snapshot | on-demand                   | retrieved skill   | MetaSkill workflow          | runtime installed   | per-turn/per-agent         |
| Use             | prompt + scripts                 | prompt + env/API                | prompt + skill_manage       | reuse path        | workflow protocol

…[truncated at 12000 chars; full text in transcript]…

````

### `98132ca9` · R026

**Tags:** `html-ui`

````text
python web server for me
````

### `98132ca9` · R027

**Tags:** `html-ui`

````text
give me the html url
````

### `98132ca9` · R028

**Tags:** `papers-rl`, `html-ui`, `decoupling-flags`

````text
1. based on all above and generate one new html 2. generate a html to introduce all papers, real ppt style and background (borrow idea from the attatched file), each paper with 3-5 eli5 page including(must) core innovation/takaways/benchmark result/methdologies/compare before and after/background and problem/diagram/workflow with step number etc.if the html is too large, split to several parts. I want in thorough explanation, complete coverage, with all evidence/links/quote/. to the level that all above or even the source paper can be throwed away 3. each page of html should be one screen, but links, expandable, pop up are also good designs. each page should have enough information, ensure high information density like need an expert 5 mins read 4. be innovative on others, this is high-stake, do your best
````

### `98132ca9` · R029

**Tags:** `other`

````text
is there cross compare table for 8 repos?
````

### `98132ca9` · R030

**Tags:** `html-ui`

````text
I want them to be visiable in html, how to do that? md render? or create some html with site map/menu to find them
````

### `98132ca9` · R031

**Tags:** `html-ui`

````text
don't show raw md. please convert to html or svg or mermaid etc.
````

### `98132ca9` · R032

**Tags:** `html-ui`

````text
don't show raw md. please convert to html or svg or mermaid etc.
````

### `98132ca9` · R033

**Tags:** `other`

````text
support both english and chinese
````

### `98132ca9` · R034

**Tags:** `other`

````text
Briefly inform the user about the task result and perform any follow-up actions (if needed). If there's no follow-ups needed, don't explicitly say that.
````

### `98132ca9` · R035

**Tags:** `html-ui`

````text
http://127.0.0.1:8765/html/site/notes/synthesis/agent-skill-architecture-survey-matrix.html  this one has no chinese, find other similar issues
````

### `98132ca9` · R036

**Tags:** `html-ui`

````text
background too black, make background like white or light color,  some blue or more ppt like
````

### `98132ca9` · R037

**Tags:** `html-ui`

````text
many pages to improve:
http://127.0.0.1:8765/html/site/notes/synthesis/survey-reports/opensquilla.html  more chinese
more compact or condense content, less blank
````

### `98132ca9` · R038

**Tags:** `other`

````text
for each repo, there should be one slide to tell how it supports skill自进化：
1. problem to solve, how, 5w(where, what etc.)
2. methdologies
3. components touched
4. example workflow/walkthrough with step number
5. code snippet, calling stack etc.
````

### `98132ca9` · R039

**Tags:** `papers-rl`, `matrix-survey`

````text
1. some issue: i can never see L3 report for the first paper, either hidden in current or scroll to next
2. please add lifecycle and  timeline in the workflow,  is it online, offline or others
````

### `98132ca9` · R040

**Tags:** `papers-rl`, `matrix-survey`

````text
1. some issue: i can never see L3 report for the first paper, either hidden in current or scroll to next
2. please add lifecycle and  timeline in the workflow,  is it online, offline or others
````

### `98132ca9` · R041

**Tags:** `other`

````text
maybe read code thoroughly to show more details on each panel, especially wallthrough, cross turn, each turn with some example message, tool, cross user prompt or session if any. generate svg/mermaid etc. if helpful
````

### `98132ca9` · R042

**Tags:** `papers-rl`

````text
each paper done?
````

### `98132ca9` · R043

**Tags:** `other`

````text
If you want even more depth, natural next steps are: add verbatim code quotes per turn card, or split into 2 slides per repo (overview + walkthrough-only) so the Mermaid diagram can be larger.: yes, or svg
````

### `98132ca9` · R044

**Tags:** `html-ui`

````text
more detailed code snippet and calling trace/stack. maybe introduce pop up/expandable to show more details or information
````

### `98132ca9` · R045

**Tags:** `html-ui`

````text
工作流 Walkthrough — 跨 Turn 示例: is pop up better? I can easily scroll to next repo, right now
````

### `98132ca9` · R046

**Tags:** `other`

````text
observability/decision_log: explain what is it, example? rule based, program based, or llm/agent judge based?
````

### `98132ca9` · R047

**Tags:** `calling-points`

````text
difference between async vs post-turn?
````

### `98132ca9` · R048

**Tags:** `html-ui`

````text
auto explain in html. also gate-4, gates.json  what are they? example?
````

### `98132ca9` · R049

**Tags:** `html-ui`

````text
auto explain in html. also gate-4, gates.json  what are they? example?
````

### `98132ca9` · R050

**Tags:** `html-ui`

````text
_spawn_background_review(): what is the input and output? does it have access to user asistant tool result message list etc. , how it queue the tasks, what is the tasks like etc. update html
````

### `98132ca9` · R051

**Tags:** `claude-hermes-m1`

````text
Nudge 周期性提醒自改进: 给出样例
````

### `98132ca9` · R052

**Tags:** `other`

````text
start_long_term_update() · file_patch: does it always update skill or could be others like memory or more or both or all?
````

### `98132ca9` · R053

**Tags:** `other`

````text
skill_manage(action=patch, name=api-testing): would there be race condition? like half applied or broken skills for read, multiple write in parallel?
````

### `98132ca9` · R054

**Tags:** `html-ui`

````text
also use pop up
````

### `98132ca9` · R055

**Tags:** `html-ui`

````text
support i18n eng and cn in every page
````

### `98132ca9` · R056

**Tags:** `html-ui`

````text
support i18n eng and cn in every page
````

### `98132ca9` · R057

**Tags:** `other`

````text
should here be more chinese?
````

### `98132ca9` · R058

**Tags:** `other`

````text
do it
````

### `98132ca9` · R059

**Tags:** `other`

````text
more in the table column
````

### `98132ca9` · R060

**Tags:** `other`

````text
don't make function name or terms or code specific name chinese
````

### `98132ca9` · R061

**Tags:** `other`

````text
don't make function name or terms or code specific name chinese
````

### `98132ca9` · R062

**Tags:** `html-ui`, `privacy-isolation`

````text
http://127.0.0.1:8765/html/deck/skill-evolution-repos.html  标出那些是支持跨用户，做了用户隔离的
````

### `98132ca9` · R063

**Tags:** `other`

````text
give evidence like code pointer
````

### `98132ca9` · R064

**Tags:** `other`

````text
some hidden
````

### `98132ca9` · R065

**Tags:** `other`

````text
on skill 自进化， for user isolation it means don't use different users interactions history to generate shared skill across users. please recheck and find evidence on whether there is user account, or user isolations etc.
````

### `98132ca9` · R066

**Tags:** `privacy-isolation`

````text
标出来所有skill自进化应该都是端侧的，没有端云跨设备
````

### `98132ca9` · R067

**Tags:** `github-push`

````text
push to my github
````

### `98132ca9` · R068

**Tags:** `github-push`

````text
push to my github
````

### `98132ca9` · R069

**Tags:** `papers-rl`, `roadmap-m1-m6`, `decoupling-flags`

````text
skill自进化： Please find out top tasksfor  the next 3-6 months on TaiChu optimization.
also borrow ideas /Users/maybewu/Documents/Projects/drafts/skill-evolving-papers first, split different parts to differnt stages by difficulty

optimize for PC use cases like other repos first, but rust friendly, harmany with linux virtual machines etc.

Hard requirements:
everything should be feature flag gated

1. store it to doc for review and iteraton under docs/ of TaiChu
2. split to 5-6 overall milestones, with reasoning, dependencies, difficulty. borrow from other repos first
3. infra or framework readiness: skill directory on different level: session, cross session, cross profile, cross subagent, split to different milestones
4. adapter layer of source like trajectories/interaction log: support different log format, different, split to different milestones
5. adapter layer of the skill output and storage: local, session, workspace?, 云空间， cloud , split to different milestones
6. coupling and decoupling point with existing agent layers(loop, agent, session, sdk layer etc.), reuse or copy session history or even kv cahce etc. not breaking existing functionalities, i would like fully decouple version first.
6. skill versioning control, still gating etc.
7. skill format: borrow from all 8 repos, improve it with progressive disclosure, and tests, gates sections, borrow easy and straight forward ideas from 
/Users/maybewu/Documents/Projects/drafts/skill-evolving-papers first, split harder parts to future stages
8. benchmark: based on skillsbench first, should be in first milestone. future milestone to include more benchmark
9. optimization areas
10. other stage and help me design
11. caveats
````

### `98132ca9` · R070

**Tags:** `roadmap-m1-m6`

````text
@/Users/maybewu/Documents/Projects/drafts/zk/TaiChu/docs/architecture/skill-self-evolution-roadmap.md:104 don't refer any doc outside TaiChu, if useful, copy them to doc to be self contained. if no copy, copy the doc to under TaiChu/
````

### `98132ca9` · R071

**Tags:** `other`

````text
are these newly added docs necessary? why not put into the same doc ? as appendxi for easier maintainence?
````

### `98132ca9` · R072

**Tags:** `roadmap-m1-m6`, `decoupling-flags`, `claude-hermes-m1`

````text
@/Users/maybewu/Documents/Projects/drafts/zk/TaiChu/docs/architecture/skill-self-evolution-roadmap.md:68 ensure it borrow full ideas from all the 8 repos especially : claude code dev, hermes, OpenSquilla, openclaw for skill自进化
````

### `98132ca9` · R073

**Tags:** `other`

````text
make it explicit in the doc
````

### `98132ca9` · R074

**Tags:** `roadmap-m1-m6`, `decoupling-flags`

````text
also make it explicit that skill自进化 should have well decoupling design, and design as standalone feature at every milestone, guarded by feature flags. well decoupling desing on code readability, revertability, runtime performance. flexibility to reuse existing interaction_log/in-ram conversation messages (flexibility on reference or copy).
````

### `98132ca9` · R075

**Tags:** `other`

````text
make them explicit in the doc
````

### `98132ca9` · R076

**Tags:** `roadmap-m1-m6`, `decoupling-flags`, `claude-hermes-m1`

````text
mile stone 1: ensure it borrow full ideas from all the 8 repos especially : claude code dev, hermes, OpenSquilla, openclaw for skill自进化. at least one part for each of them
````

### `98132ca9` · R077

**Tags:** `roadmap-m1-m6`, `decoupling-flags`, `claude-hermes-m1`

````text
mile stone 1: ensure it borrow full ideas from all the 8 repos especially : claude code dev, hermes, OpenSquilla, openclaw for skill自进化. at least one part for each of them
````

### `98132ca9` · R078

**Tags:** `other`

````text
how these 8 repos:
1.  track what skills were used
2. when to update skills
3. how to pick one or multiple skills to update
````

### `98132ca9` · R079

**Tags:** `session-scope`, `calling-points`

````text
1. please analyze and note  whether it is session or cross session skill update
2. when to update skills: add more details on which is online, async with the session, offline, or others
````

### `98132ca9` · R080

**Tags:** `roadmap-m1-m6`, `session-scope`

````text
yes, add all these to appendix first and also put relevant parts. online and single session skill自进化 should be in first milestone.
````

### `98132ca9` · R081

**Tags:** `other`

````text
please analyze each of the 8 repos:
1. whether the skill update is via a function call or an agent call
2. function  is a normal tool of agent with same interface, or a general function
keep them to appendix
````

### `98132ca9` · R082

**Tags:** `roadmap-m1-m6`

````text
please design the TaiChu  milestones.
my idea for skill自进化 could be wrong or need to be improved: 
firstly called a  tool with normal agent tool interface
then the tool could be a custom tool called by agent in the future (reusing existing agent design)
more in the future it could use multiple agents to do skill自进化
````

### `98132ca9` · R083

**Tags:** `roadmap-m1-m6`

````text
please design the TaiChu  milestones.
my idea for skill自进化 could be wrong or need to be improved: 
firstly called a  tool with normal agent tool interface
then the tool could be a custom tool called by agent in the future (reusing existing agent design)
more in the future it could use multiple agents to do skill自进化
````

### `98132ca9` · R084

**Tags:** `other`

````text
analyze the 8 repos, when updating skill or skills:
1. does it only create/update only the skill.md or more like scripts
````

### `98132ca9` · R085

**Tags:** `roadmap-m1-m6`, `docs-meta`

````text
M1 skill_evo actions（v1）： propose · patch · list · describe · discard — 详见附录 G.2 JSON schema。
for patch, it seems a tool called by llm model or agent? there seems no fixed rule to call a patch without llm.
is it using the same agent code reused for other agent user session as well? 
if the patch tool is called by llm model or agent already in existing repos, it makes sense to be in milestone one.
````

### `98132ca9` · R086

**Tags:** `roadmap-m1-m6`, `calling-points`

````text
yes, please capture all of these in milestone 1 like calling point: agent session, plugin, blocking or asyc, hook etc. since it is all in milestone 1, design elegantly like underlying libs/functions/tools etc.
````

### `98132ca9` · R087

**Tags:** `decoupling-flags`, `no-modify-tools`

````text
don't modify any existing tools. and there are different tools from different repos for skill自进化， which one you borrow / reuse from other repos? how to design M1 to cover them all, but still in M1
````

### `98132ca9` · R088

**Tags:** `roadmap-m1-m6`, `taichu-code-analysis`

````text
analyze existingTaiChu  skill format, parser, store, tool and remote store or service and interface thoroughly via reading code:
does current Milestone1 need to change any of that?
analyze first, don't modify code or doc yet, just tell me first
````

### `98132ca9` · R089

**Tags:** `calling-points`

````text
add to appendix first.
, optional compaction reinject, and registering the new tool in module.rs: 
1. why compaction comes into the picture
2. if a tool is registered, how is it called(what skill to update, how, patch, which part to patch)
3. it should be by llm model/agent, hook is one way, any other way like plugin, called at specific point like very 5 rounds
4. how does it reuse in-ram msg history?
all these could touch existing code
````

### `98132ca9` · R090

**Tags:** `roadmap-m1-m6`, `decoupling-flags`, `calling-points`, `claude-hermes-m1`

````text
每 5 用户轮（Claude）
✗ → M3
aux LLM + survey
每 N tool iters nudge（Hermes）
✗ → M3
子 Agent 再调 skill_evo: if it is copy frm cluade and hermes, they should be in M1

4. in-ram 消息如何复用？（H.4）
CP	模式	用途
CP-01
InRamBorrow
after_tool_call 里从 tool result 取正文进 registry
CP-02
registry 快照
compact 后重注入，不依赖全 history 扫描
CP-03
Borrow 轻量 + JSONL 写
turn 末写 DecisionLogRecord
CP-04
通常不读全 history
patch 串在 tool args 里
CP-05
JsonlReadOnly
async miner 读 interaction JSONL
M3 review
InRamSnapshot
TurnCompleted 一处拷贝给侧车
禁止：skill-os 跨 turn 缓存 SessionHandle；侧车把全 history 塞回主模型 prompt()。: M1 should cover the existing solutions from other repos
````

### `98132ca9` · R091

**Tags:** `roadmap-m1-m6`, `decoupling-flags`, `calling-points`, `claude-hermes-m1`

````text
每 5 用户轮（Claude）
✗ → M3
aux LLM + survey
每 N tool iters nudge（Hermes）
✗ → M3
子 Agent 再调 skill_evo: if it is copy frm cluade and hermes, they should be in M1

4. in-ram 消息如何复用？（H.4）
CP	模式	用途
CP-01
InRamBorrow
after_tool_call 里从 tool result 取正文进 registry
CP-02
registry 快照
compact 后重注入，不依赖全 history 扫描
CP-03
Borrow 轻量 + JSONL 写
turn 末写 DecisionLogRecord
CP-04
通常不读全 history
patch 串在 tool args 里
CP-05
JsonlReadOnly
async miner 读 interaction JSONL
M3 review
InRamSnapshot
TurnCompleted 一处拷贝给侧车
禁止：skill-os 跨 turn 缓存 SessionHandle；侧车把全 history 塞回主模型 prompt()。: M1 should cover the existing solutions from other repos
````

### `98132ca9` · R092

**Tags:** `docs-meta`

````text
Please add to docs first.
````

### `98132ca9` · R093

**Tags:** `roadmap-m1-m6`, `docs-meta`

````text
is the roadmap ready? does it have metadata like date? is it one single doc? rename it to v1?
````

### `98132ca9` · R094

**Tags:** `co-improve`

````text
does it cover:
cloud / device co-improvement on skills?
device to device co-improvement on skills?
these could happen, right?
````

### `98132ca9` · R095

**Tags:** `calling-points`, `trigger-adapter`

````text
for online, async, offline Evolution: does it have trigger adapter and triggering strategy covered ? like online (plugin, hook etc.) like every 5 turns etc.
````

### `98132ca9` · R096

**Tags:** `other`

````text
add and improve
````

### `4008ce97` · R001

**Tags:** `claude-hermes-m1`

````text
Claude Rev	OpenClaw	Hermes	GenericAgent	OpenSquilla	ZeroClaw	TaiChu
直接 Prompt (Direct Prompt)	★ injected <skill>	Skill tool body	read→prompt	skill_view body	SOP text	skill_view	read content	load_skill result
Tool 包装 (Tool Wrapper)	·	Skill as tool	·	skills as tools: explain skill as tool
````

### `4008ce97` · R002

**Tags:** `other`

````text
give example
````

### `4008ce97` · R003

**Tags:** `other`

````text
what is fm? short for?
````

### `e6cc5cc2` · R001

**Tags:** `roadmap-m1-m6`

````text
Search through my recent agent transcripts to find conversations about: roadmap
````

### `e6cc5cc2` · R002

**Tags:** `other`

````text
what is the title for each fof them
````

### `e6cc5cc2` · R003

**Tags:** `other`

````text
any of them archived.  why not aligned
````

### `current-session` · R006

**Tags:** `co-improve`

````text
P3 platform line is blunt: 无端云跨设备进化同步. Appendix C: 八仓也无 evolution 路径上的跨设备 patch sync.

Could they happen?
Yes. TaiChu already has clouds for collab: remote SubAgent, runs_on / catalog install, session-sync, file push/pull. So in product terms you could invent:

Cloud ↔ device: phone drafts staging → upload skilldiff → PC/cloud review → accept → redistribute via catalog; or cloud miner proposes patches that devices pull after accept.
Device ↔ device: phone learn → push skill package / skilldiff → PC merges with same promote/gates; or remote SubAgent on PC evolves a skill and pulls the package back.
v1 avoids auto versions of that because they mix privacy (don’t sync trajectories), auditability (“cloud rewrote my skill” with no accept), and identity (whose canonical wins across devices).

What’s in scope as a thin precursor (not co-improve)
M5: skill_evo_export_diff / cloud read — exchange approved skill products, import still via M3 accept
Multi-device: share execution (tools / SubAgent), not shared skill-evolution loops
Harmony: evolve on PC → device refresh_skills consumes
If you want this in the doc as a named M7+ / out-of-v1 track (with gates: no trajectory sync, only skilldiff + accept), say so and we can add a short section without expanding v1.0 scope.
these could happen, please add and improve.
````

### `current-session` · R007

**Tags:** `meta-archive`

````text
Please document all of my previous raw requests in this sessions and other sessions
````

