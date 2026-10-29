# Agent handoff: Skill Evolving Agents

Updated: 2026-10-28 (Asia/Hong_Kong)

## Objective

Continue engineering this system into a reliable, measurable, resource-aware
skill evolution pipeline:

```text
trace or inventory evidence
  -> deterministic normalization and signal detection
  -> low-cost semantic filtering and skill recall
  -> bounded diagnosis and goal decisions
  -> create/update/merge/split/delete/no-change
  -> verification and deterministic judgment
  -> atomic publication, inventory update, metrics, and replay feedback
```

Optimize for useful, auditable changes—not merely for pipeline activity or
directory creation. `scripts/`, `references/`, `assets/`, `agents/`, and
`evals/` should be created or updated only when evidence demonstrates reusable
value. Reject placeholders, copied prose, trivial echo scripts, unused files,
and changes made only to satisfy target rates.

## Start here

Read these files before editing:

- `readme.md`
- `run-guide.md`
- `tuning-guide.md`
- `config/knob-registry.json`
- `profiles/action-oriented-local-service.json`
- `common/pipeline_metrics.py`
- `run_pipeline.py`
- `tests/test_pipeline_contracts.py`

Before changing anything:

```bash
git status --short --branch
git fetch origin
git log --oneline --left-right HEAD...origin/main
git diff --stat
```

Preserve all existing modified and untracked files. Never use `git reset
--hard`, `git clean`, or broad restore commands in a dirty checkout. Prefer a
clean worktree based on `origin/main` for isolated work and verification.

## Current verified baseline

The personal repository baseline is:

```text
43dacac Separate draft targets from reviewed gold labels
```

That commit passed all 219 tests in a clean worktree and the 23-case
deterministic funnel benchmark at 23/23. It includes configurable funnel
targets, single-session diagnosis controls, novel-versus-idempotent metrics,
an action-oriented profile, inventory and release helpers, replay support,
privacy helpers, dashboard extensions, and:

- `evaluation/funnel_benchmark.py` with `evaluation/funnel_cases.json`: labeled
  calibration and held-out cases for positive, negative, already-applied,
  semantic-policy, creation-policy, and resource-usefulness boundaries;
- cross-session grouping for repeated references, starter assets, and delegated
  prompts, so the evolution gate receives the recurrence evidence it scores;
- converged replay accounting: resource opportunities suppressed because an
  equivalent authored resource exists count as already applied, so a replay
  reports `converged` consumer targets instead of false `missed` targets;
- fixed-key operation breakdowns in every phase (`proposed_by_operation`,
  `changed_by_operation`, `operations_by_operation`, `passed_by_operation`,
  `accepted_by_operation`), including explicit zero merge/split/delete counts;
- reference consolidation by source root, deterministic Diagnosis for
  qualified resource findings, exact-replay detection before Diagnosis, an
  18k verifier evidence cap, and a 150-word Optimize response budget;
- a stage-addressable golden benchmark (`evaluation/benchmark_core.py`,
  `evaluation/cases/`) with six trace cases covering create, update, merge,
  split, delete, and no-change, validated golden diagnosis/action contracts,
  pending human-review states, `--require-reviewed`, `--require-gold`, and an
  HTML dashboard. Agent-authored labels are `draft`; two independent reviewers
  covering domain-expert and user-advocate roles are required for `gold`.

Four fresh/replay trace runs after these changes used 37 DSH calls and 7.75M
tokens versus 53 calls and 10.87M tokens before (28.7% fewer tokens, about 32%
lower peak cost). Wall time was mixed: A and C improved, B and the
non-equivalent D run were slower; do not claim aggregate wall-time savings.

A controlled duplicate-inventory structural benchmark produced accepted merges
in 9 of 10 inventory-only runs; the remaining run correctly chose no_change
for two references covering different documents. Three early runs emitted two
merge operations for the same duplicate pair, which led to candidate
deduplication: one review unit now claims a skill set, overlapping candidates
are retained under `suppressed_candidates`, and a verification run emits one
merge with two suppressed candidates. This is test evidence, not a production
inventory change.

Controlled split and delete scenarios also reached accepted publication. Split
parts now receive metadata rows with inherited labels; the split run produced
release-handbook and retention-handbook and removed ops-handbook. A retirement
scenario with post-creation non-use and content/label subsumption produced one
accepted delete after delete candidates were included in candidate
deduplication.

The pre-fix reference run on the same 23 cases passed 20/23. All three failures
were supporting resources used once in each of three sessions.

The separate `celia-hk-agent/skill-evolving-agents` repository is the
privacy-reviewed public export of this directory. It mirrors the public-safe
tracked files; credentials, raw traces, private documents, generated run
state, and internal product snapshots are excluded. It is not a configured
remote, subtree, submodule, or automatic mirror. Review every export before
pushing.

## Cost-aware execution

Use the lowest adequate tier:

1. deterministic rules, regex, scripts, and contracts
2. local embedding inference
3. small hosted model or agent harness
4. large model only for cases requiring additional intelligence

The action-oriented local profile uses:

- embedding model: `Qwen/Qwen3-Embedding-0.6B`
- pinned revision: `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`
- dimensions: 1024
- default local endpoint: `127.0.0.1:8181`
- deterministic hashing fallback when the service cannot start

Use DSH with DeepSeek for hosted agent phases when requested. Do not silently
replace it with Codex for paid trace runs. Keep trace identity separate from
runner/model identity in names and metadata.

Credentials belong only in the ignored repository-root `.env`. Never print,
commit, or copy credential values into prompts, logs, fixtures, or docs.

## Highest-priority engineering work

### Build a labeled benchmark

Create privacy-safe calibration and held-out cases covering:

- create, update, merge, split, delete, and no-change
- useful and unnecessary scripts/references/assets/agents/evals
- single-session and repeated multi-session evidence
- already-applied/idempotent evidence
- false-positive methodology extraction
- noise, missing evidence, malformed traces, and execution failures

Each case should define expected diagnosis admission, acceptable operations,
resource decisions, and rejection reasons. Version the dataset and do not tune
against the final held-out set.

### Measure the full funnel

Persist counts and machine-readable reasons for:

```text
raw candidates
-> deterministic signals
-> semantic-filter survivors
-> admitted diagnoses
-> goal decisions
-> novel action scopes
-> proposals by operation and resource kind
-> optimized changes
-> verification outcomes
-> accepted publications
-> replay regressions
```

Report precision, recall, latency, model calls, and cost by detector, domain,
operation, resource kind, evidence count, backend, and profile. Include the
distribution of action counts per trace. Distinguish a converged replay from a
pipeline that failed to generate proposals.

### Tune with constraints

Use configuration-driven search over thresholds and caps. Optimize accepted
quality and coverage while penalizing false positives, regressions, agent
calls, latency, duplicate proposals, and unused resources. Treat privacy,
contract validity, rollback, regression rate, and hard call budgets as
constraints—not soft preferences.

Store the code revision, dataset version, profile, seed, candidate
configuration, metrics, and artifacts for every experiment.

### Verify resource usefulness

- Scripts require a stable interface, fixtures, execution tests, and semantic
  assertions. File existence is insufficient.
- References require retrieval/use evidence and should reduce SKILL.md size
  through progressive disclosure.
- Assets require a real reusable template or media artifact and a reuse test.
- Delegated agents require a concrete delegation boundary and measurable value.
- Evals must exercise claims and observed failure modes.

Track script execution success, reference retrieval/use rate, asset reuse,
token reduction, unused-resource penalties, and duplicated-content penalties.

### Harden structural operations

Exercise merge, split, and delete using overlapping and conflicting skills.
Verify source snapshots, provenance, unique-capability preservation, metadata
and inventory consistency, migration behavior, release bundles, and rollback.
Merge must also work from inventory evidence when no new trace is supplied.

## Required development loop

1. Select a labeled calibration and held-out slice.
2. Run the current baseline with the intended profile/backend.
3. Inspect every funnel boundary and reason code.
4. Classify failures as detector, semantic filter, admission, recall, goal,
   mutation, verification, publication, or replay failures.
5. Make the smallest measured code/config change.
6. Rerun calibration and held-out cases.
7. Replay accepted evidence to confirm idempotency.
8. Run tests from a clean worktree.
9. Commit only scoped source, configuration, test, and operational-doc changes.

Verification:

```bash
cd skill_evolving_agents
python3 -m unittest discover -s tests -p 'test_*.py'
python3 evaluation/funnel_benchmark.py --out /tmp/funnel-scorecard.json
cd ..
git diff --check
```

Set `TMPDIR` to a path under the session workspace when the file sandbox blocks
the platform temporary directory. `evaluation/funnel_benchmark.py` writes
per-case workspaces to a temporary directory unless `--keep-workspaces` is
given.

Do not claim perfection. Report benchmark size, confidence, residual failures,
and limitations.

## Copyable continuation prompt

```text
Continue engineering skill_evolving_agents in this repository. Read
skill_evolving_agents/AGENT-HANDOFF.md completely, then inspect git status and
origin/main before editing. Preserve all dirty and untracked files; prefer a
clean worktree based on origin/main.

Improve the evidence -> diagnosis -> goal -> resource-aware mutation ->
verification -> publication funnel so create/update/merge/split/delete/no-change
and scripts/references/assets/agents/evals are precise, measurable, stable, and
idempotent. Use deterministic and embedding stages for broad low-cost recall,
then DSH + DeepSeek only for bounded intelligence stages. Do not use Codex for
paid trace runs unless explicitly authorized.

First establish or extend labeled positive, negative, already-applied, and
resource-usefulness benchmark cases. Measure the baseline funnel and failure
reasons. Implement the highest-impact measured fix, then rerun calibration,
held-out, and idempotent replay cases. Do not generate placeholder resources to
hit activity targets. Require semantic or executable verification and a clean
worktree test run before committing. Keep credentials, private documents, raw
traces, databases, and run artifacts out of Git. Do not update the separate
public repository without an explicit privacy-reviewed export.
```
