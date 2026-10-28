# Matrix evolving agents

This is the agent subsystem analogous to `skill_evolving_agents`. Seven narrow agents operate over one segregated run and exchange validated artifacts rather than sharing implicit conversational state.

```text
01 preprocessing → 02 diagnosis → 03 expansion goal → 04 sampling
  → 05 verifier → 06 deterministic judge → 07 visual dashboard
```

Run it directly:

```bash
RUN_DIR=$(sampler workspace init matrix-evolution --runs-root runs)
sampler plan --run-dir "$RUN_DIR" --max-samples 30
sampler run --run-dir "$RUN_DIR" --adapter fake
python matrix_evolving_agents/run_pipeline.py --workspace "$RUN_DIR" --max-layer 3
```

Or use `sampler agents run --run-dir "$RUN_DIR"`.

Each agent has a strict read/write boundary in its numbered directory. The host runner writes atomic stage status records and an append-only `output/logs/agent-execution.jsonl`. Every finding receives an `evolve-goal.json`; the pipeline also writes `diagnosis.json`, `goal-reduction.json`, `sample-queue.json`, `verification.json`, `judge.json`, `pipeline-summary.json`, the complete OOD tree, and the visual dashboard.

The hierarchy is evidence-gated: roots are target-relative ID cells; layer 1 introduces one controlled shift; layer 2 composes two axes; layer 3 explores bounded failure neighborhoods. JSON and SQLite are authoritative. HTML is a review surface.

