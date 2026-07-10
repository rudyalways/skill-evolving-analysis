# GenericAgent — 20 维度源码分析

> Path: `/Users/maybewu/Documents/Projects/oss/genericagent`  
> Upstream: [lsdefine/genericagent](https://github.com/lsdefine/genericagent)

| # | Dimension | Summary | Key paths |
|---|-----------|---------|-----------|
| 1 | **Architecture** | Monolithic Python: task queue → agent_runner_loop → ga.py handlers | `agentmain.py`, `agent_loop.py`, `ga.py` |
| 2 | **Agent loop** | Sync generator: LLM → tool_calls → dispatch → StepOutcome | `agent_loop.py:42-107` |
| 3 | **Harness** | BaseHandler + StepOutcome; do_{tool} convention | `agent_loop.py:7-29` |
| 4 | **Session** | MixinSession / NativeClaude/OAI; slash /session.* | `llmcore.py`, `agentmain.py` |
| 5 | **Memory** | **L1–L4 tiered markdown**; action-verified axiom | `memory/memory_management_sop.md` |
| 6 | **Skills** | **Not SKILL.md** — `memory/*_sop.md` via file_read | `memory/`, `ga.py:423-425` |
| 7 | **Workflow** | Plan mode; project_mode; ultraplan asset | `ga.py:432-476`, `plugins/project_mode.py` |
| 8 | **Reflection** | `--reflect` mode; Goal Mode inspect/improve | `reflect/goal_mode.py`, `agentmain.py:201-291` |
| 9 | **Self-improvement** | start_long_term_update distillation | `ga.py:508-523` |
| 10 | **Skill evolution** | **None** — hand-authored SOPs only | — |
| 11 | **Prompt** | sys_prompt.txt + anchor working memory rebuild | `ga.py:_get_anchor_prompt` |
| 12 | **Evaluation** | Plan VERIFY gate; Goal Mode cycles | `ga.py:472-475` |
| 13 | **Hooks** | Simple plugin registry: agent/turn/tool events | `plugins/hooks.py` |
| 14 | **Context** | compress_history_tags; trim_messages_history | `llmcore.py:40-111` |
| 15 | **Tools** | JSON schema; do_* on GenericAgentHandler | `assets/tools_schema.json`, `ga.py` |
| 16 | **Multi-agent** | Agent team BBS; checklist subprocess workers | `reflect/agent_team_worker.py` |
| 17 | **Training/RL** | None | — |
| 18 | **Interesting** | Reflect scheduler; L1≤30-line index; anchor prompt | `reflect/scheduler.py` |
| 19 | **Weaknesses** | Sync blocking; no skill gates/versioning | architecture |
| 20 | **For TaiChu** | L0 SOP protocol; reflect cron; Goal Mode loop | comprehensive survey P2 |

## Skill evolution sub-matrix

| Sub | Status | Evidence |
|-----|--------|----------|
| Representation | *_sop.md procedures | `memory/*_sop.md` |
| Loading | On-demand file_read | `ga.py` |
| Evolution | Manual only | — |
| Reflection | Goal Mode; L4 session mining | `reflect/goal_mode.py` |
| Memory types | L1 index, L2 facts, L3 SOP, L4 sessions | `memory_management_sop.md` |
| Harness ext | None for skills | — |
| Evaluation | Plan VERIFY only | `ga.py:472-475` |
| RL readiness | None | — |
| Step traces | temp/model_responses/ logs | `agentmain.py` |
| Versioning | None | — |
| Ranking | file_access_stats.json | `ga.py log_memory_access` |
| Candidates | None | — |
| Auto merge | file_patch for memory | `start_long_term_update` |
