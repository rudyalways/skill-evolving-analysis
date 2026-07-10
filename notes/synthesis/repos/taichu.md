# TaiChu — 20 维度源码分析

> Path: `/Users/maybewu/Documents/Projects/drafts/zk/TaiChu` (private)  
> Upstream: [taichu.fun/gitea/SystemAgentDev/TaiChu](https://taichu.fun/gitea/SystemAgentDev/TaiChu.git)

| # | Dimension | Summary | Key paths |
|---|-----------|---------|-----------|
| 1 | **Architecture** | Rust layered SDK L1–L5; 端云协同 overlay | `docs/overview.md`, `core/taichu-core-sdk/` |
| 2 | **Agent loop** | Pi-mono dual loop; steer/follow-up; StreamFn injected | `core/agent-loop/src/agent_loop.rs` |
| 3 | **Harness** | Embeddable library; Runtime/SessionManager facade | `core/taichu-core-sdk/src/runtime.rs` |
| 4 | **Session** | Multi-instance (session, channel, device); JSONL/DB history | `docs/architecture/session-management.md` |
| 5 | **Memory** | MEMORY.md in prompt; MemoryStore planned | `core/agent-framework/src/prompt_builder.rs` |
| 6 | **Skills** | Catalog XML + **load_skill**; runs_on device routing | `core/builtintools/src/skill/load_skill.rs` |
| 7 | **Workflow** | No built-in plan mode (benchmark gap doc) | `docs/architecture/agent-benchmark-improvement-plan.md` |
| 8 | **Reflection** | Design-only; no reflect scheduler | `docs/architecture/user-interaction-improvement.md` |
| 9 | **Self-improvement** | **None runtime** | comparison doc L952 |
| 10 | **Skill evolution** | **None** — P2 roadmap only | `docs/architecture/skill-system-cross-repo-comparison.md` |
| 11 | **Prompt** | LocalFsPromptBuilder ordered assembly | `core/agent-framework/src/prompt_builder.rs` |
| 12 | **Evaluation** | Benchmark improvement plan; integration tests | `core/*/tests/` |
| 13 | **Hooks** | TransformContext; Before/AfterToolCall; hook gateway design doc | `docs/architecture/extension-hooks-and-timing.md` |
| 14 | **Context** | LLM summarization compaction; **load_skill body may be lost** | `core/agent-session/src/compaction.rs` |
| 15 | **Tools** | Trait ToolDefinition + ToolDomains filtering | `core/builtintools/`, `tool_domains.rs` |
| 16 | **Multi-agent** | run_subagent local/remote; no skill inherit | `core/subagent/`, comparison doc L776-781 |
| 17 | **Training/RL** | None; llm-router only | `services/rust/llm-router/` |
| 18 | **Interesting** | **runs_on + remote delegation**; A-system per-turn skill list | `load_skill.rs:110-132`, taichu-service api |
| 19 | **Weaknesses** | No invoked_skills; no evolution; no subagent skill preload | comparison doc L47-51 |
| 20 | **For TaiChu** | See comprehensive survey P0–P3; existing comparison doc | `skill-system-cross-repo-comparison.md` |

## Skill evolution sub-matrix

| Sub | Status | Evidence |
|-----|--------|----------|
| Trigger | ❌ None | comparison doc L952 |
| Detection | Interaction JSONL only | comparison doc L831 |
| Proposal | ❌ Design P2 | comparison doc L982-983 |
| User gate | ❌ | comparison doc L839-841 |
| Write-back | ❌ Agent cannot write canonical skills | comparison doc L1057 |
| Compaction | ❌ **Risk:** load_skill body summarized away | `context-and-skills.md:64-68` |
| Discovery | Session scan; Toollery filter; A-system wire | `prompt_builder.rs`, `session.rs` |
| Usage ranking | ❌ | comparison doc L973 |
| SubAgent skills | ❌ Child rescans roots only | `manager.rs:1736-1796` |
| Cloud/device routing | ✅ runs_on + remote_delegation | `load_skill.rs:110-132` |

## 已有深度文档

`/Users/maybewu/Documents/Projects/drafts/zk/TaiChu/docs/architecture/skill-system-cross-repo-comparison.md` — 8-repo 对比 v2 (2026-07-06)，本调研与其结论一致并扩展至 20 维度。
