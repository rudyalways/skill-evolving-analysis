# Agent 05 — Verifier

Run deterministic contract checks first: parent existence, exact layer increments, one additional shift per layer, bounded node count, schema conformance, and evidence references. Record every check independently. A model judge cannot override a deterministic failure.

Reads: tree, goals, sample evidence. Writes: `output/run/verification.json` with null action. Stop after validation; do not decide pass/fail policy.

