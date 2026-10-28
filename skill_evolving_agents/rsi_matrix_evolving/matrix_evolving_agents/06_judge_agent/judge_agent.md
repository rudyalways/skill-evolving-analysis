# Agent 06 — Judge

Apply the terminal deterministic formula to validated verification output. Pass only when the overall verifier status and every required deterministic check pass. No model call, retry, or taxonomy mutation is allowed.

Reads: `verification.json`. Writes: `output/run/judge.json`. Both pass and fail are terminal for the cycle.

