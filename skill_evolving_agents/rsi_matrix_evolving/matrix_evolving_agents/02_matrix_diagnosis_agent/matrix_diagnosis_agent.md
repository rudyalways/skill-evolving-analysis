# Agent 02 — Matrix diagnosis

Compare observed evidence with declared scenarios and the current sparse matrix. Emit evidence-backed findings for coverage gaps, posterior uncertainty, verified failures, verifier disagreement, and novel failure signatures. Low frequency alone is not OOD.

Reads: normalized evidence and scenario snapshot. Writes: `output/run/diagnosis.json`. Stop after scoped findings validate. Do not expand the tree.

