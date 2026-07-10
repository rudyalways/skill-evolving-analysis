# OpenSquilla — 20 维度源码分析

> Path: `/Users/maybewu/Documents/Projects/oss/opensquilla`  
> Upstream: [opensquilla/opensquilla](https://github.com/opensquilla/opensquilla)

| # | Dimension | Summary | Key paths |
|---|-----------|---------|-----------|
| 1 | **Architecture** | Gateway → TurnRunner staged harness → Agent FSM | `engine/runtime.py`, `engine/pipeline.py` |
| 2 | **Agent loop** | Explicit FSM: IDLE→THINKING→TOOL_CALLING→DONE | `engine/agent.py`, `engine/types.py` |
| 3 | **Harness** | TurnRunnerHarness stage adapters | `engine/turn_runner/harness.py` |
| 4 | **Session** | SessionManager; compaction lifecycle; archive | `session/manager.py`, `compaction_lifecycle.py` |
| 5 | **Memory** | Hybrid FTS+vector; **Dream** cron promotion | `memory/dream/runner.py`, `dream/ranking.py` |
| 6 | **Skills** | 6-layer precedence; skill + meta DAG | `skills/loader.py`, `skills/types.py` |
| 7 | **Workflow** | **MetaOrchestrator** DAG parallel steps | `skills/meta/orchestrator.py` |
| 8 | **Reflection** | Dream signal classification (correction/failure/positive) | `memory/dream/candidates.py` |
| 9 | **Self-improvement** | **auto_propose** from decision-log co-occurrence | `skills/creator/auto_propose.py` |
| 10 | **Skill evolution** | **proposals → 4-gate → accept MANAGED** | `skills/proposals_lib.py`, `runtime_e2e.py` |
| 11 | **Prompt** | Pre-turn pipeline; SkillInjector full/compact | `engine/pipeline.py`, `skills/injector.py` |
| 12 | **Evaluation** | Proposal gates; meta trigger-accuracy; eval_prompts | `proposals_lib.py`, `meta/trigger_accuracy.py` |
| 13 | **Hooks** | TurnHook, ToolHook, CompactionHook protocols | `engine/hooks/types.py` |
| 14 | **Context** | Compaction; ContextBudgetGovernor; ToolResultStore | `context_budget.py`, `session/compaction.py` |
| 15 | **Tools** | Central dispatch + policy chain; 30+ builtins | `tools/dispatch.py`, `tools/policy/chain.py` |
| 16 | **Multi-agent** | SubagentManager; MetaOrchestrator one-shot agents | `engine/subagent.py`, `meta/executors/agent.py` |
| 17 | **Training/RL** | Squilla Router LightGBM (routing only) | `squilla_router/v4_phase3.py` |
| 18 | **Interesting** | Dream evidence-gated promotion; meta skill_exec entrypoints | `dream/curated_apply.py` |
| 19 | **Weaknesses** | 6000+ line agent.py; steep operational surface | `engine/agent.py` |
| 20 | **For TaiChu** | Proposal+gate pattern; Dream; trigger-accuracy fixtures | comprehensive survey P1 |

## Skill evolution sub-matrix

| Sub | Status | Evidence |
|-----|--------|----------|
| Representation | SKILL.md → SkillSpec; meta adds composition_raw | `skills/types.py` |
| Loading | 6-layer + RRF semantic retrieval | `skills/retrieval/fusion.py` |
| Evolution | auto_propose + Dream hook + meta-creator | `creator/auto_propose.py` |
| Reflection | Dream classify + LLM promotion patch | `dream/runner.py` |
| Memory types | Hybrid chunks; Dream → MEMORY.md | `memory/types.py` |
| Harness ext | runtime_e2e meta vs baseline judge | `creator/runtime_e2e.py` |
| Evaluation | **4 gates** in evaluate_proposal_gates | `proposals_lib.py` |
| RL readiness | Router ML only | `squilla_router/` |
| Step traces | PipelineStepRecord; TraceContext | `observability/trace.py` |
| Versioning | skills-lock.json SHA256 | `skills/hub/lockfile.py` |
| Ranking | Dream rank + RRF | `dream/ranking.py` |
| Candidates | Dream scan + auto_propose chains | `dream/candidates.py` |
| Auto merge | accept_proposal → managed skills | `proposals_lib.py:425` |
