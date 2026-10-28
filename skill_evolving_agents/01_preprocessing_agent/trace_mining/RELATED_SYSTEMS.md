# Related trace-mining and evaluation systems

This report compares systems relevant to trace normalization, interaction
failure detection, semantic clustering, observability, human review, and
closed-loop agent improvement. The repositories were cloned under
a local `oss` checkout and inspected at source level.

## Source snapshots

- `claude-doctor`: `f5efb2a59e9a608f03cc35e14b8480f212301c27`
- `totalrecall`: `4338816fec76982900e34d12eda8705aed795e7f`
- `openclaw-trace`: `4aff7f05dc55a38d5943c79902a9b20cb065b56b`
- `chatbot-auditor`: `d334716ef021eb5e71199854a0b62f910e36aa0d`
- `stowken`: `0a79aeab8684d2cd0792683383452e6b14dc5f11`
- `argilla`: `5338519accb13ae422f8bf9c0642651c249c49af`
- `langfuse`: `02d03015148b00d820d42cf2a5801d75c8d253a8`
- `semantic-conventions-genai`:
  `8538971bd11dba723fdd33c804b5a32121827ff7`

## Executive conclusions

No single project implements the complete loop needed here.

- Claude Doctor and chatbot-auditor provide inexpensive deterministic
  detectors, scores, evidence, and fixed recommendations.
- TotalRecall has the closest incremental learning loop: normalize several
  agent formats, combine deterministic and Claude analysis, merge recurring
  patterns, propose rules, apply them with approval, and monitor recurrence.
- openclaw-trace has the strongest grounded batch-mining ideas: bounded chunks,
  validated evidence quotes, stable fingerprints, ranking, ticket IR, and
  actor-critic research briefs.
- Stowken contributes storage and retrieval methodology: content-addressed
  segments, exact and near deduplication, embedding reuse, semantic search,
  deterministic clustering, and outlier discovery.
- Langfuse contributes production-scale tracing, queued evaluation,
  deterministic sampling, transcript assembly, LLM-as-judge, topic continuity,
  datasets, and experiment runs.
- Argilla contributes the human-review data model: machine suggestions remain
  distinct from human responses, with typed questions, vectors, search, bulk
  ingestion, and export.
- OpenTelemetry GenAI contributes portable names and boundaries for agent,
  model, tool, workflow, token, duration, error, and evaluation telemetry.

The recommended system is therefore hybrid:

```text
deterministic normalization
→ composable rule and metric detectors
→ optional embeddings
→ gated LLM diagnosis
→ recurring-pattern aggregation
→ skill goal and edit
→ replay and recurrence verification
→ human approval where risk requires it
```

## Claude Doctor

Repository: [millionco/claude-doctor](https://github.com/millionco/claude-doctor)

### Goal

Analyze Claude Code transcripts for behavioral anti-patterns and generate
candidate rules for `CLAUDE.md` or `AGENTS.md`.

### Methodology

It is entirely script-based. There is no LLM, agent, embedding model, or vector
database.

- Structural detectors count repeated edits, consecutive tool errors,
  read-to-edit ratio, short-session abandonment, and session restarts.
- Behavioral detectors use regex correction markers, fixed keep-going phrases,
  turn ratios, message-length drift, timing, and word-set Jaccard similarity.
- Sentiment uses the JavaScript `sentiment` package with AFINN-style lexical
  scores plus coding-agent words such as `undo`, `revert`, `wrong`, and
  `broken`.
- Repeated instructions use Jaccard similarity at `0.6` within a five-turn
  lookahead. This detects lexical overlap, not paraphrases.
- Project score is the sum of detector scores multiplied by severity weights,
  divided by session count.

Detector thresholds and formulas are in
`packages/cli/src/constants.ts` and `packages/cli/src/signals/`.

### Outputs

A signal contains:

```json
{
  "signalName": "repeated-instructions",
  "severity": "critical",
  "score": -12,
  "details": "User repeated similar instructions 4 time(s).",
  "sessionId": "session-id",
  "examples": ["request A ~ request B"]
}
```

It emits terminal views, Markdown, JSON, `.claude-doctor/model.json`, and
`.claude-doctor/guidance.md`. Recommendations are selected from a hardcoded
string pool in `suggestions.ts`; they are not generated semantically.

### Fix loop and limitations

Users review and paste rules manually. The project does not patch instructions,
run regression scenarios, or prove that a rule helped. Files have no explicit
size/count limit, but every parsed event is accumulated in memory and each
detector reparses the same transcript. User messages over 2,000 characters are
ignored by message-based detectors. The parser is Claude-specific.

### Useful innovations

- Cheap, transparent detector baselines.
- Evidence snippets attached to each signal.
- Project-level aggregation before recommending a rule.
- Immediate single-session health guidance.

## TotalRecall

Repository: [modelflytao/totalrecall](https://github.com/modelflytao/totalrecall)

### Goal

Continuously learn collaboration friction from Claude Code, Codex, and OpenCode
sessions, maintain recurring patterns, and propose project rules.

### Methodology

TotalRecall is hybrid:

- Python adapters normalize Claude Code JSONL, Codex rollouts, and OpenCode
  SQLite exports into a `NormalizedSession`.
- Deterministic events identify tool errors and file-edit churn.
- Claude CLI performs semantic friction extraction using a structured skill
  prompt. The default configured extraction/synthesis model is
  `claude-sonnet-4-6`.
- Pattern matching tries stable `pattern_id`, slug identity, then
  `SequenceMatcher` similarity at `0.82`.
- Evidence is deduplicated by snippet hash or session ID.
- Pattern strength is:

```text
occurrences × exp(-days_since_last_seen / 14) × severity / 5
```

- A crash-safe queue, file-hash ledger, single worker lock, quiet-period check,
  and self-analysis exclusion make incremental processing robust.

It does not use embeddings.

### Outputs

LLM findings contain category, description, severity from 1–5, turn references,
pattern ID, slug, and a phase-two hint. Persistent patterns add occurrence
evidence, timestamps, applied rule, application time, and verdict override.
The system writes JSON pattern files, an index, `insights.md`,
`proposals.json`, and `proposals.md`.

### Fix loop

Rule proposals require explicit apply/reject action. Applying writes a marked
rule block and an import in `CLAUDE.md`. Later sessions automatically classify
an applied rule as ineffective after at least two reachable recurrences, or
resolved after a configured recurrence-free period. Reachability matters:
Codex recurrence does not condemn a Claude-only rule.

### Useful innovations

- Separate deterministic and semantic signal classes.
- Existing-pattern catalog passed into extraction for stable IDs.
- Incremental recurrence and recency scoring.
- Tool-reachability-aware effectiveness.
- Extensive adapter, queue, merge, and lifecycle tests.

### Limitations

Semantic analysis requires an authenticated Claude CLI. LLM output still needs
schema validation. GPL-3.0 licensing should be considered before copying code;
the architecture and formulas can be independently implemented.

## openclaw-trace

Repository:
[Phantastic-AI/openclaw-trace](https://github.com/Phantastic-AI/openclaw-trace)

### Goal

Mine grounded errors, frustration, opportunities, and positive outcomes from
OpenClaw sessions; roll them into stable work items; generate research briefs;
and run improvement experiments.

### Methodology

The default miner uses an OpenAI-compatible chat-completions client with
`gpt-4.1-mini`. It also has a no-LLM heuristic mode.

- Long sessions are divided into overlapping chunks.
- Chunk boundaries extend across tool-call/tool-result pairs.
- LLM-produced evidence quotes must be exact substrings of source events.
- Item IDs hash session, kind, summary, and evidence.
- Rollup signatures hash signal kind, summary bigrams, and tags.
- Groups may be merged with token Jaccard at `0.62`; borderline groups at
  `0.5` can be sent to an LLM merger.
- Group score combines `log1p(item_count)`, maximum severity, incident bonus,
  and smaller error/frustration bonuses.
- A second taxonomy maps raw signals into product-facing kinds such as defect,
  UX friction, reliability/performance, capability gap, and process/tooling.

There are no embeddings in the core pipeline.

### Outputs

Mined JSONL items include stable ID, session, source, kind, summary, severity,
confidence, tags, source span, exact evidence quotes, and optional proposed
fix. Rollups add stable signature/fingerprint IDs, counts, taxonomy counts,
tier, score, and sample references. Ticket IR adds title, body, priority, and
fingerprint for external trackers.

### LLM and agent usage

- Signal mining and optional merge decisions use OpenAI-compatible calls.
- Research briefs can invoke Claude or Codex CLI in actor/critic roles.
- An experimental recursive analyzer asks a model to generate analysis code
  over a transcript interface.

### Fix loop and limitations

The system produces tickets, briefs, and experiment artifacts; it does not
automatically patch a production agent. The repository has experiment scripts
but no conventional unit-test suite and no license file at the inspected
revision.

### Useful innovations

- Exact-quote grounding validation.
- Stable cross-run fingerprints.
- Deterministic fallback when no model is available.
- Tiered triage and ticket interchange format.
- Tool-sequence n-grams for discovering implicit workflows.

## chatbot-auditor

Repository:
[HemantBK/chatbot-auditor](https://github.com/HemantBK/chatbot-auditor)

### Goal

Audit existing customer-support conversations for named failure modes such as
death loops, silent churn, buried escalation, sentiment collapse, policy
violations, and misinformation.

### Methodology

The default implementation is deterministic and stateless:

- Adapters normalize JSON/JSONL, CSV/TSV, Intercom, and Zendesk into Pydantic
  conversations.
- Pure detectors return typed detections through a registry.
- Death loops form connected components with union-find when bot messages have
  lexical similarity at least `0.85`.
- Silent churn combines missing confirmation, final-speaker shape, question
  state, message count, and reported-resolution mismatch.
- Escalation burial detects escalation phrases without a later transfer.
- Sentiment collapse compares the mean keyword sentiment of the first and last
  thirds of user messages.
- Confidence values are bounded deterministic formulas, usually starting near
  `0.5–0.75` and capped at `0.95`.
- Flagged conversation priority is the sum of
  `severity_weight × confidence`.

Optional semantic similarity uses
`sentence-transformers/all-MiniLM-L6-v2` and cosine similarity. No LLM client is
required or bundled; custom LLM moderation/sentiment backends can implement
protocols.

### Outputs

`Detection` contains failure mode, severity, confidence, evidence,
recommended action, and metadata. Reports are available as text, JSON,
Markdown, and HTML. A FastAPI service exposes health, detector listing, and
analysis endpoints.

### Verification methodology

A reproducible synthetic corpus computes confusion matrices, precision,
recall, and F1 per detector. This is stronger than only checking that detector
code executes.

### Useful innovations

- Named failure-mode taxonomy and typed evidence.
- Pure composable detector registry.
- Reported-resolved versus behavioral-resolution discrepancy.
- Optional semantic backend without contaminating core detector logic.
- Synthetic benchmark and threshold-sweep discipline.

### Limitations

It has no persistence, longitudinal pattern store, or fix loop. English
keywords dominate. Knowledge-free policy/fact detectors can produce review
noise. License: Apache-2.0.

## Stowken

Repository: [stowken/stowken](https://github.com/stowken/stowken)

### Goal

Store large LLM conversation corpora efficiently while supporting query,
cost analysis, semantic search, clustering, and outlier detection.

### Methodology

- Messages are segmented by role.
- Exact segment identity is SHA-256 over token bytes.
- A conversation manifest points to ordered shared segments.
- New blobs are compressed; repeated blobs increment references.
- Near deduplication uses 128-value MinHash, two-token shingles, and LSH with
  16 bands × 8 rows. Estimated Jaccard is matching MinHash positions divided by
  128. The default near-duplicate threshold is `0.85`.
- Semantic embeddings are normalized once, then cosine similarity becomes a
  dot product.
- Conversation clustering uses deterministic k-means++ and cosine distance.
- Outlier score is `1 - maximum_similarity_to_any_centroid`.

Core storage needs no model. Optional OpenAI adapters support
`text-embedding-3-small`, `text-embedding-3-large`, and
`text-embedding-ada-002`. Optional LLM summaries default to `gpt-4o-mini`.
Custom embedding and summarizer adapters are supported.

### Persistence and outputs

Filesystem or S3 stores content-addressed segments and manifests; SQLite stores
metadata and embeddings. Outputs include store/compression statistics,
retrieved conversations, semantic-search hits, clusters, outliers, cost
reports, and JSONL/Hugging Face/Parquet exports.

Important metrics include exact dedup ratio, compression ratio, estimated
bytes saved, duplicate wasted bytes, segment counts, and embedding coverage.

### Useful innovations

- Store system prompts and repeated context once.
- Embed each unique segment once.
- Separate near-duplicate storage threshold from stricter embedding-reuse
  threshold.
- Two-level retrieval over segments and whole-conversation summaries.
- Deterministic outlier sampling for human review.

### Limitations

Near deduplication can cost more than it saves on some corpora. Semantic search
is a brute-force scan and requires another index near million-scale vectors.
There is no sentiment or skill-improvement loop. License: MIT or Apache-2.0.

## Argilla

Repository: [argilla-io/argilla](https://github.com/argilla-io/argilla)

### Goal

Create high-quality labeled datasets through collaboration between engineers,
models, and human annotators.

### Methodology

Argilla is annotation-first rather than trace-first:

- A dataset contains typed records.
- Records contain fields, metadata, optional vectors, machine suggestions, and
  human responses.
- Questions support labels, multilabels, rankings, ratings, spans, and free
  text.
- An ingestion mapper converts arbitrary dictionaries or Hugging Face columns
  into typed record components.
- Elasticsearch/OpenSearch provides lexical, filtered, and vector kNN search.
- PostgreSQL stores canonical records and annotations.
- Client-supplied vectors enable similarity search; Argilla does not bundle an
  embedding service.

There is no core LLM-as-judge, trace/span model, automatic clustering, or
automatic fix loop. External models create suggestions; humans accept, reject,
or replace them.

### Outputs

Record schemas preserve status, fields, metadata, vectors, responses,
suggestions, and external IDs. Data can be exported as JSON or Hugging Face
datasets. Webhooks can trigger downstream processing when records are created,
updated, or completed.

### Useful innovations

- Keep machine suggestions distinct from human truth.
- Typed review questions instead of one generic approval field.
- Declarative mapping from heterogeneous source data.
- External IDs for idempotent upsert.
- Search/filter/vector review queues.
- Human-reviewed datasets export cleanly into training or regression systems.

### Limitations

It is not a trace store, and its older LangChain callback integration does not
represent the current data model. Embeddings must be generated elsewhere.
License: Apache-2.0.

## Langfuse

Repository: [langfuse/langfuse](https://github.com/langfuse/langfuse)

### Goal

Provide production LLM tracing, evaluation, datasets, experiments, prompt
management, analytics, and human feedback.

### Architecture and methodology

- SDK, API, and OpenTelemetry events enter a validated ingestion service.
- Raw events can be persisted to object storage and processed through queues.
- ClickHouse stores high-volume traces, observations, scores, and experiment
  run items.
- PostgreSQL stores configuration, datasets, evaluators, and job state.
- Redis coordinates queues, trace-idle batching, and locks.
- Transcript replay assembles messages across spans and deduplicates repeated
  messages.
- Evaluation jobs support filters, variable mapping, deterministic sampling,
  delay, and new/existing time scope.
- Evaluation outputs become numeric, categorical, or string scores linked to
  traces, observations, sessions, dataset runs, evaluators, and rules.
- Recursion guards prevent evaluator-generated traces from evaluating
  themselves.

### Models and clustering

LLM-as-judge execution is a first-class queued evaluator. Code evaluators and
human scores share the score model. Topic analysis summarizes trace facets,
embeds summaries, clusters them with native HDBSCAN, classifies clusters, and
uses centroid similarity and continuity rules to preserve topic identity over
time.

The platform supports multiple model providers rather than prescribing one
fixed evaluator model.

### Outputs

Primary outputs are traces, observations, scores, session views, topic
definitions, datasets, versioned dataset items, experiment runs, score
matrices, dashboards, alerts, and CSV/JSON exports. Dataset items retain source
trace and source observation lineage.

### Useful innovations

- Trace-idle assembly before expensive processing.
- Deterministic sampling based on trace ID.
- Filter plus variable-mapping evaluation jobs.
- Uniform score persistence for code, model, and human evaluators.
- Evaluation recursion guards.
- Production traces promoted into lineage-preserving regression datasets.
- Topic continuity rather than recreating unrelated cluster IDs each run.

### Limitations

Self-hosting requires substantial infrastructure: ClickHouse, PostgreSQL,
Redis, object storage, workers, and the web application. Many topic features
are cloud-oriented or feature-flagged. Core code is MIT; enterprise directories
have a separate license.

## OpenTelemetry GenAI semantic conventions

Repository:
[open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai)

### Goal

Standardize telemetry names and semantics for model inference, agents,
workflows, planning, retrieval, memory, embeddings, tools, MCP, evaluation,
tokens, durations, and errors.

### Methodology

This repository defines schemas and conformance scenarios; it does not analyze
sentiment, cluster traces, call models, or recommend fixes.

Relevant operations include:

- `gen_ai.invoke_agent.internal`
- `gen_ai.invoke_workflow.internal`
- `gen_ai.plan.internal`
- `gen_ai.execute_tool.internal`
- `gen_ai.execute_tool.load_skill.internal`
- `gen_ai.execute_tool.read_skill_resource.internal`
- `gen_ai.execute_tool.command.internal`
- client inference and embedding spans

Metrics include agent/workflow/tool duration, model duration and time to first
token, inference-call count, tool-call count, and token usage. Evaluation
events support name, numeric score, categorical label, explanation, and
response ID.

### Privacy

System instructions, input/output messages, tool definitions, tool arguments,
and tool results are opt-in because they may be large or sensitive. The
recommended production pattern is metadata on spans and content in external
storage referenced by ID.

### Useful innovations

- Portable names for timing and count metrics.
- Explicit agent/workflow/plan/tool boundaries.
- Skill loading and skill-resource telemetry.
- Evaluation events that can represent verifier/judge output.
- Clear privacy boundary between metadata and content.

### Limitations

Most GenAI conventions are still marked development, and the repository does
not yet publish a completed schema URL. Vendor logs such as Codex rollouts need
an adapter before they resemble OTel spans.

## Cross-system methodology

### Deterministic rules

Best for transparent, inexpensive signals:

- tool errors and retry streaks
- edit/read churn
- correction phrases
- interruption and abandonment
- timing and token metrics
- exact evidence validation
- schema and policy checks

Use them on every eligible turn or session.

### Lexical and hash-based similarity

- Jaccard and `SequenceMatcher` are inexpensive but miss paraphrases.
- MinHash/LSH scales approximate Jaccard to large corpora.
- Stable content hashes, pattern IDs, and fingerprints enable idempotency and
  longitudinal tracking.

Use lexical methods before embeddings and preserve their feature values in
findings for explainability.

### Embeddings

Embeddings are most useful for:

- paraphrased repeated requests
- semantic topic and friction clustering
- finding related historical failures
- selecting representative traces
- outlier discovery

They are not sentiment scores. Keep vectors external or derived, attach model
and version metadata, and never make raw logs depend on one embedding provider.

### LLM and agent analysis

Use an LLM only after cheap gates:

- nuanced root-cause diagnosis
- mapping friction to a skill and section
- summarizing or naming uncertain clusters
- proposing an edit
- judging ambiguous policy compliance

Ground every LLM finding with source turn IDs or exact quotes. Use deterministic
sampling, structured output validation, self-analysis exclusion, and
evaluation recursion guards.

### Human review

Human review is valuable for:

- accepting new detector labels
- resolving false positives
- approving broad instruction changes
- curating regression examples
- overriding automated verdicts

Represent machine suggestions and human decisions separately.

## Recommended architecture for skill_evolving_agents

### Signal path

Add a composable signal stage after canonicalization:

```text
canonical turns
├── deterministic detectors
├── lexical similarity
├── optional embedding detectors
├── timing and tool metrics
└── gated semantic analysis
        ↓
typed signal findings
        ↓
recurring patterns with stable fingerprints
```

Unlike single-choice clustering strategies, detectors should be a configured
list because independent detectors can run together.

### Finding contract

```json
{
  "schema_version": 1,
  "signal_id": "sig-...",
  "detector": "repeated-instructions",
  "detector_version": "1",
  "scope": "session",
  "trace_ids": ["codex:session:turn-a", "codex:session:turn-b"],
  "severity": "high",
  "confidence": 0.86,
  "score": -9,
  "features": {
    "method": "jaccard",
    "similarity": 0.78,
    "distance_turns": 2
  },
  "evidence": [
    {
      "turn_path": "traces/derived/normalized/turns/a.json",
      "field": "user.text",
      "quote_sha256": "..."
    }
  ]
}
```

### Pattern contract

Aggregate findings across distinct sessions:

```json
{
  "schema_version": 1,
  "pattern_id": "pattern-...",
  "fingerprint": "fp1:...",
  "kind": "repeated-instructions",
  "occurrences": 7,
  "distinct_sessions": 5,
  "severity": 4,
  "confidence": 0.83,
  "strength": 4.91,
  "first_seen": "2026-10-01T00:00:00Z",
  "last_seen": "2026-10-21T00:00:00Z",
  "status": "active",
  "target_reachability": ["cursor"],
  "evidence_signal_ids": ["sig-a", "sig-b"]
}
```

### Downstream behavior

- Diagnosis validates findings, rejects false positives, determines root cause,
  and maps patterns to capability paths.
- Skill selection adds pattern kind, severity, confidence, recurrence,
  recency, and reachability to its scoring.
- Goal generation operates on recurring patterns rather than individual
  complaints.
- Optimize edits only the targeted skill or agent section.
- Verification reruns detectors and representative replay scenarios.
- Judge compares before/after pattern metrics and checks for regressions.

### Metrics

Store at least:

- raw and canonical bytes/tokens
- detector execution count and duration
- findings by detector/version/severity
- precision/recall/F1 on labeled fixtures
- distinct-session recurrence
- pattern strength and trend
- embedding model/version and coverage
- LLM calls, tokens, cost, latency, and validation failures
- false-positive and human-override rates
- pre/post-application recurrence for each evolved skill

### Implementation priority

1. Port deterministic detectors with typed evidence.
2. Add synthetic labeled fixtures and detector F1 reports.
3. Aggregate recurring patterns with stable fingerprints and recency strength.
4. Add hosted embeddings for semantic repetition, clusters, and outliers.
5. Gate LLM diagnosis on uncertain or high-impact patterns.
6. Promote verified failures into regression datasets.
7. Add recurrence-based verification after skill changes.

## Adoption cautions

- Do not copy GPL-3.0 TotalRecall code into a differently licensed project
  without accepting its license obligations.
- Do not rely on openclaw-trace code until its licensing is clarified.
- Do not treat lexical sentiment as ground truth.
- Do not copy every recommendation into every agent prompt.
- Do not let evaluators recursively analyze their own traces.
- Do not cluster only by topic; preserve separate topic and friction views.
- Do not allow embeddings or LLMs to mutate canonical raw-derived records.
- Do not interpret user response delay alone as agent latency.
