# Cluster

Group canonical turns by compact core text. This phase is optional and deterministic. It runs after normalization and slicing when clustering was requested.

## Context

`cluster_traces.py` computes TF-IDF features from each canonical turn's user request, final assistant response, and outcome. An optional embedding strategy reads externally generated vectors configured in `common/preprocessing-config.json`. Each cluster directory contains `manifest.jsonl` and `representatives.jsonl`. When a cut algorithm anchors a window on a member, the directory also contains `cut.jsonl` with that window. Coverage stays on the manifest; diagnosis reads the window.

## Constraints

Do not embed or cluster raw vendor records, full tool outputs, hidden reasoning, or base64. Do not copy canonical turn files into clusters. Do not assign capability labels.

## Workflow

Write pointer records under `workspace/traces/derived/cluster/<cluster>/manifest.jsonl`. Every eligible trace ID is covered by at least one cluster or `unassigned`, and every `turn_path` resolves to a canonical turn with the same ID.

## Applies when

Canonical turns exist and clustering was requested.
