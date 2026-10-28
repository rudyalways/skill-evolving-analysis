# Agent 04 — Sampling

Generate OOD category proposals from validated goals, preserve parent/child lineage, and produce a coverage-aware frontier queue. A cycle may update statistics without adding nodes, add siblings at an existing depth, or add deeper categories. Never derive category depth from the cycle/step number.

Return JSON with a `proposals` array. Every proposal contains `scenario_id`, a slash-separated `category_path`, optional `display_name`, and evidence references. Paths use `/` as the only hierarchy separator and contain at most three segments, for example `tool_use/recovery/retryable`. Include missing prefixes required by a deeper proposal. The host parser validates paths and updates the tree; prose or unvalidated output never mutates it.

Reads: goals, scenarios, observations, sampling policy. Writes: `output/evolution/ood-tree.json` and `output/run/sample-queue.json`. It proposes work; target invocation remains in the shared runner.

