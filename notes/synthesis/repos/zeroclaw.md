# ZeroClaw — 20 维度源码分析

> Path: `/Users/maybewu/Documents/Projects/oss/zeroclaw`  
> Upstream: [zeroclaw-labs/zeroclaw](https://github.com/zeroclaw-labs/zeroclaw)

| # | Dimension | Summary | Key paths |
|---|-----------|---------|-----------|
| 1 | **Architecture** | Rust modular: agent, tools, memory, skills, gateway, goals | `src/lib.rs`, `src/main.rs` |
| 2 | **Agent loop** | Tool-use loop; parallel/sequential exec; loop detection | `agent/loop_.rs`, `agent/agent.rs` |
| 3 | **Harness** | TurnBuffer; auto_compact_history; multi-format parsing | `agent/loop_/history.rs`, `parsing.rs` |
| 4 | **Session** | SessionManager trait; Sqlite/Memory backends; TTL | `agent/session.rs`, `gateway/ws.rs` |
| 5 | **Memory** | Pluggable: Sqlite, Qdrant, Markdown, hybrid… | `memory/mod.rs`, `memory/hygiene.rs` |
| 6 | **Skills** | SKILL.md or SKILL.toml; open-skills sync | `skills/mod.rs`, `skills/tool_handler.rs` |
| 7 | **Workflow** | Goals engine state/goals.json; SOP gate eval | `goals/engine.rs`, `tools/sop_status.rs` |
| 8 | **Reflection** | LoopDetector warn → hard stop | `agent/loop_/detection.rs` |
| 9 | **Self-improvement** | Nightly consolidation cron; hygiene archival | `cron/consolidation.rs`, `memory/hygiene.rs` |
| 10 | **Skill evolution** | **Audit + load only** | `skills/audit.rs` |
| 11 | **Prompt** | prompt.rs; skills full/compact injection | `agent/prompt.rs`, `skills/mod.rs` |
| 12 | **Evaluation** | Skill audit; economic min_evaluation_threshold | `skills/audit.rs`, `economic/mod.rs` |
| 13 | **Hooks** | HookHandler trait; session_memory (placeholder) | `hooks/traits.rs`, `hooks/runner.rs` |
| 14 | **Context** | auto_compact; CanaryGuard exfiltration block | `loop_/history.rs` |
| 15 | **Tools** | Rich Tool trait; MCP; subagent_spawn | `tools/mod.rs`, `security/policy.rs` |
| 16 | **Multi-agent** | SubAgentRegistry; team topology budgeting | `tools/subagent_spawn.rs`, `agent/team_orchestration.rs` |
| 17 | **Training/RL** | Economic tracker (task payment model) | `economic/tracker.rs` |
| 18 | **Interesting** | LoopDetector; SkillToolHandler shell bridge; team topology | `loop_/detection.rs`, `skills/tool_handler.rs` |
| 19 | **Weaknesses** | SessionMemoryHook no-op; 7000+ line loop_.rs | `hooks/builtin/session_memory.rs` |
| 20 | **For TaiChu** | Loop detection; subagent registry; skill audit | comprehensive survey P2 |

## Skill evolution sub-matrix

| Sub | Status | Evidence |
|-----|--------|----------|
| Representation | SKILL.md / SKILL.toml | `skills/mod.rs` |
| Loading | workspace + open-skills repo | `skills/mod.rs` |
| Evolution | None | — |
| Reflection | Loop detection only | `loop_/detection.rs` |
| Memory types | Multi-backend + categories | `memory/traits.rs` |
| Harness ext | Skill audit | `skills/audit.rs` |
| Evaluation | Audit + economic threshold | `config/schema.rs` |
| RL readiness | None | — |
| Step traces | OTel / runtime_trace | `observability/` |
| Versioning | manifest version field | `skills/mod.rs` |
| Ranking | None | — |
| Candidates | None | — |
| Auto merge | None | — |
