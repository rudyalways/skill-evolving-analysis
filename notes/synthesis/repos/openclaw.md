# OpenClaw — 20 维度源码分析

> Path: `/Users/maybewu/Documents/Projects/oss/openclaw`  
> Upstream: [openclaw/openclaw](https://github.com/openclaw/openclaw)

| # | Dimension | Summary | Key paths |
|---|-----------|---------|-----------|
| 1 | **Architecture** | Multi-channel gateway + Pi/Codex pluggable harness; plugin-first | `src/gateway/server.ts`, `src/plugins/loader.ts` |
| 2 | **Agent loop** | Outer reply loop → inner retry loop → harness attempt; tool hooks | `auto-reply/reply/agent-runner.ts`, `pi-embedded-runner/run.ts` |
| 3 | **Harness** | `AgentHarness` trait; plugin selection + Pi fallback | `agents/harness/types.ts`, `harness/selection.ts` |
| 4 | **Session** | Session store, lifecycle FSM, write lock, subagent registry | `config/sessions.ts`, `gateway/session-lifecycle-state.ts` |
| 5 | **Memory** | Plugin-slot hybrid FTS+vector; **Dreaming** Light/Deep/REM | `extensions/memory-core/`, `memory-host-sdk/dreaming.ts` |
| 6 | **Skills** | SKILL.md; 6-source merge; lazy load via read tool | `agents/skills/workspace.ts`, `skill-contract.ts` |
| 7 | **Workflow** | `update_plan` tool; cron isolated agents; no symbolic planner | `agents/tools/update-plan-tool.ts` |
| 8 | **Reflection** | MS Teams feedback; dreaming; skill-workshop reviewer | `feedback-reflection-prompt.ts`, `skill-workshop/reviewer.ts` |
| 9 | **Self-improvement** | skill-workshop auto-capture; dreaming auto-write (0.97 conf) | `extensions/skill-workshop/index.ts` |
| 10 | **Skill evolution** | **skill-workshop**: proposals → scan → apply/quarantine | `skill-workshop/store.ts`, `skills.ts`, `tool.ts` |
| 11 | **Prompt** | Layered system prompt; skills snapshot cache; hook mutation | `agents/system-prompt.ts`, `before_prompt_build` hooks |
| 12 | **Evaluation** | qa-lab suites; qa-matrix contracts; trajectory export | `extensions/qa-lab/`, `trajectory/export.ts` |
| 13 | **Hooks** | 70+ plugin hooks + bundled workspace hooks | `plugins/hooks.ts`, `hooks/bundled/` |
| 14 | **Context** | Context engine; compaction-safeguard; history limits | `context-engine/types.ts`, `compaction-safeguard.ts` |
| 15 | **Tools** | openclaw-tools + Pi coding tools + plugin merge + policy | `agents/openclaw-tools.ts`, `tool-policy-pipeline.ts` |
| 16 | **Multi-agent** | subagent spawn; depth/child limits; announce loop | `agents/subagent-spawn.ts`, `subagent-registry.ts` |
| 17 | **Training/RL** | Trajectory JSONL only; no in-repo trainer | `trajectory/runtime.ts`, `trajectory/types.ts` |
| 18 | **Interesting** | Lazy skills; snapshot versioning; compact prompt degradation | `refresh-state.ts`, `workspace.ts` |
| 19 | **Weaknesses** | Monolithic attempt.ts; brittle heuristic signals; no skill ranker | `skill-workshop/signals.ts` |
| 20 | **For TaiChu** | Snapshot skills; proposal queue; trajectory JSONL; context engine API | See comprehensive survey P1 |

## Skill evolution sub-matrix

| Sub | Status | Evidence |
|-----|--------|----------|
| Representation | SKILL.md + SkillProposal create/append/replace | `skill-workshop/types.ts` |
| Loading | Static scan + lazy body + snapshot cache | `workspace.ts` |
| Evolution | Heuristic + LLM review on agent_end | `skill-workshop/index.ts` |
| Reflection | End-of-run; interval-gated LLM review | `reviewer.ts` |
| Memory types | FTS+vector; dreaming phases; session-memory hook | `memory-search.ts` |
| Harness ext | Plugin harness + hook bridge | `agent-harness-runtime.ts` |
| Evaluation | skill-scanner; qa-lab | `security/skill-scanner.ts` |
| RL readiness | Trajectory export partial | `trajectory/` |
| Step traces | openclaw-trajectory JSONL | `trajectory/runtime.ts` |
| Versioning | Monotonic snapshot version | `refresh-state.ts` |
| Ranking | None for skills | — |
| Candidates | maxCandidatesPerRoot + proposal store | `store.ts` |
| Auto merge | auto approvalPolicy + append/replace | `workshop.ts` |
