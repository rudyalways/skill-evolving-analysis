# Agent 07 — Visual dashboard

Render the verified run as a self-contained, light-background HTML review surface. Show a connected parent/child tree, timeline slider and playback, nodes appearing as the tree expands, and attempts/posterior/success/cost statistics changing across real cycle snapshots. Provide filters without changing run state.

Reads: verified `ood-tree.json`, append-only `history.jsonl`, and aggregate metrics. Writes: `output/dashboard.html`. The HTML is a review surface; JSON, history, and SQLite remain authoritative.

