# Run guide

`Dockerfile.agent-runtime` builds one reusable Linux runtime containing Python,
Node.js, and Claude Code. It contains no agent briefs, skills, capability data,
or live workspace. For every session, the host runner starts an ephemeral
container and read-only mounts only the selected `AGENT.md`, selected stage
directory, `common`, and `skill_capabilites`. That session's isolated workspace
is the only read-write mount.

The same image runs preprocessing, label-skills, label-traces-cluster, goal,
optimize, verifiter, and judge. Stage isolation comes from the allowlisted
mounts rather than separate images. Canonical turns, pointer manifests, skill
labels, goals, edits, and `verification.json` are the validated handoffs.

## Real run

Keep the trace pool in `workspace/candidate_traces`, beside `workspace/runs`.
Start a run from one trace. The script names it
`run-<source>-<session hex>-<turns>turns` and copies that single JSONL into
`workspace/runs/<run-id>/traces/raw/<source>/`:

```bash
python3 skill_evolving_agents/candidate_traces.py
python3 skill_evolving_agents/candidate_traces.py new run-codex-01a135-73turns
```

The legacy `raw/target_agent` location remains accepted for Codex. Put existing
skills in `workspace/runs/<run-id>/target/to_be_improved_skills`.

## Automated runner

`run_pipeline.py` is the host control plane. By default it selects an
authenticated hosted CLI in this order: Cursor, Codex, Claude Code. The model
runs remotely; only the CLI and its tools run on the host. Multi-source
normalization, feedback detection, exact/near deduplication, feature extraction,
and default clustering are deterministic Python steps and consume no model
tokens. Skill labeling uses the authoritative
run directly. Fanout workers omit raw vendor logs and receive canonical turns,
pointer manifests, the selected stage package, common code, and capability
data.

A Cursor session starts outside this git repository. `--workspace` is that
session view: the stage brief, the stage directory, `common`,
`skill_capabilites`, and a `workspace` link. `--add-dir` adds only that
session's run or worker directory so the sandbox can write it. The prompt
tells the model to read the named skill files and the named input paths, write
the decision, and stop.

Create a one-trace run from the pool. The command creates the run directory
and copies that trace:

```bash
python3 skill_evolving_agents/candidate_traces.py new run-codex-01a135-73turns
```

Put the existing skills in
`skill_evolving_agents/workspace/runs/<run-id>/target/to_be_improved_skills`.

Run without clustering:

```bash
python3 skill_evolving_agents/run_pipeline.py run-codex-01a135-73turns
```

Run with optional semantic clustering. Evolution still defaults to selected
high-confidence findings:

```bash
python3 skill_evolving_agents/run_pipeline.py run-codex-01a135-73turns --cluster
```

Use `--review-clusters` only when a model should review deterministic cluster
names. `common/preprocessing-config.json` selects an `active_profile`. Each
profile chooses one registered adapter, selector, evidence policy, projector,
feature method, clusterer, and naming method. Override it with
`--mining-profile <name>`. Run isolated comparisons with repeatable
`--experiment-profile <name>`; these write only below
`traces/derived/experiments/<name>` and never feed downstream agents.

Built-in algorithms live under
`01_preprocessing_agent/trace_mining/strategies`. Add a strategy there,
register it explicitly, then select it by name in a profile. Arbitrary Python
imports from config are rejected. The default profile retains bounded
tool-evidence hydration and TF-IDF threshold clustering; the `embedding`
profile consumes vectors from `traces/inputs/embeddings.jsonl`.
Canonical turns are pretty JSON under `traces/derived/normalized/turns`.
`signals/findings.jsonl` contains all deterministic findings and
`findings/<signal-id>` contains pointer-only selected scopes. Exact and MinHash
near-duplicate aliases are in `features/dedup-manifest.jsonl`; semantic
clusters contain representative and outlier pointers. Size and token estimates
are written to `logs/metrics.sqlite` and normalized metrics JSON.

Compare the default run with a text-only, cut-only experiment:

```bash
python3 skill_evolving_agents/run_pipeline.py run-001 --cluster \
  --mining-profile default --experiment-profile text-only
```

Diagnosis, goal, and non-conflicting operations each default to 16 concurrent
workers. Use 10 to 20 for this pool:

```bash
python3 skill_evolving_agents/run_pipeline.py run-001 --cluster \
  --cluster-workers 16 --op-workers 16
```

Each worker writes only its private copy. After validation, a single reducer
publishes scoped diagnosis and goal artifacts. Identical proposed operations
are reduced once in `run/goal-reduction.json`. Remaining operations are batched
by affected skill names: disjoint operations run in parallel; update, delete,
merge, split, or create operations that overlap a source or target name run in
later batches. Each operation keeps its Optimize → Verifiter → Judge → optional
retry loop inside one worker. Temporary copies under `.pipeline-workers` are
removed after reduction.

`signals.selection.include_infrastructure_failures` decides whether an
infrastructure-only finding or cluster can evolve a skill. While it is false,
those units never reach Diagnosis, Goal, Optimize, Verifiter, or Judge. The
same predicate runs again before a result is recorded as accepted. A skill
already created from that source is removed, and `run/pipeline-summary.json`
records `accepted: false`. A Judge pass does not override the config.

Authenticate the preferred CLI first:

```bash
agent login
agent status
agent models
```

Cursor is currently the only enabled host backend. Codex, Claude Code, and
Ollama remain implemented but are disabled by default:

```bash
export SKILL_EVOLVER_ENABLE_CODEX=1
export SKILL_EVOLVER_ENABLE_CLAUDE=1
export SKILL_EVOLVER_ENABLE_OLLAMA=1
```

Use `--agent cursor|codex|claude|ollama` to require one enabled backend instead
of automatic selection. Use `--model <model>` with the identifier accepted by
that backend. For Cursor, choose a Claude identifier shown by `agent models`.
The Claude backend defaults to the explicit first-party
`claude-sonnet-5-5` identifier rather than a locally configured model alias.

Ollama is never installed or pulled automatically. After enabling it, pass
`--allow-local-fallback`; its default model is `qwen2.5-coder:1.5b`.

`--agent docker-claude` retains the container-installed Claude Code mode. It
requires `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or
`CLAUDE_CODE_OAUTH_TOKEN`. `--build` builds
`skill-evolver-agent-runtime` once. Claude Code is installed while the image is
built, not during every worker session. Pass
`--build-arg CLAUDE_CODE_VERSION=<version>` to a manual Docker build when a
specific CLI version is required.

The runner executes deterministic preprocessing once and label-skills once. It
fans diagnosis and goal out by selected finding, with a barrier and deterministic
reducer after each stage. It then runs conflict-free operation batches. A
`back` decision repeats Optimize, Verifiter, and Judge once inside that
operation's isolated worker.

This stateful pipeline is intentionally not Docker Compose or one Harbor
dataset run. Harbor is suited to independent trials; these sessions discover
later fanout, isolate mutable work, and reduce validated outputs into one
authoritative workspace.

Mounting only a host CLI command into a container is not sufficient. The host
binary may be for macOS while the image is Linux, and authentication is stored
separately. Container execution therefore needs a Linux CLI installed in the
container plus either an API token or a deliberately mounted credential store.
API tokens are safer than mounting the full Cursor, Codex, or Claude home
directory.

## Manual start

Normally, let the runner build and launch the runtime:

```bash
python3 skill_evolving_agents/run_pipeline.py run-001 \
  --agent docker-claude --build --cluster
```

To build the runtime directly:

```bash
docker build \
  -f skill_evolving_agents/Dockerfile.agent-runtime \
  -t skill-evolver-agent-runtime skill_evolving_agents
```

Each `docker run --rm` is generated by `run_pipeline.py`. It mounts:

- the run or worker workspace at
  `/opt/skill-evolver/skill_evolving_agents/workspace`
- the selected brief at
  `/opt/skill-evolver/skill_evolving_agents/AGENT.md:ro`
- only the selected stage directory at its normal relative path with `:ro`
- `common` and `skill_capabilites` with `:ro`

The entrypoint rejects a container without the workspace mount, agent brief,
`STAGE_DIR`, or selected stage mount. The runner validates outputs before
publishing them and writes authoritative completion records under
`run/status/<stage>/<item>.json`. Containers are removed automatically.

## Stop

Worker containers use `--rm`; no manual container cleanup is needed.
`workspace/runs/<run_id>/` stays on the host and is used for stats, auditing,
and later runs:

- `traces/raw/{codex,claude,cursor}`, immutable vendor logs
- `traces/derived/normalized/turns` and selective tool evidence
- `traces/derived/signals`, selected findings, deduplication features, the cut
  manifest, and optional pointer-only cluster manifests
- `target/to_be_improved_skills` and `target/raw_skills`
- `target/to_be_improved_skills_metadata/metadata.json`
- `run/diagnosis.json`, each `run/<cluster>/evolve-goal.json`, each sliced `run/<cluster>/ops/<op>/evolve-goal.json`, the active compatibility files, and archived `run/<cluster>/ops/<op>/verification.json`
- runner-owned completion records under `run/status/<stage>/<item>.json`
- `logs/execution.jsonl`
- `logs/metrics.sqlite`

## Timing and metrics

Every timed phase writes three synchronized representations:

- `logs/pipeline-timings.jsonl`: append-only human-readable span records
- `logs/pipeline-trace.json`: Chrome Trace Event format; open it in
  `chrome://tracing` or <https://ui.perfetto.dev>
- `logs/metrics.sqlite`: this run's preprocessing and pipeline span tables

The same spans are also inserted into `workspace/metrics.sqlite` for cross-run
statistics. Categories distinguish `llm_agent`, `deterministic`, and
`orchestration` wall time. Agent spans measure the complete CLI session,
including model inference and tools invoked inside that session; provider APIs
do not expose enough portable timing data to split inference from agent tool
time further.

After every run, including a failed one, the runner writes
`logs/run-timing.json`. Open that file first. `policy` states the caps that
were applied. `edits` is one row per goal op with its rank, gate decision,
publication, and the final judge result. `spans[].detail` is the full metadata
for that slice, including fields not shown as columns. `logs/audit.jsonl` and
the instant events in `logs/pipeline-trace.json` are the same decisions on a
timeline. Import the trace in Perfetto and click an instant for the args.

What each mark answers:

- `edit-decision`: why an update was `selected`, `bundled`, `duplicate`,
  `over_cap`, or `below_gate`. Args include `severity`, `confidence`, `score`,
  `match_score`, `super_score`, `min_super_score`, and `max_ops_per_skill`.
  A dropped edit has this mark and no later agent span.
- `goal-decision`: disposition, op names, and skill names for one goal.
- `diagnosis` spans: `slice_user_turns`, `slice_tokens`, `slice_truncated`,
  plus the finding `detector`, `severity`, `confidence`, and `score`.
- `diagnosis-queue`, `goal-queue`, `operation-queue`: wait before that session.
  `operation-queue` for a later same-skill batch starts when operations were
  scheduled, so its duration is the wait behind the earlier edit.
- `optimize`, `verifiter`, `judge`: one slice per attempt. `attempt`,
  `retry_budget`, `max_attempts`, `bundle_size`, and the rank fields are on
  the slice. `session_log` is `logs/sessions/<stage>/<item>.jsonl`. The
  sibling `.prompt.txt` is the prompt. `tool_events` counts tool-call lines
  in that stream.
- `judge-decision`: one instant per judge result. `judge_action` is `pass`,
  `back`, or `fail`. `judge_to` is the edit name the judge wrote. `will_retry`
  is true only when `back` is still inside the budget. The budget is one
  return, so the second `back` has `will_retry` false and the op stops.
  Judge restarts optimize, verifiter, and judge. It does not reopen
  preprocessing, labeling, or goal.
- `worker-copy`: isolated workspace copy, separate from agent time.
- `cut_budget`: every cut window against `max_user_turns` and `max_tokens`.

Use that file to check a timing claim:

- `wall_seconds` is the clock time from the first span to the last.
- Each phase has `sum_seconds` (worker time added together), `wall_seconds`
  (first start to last end), and `peak_concurrency` (how many of that phase
  overlapped). Diagnosis and goals are parallel when peak is greater than 1
  and wall is close to the slowest span rather than the sum.
- Each span row has `queue_wait_ms`, `workers`, `batch_index`, and
  `conflicts`. An operation in a later batch records its wait from the moment
  operations were scheduled, so a same-skill edit shows a long
  `operation-queue` slice while the earlier edit runs.
- Diagnosis rows include `slice_user_turns`, `slice_tokens`, and
  `slice_truncated` for the slice that session was given.
- `tool_events` and `session_log` point at `logs/sessions/<stage>/<item>.jsonl`,
  the raw agent stream. The prompt for that session is the sibling
  `.prompt.txt`. `session_cwd` is the directory the CLI process started in.
- `cut_budget` is copied from `traces/derived/cut/budget.json`, which lists
  every cut window against `max_user_turns` and `max_tokens`.
- `worker-copy` spans are the isolated workspace copy and are separate from
  the agent span.
- `bundle_size` on an optimize, verifiter, or judge span is how many same-skill
  updates were merged into that one pass. `run/goal-reduction.json` records
  `bundled` and `over_cap`. The merged goal's `bundle.selected` lists the
  source edits. The cap is `evolution_policy.max_ops_per_skill` (default 5),
  overridable with `--max-ops-per-skill`.

Updates of the same skill run as one optimize, one verifiter, and one judge.
The runner ranks those updates by super score and keeps the top ones up to
the cap. Super score is severity weight × confidence × (1 + absolute detector
score) + the label-matching score for that skill. Severity weights are low 1,
medium 2, high 3, and critical 4. A missing severity uses weight 1. The best
edit is always kept. Every other edit must reach `min_super_score` (default 0,
`--min-super-score`) or it is recorded as `below_gate` and is not sent to an
agent. Edits past the cap are `over_cap`. The surviving edits are unioned into
one `update` op. Verification and judge still run once, with `--op 1`. Judge
does not rank them again: `pass` is refused when any skill check failed. A
delete, merge, split, or create that touches that skill stays its own pass and
still waits if it conflicts.

`diagnosis-queue`, `goal-queue`, and `operation-queue` are their own Chrome
trace slices, so a Perfetto import shows the wait on a separate track from the
agent session. `run/status/<stage>/<item>.json` still records started, done,
or failed for that step.

Start the live cross-run dashboard:

```bash
python3 skill_evolving_agents/common/metrics_dashboard.py
```

Open `http://127.0.0.1:8765`. The browser queries
`workspace/metrics.sqlite` through `/api/metrics` every two seconds, so active
and concurrent workers appear without regenerating a file. It shows wall time,
summed parallel worker time, category totals, errors, and cross-run average,
P50, P95, and maximum duration by phase.

For a portable static snapshot instead:

```bash
python3 skill_evolving_agents/common/metrics_dashboard.py --snapshot
```
