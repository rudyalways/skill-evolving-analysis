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

Keep the trace pool in `workspace/candidate_traces` and source skill inventory
in `workspace/candidate_skills`, beside `workspace/runs`. Start a run from one
trace. The script names it
`run-<source>-<session hex>-<turns>turns` and copies that single JSONL into
`workspace/runs/<run-id>/traces/raw/<source>/`. It also copies each candidate
skill directory containing `SKILL.md` into that run:

```bash
python3 skill_evolving_agents/candidate_traces.py
python3 skill_evolving_agents/candidate_traces.py new run-codex-01a135-73turns
```

The legacy `raw/target_agent` location remains accepted for Codex. Use
`--seed-run` only when a run should inherit another run's skill inventory
instead of `workspace/candidate_skills`.

Candidate inventory is now a validated boundary. Before a new run is seeded,
each skill must pass the authored-skill format checks and any bundled
`evals/evals.json` validation. Invalid skills are excluded and listed with
their errors in `run/trace-selection.json` under `invalid_candidate_skills`;
they are not silently presented to the agents as usable skills. Trace-free
inventory runs write the equivalent audit to
`run/inventory-seed-validation.json`.

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

The deployment profile defaults to `profiles/full-agent.json`, which preserves
the existing behavior. Select and snapshot another validated profile with:

```bash
python3 skill_evolving_agents/run_pipeline.py run-001 \
  --pipeline-profile balanced
```

The selected profile and its digest are written under `run/config`, with a
validated phase envelope under `run/status/control-plane`. The balanced
profile initially places the semantic embedding phase in `observe` mode: its decisions
must be recorded but cannot change routing until the adapters are calibrated.
See `services/embedding_api/README.md` for the standalone service protocol.
`config/super-config.json` registers every selectable phase algorithm and its
canonical input/output contracts. Profile resolution rejects incompatible
algorithm chains before execution and writes the resolved selection to
`run/config/execution-config.json`. Phase-envelope aggregates by phase, mode,
and algorithm are written to `logs/phase-adapter-metrics.json`.
Profiles may also set an agent-call budget. The runner reserves calls atomically
before launching a hosted session and writes `logs/agent-call-budget.json`.
Once `hard_agent_call_cap` is reached, no additional paid agent session starts.

### Configurable funnel targets

Use `profiles/action-oriented-local-service.json` when the purpose of a run is
to exercise the complete evolution funnel rather than minimize calls. Its
`evolution_gate.diagnosis_target_rate` and `maximum_diagnosis_scopes` control
how many selected findings may reach Diagnosis; the agent-call cap remains the
hard safety boundary. `funnel_targets` are optimization objectives, not quotas
that can override evidence, verification, idempotency, or Judge.

`logs/phase-metrics.json` reports these rates and their target deltas:

- `diagnosis_rate`: diagnosed findings / selected findings.
- `goal_decision_rate`: Goal decisions, including evidence-backed no-change /
  selected findings.
- `action_scope_rate`: scopes proposing at least one operation / selected
  findings.
- `novel_action_scope_rate`: action scopes / Goal scopes that were not exact
  replays of an already-applied finding. This is the primary action objective;
  excluding idempotent replay prevents duplicate edits made only to hit a rate.
- `proposal_rate` and `novel_proposal_rate`: operations proposed against the
  corresponding selected or novel denominator.
- `final_acceptance_rate` and `novel_final_acceptance_rate`: accepted
  operations against those denominators.
- `proposal_acceptance_rate`: accepted / proposed operations.

The same report includes distributions for operations per scope, proposed
operation type, accepted operation type, idempotent replay scopes, and target
status (`met`, `missed`, or `unavailable`). A missed target is a tuning signal;
it must never cause the pipeline to fabricate an action or weaken verification.

### Trace-free inventory maintenance

Use `--inventory-only` to inspect and improve the current candidate skill
inventory without supplying a trace. If the named seed does not exist, the
runner creates it from `workspace/candidate_skills` and its cached metadata.

```bash
python3 skill_evolving_agents/run_pipeline.py inventory-maintenance \
  --inventory-only --agent dsh --model deepseek-chat
```

This path skips trace normalization and detection. It deterministically scores
skill pairs, writes `run/inventory-merge-candidates.json`, and materializes one
auditable maintenance finding per qualified pair. Each finding contains the
pair's score, reasons, and complete skill documents. The goal agent may choose
merge, a focused update, or no-change; every proposed mutation still passes
through Optimize, Verifiter, Judge, atomic publication, metrics, and database
capture. A similarity candidate is review evidence, not an automatic merge.

Embedding profiles support `in_process` library calls, a managed
`local_process` with configurable host/port, or `remote_api`. The managed mode
waits for service health and always terminates the child process during runner
cleanup. See `services/embedding_api/README.md`.

A Cursor session starts outside this git repository. `--workspace` is that
session view: the stage brief, the stage directory, `common`,
`skill_capabilites`, and a `workspace` link. `--add-dir` adds only that
session's run or worker directory so the sandbox can write it. The prompt
tells the model to read the named skill files and the named input paths, write
the decision, and stop.

Create, merge, and split Optimize sessions also receive
`workspace/_templates/complete-skill/`, a complete structural reference with
`SKILL.md`, `agents`, `scripts`, `references`, `assets`, and `evals`. The Goal
stage must still authorize every output directory with a concrete resource
contract. New goals record an explicit five-row `resource_plan` covering
`scripts`, `references`, `assets`, delegated `agents`, and `evals`. Each row
records `use` or `omit`, a reason, and confidence; `use` rows must exactly match
the canonical directories named in `dirs`. This preserves negative planning
decisions for audit and learning instead of recording only created resources.
For update and merge, the runner normalizes this plan against the active skill
inventory before Optimize. Existing authored resources are always inherited;
`omit` means only that the new finding does not justify adding that resource
kind. Removal requires a concrete `remove` entry. The deterministic post-edit
validator rejects dropped nested files or eval cases, and accepted operation
`resource-metrics.json` files include inherited, preserved, explicitly removed,
and preservation-rate fields. Generated `agents/openai.yaml` is excluded from
these authored-resource counts.
The optimizer must not edit or publish the reference, and the runner
copies back only operation-named skill directories, so `_templates` cannot
enter the candidate inventory. Update sessions do not receive the reference.

Canonical resource directories allow files up to four path components deep.
After Judge accepts an operation, the runner deterministically creates each
surviving skill's `agents/openai.yaml` from its frontmatter and preserves
unrelated existing policy or dependency blocks. The model does not author the
three standard interface fields. The runner also writes per-operation
`resource-metrics.json`, records the same measurements as a metrics audit event,
and includes run aggregates in the online-learning database. Resource metrics
include per-kind plan compliance plus observed delegated-agent prompt and eval
use. They report delegated agent files separately from deterministically generated
`agents/openai.yaml` interface metadata. Observed runtime
rates remain null when logs contain no corresponding execution or use evidence.

### Release bundles and rollback

Every accepted operation is prepared as a content-addressed release before the
active run inventory is changed. The immutable bundle under
`run/releases/<release-id>/` contains the before and after skill trees,
metadata and changelog snapshots, the exact operation, operation evidence,
tree digests, and replay-derived release channel. `publication.json` records
the release ID and channel.

A qualified paired held-out replay enters the `canary` channel. An otherwise
accepted operation without qualifying replay publishes explicitly as
`provisional`; structural verification is never mislabeled as behavioral
promotion. `run/releases/active.json` is replaced atomically under a
cross-process file lock. `stable.json` advances only after the canary has at
least 20 observations and remains within the failure, latency, and cost
regression bounds. A severe regression rolls back immediately. If inventory
merge fails, the runner restores the captured before snapshot.

Record a canary observation (repeat as traffic accumulates):

```bash
python3 skill_evolving_agents/common/release_bundle.py observe \
  skill_evolving_agents/workspace/runs/<execution-run-id> <release-id> \
  --samples 20 --failures 0 --latency-regression 0.05 --cost-regression 0.02
```

For an operator-directed rollback inside a run workspace:

```bash
python3 skill_evolving_agents/common/release_bundle.py rollback \
  skill_evolving_agents/workspace/runs/<execution-run-id> <release-id>
```

Rollback restores affected skill trees, metadata, and changelogs from the
bundle and writes a rollback record.

### Held-out replay, inventory pointers, privacy, and tenants

Place immutable held-out cases at
`evaluation/held_out/<skill>.json` inside the run workspace and configure
`SKILL_EVOLVER_REPLAY_COMMAND`. The command receives one JSON request on stdin
for each `without_skill` and `with_skill` case and must return a JSON object
with boolean `passed` and `activated` fields; numeric token, tool-call, error,
and timing fields are optional. The runner creates and validates the replay
manifest and benchmark automatically. Without a real evaluator command it
records `not_run` and cannot promote the release.

Published candidate inventories are snapshotted under
`workspace/inventory_releases/<content-digest>/` and selected by the atomically
replaced `workspace/active-inventory.json`. New trace and inventory runs read
the pointer; the legacy candidate folders are only a compatibility mirror.

Normalization redacts credential-shaped values, authorization fields, private
keys, and email addresses before canonical turns, trajectories, or tool
evidence reach agents. Trace strings remain untrusted data; redaction is not an
instruction interpreter. Use `--tenant <id>` to place run state, inventory,
metrics, and optimization data below `workspace/tenants/<id>/`; tenant IDs are
validated before path resolution and traversal values are rejected.

Repeated resource opportunities have a conservative single-session creation
gate. By default it requires confidence `>= 0.90`, at least three occurrences
across three independent windows, no equivalent existing resource, all three
deterministic false-positive guards, and a resource-specific contract. This
does not relax the generic skill-creation recurrence policy.

Resource contracts are provenance ceilings. A repeated-read detector that has
only a source path emits `content_available: false` and
`content_digest_available: false`; Goal may request a navigational index and a
runtime freshness check, but not copied knowledge, exact headings, or a digest
the trace did not provide.

Before Verifier runs, deterministic output validation rejects a positive
resource decision that produced only an empty directory, an authored non-eval
resource that is not mentioned by relative path in `SKILL.md`, or a Python
helper that does not compile. Generated interface metadata cannot satisfy a
delegated-agent resource decision.

Resource coverage reports must distinguish **authored change**, **preserved
coverage**, **suppressed duplicate**, and **no qualifying evidence**. A run
does not count as creating or updating a resource merely because the skill has
an inherited file, an empty directory, generated `agents/openai.yaml`, or an
eval fixture. Reports claiming substantive resource evolution must name the
new or changed file and its accepted operation; unchanged existing scripts or
assets are reported as preserved coverage instead.

Asset detection is command-shaped, not keyword-shaped. A copy/reuse candidate
must be an actual `cp`, `copy`, or `rsync` command whose operand names a
template, starter, or scaffold. A command that only mentions `templates` in a
later query, patch body, or program expression is not asset reuse. When recent
traces contain no genuine reusable starter/template evidence, the precise
result is `no qualifying asset evidence`; profiles must not force an asset
placeholder merely to satisfy a requested resource mix.

Cross-run recurrence for resource opportunities is keyed by detector,
resource family, and normalized resource fingerprint. Reads of unrelated
documents and reuse of unrelated starters cannot mature each other into a
create/update decision.

The current implementation uses evidence-only resource discovery: Goal may
authorize a resource only from the active finding. A deterministic
`resource-script-opportunity` detector promotes qualified repeated polling
mechanics into their own active findings, with a reserved selection slot and an
auditable rejection ledger. This remains conservative and can leave other
resource kinds prose-heavy even when mechanics repeat across runs.
The proposed profile-backed `--resource-discovery` control and its
`evidence-only`, `accumulate`, and `prototype` modes are specified in
[`tuning-guide.md`](tuning-guide.md). The flag is not implemented yet; do not
put it in production commands until it appears in `run_pipeline.py --help`.

Create a one-trace run from the pool. The command creates the run directory
and copies that trace plus the stable candidate skill inventory:

```bash
python3 skill_evolving_agents/candidate_traces.py new run-codex-01a135-73turns
```

Run without clustering. The command moves that seed to
`workspace/runs/<run-id>@YYYY-MM-DDTHH:MM` and removes the unstamped directory:

```bash
python3 skill_evolving_agents/run_pipeline.py run-codex-01a135-73turns
```

Continue a stamped run from a failed optimize, from verification after
optimize saved a skill, or from judge after verification completed. This does
not repeat preprocessing, labeling, diagnosis, or goal. Accepted operations
are left as they are. The run id is the stamped directory name:

```bash
python3 skill_evolving_agents/run_pipeline.py \
  run-codex-01a135-30turns@2026-10-22T19:32 --from optimize
python3 skill_evolving_agents/run_pipeline.py \
  run-codex-01a135-30turns@2026-10-22T19:32 --from verification
python3 skill_evolving_agents/run_pipeline.py \
  run-codex-01a135-30turns@2026-10-22T19:32 --from judge
```

`--from optimize` uses the saved operation goal and reruns optimize, verify,
and judge. It is limited to operations where optimize did not complete.
`--from judge` requires a completed verification result. A verification
timeout has no result to judge, so continue it with `--from verification`.

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
`signals/selection-decisions.jsonl` records why every finding was selected,
rejected, deduplicated, or deferred. Repeated semantically related long-turn
windows can form a bounded `recurring-long-workflow` candidate; a long turn by
itself is never promoted. Selection ranks qualified findings, deduplicates
overlapping evidence, and applies the configured per-run cap.
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

Each worker writes only its private copy. A finding's goal starts as soon as
its diagnosis is validated and published; diagnosis and goal share the cluster
worker cap. Operation scheduling still waits until every goal exists. Identical
proposed operations are reduced once in `run/goal-reduction.json`. Remaining
operations are batched
by affected skill names: disjoint operations run in parallel; update, delete,
merge, split, or create operations that overlap a source or target name run in
later batches. Each operation keeps its Optimize → Verifiter → Judge pass
inside one worker; retries are disabled. Judge is a deterministic host step:
after Verifiter output passes its contract, it maps `overall_status` directly
to terminal `pass` or `fail` without another model call. Temporary copies
under `.pipeline-workers` are removed after reduction.

Each proposed op also owns a durable directory at
`run/<finding-id>/ops/<op-index>/`. It always contains the sliced goal,
verification input, verification result or terminal skip/failure marker,
judge record, and changelog. The judge record hashes the other four artifacts.
The changelog keeps current phase state plus append-only phase events. Gates,
deduplication, bundling, and worker failures produce complete terminal bundles
instead of leaving missing files.

A `no_change` scope writes the same five files directly under
`run/<finding-id>/`. Its dated changelog records Goal as completed and
Optimize, Verification, and Judge as skipped, so an early terminal decision
does not leave later phases unaudited.

`signals.selection.include_infrastructure_failures` decides whether an
infrastructure-only finding or cluster can evolve a skill. While it is false,
those units never reach Diagnosis, Goal, Optimize, Verifiter, or Judge. The
same predicate runs again before a result is recorded as accepted. A skill
already created from that source is removed, and `run/pipeline-summary.json`
records `accepted: false`. A Judge pass does not override the config.

The checked-in configuration selects Codex with `gpt-6-luna`, the
cost-efficient model for scoped work. Verify the CLI installation and sign-in:

```bash
codex --version
codex login status
codex doctor --summary
```

The agent and its model come from `common/agent-config.json`. Each entry has
`backend`, `model`, and `status`. Exactly one status is `active`. The runner
uses that entry. Change which one runs by marking it `active` and the others
`inactive`. A one-call smoke test that does not modify the repository is:

```bash
codex exec --ephemeral --sandbox read-only --model gpt-6-luna \
  "Reply with exactly: CODEX_OK"
```

Supported host backends are Cursor (`agent`), Claude Code (`claude`), Codex
(`codex`), DeepSeek Harness CLI (`dsh`), Hermes Agent (`hermes`), and
OpenClaw (`openclaw`). The last three use their documented one-shot entry
points: `dsh --profile headless`, `hermes --oneshot`, and
`openclaw agent exec --message-file -`. They are optional installations; an
explicitly selected backend fails before a run when its executable or
authentication check is unavailable.

DSH resolves from `DSH_BIN`, `PATH`, the installed application, or a mounted
DeepSeek Harness image, in that order. Set `DSH_PATCH` when the headless
profile needs an additional provider patch. The runner invokes `dsh` directly;
it does not depend on an example wrapper or checkout. When DSH's configured
model is `flint`, the runner automatically applies
`config/dsh-flint.patch.yml`, which reads `FLINT_BASE_URL` and
`FLINT_API_KEY` from the environment.

The signed-in DeepSeek account patch uses `deepseek-flash` with low reasoning
effort. Pipeline stages already constrain inputs, validate every handoff, and
price verification deterministically; high reasoning effort mainly increased
stage self-dialogue in measured runs without improving accepted outcomes.
The patch also sets DSH's approval policy to `never` so unattended headless
runs do not open the desktop approval window. This does not select DSH's
`danger-full-access` permission preset: the normal `workspace-write` sandbox
remains in effect through the `headless-workspace-write` preset. Remove the
`approval` and `permission` entries from the patch when interactive
confirmation is preferred.

Verifier sessions use an evidence-bundle protocol. For creates, the host embeds
the candidate `SKILL.md`. For updates, it computes immutable boundary facts for
frontmatter, preamble, and unclaimed sections, then embeds only the claimed
candidate sections. It lists all resource paths but embeds resource contents
only for directories required by the goal. Existing inventory descriptions
provide a compact duplicate/subsumption check. The model therefore performs
only the semantic exception decision and uses no tools.
Filesystem shape, hashes, scoring, schema validation, aggregation, and judge
actions remain runner-owned. Removed delete targets and merge/split sources are
verified entirely deterministically when their immutable baseline exists and
their candidate path is absent. In the first like-for-like DSH benchmark, an
accepted update fell from 101.8 seconds to 10.9 seconds without changing its
verdict. A later large-update regression reached 111.7 seconds; the narrowed
boundary-fact bundle replayed that same accepted update in 20.9 seconds with
the same pass verdict.

Every published goal records one recall observation for every inventory skill
in `skill_recall_observations` in `workspace/metrics.sqlite`: recalled rows
carry their rank and score, while non-recalled inventory rows record the same
scope as an exposure. These durable rows, rather than file timestamps or an
absence inferred from logs, feed retirement eligibility. When embedding or
taxonomy recall reports no candidate, a conservative lexical collision guard
compares only the diagnosis and generalized lesson with existing skill names,
descriptions, and instructions. It can recover likely existing skills for Goal
to update, but cannot by itself authorize a merge or delete.

`workspace/operation-coverage.json` aggregates proposed, accepted, and rejected
create/update/delete/merge/split operations from retained real run summaries.
It deliberately excludes unit tests, and `unverified_real_operations` makes
missing live coverage explicit rather than allowing contract tests to be
mistaken for end-to-end evidence.

Inventory-only runs also evaluate conservative retirement candidates. A skill
is eligible for delete review only after at least 20 distinct recall scopes recorded
after its own evaluation timestamp, zero recalls in those scopes, at least
0.90 weighted capability-label containment by one surviving skill, and at
least 0.90 instruction-token containment by that same skill. The goal agent may
delete only the nominated quiet skill and must otherwise choose `no_change`.
This keeps newly created, low-frequency, and merely similar skills out of the
retirement path. The detector nominates candidates; normal optimize,
verification, judge, publication, and coverage records remain mandatory.
Replaying the same finding under multiple run IDs still counts as one scope;
reruns cannot manufacture retirement evidence.
Every inventory evaluation writes `run/inventory-retirement-evidence.json`
for all current skills, including threshold progress, recalled-scope count,
best subsumer and containment scores, eligibility, and explicit blockers. This
artifact is the tuning and audit surface even when no delete is nominated.
Inventory-only audits give legacy metadata entries that lack `evaluated_at` a
one-time baseline with reason `legacy_inventory_backfill`. Existing lifecycle
timestamps are preserved, and observations before the baseline never count
toward retirement.
Only directories containing `SKILL.md` (or legacy `skill.md`) are inventory
members. Empty resource directories left behind by a removed skill are not
allowed to resurrect it or force an unnecessary relabel pass.

Accepted delete, merge-source, and split-source removals are recoverable.
Immediately before removing a candidate-pool directory, publication copies
the complete skill to
`workspace/quarantine/retired/<skill>/<run-digest>/skill/`, copies its external
changelog, and writes `retirement.json` with the originating run, metadata
snapshot, and pre-removal content digest. The operation bundle also writes
`retirement-archives.json`. Publication refuses an archive-path collision when
the saved content differs; a deletion therefore cannot silently overwrite its
rollback source.

The inactive Hermes and OpenClaw examples use the local Recursive Flint model.
Load `/Users/maybewu/Documents/Projects/myexpore/recursive/.env` in the shell,
then configure the CLI provider with `FLINT_BASE_URL` and `FLINT_API_KEY`.
Hermes uses its configured `HERMES_HOME`; OpenClaw uses
`OPENCLAW_CONFIG_PATH` and `OPENCLAW_STATE_DIR`. The runner inherits those
variables but never copies their values into run artifacts. The endpoint
should expose model id `flint`, with OpenClaw's provider/model reference set to
`flint-local/flint`. When the executables are not on `PATH`, the runner checks
`../../oss/hermes-agent/.venv/bin/hermes` and `../../oss/openclaw/openclaw.mjs`;
`HERMES_BIN`, `OPENCLAW_BIN`, and `OPENCLAW_NODE` remain explicit overrides.
DSH, Hermes, and OpenClaw are configured for the same local Flint endpoint.
Override any configured model for one run with `--model`.

## Runtime goal

End-to-end wall time, including every agent phase, should stay within:

- 5 minutes for a short trace (up to 30 user turns)
- 10 minutes for a long trace (more than 30 user turns)

The runner now enforces these ceilings, rather than treating them only as an
operator convention. `run/config/runtime-budget.json` records the selected
five- or ten-minute budget, and every agent session timeout is clamped to the
remaining end-to-end budget. A late verifier therefore cannot extend a short
run beyond its five-minute policy window.

The low-cost profiles request Qwen3-Embedding-0.6B. If its optional
`sentence-transformers` runtime is unavailable, startup degrades explicitly to
the deterministic hashing-reference backend and writes
`run/config/embedding-runtime-fallback.json`. This is an auditable degraded
mode, not a claim that hashing has Qwen-level semantic quality; install
`services/embedding_api/requirements.txt` to remove the fallback.
The fallback covers both in-process construction errors and managed local
services that start but exit before becoming healthy. When the signed-in
DeepSeek DSH patch is selected, the recorded model is `deepseek-flash` rather
than the unrelated default model from `agent-config.json`.

The CPU-local profile bounds semantic-filter inputs and recalled skill
documents to 1,200 characters and gives the shared Qwen process a 60-second
request budget. On the measured nine-skill inventory this reduced semantic
filtering from 29.97 seconds to 14.30 seconds and allowed native embedding
recall to complete without fallback. Any recall fallback records both
`fallback_from` and `fallback_error` in `label-matching.json`; it must not be
reported as native embedding recall.

The local embedding service batches all candidate texts in one model call and
all instructed queries in a second model call. On the same seven-finding,
1,200-character Qwen3-Embedding-0.6B workload, this reduced measured semantic
filter service time from 43.31 seconds to 7.40 seconds (82.9%) while preserving
the model revision, inputs, ranking formula, and downstream selection policy.
`run/status/semantic-prefilter/all.json` records both `service_ms` and
end-to-end `wall_ms`; `logs/phase-adapter-metrics.json` must report the latter
rather than zero so latency optimization uses measured execution time.
The local Qwen CPU profile gives semantic filtering and recall 30-second HTTP
timeouts. Batched inference is measured near 7.4 seconds on the reference
machine, so the generic 1.5-second remote-service default is not suitable for
this profile. Phase timeouts must cover measured warm inference latency and
must not exceed the embedding runtime's 60-second request ceiling.

Replaying an already-applied finding is idempotent. Before Goal, the runner
scans every current inventory changelog for that exact finding ID; this check
does not depend on which skills semantic recall happens to return. A match
writes a deterministic `no_change` and skips Goal, Optimize, Verify, and Judge
agent calls. A failed selected Diagnosis or Goal lane is never converted into
`no_change`: the run fails explicitly while preserving its status and timing
artifacts for retry.

`logs/run-timing.json` reports conservative agent-call savings. The actual
count comes from recorded LLM spans. Each mined finding deferred by the
evolution gate counts as two avoided calls—Diagnosis and Goal—and no assumed
Optimize or Verify saving is added because those calls depend on a proposed
operation. Diagnosis coverage uses scopes admitted by the evolution gate as
its denominator while retaining `mined_selected_scopes` separately. This makes
intentional filtering visible as savings instead of falsely reporting missing
diagnosis work.

Low-cost recurrence also persists across runs. Before Diagnosis, every selected
finding contributes one observation per source session to
`finding_recurrence_observations` in `workspace/metrics.sqlite`. The evolution
gate groups observations by detector and counts distinct source sessions;
rerunning the same trace cannot manufacture recurrence. Its
`traces/derived/evolution-gate.json` decision records current and historical
session counts, current and accumulated evidence counts, and the recurrence
key. A finding that matures through historical evidence still proceeds through
normal semantic recall and Goal, so an existing skill can yield `no_change`
instead of a duplicate update or create.

These are total-run ceilings, not per-agent allowances. If a run crosses its
ceiling, stop it and treat the delay as a pipeline defect. Do not normalize a
long-thinking or stalled provider session by extending the wait. Preserve the
phase statuses and timing artifacts, then investigate fanout size, prompt/input
size, provider latency, and missing process timeouts before retrying.

Each hosted agent session is terminated after 180 seconds so one stalled
fanout item cannot consume the total-run budget. Verification is the
exception. One skill's checks and scored JSON were still being written at
180 seconds, so a verifier session is terminated after 360 seconds
(`SKILL_EVOLVER_VERIFIER_TIMEOUT_SECONDS`). Skills named by one operation
start together, and the operation waits for the slowest skill. Set
`SKILL_EVOLVER_AGENT_TIMEOUT_SECONDS` only for a measured diagnostic override
of the other stages. Raising either limit does not change the 5/10-minute
total-run ceilings.
Diagnosis, goal, optimize, verification, and judge timeouts are lane-local.
The failed lane records a short status and stays out of later phases.
When optimize finishes, its skill is saved under
`run/<finding>/ops/<n>/candidate/` before verification starts. A later
verification or judge failure keeps that copy. Continue that run with
`--from verification` or `--from judge`. Successful lanes continue through
reduction, optimization, verification, judge, and publication.

`--agent` overrides the active backend for one invocation and still uses that
backend's configured model. `--model` overrides only the model.

`--agent docker-claude` retains the container-installed Claude Code mode. It
requires `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or
`CLAUDE_CODE_OAUTH_TOKEN`. `--build` builds
`skill-evolver-agent-runtime` once. Claude Code is installed while the image is
built, not during every worker session. Pass
`--build-arg CLAUDE_CODE_VERSION=<version>` to a manual Docker build when a
specific CLI version is required.

The runner executes deterministic preprocessing once and label-skills once. It
fans diagnosis out by selected finding and starts that finding's goal as soon
as its diagnosis is published. Diagnosis and goal share the cluster worker cap.
A deterministic reducer publishes each artifact, and operation scheduling waits
until every goal exists so same-skill edits can be reduced together. It then
runs conflict-free operation batches. A single Optimize, Verifiter, and Judge
pass runs inside each operation's isolated worker. Retries are disabled.

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
- `target/to_be_improved_skills_metadata/metadata.json` holds skill records and no changelog. The runner reads and writes it. Each skill's history is the append-only `target/skill_changelogs/<skill>.md`. An optimize session receives a temp directory, `optimize-input/`, containing that skill directory and `<skill>.md` beside it, and does not receive metadata. After the run, skill directories go to `workspace/candidate_skills`, metadata to `workspace/candidate_skills_metadata/metadata.json`, and changelogs to `workspace/candidate_skills_changelog/<skill>.md`. The next `candidate_traces.py new` copies those three into the run.
- Publication validates every skill before copying it. The complete decision is
  written to `run/inventory-publication-validation.json`; invalid directories
  are excluded, and incremental publication refuses an invalid accepted skill.
- `run/pipeline-summary.json.outcome` distinguishes inherited inventory from
  work performed in this run. Use `inherited_skill_count`,
  `proposed_operation_count`, `accepted_operation_count`,
  `rejected_operation_count`, `accepted_changed_skills`, and
  `zero_accepted_changes` when comparing runs. A directory visible after a run
  is not evidence that the run created or updated it.
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
- `optimize`, `verifiter`, `judge`: one slice per operation. `attempt`,
  `retry_budget`, `max_attempts`, `bundle_size`, and the rank fields are on
  the slice. `session_log` is `logs/sessions/<stage>/<item>.jsonl`. The
  sibling `.prompt.txt` is the prompt. `tool_events` counts tool-call lines
  in that stream.
- `judge-decision`: one instant per judge result. `judge_action` is `pass` or
  `fail`; `judge_to` is empty and `will_retry` is false because
  `retry_budget` is 0 and `max_attempts` is 1.
- `worker-copy`: isolated workspace copy, separate from agent time.
- `cut_budget`: every cut window against `max_user_turns` and `max_tokens`.

Use that file to check a timing claim:

- `wall_seconds` is the clock time from the first span to the last.
- Each phase has `sum_seconds` (worker time added together), `wall_seconds`
  (first start to last end), and `peak_concurrency` (how many of that phase
  overlapped). Diagnosis workers are parallel when peak is greater than 1
  and wall is close to the slowest span rather than the sum. A goal span may
  overlap a later finding's diagnosis.
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
  source edits. The cap is `evolution_policy.max_ops_per_skill` (default 3),
  overridable with `--max-ops-per-skill`.
- A non-representative bundled source remains `skipped` for its own optimize,
  verification, and judge phases because those phases run once on the merged
  representative. Its `publication.json` uses outcome `bundled` and
  `selected_operation` points to the authoritative verified operation.

Updates of the same skill run as one optimize, one verifiter, and one judge.
The runner ranks those updates by a bounded priority score and keeps the top
ones up to the cap. Severity maps to low .25, medium .50, high .75, and
critical 1.00. Detector strength is `abs(score) / (abs(score) + 4)`, and skill
match is clamped to `[0, 1]`. Priority is `.40*severity + .30*confidence +
.20*detector_strength + .10*skill_match`. The component values are stored in
`score_components` for audit. The best edit is always kept. Every other edit
must reach `min_super_score` (default 0.65,
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
