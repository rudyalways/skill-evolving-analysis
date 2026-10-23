# Low-cost pipeline proposal

Status: implemented initial profile  
Profile: `profiles/low-cost.json`

## Goal

Reduce the current per-finding and per-operation fanout. A trace with six
findings and four proposed operations can otherwise require roughly one label
session, six diagnosis sessions, six goal sessions, four optimize sessions,
and four verifier sessions. The target is normally zero agent calls for weak
single-trace evidence and approximately two to seven calls for a strong trace.

## Cost-tier service layer

Algorithms do not call models directly. They select a capability from the
service registry in `config/service-tiers.json`:

| Tier | Service class | Typical work |
| --- | --- | --- |
| 0 | Rules/scripts | regex, parsing, hashes, schemas, deterministic scoring |
| 1 | Embedding/classifier, normally <=1B | classify, rank, deduplicate, search |
| 2 | Small generation model, such as a 4B-class model or JEV | compact JSON extraction and known-template decisions |
| 3 | Large LLM/full agent | novel diagnosis, semantic editing, tool-based verification |

The dependency direction is `services -> libraries/APIs -> algorithms ->
phases -> profiles -> super-config resolution`. An algorithm declares required
capabilities and a default service. Preflight verifies that the selected
service provides those capabilities and stays under `max_cost_tier`.

The low-cost profile prefers tier 1, permits escalation up to tier 3, targets
four agent calls, and sets a hard cap of eight. The evidence gate reduces tier-3
fanout, while the runner atomically reserves every agent session and refuses to
start another after the cap. Usage and remaining budget are written to
`logs/agent-call-budget.json`, including across continuation processes.

Tier 2 uses the shared `services/generation_api` protocol for small-model JSON
or JEV generation. Its reference server is test-only and performs no inference;
a real provider must return schema-valid JSON plus pinned model revision and
usage data.

## Implemented cascade

```text
trace
  -> deterministic normalization and signal detection
  -> embedding classification
  -> recurrence/evidence evolution gate
  -> agent diagnosis for survivors
  -> embedding skill recall, deterministic fallback on service error
  -> agent goal for survivors
  -> existing operation bundling by affected skill
  -> optimize
  -> verify and deterministic publish
```

The evolution gate runs before diagnosis fanout. It immediately admits critical
findings and configured explicit-correction detectors. Other findings require
either distinct-session recurrence or enough evidence records at the configured
confidence. Rejected and deferred findings remain on disk and are recorded in
`traces/derived/evolution-gate.json`; they are not deleted.

The semantic prefilter accepts only a strong, well-separated relevant-category
match and rejects only a strong, well-separated `noise` match. Low similarity
and near ties escalate rather than being treated as negative evidence. Service
errors also escalate. Skill recall embeds the scoped diagnosis and
searches skill instructions plus metadata. Its result is normalized to the
existing `label-matching/v1` contract. If the embedding service is unavailable,
the current weighted taxonomy-path recall runs instead.

## Phase recommendations

| Phase | Low-cost implementation | Agent use |
| --- | --- | --- |
| Normalize | deterministic | none |
| Signal detection | deterministic | none |
| Semantic filtering | embedding classifier | none; uncertainty survives |
| Evolution gate | deterministic evidence/recurrence policy | none |
| Skill labeling | cached labels; embedding planned | uncertain labels only |
| Diagnosis | agent after gate | survivor only |
| Skill recall | embedding plus deterministic fallback | none |
| Goal | agent | survivor only; deterministic templates planned |
| Optimize | agent, bundled by skill | semantic edits only |
| Structural verification | deterministic checks plus current verifier | agent reduction planned |
| Judge/publish | deterministic | none |

Embeddings are suitable for filtering, classification, deduplication, nearest
template retrieval, and skill recall. They must not decide whether a semantic
edit is correct or publish a skill.

## Run

Start the shared service once:

```bash
python3 skill_evolving_agents/services/embedding_api/server.py --port 8080
```

Run the profile:

```bash
python3 skill_evolving_agents/run_pipeline.py <run-id> \
  --pipeline-profile low-cost
```

`low-cost` uses the embedding implementation directly as a library and makes
no HTTP request. Its default is the pinned
`Qwen/Qwen3-Embedding-0.6B` model with 1024-dimensional normalized vectors and
an instruction specialized for skill/finding retrieval. To let the runner
start and stop one local API service on a
configurable port instead, use:

```bash
python3 skill_evolving_agents/run_pipeline.py <run-id> \
  --pipeline-profile low-cost-local-service
```

Its default port is `8181`; change `embedding_runtime.port` in the profile.
Use `transport: remote_api` and `endpoint` when multiple pipeline containers
should share one externally managed, warmed model.

The included hashing backend is a protocol reference, not a production
semantic model. Deploy a pinned semantic model behind the same API before
calibrating production thresholds.

## Tuning evidence

Use these artifacts together:

- `traces/derived/semantic-prefilter-shadow.json`: category matches and scores
- `traces/derived/evolution-gate.json`: selected/deferred reasons and counts
- `run/*/label-matching.json`: recall algorithm, matches, and fallback state
- `logs/phase-adapter-metrics.json`: phase/mode/algorithm latency and outcomes
- `logs/phase-metrics.json`: funnel and quality availability

Tune thresholds on an adjudicated judgment set. Keep a random audit sample of
rejected and deferred findings. Candidate coverage is not recall; retrieval
recall requires exhaustive relevance labels for the sampled skill inventory.

## Next reductions

1. Incremental embedding-based skill labeling keyed by skill content hash.
2. Connect a pinned small-model provider to the tier-2 generation API and
   implement diagnosis/goal canonical normalizers.
3. Diagnosis-template retrieval for known high-precision failure categories.
4. Deterministic goals for `no_change`, `defer`, and unambiguous single-skill
   updates.
5. Batch uncertain diagnoses and goals into one structured agent request.
6. Deterministic verification by default, with replay or verifier agents only
   for high-risk and sampled changes.

