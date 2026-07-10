# Hermes Agent — 20 维度源码分析

> Path: `/Users/maybewu/Documents/Projects/oss/hermes-agent`  
> Upstream: [nousresearch/hermes-agent](https://github.com/nousresearch/hermes-agent)

| # | Dimension | Summary | Key paths |
|---|-----------|---------|-----------|
| 1 | **Architecture** | Python monolith: AIAgent + gateway + Atropos env + plugins | `run_agent.py`, `environments/agent_loop.py` |
| 2 | **Agent loop** | OpenAI tool-calling loop until max_iterations | `environments/agent_loop.py`, `run_agent.py` |
| 3 | **Harness** | Atropos `HermesAgentBaseEnv` for RL/benchmarks | `environments/hermes_base_env.py` |
| 4 | **Session** | SQLite SessionDB + FTS5; gateway session reset | `hermes_state.py`, `gateway/session.py` |
| 5 | **Memory** | MEMORY.md/USER.md + plugin providers (Honcho, mem0) | `tools/memory_tool.py`, `agent/memory_manager.py` |
| 6 | **Skills** | agentskills.io; progressive disclosure | `tools/skills_tool.py`, `skill_manager_tool.py` |
| 7 | **Workflow** | todo tool; cron; delegate; no planner tool | `tools/todo_tool.py`, `delegate_tool.py` |
| 8 | **Reflection** | Verification blocks; **background review** fork | `run_agent.py:1753-1830`, `prompt_builder.py` |
| 9 | **Self-improvement** | Memory/skill nudges + post-turn background agent | `run_agent.py:9604-9632` |
| 10 | **Skill evolution** | **skill_manage** CRUD + background review create/update | `tools/skill_manager_tool.py` |
| 11 | **Prompt** | prompt_builder layers; Anthropic cache control | `agent/prompt_builder.py`, `prompt_caching.py` |
| 12 | **Evaluation** | Benchmark envs; trajectory_compressor; RL tool | `environments/benchmarks/`, `rl_training_tool.py` |
| 13 | **Hooks** | Gateway HOOK.yaml + plugin hooks (dual system) | `gateway/hooks.py`, `hermes_cli/plugins.py` |
| 14 | **Context** | ContextCompressor prune+summarize; frozen memory snapshot | `agent/context_compressor.py` |
| 15 | **Tools** | 40+ tools; terminal backends; MCP; checkpoints | `toolsets.py`, `tools/registry.py` |
| 16 | **Multi-agent** | delegate_task (depth 2); mixture_of_agents | `tools/delegate_tool.py` |
| 17 | **Training/RL** | **First-class**: Tinker-Atropos RL training tool | `tools/rl_training_tool.py`, `hermes_base_env.py` |
| 18 | **Interesting** | Frozen prefix cache; shadow-git checkpoints; skills manifest sync | `memory_tool.py`, `skills_sync.py` |
| 19 | **Weaknesses** | 9.8k-line run_agent.py; no skill ranking/gates | architecture split |
| 20 | **For TaiChu** | Background review + skill_manage + Atropos env interface | comprehensive survey P0 |

## Skill evolution sub-matrix

| Sub | Status | Evidence |
|-----|--------|----------|
| Representation | SKILL.md YAML frontmatter | `skills_tool.py` |
| Loading | Index in prompt; skill_view on demand | `skill_utils.py` |
| Evolution | skill_manage create/edit/patch/delete | `skill_manager_tool.py` |
| Reflection | Post-turn bg review; nudge every 10 iters | `run_agent.py:9604-9610` |
| Memory types | Procedural=skills; declarative=MEMORY.md | `skill_manager_tool.py:10-12` |
| Harness ext | Plugin hooks + Atropos subclass | `hermes_base_env.py` |
| Evaluation | Benchmark rewards only | `environments/benchmarks/` |
| RL readiness | **Strong** | `rl_training_tool.py` |
| Step traces | agent:step hook; trajectory JSONL | `gateway/hooks.py`, `agent/trajectory.py` |
| Versioning | Bundled origin-hash manifest | `skills_sync.py` |
| Ranking | None | — |
| Candidates | None | — |
| Auto merge | None | — |
