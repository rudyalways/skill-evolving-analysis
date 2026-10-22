# Trace mining

Trace mining should use the cheapest reliable method for each signal. The
default pipeline is deterministic Python. It does not call an LLM:

1. Parse Codex, Claude Code, and Cursor JSONL into canonical turns through a
   registered source adapter.
2. Remove system/developer prompts, ambient state, reasoning, token events,
   compaction records, duplicate lifecycle events, and embedded base64.
3. Apply rule-based turn selection and bounded tool-evidence policies.
4. Project user request, final response, and outcome into compact text.
5. Detect deterministic feedback signals and select high-confidence findings.
6. Exact/MinHash-deduplicate text before TF-IDF or external-embedding
   clustering; expand pointer manifests back to every canonical turn.

An agent is used only when `--review-clusters` requests semantic review. The
`embedding` profile consumes precomputed vectors from
`traces/inputs/embeddings.jsonl`; it does not download or start an embedding
model. Vector production can therefore use a hosted embedding API, a separately
managed local model, or an offline experiment.

## Prompt retention

Raw logs remain immutable. Long system prompts should not be repeated in
canonical turns or clustering text. If policy analysis is added, store each
unique prompt once by content hash, split it by heading or rule, and classify
sections as platform, project, skill, or user supplied.

Platform boilerplate is not an evolvable skill signal. Project and skill
sections may be retrieved only when a trace suggests policy noncompliance.
Select a small number of sections by semantic similarity plus diversity, while
always retaining hard safety constraints and output contracts. Canonical turns
should carry prompt and section IDs rather than duplicated prompt text.

## Friction and dissatisfaction signals

Signal extraction is a composable stage after canonicalization. The current
configuration enables several independent deterministic detectors:

- lexical corrections such as `no`, `wrong`, `stop`, `still`, `again`,
  `I asked`, and `don't`
- semantic repetition between consecutive user requests
- unresolved-goal repetition after an assistant response
- repeated tool failures, unchanged retries, file rereads, and edit churn
- long agent execution followed by a rapid correction
- missing final responses, interruption, or abandonment

Each finding should contain detector name and version, confidence, severity,
trace IDs, bounded evidence pointers, and the feature values that triggered
it. Keep detector output separate from canonical turns so detectors can be
changed and replayed without reparsing raw logs.

## Sentiment

Embeddings measure semantic proximity; they are not sentiment scores. Common
sentiment approaches are:

1. Lexicon or regex rules: cheapest and explainable, but narrow.
2. A small supervised text classifier: inexpensive and appropriate for stable
   labels such as positive, neutral, frustrated, or corrective.
3. An LLM classifier: best for nuanced context, but slower, more expensive,
   and less deterministic.

For this pipeline, use rules first, then a small hosted classifier for
ambiguous messages. Reserve an LLM judge for sampled findings, detector
evaluation, or uncertain high-impact cases. Frustration should not be inferred
from sentiment alone; combine it with corrections, repetition, unresolved
goals, failures, and timing.

## Timing

Record these separately:

- agent duration from `task_started` to `task_complete`
- time to first model output
- model-call, tool-call, retry, and wait durations
- time from final answer to the next user request
- number of model calls, tool calls, failures, and repeated operations

Long user-response latency does not prove the agent was slow because the user
may have left. A stronger inefficiency signal is long agent duration plus a
rapid corrective response, a semantically repeated request, or an unresolved
goal. Follow OpenTelemetry GenAI span conventions where source traces expose
enough timestamps.

## Suggested execution tiers

- Tier 0, always: parsing, regex, counters, timing, hashes, exact deduplication.
- Tier 1, usually: TF-IDF, MinHash/Jaccard, and hosted embeddings over user
  requests only.
- Tier 2, gated: small sentiment or correction classifier for uncertain rows.
- Tier 3, sampled: LLM/agent analysis for nuanced root cause and proposed skill
  changes.

This cascade keeps routine mining deterministic and cheap while preserving an
LLM path for cases where semantic judgment materially improves the result.

## Downstream pipeline impact

Signal extraction changes preprocessing and diagnosis substantially, goal
generation and verification moderately, and skill editing/orchestration only
slightly:

```text
raw traces
→ canonical turns
→ deterministic signal detectors
→ signal findings
→ recurring-pattern aggregation
→ optional deduplicated topic clustering
→ high-confidence finding fanout
→ diagnosis
→ skill matching
→ goal
→ optimize
→ verify against the original signals
→ judge
```

Keep two clustering views. Topic clusters describe what users are trying to
accomplish; friction clusters describe how the agent is failing. A trace may
belong to both through pointer manifests.

The diagnosis agent should validate computed findings, reject false positives,
identify root cause, and locate affected skill sections instead of spending
tokens rediscovering deterministic symptoms. Skill selection should include
signal type, severity, recurrence, and confidence as additional matching
features. Goal generation should prioritize patterns recurring across sessions,
not isolated negative turns.

Verification should rerun the targeted detectors or replay representative
trace scenarios. The judge should compare before/after evidence and reject a
change that does not improve the targeted failure pattern. SQLite and dashboard
metrics should track occurrences, affected sessions, severity, confidence,
false positives, and trends.

A detector finding should use a stable, replayable contract:

```json
{
  "signal_id": "sig-...",
  "session_id": "session",
  "trace_ids": ["codex:session:turn-3", "codex:session:turn-5"],
  "detector": "repeated-instructions",
  "detector_version": "1",
  "severity": "high",
  "score": -9,
  "confidence": 0.78,
  "evidence": [
    {"trace_id": "codex:session:turn-3", "turn_path": "traces/derived/normalized/turns/codex-a.json", "field": "user.text", "quote_sha256": "..."}
  ],
  "features": {
    "method": "jaccard",
    "pair_count": 2,
    "max_similarity": 0.78
  }
}
```

Detectors should identify evidence cheaply; they should not directly prescribe
skill edits. Diagnosis and goal agents still determine the appropriate skill,
facet, and operation. Skill labeling, isolated fanout, worker workspaces, the
Optimize → Verifiter → Judge loop, raw-trace immutability, and bounded pointer
manifests remain unchanged.

## Related systems

Detailed source-level comparisons, algorithms, metrics, model usage, output
contracts, licenses, and adoption recommendations are in
[`RELATED_SYSTEMS.md`](RELATED_SYSTEMS.md).

- [claude-doctor](https://github.com/millionco/claude-doctor) detects
  correction-heavy sessions, repeated instructions, error loops, edit
  thrashing, and rapid corrections.
- [TotalRecall](https://github.com/modelflytao/totalrecall) combines
  deterministic friction extraction with gated semantic analysis and recurring
  pattern strength.
- [openclaw-trace](https://github.com/Phantastic-AI/openclaw-trace) mines
  evidence-backed friction signals and clusters them into improvement work.
- [OpenTelemetry GenAI conventions](https://github.com/open-telemetry/semantic-conventions-genai)
  define agent, model, tool, token, error, and duration telemetry.
- [Langfuse](https://langfuse.com/docs) provides self-hosted trace/session
  observability, scoring, latency, and evaluation.
- [Stowken](https://github.com/stowken/stowken) demonstrates content-addressed
  prompt deduplication and semantic clustering.
- [Argilla](https://github.com/argilla-io/argilla) supports human review and
  labeling of mined findings.

The recommended direction is to borrow detectors and telemetry conventions,
while keeping this repository's canonical files, strategy profiles, pointer
manifests, and SQLite metrics as the self-contained execution layer.
