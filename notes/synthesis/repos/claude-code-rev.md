# Claude Code Rev — 20 维度源码分析

> Path: `/Users/maybewu/Documents/Projects/oss/experimental/claude-code-rev`  
> Upstream: [oboard/claude-code-rev](https://github.com/oboard/claude-code-rev) — **社区 source-map 还原，非 Anthropic 官方**

| # | Dimension | Summary | Key paths |
|---|-----------|---------|-----------|
| 1 | **Architecture** | TypeScript/Bun CLI + React Ink REPL; monolithic src/ | `src/main.tsx`, `src/query.ts` |
| 2 | **Agent loop** | Central `query()` async generator → runTools → repeat | `src/query.ts`, `services/tools/toolOrchestration.ts` |
| 3 | **Harness** | Terminal REPL + headless CLI + SDK path | `screens/REPL.tsx`, `cli/print.ts` |
| 4 | **Session** | Disk-backed; --resume; compact_boundary in messages | `utils/sessionStorage.ts`, `sessionRestore.ts` |
| 5 | **Memory** | Auto-memory dir; **auto-dream** consolidation | `services/autoDream/`, `memdir/` |
| 6 | **Skills** | 3-channel: listing attachment, Skill tool, invoked_skills post-compact | `utils/attachments.ts`, `services/compact/compact.ts` |
| 7 | **Workflow** | Plan mode ExitPlanMode; ultraplan feature | `utils/ultraplan/`, `compact.ts` |
| 8 | **Reflection** | Post-sampling hooks; advisor; forkedAgent helpers | `utils/hooks/postSamplingHooks.ts`, `forkedAgent.ts` |
| 9 | **Self-improvement** | **skillImprovement** every 5 turns; skillify bundled skill | `utils/hooks/skillImprovement.ts`, `skills/bundled/skillify.ts` |
| 10 | **Skill evolution** | Auxiliary model JSON patches + user survey apply | `SkillImprovementSurvey.tsx` |
| 11 | **Prompt** | buildEffectiveSystemPrompt priority stack; attachments per turn | `utils/systemPrompt.ts`, `attachments.ts` |
| 12 | **Evaluation** | No in-repo benchmark harness | analytics only |
| 13 | **Hooks** | Rich HooksSchema; skill-scoped; stop hooks | `utils/settings/types.ts`, `query/stopHooks.ts` |
| 14 | **Context** | Multi-tier compact: auto, micro, reactive, collapse | `services/compact/`, `contextCollapse/` |
| 15 | **Tools** | Bash, Read, Write, Agent, Skill, MCP… | `src/tools/` |
| 16 | **Multi-agent** | AgentTool subagents + swarm/teammates | `tools/AgentTool/runAgent.ts`, `utils/swarm/` |
| 17 | **Training/RL** | None | — |
| 18 | **Interesting** | **invoked_skills compaction survival**; usage decay 7d; dual-model split | `compact.ts:1494`, `skillUsageTracking.ts` |
| 19 | **Weaknesses** | Restoration gaps/shims; monolithic files; subagent preload ≠ invoke | `README.md` |
| 20 | **For TaiChu** | invoked_skills; skillImprovement pattern; usage decay | comprehensive survey P0 |

## Skill evolution sub-matrix

| Sub | Status | Evidence |
|-----|--------|----------|
| Trigger | Every 5 REPL turns; /skillify | `skillImprovement.ts:31,75-80` |
| Detection | invokedSkills Map | `bootstrap/state.ts` |
| Proposal | Aux model JSON {section, change, reason}[] | `skillImprovement.ts:33-37` |
| User gate | SkillImprovementSurvey UI | `useSkillImprovementSurvey.ts` |
| Write-back | applySkillImprovement patches disk | survey hook |
| Compaction | invoked_skills attachment survives compact | `compact.ts:1494-1534` |
| Discovery | skill_listing incremental; chokidar reload | `attachments.ts:2661` |
| Usage ranking | 7-day half-life decay score | `skillUsageTracking.ts:44-54` |
| SubAgent preload | metadata only, not invoke registry | `runAgent.ts:577-628` |
