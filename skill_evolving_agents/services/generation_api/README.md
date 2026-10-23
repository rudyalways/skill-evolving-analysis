# Tier-2 structured generation API

This service boundary supports small JSON-generation models and JEV-style
structured generation without installing a model in every pipeline container.

```text
POST /v1/generate-json
GET  /healthz
```

Requests contain canonical input data, an output schema, a short instruction,
an optional pinned model name, and `method: json|jev`. Responses contain the
validated JSON candidate, model revision, method, latency, and available usage.

The included server performs no inference. It accepts `_reference_output` only
for protocol and integration tests. A production deployment should replace its
provider with a pinned small model while preserving this API and must validate
the returned JSON against the requested schema before returning success.
