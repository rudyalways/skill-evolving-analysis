# Normalize and slice traces

Multi-source normalization and turn slicing are deterministic preprocessing
states.
The runner invokes the scripts in `01_preprocessing_agent/scripts`; a model
does not parse raw vendor JSONL.

## Context

`normalize_codex.py` uses registered adapters for immutable logs under
`workspace/traces/raw/{codex,claude,cursor}` (with `raw/target_agent` accepted
for backward compatibility). It emits one bounded canonical record per
substantive user turn. Detailed tool events are selective sidecars.
Deterministic signal mining writes typed findings; deduplication and clustering
write pointer-only manifests.

## Constraints

Do not edit raw logs. Do not preserve system instructions, ambient UI state,
token accounting, world state, compaction snapshots, hidden reasoning,
duplicate lifecycle events, or inline base64 in canonical turns. Do not copy
full turn payloads into cut or cluster directories.

## Workflow

Run deterministic normalization, validate every canonical turn, and write a
cut manifest that covers every eligible trace ID exactly once. Record byte and
estimated-token reduction metrics in `logs/metrics.sqlite` and
`derived/normalized/metrics.json`.

`cut.algorithms` in `common/preprocessing-config.json` is the cut algorithm
list. The same list is written to `traces/derived/cut/algorithms.json`. Each
algorithm proposes a short window; the coverage manifest stays complete.
`traces/derived/cut/windows.jsonl` holds the windows a diagnosis agent should
read:

- `consecutive_repetition`: three or more similar requests in a row, plus the
  request before and the request after, at most five turns
- `long_turn`: one request whose agent run exceeds five minutes, plus one
  request before and one after
- `long_turn_then_correction`: a long run whose next message is a correction
- `correction_burst`: consecutive corrections, plus the turn they correct
- `rapid_correction`: a correction that arrives within seconds
- `tool_failure_streak`: consecutive failed turns
- `keep_going_streak`: consecutive keep-going requests, plus the unfinished turn
- `unresolved_repeat`: the next request repeats an unanswered one
- `abandonment`: a turn with no final response, plus the preceding request
- `repeated_assistant`: consecutive replies that say the same thing
- `oscillation`: an ask that goes away and comes back at least three times

`max_user_turns` caps how many user rounds a window keeps. `max_tokens`
caps the user, assistant, and error text copied into each window `slice`.
Diagnosis reads that slice.

A long-turn window with a large tool sidecar also gets a trimmed excerpt at
`traces/derived/cut/tool_evidence/`. Read that excerpt instead of the full
sidecar.

## Applies when

Supported vendor logs are present and the pipeline needs compact canonical
turns.
