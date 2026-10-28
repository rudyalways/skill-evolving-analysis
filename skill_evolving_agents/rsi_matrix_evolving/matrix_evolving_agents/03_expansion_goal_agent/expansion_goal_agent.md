# Agent 03 — Expansion goal

Turn each diagnosed finding into one bounded evolution goal. Layer 1 changes one axis, layer 2 composes two named axes, and layer 3 explores a failure neighborhood. Deduplicate identical goals before sampling.

Reads: diagnosis and policy. Writes: `output/run/<finding-id>/evolve-goal.json` plus `goal-reduction.json`. Do not invoke targets or judge results.

