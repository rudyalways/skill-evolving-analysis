# Policy subsystem

This package is the stable boundary between pipeline execution and the system
that chooses configuration.

Dynamic phase routing is handled by the adjacent constrained state machine.
Its private product-roadmap document is intentionally excluded from version
control.
The policy produces typed transition decisions; the state machine decides
whether they are legal and executable.

```text
workspace evidence
  → features.py
  → PolicyProvider
       FixedPolicy      (current production behavior)
       CandidatePolicy  (grid/random/wide-deep/MCTS)
       ModelPolicy      (future transformer runtime)
  → contracts.py
  → compiler.py
  → validated profile/preprocessing/recall documents
  → pipeline runtime
```

`run_pipeline.py` routes the fixed profile through this boundary after
deterministic preprocessing and before semantic and expensive downstream
phases. It writes `features.json`, `decision.json`, and `compiled.json` under
`run/config/policy/`. The same records are stored in
`workspace/optimization.sqlite`, collecting training data without changing
current behavior.

## Modules

- `contracts.py`: versioned feature, decision, and compiled-policy validation.
- `features.py`: bounded dense features and transformer-ready typed tokens.
- `heads.py`: registry-to-output-head metadata.
- `providers.py`: fixed, search candidate, and model inference adapters.
- `compiler.py`: domain, coupling, profile, and immutable-boundary checks.
- `store.py`: immutable features, decisions, feedback, and checkpoints.

The runtime never imports a transformer framework. A model server or local
runtime supplies a callable to `ModelPolicy`; its output remains ordinary typed
data. Training and serving dependencies stay out of non-neural containers.

## Decision timing

The first adaptive point is post-detection. Deterministic parsing, redaction,
and signal extraction run first, giving the policy useful trace features. The
compiled policy controls semantic filtering and later phases. A future earlier
deployment-only decision may choose available services, but cannot bypass
normalization or privacy controls.

## Feedback

Append feedback with `evaluation/optimize_config.py feedback`. Source classes
are human, verifier, benchmark, and runtime. The JSON value can represent
Boolean approval, a rating, stars, a corrected category, or structured
evaluation. Corrections use `--supersedes`; evidence is never overwritten.
