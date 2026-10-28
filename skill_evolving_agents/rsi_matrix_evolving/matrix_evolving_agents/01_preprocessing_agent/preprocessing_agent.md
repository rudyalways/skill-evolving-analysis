# Agent 01 — Preprocessing

Normalize only observable run evidence from the run-local SQLite store and imported traces. Retain prompts, responses, tool events, timing, usage, outcomes, hashes, and bounded excerpts. Never retain or request hidden reasoning.

Reads: `input/`, `output/sampler.db`. Writes: `output/traces/derived/observable-evidence.json`. Stop after the artifact validates. Do not diagnose gaps or generate samples.

