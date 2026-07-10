# Codex (OpenAI) — 20 维度源码分析

> Path: `/Users/maybewu/Documents/Projects/oss/codex`  
> Upstream: [openai/codex](https://github.com/openai/codex)

| # | Dimension | Summary | Key paths |
|---|-----------|---------|-----------|
| 1 | **Architecture** | Rust monorepo: ThreadManager → Session → run_turn | `codex-rs/core/`, `thread_manager.rs` |
| 2 | **Agent loop** | Sampling loop; pre-compact; tool one-at-a-time | `core/src/session/turn.rs` |
| 3 | **Harness** | Product runtime; TestCodex fixture for tests | `core/tests/common/test_codex.rs` |
| 4 | **Session** | thread-store; resume/fork; ThreadMemoryMode | `core/src/codex_thread.rs` |
| 5 | **Memory** | Config memories; 2-phase distill templates; no MEMORY.md | `memories/write/templates/` |
| 6 | **Skills** | core-skills crate; scopes; @mention injection | `core-skills/src/loader.rs`, `injection.rs` |
| 7 | **Workflow** | update_plan; Plan mode; agent_jobs CSV batch | `tools/handlers/plan.rs`, `agent_jobs.rs` |
| 8 | **Reflection** | ReviewTask subagent; Guardian approval reviewer | `tasks/review.rs`, `guardian/mod.rs` |
| 9 | **Self-improvement** | Indirect: filesystem skill edits; generate_memories | `skill-creator/SKILL.md` |
| 10 | **Skill evolution** | **None in core** — user-managed files + sample skill-creator | `tui/config_update.rs` |
| 11 | **Prompt** | AGENTS.md walk; skills metadata block; hook injection | `agents_md.rs`, `available_skills_instructions.rs` |
| 12 | **Evaluation** | Extensive integration tests; skill_approval tests | `core/tests/suite/` |
| 13 | **Hooks** | **Typed Rust hooks**: Pre/PostToolUse, Compact, SessionStart… | `hook_runtime.rs`, `hook_config.rs` |
| 14 | **Context** | Auto compact local+remote; ContextManager; rollout truncate | `context_manager/`, `turn.rs` |
| 15 | **Tools** | ToolRouter; shell, MCP, multi_agents v2, apply_patch | `tools/registry.rs`, `multi_agents_v2.rs` |
| 16 | **Multi-agent** | MultiAgent v1/v2; agent_jobs; ReviewTask; Guardian | `tools/handlers/multi_agents_v2.rs` |
| 17 | **Training/RL** | Telemetry only; tool_dispatch_trace | `tools/tool_dispatch_trace.rs` |
| 18 | **Interesting** | Guardian fail-closed; implicit skill invocation from shell | `guardian/mod.rs`, `skills.rs` |
| 19 | **Weaknesses** | Skills not mutable runtime objects; large crate surface | architecture spread |
| 20 | **For TaiChu** | Typed hook runtime; Guardian reviewer; tool dispatch traces | hooks pattern |

## Skill evolution sub-matrix

| Sub | Status | Evidence |
|-----|--------|----------|
| Representation | SKILL.md + agents/openai.yaml | `core-skills/loader.rs` |
| Loading | SkillsManager cache; metadata budget | `core-skills/manager.rs` |
| Evolution | Out-of-band file authoring | `skill-creator/SKILL.md` |
| Reflection | Manual; ReviewTask for code not skills | `tasks/review.rs` |
| Memory types | Thread memory + AGENTS.md | `agents_md.rs` |
| Harness ext | 10 hook types + MCP plugins | `hook_config.rs` |
| Evaluation | Integration + skill approval tests | `suite/skill_approval.rs` |
| RL readiness | Low — traces only | `tool_dispatch_trace.rs` |
| Step traces | Rollout + dispatch trace + OTEL | `turn_metadata.rs` |
| Versioning | None | — |
| Ranking | None | — |
| Candidates | None | — |
| Auto merge | None | — |
