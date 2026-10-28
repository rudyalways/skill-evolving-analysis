# Matrix Sampler

A standalone, local-first system for authorized model and agent sampling, trace mining, deterministic-first verification, sparse coverage planning, and red-team reporting. It stores observable prompts, outputs, tool events, timings, and outcomes—never hidden chain-of-thought. Live testing must be limited to targets, tools, sandboxes, accounts, and data you are authorized to evaluate.

## Five-minute local demo

Requires Python 3.11+.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
sampler target init
sampler scenarios validate
sampler traces ingest tests/fixtures/synthetic-traces.jsonl
sampler plan --budget-usd 1 --max-samples 20 --strategy thompson-diverse --output .sampler/demo-plan.json
sampler run .sampler/demo-plan.json --adapter fake --concurrency 4
sampler report --target draft-unknown-target --output .sampler/report.md
cat .sampler/report.md
pytest -q
```

## Segregated experiment runs

For experiments, create a timestamped run workspace. Each invocation snapshots its own target profile, scenario registry, policy configuration, trace inputs, and plan under `input/`. All mutable state is confined to `output/`: the SQLite database, batch result, report, logs, events, and content-addressed artifacts. A run directory can therefore be archived, copied, or inspected without depending on another run.

```bash
RUN_DIR=$(sampler workspace init deepseek-cache-boundary --runs-root runs \
  --scope both --target-model deepseek-chat \
  --harness matrix-sampler --harness-profile balanced \
  --samples-per-step 25 --steps 4 --max-samples 100 \
  --prompt-set capability-discovery --prompt-set limitations)
sampler traces ingest /path/to/trace.jsonl --run-dir "$RUN_DIR"
sampler plan --run-dir "$RUN_DIR" --budget-usd 5 --max-samples 200
sampler run --run-dir "$RUN_DIR" --adapter fake --concurrency 4
sampler report --run-dir "$RUN_DIR" --target draft-unknown-target
sampler evolve --run-dir "$RUN_DIR" --max-layer 3 --branch-factor 2
sampler dashboard --run-dir "$RUN_DIR"
sampler dashboard --runs-root runs --title "Matrix Evolver · runs"
sampler workspace show "$RUN_DIR"
```

The layout is deliberately explicit:

```text
runs/<name>@<timestamp>/
  manifest.json
  input/
    target-profile.json
    run-config.json
    scenarios.json
    configs/
    traces/
    plan.json
  output/
    sampler.db
    batch-result.json
    report.md
    evolution/
      ood-tree.json
      layer-metrics.json
      history.jsonl
    dashboard.html
    events/
    logs/
    artifacts/
```

Input snapshots and the generated plan carry SHA-256 provenance in `manifest.json`. Name collisions receive `-2`, `-3`, and so on. Commands given `--run-dir` never read or write the shared `.sampler` database. The original non-segregated commands remain available for quick local experiments. `--runs-root` accepts an absolute or relative path, so experiments may live alongside other draft projects or under a dedicated workspace tree.

Every run snapshots `input/run-config.json`, following the explicit profile pattern used by `skill_evolving_agents`. It records whether the run evaluates the target, the harness, or both; target model and adapter; harness name/profile; samples per step, configured steps, total cap, strategy, seed, and concurrency; and evolution depth/branch/node limits. Planning, execution, and evolution consume these run defaults unless a command-line override is supplied. The runs dashboard displays the configuration beside each run so results with different scales are not compared without context.

Prompt sets are also embedded in the same immutable run configuration. Built-ins include `capability-discovery` (for prompts such as “What can you do?”, “What are your capabilities?”, and “What are you good at?”), `limitations`, and `harness-awareness`. Repeat `--prompt-set` to combine them, or provide `--prompt-set-file custom-prompts.json` for run-specific sets. Planning converts the selected sets into ordinary samples with provenance. Their outputs are explicitly tagged `self_report`: they are claims to diagnose and verify, not proof that the target actually has the stated capability.

Rerun `sampler run` with the same plan to see idempotent resume: stable run IDs prevent duplicate invocation and billing. The fake adapter is deterministic per sample. The synthetic trace import produces target-relative ID frequencies and evidence-backed `ood_candidate` proposals for declared-but-unobserved scenarios.

## Commands

```text
sampler target init
sampler workspace init NAME --runs-root runs
sampler workspace show RUN_DIR
sampler scenarios validate
sampler traces ingest PATH [--run-dir RUN_DIR]
sampler matrix build
sampler plan --run-dir RUN_DIR --budget-usd 5 --max-samples 200 --strategy thompson-diverse
sampler run [PLAN.json] [--run-dir RUN_DIR] --concurrency 4
sampler evaluate RUN_OR_BATCH_ID
sampler report --run-dir RUN_DIR --target TARGET_ID
sampler evolve --run-dir RUN_DIR --max-layer 3 --branch-factor 2
sampler dashboard --run-dir RUN_DIR
sampler agents run --run-dir RUN_DIR --max-layer 3
```

The current safe draft target in `target-profile.json` uses replay mode because no target brief was supplied. Replace `unknown` fields with the authorized target’s normal domains/scenarios/capabilities, allowed tools and side effects, budgets, output formats, ground truth, and trace/redaction rules. Secrets are referenced by environment-variable name only.

## Architecture

Adapters only translate transport and event formats. The canonical protocol feeds the scenario registry, candidate planner, budgeted runner, independent verifiers, SQLite event store, aggregate report, and next-sample policy. Raw events and labels are separate. A deterministic failure has precedence over judge labels, while disagreement is retained.

Implemented adapters are an OpenAI-compatible chat API, Anthropic-compatible messages API, in-process callable/fake target, and trace replay. The typed protocol is ready for agent HTTP/SDK/CLI bridges without moving scenario or scoring policy into transports.

The planner uses a seeded greedy pair-coverage approximation rather than a Cartesian product, logs every priority component, suppresses canonical prompt duplicates, and exposes Beta-posterior stop logic. SQLite migrations normalize targets, scenarios, samples, runs, events, labels, cells, policies, artifacts, and trace features. Reports separate adapter/infrastructure errors from target failures.

## Evolving-agent loop and OOD layers

`sampler evolve` follows the evolving-agent pattern from `skill-evolving-analysis`: observable evidence is normalized, gaps are diagnosed, bounded children are proposed, samples verify each proposal, and supported branches are promoted or expanded. Unverified model output never silently rewrites the taxonomy.

- Layer 0 contains ID-observed and ID-declared scenario roots.
- Agents propose slash-separated category paths such as `tool_use/recovery/retryable`.
- Category depth is parsed from the path and is independent of the evolution step number.
- A step may update statistics only, add siblings, or add deeper categories; paths are limited to three segments.

Every node stores parent/child lineage, expansion evidence, mutation instructions, attempts, Beta posterior, confidence interval, failure rate, novel failure count, and cost. Expansion stops at the configured depth, node budget, evidence floor, or when a parent is sufficiently successful and certain. `output/evolution/layer-metrics.json` aggregates performance by depth; `output/evolution/ood-tree.json` retains the complete lineage.

`sampler dashboard` produces a dependency-free, responsive, light-background `output/dashboard.html`. Its connected tree and time controls replay the append-only `history.jsonl`: new nodes grow into view while attempts, posterior means, confidence intervals, failures, and cost update on existing nodes. It also provides layer/status filters, semantic search, lineage inspection, and per-layer metrics. Data is embedded, so it remains usable when a run is archived or moved.

`sampler dashboard --runs-root PATH` builds `PATH/runs-dashboard.html`, following the cross-run picker pattern from `skill_evolving_agents`. It discovers segregated run workspaces recursively, refreshes each run-owned tree dashboard from that run's own `output/evolution/` artifacts, and embeds only the selected run. Runs without a tree remain visible as `tree pending`; no run reads or writes another run's inputs, database, history, or outputs.

## Multi-agent subsystem

The actual staged agent system lives in [`matrix_evolving_agents/`](matrix_evolving_agents/README.md), mirroring the structural role of `skill_evolving_agents` rather than merely borrowing its run layout. It contains seven numbered agents: preprocessing, matrix diagnosis, expansion-goal generation, sampling, verification, deterministic judging, and visual-dashboard generation. Run the complete artifact-validated pipeline with `sampler agents run --run-dir RUN_DIR`.

See [the reference import report](docs/reference-import-report.md) for adopted concepts, conflicts, hashes, and inherited uncovered cells.

