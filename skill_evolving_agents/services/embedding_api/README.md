# Embedding service

This directory defines the network boundary used by semantic prefilters and
skill recall. Pipeline and agent containers use `client.py`; they do not load a
model.

## Selected production default

The local profiles use `Qwen/Qwen3-Embedding-0.6B`, pinned to revision
`97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, through
`sentence-transformers`. It is the Qwen3 embedding member that fits the tier-1
approximately-1B ceiling while retaining multilingual and code retrieval,
32K model context, instruction-aware queries, and Matryoshka dimensions. The
configured vector size is the full 1024 dimensions.

The 4B and 8B variants score higher but belong in a more expensive deployment
tier and would weaken the purpose of the low-cost gate. Add a reranker only
after labeled recall/precision data shows that embedding-only top-k retrieval
is insufficient.

The first local run downloads the pinned model into the normal Hugging Face
cache. Later runs reuse that cache. Model loading occurs once per pipeline run
for `in_process`, or once in the managed child for `local_process`; it never
occurs separately in each phase or agent container.

Install the local runtime once:

```bash
python3 -m pip install -r \
  skill_evolving_agents/services/embedding_api/requirements.txt
```

The dependency range intentionally stays on Transformers 4.x and Sentence
Transformers 5.x. Qwen3 requires Transformers 4.51 or newer, while an
unbounded major upgrade can pull incompatible HTTP/runtime dependencies into
an existing Python installation.

Start the dependency-free reference server:

```bash
python3 skill_evolving_agents/services/embedding_api/server.py --port 8080
```

The reference hashing backend exists for protocol tests and local deployment
checks. It is lexical, not a production semantic embedding model. Replace
`HashingBackend` behind the same endpoints with a pinned hosted or local model.

Endpoints:

- `POST /v1/embeddings`
- `POST /v1/classify`
- `POST /v1/search`
- `GET /v1/models`
- `GET /healthz`

Every successful response includes the model revision and request ID. Search
and classification indexes in the reference server are request-local; a
production server should use immutable, versioned indexes and return their
revision.

## Runtime modes

Profiles configure one shared `embedding_runtime`:

```json
{"transport": "in_process"}
```

Uses the embedding backend as a Python library without HTTP. This has the least
overhead and is the default in `low-cost.json`.

```json
{
  "transport": "local_process",
  "host": "127.0.0.1",
  "port": 8181,
  "startup_timeout_seconds": 10
}
```

Starts one managed local service for the pipeline run, waits for `/healthz`,
shares it across embedding phases, and terminates it in the runner's `finally`
block. See `profiles/low-cost-local-service.json`.

```json
{
  "transport": "remote_api",
  "endpoint": "http://embedding-service:8080",
  "timeout_ms": 1500
}
```

Uses an independently deployed service. This is appropriate when several
containers should share one warmed model.
