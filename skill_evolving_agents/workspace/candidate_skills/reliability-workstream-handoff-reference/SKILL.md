---
name: reliability-workstream-handoff-reference
description: Consult a durable navigational index for the reliability workstream handoff and promotion policy before answering questions about workstream sequencing, admission or handoff rules, or production promotion constraints, and rebuild the index at runtime when the source digest changes.
---

## Overview

Own the durable entry point for the reliability workstream policy source:
`docs/operations/reliability_workstreams/handoff_prompts.md`, resolved against
the repository root. The entry point is the navigation-only index at
`references/reliability-workstream-handoff-index.md`: a source locator, a
topic-to-section map built at runtime from the real source headings, a
freshness rule, and the exact read-when condition.

The index locates governing text; it never reproduces it. Its purpose is to let
a later step jump straight to the governing heading instead of dumping or
rescanning the whole policy document, while keeping line ranges honest as the
source changes.

## When to Use

Activate when any one of these is true; a single trigger is sufficient and no
other condition must also hold:

- The step needs the reliability workstream handoff or promotion policy, even
  when no earlier turn retrieved it.
- The question concerns workstream sequencing, admission or handoff rules,
  production promotion constraints, or a specific owner decision recorded there.
- A prior turn retrieved the policy and the current step needs the same rule
  again, so the compact index should replace a second full read.
- The source digest has changed since the index was last built, or the index has
  never been built, and the current step needs the policy.

## Do Not Use

Do not use for unrelated documentation, product, or API reading. Do not use when
the current conversation already answered the question. Do not use the index as
a substitute for reading the cited source section when exact wording governs the
result. Do not use it to author or edit the policy document itself.

## Workflow

1. Open `references/reliability-workstream-handoff-index.md` and confirm it
   names the source path and the read-when condition. If either is missing, stop
   and treat the source as unavailable rather than guessing.
2. Resolve the source path relative to the repository root. Confirm the file
   exists and is readable; if not, stop and follow the fallback in Constraints.
3. Compute the current SHA-256 digest at runtime, for example:
   `shasum -a 256 docs/operations/reliability_workstreams/handoff_prompts.md`
   (use `sha256sum` where `shasum` is unavailable). Do not trust a digest copied
   from the index or from an earlier turn.
4. Compare the computed digest with the index's recorded `source_sha256`. The
   authored index is deliberately **unindexed**: source content and digest were
   unavailable when it was written, so no digest, headings, or line ranges are
   recorded and the first check always takes the rebuild path. A match reuses
   the recorded topic-to-section ranges. A mismatch or an unindexed state
   requires re-extraction before any citation.
5. Re-extract the section map from the source itself. List the real headings and
   their line numbers, for example:
   `grep -nE '^#{1,6}[[:space:]]+' docs/operations/reliability_workstreams/handoff_prompts.md`
   Build each topic row only from headings that actually appear: topic key from
   the heading wording, heading text verbatim, and line range from that heading
   line to the line before the next heading. Pair the new map with the digest
   just computed for the life of the task; never carry old ranges across a
   mismatch.
6. Match the question to the smallest governing topic, then read only that
   range, for example:
   `sed -n 'START,ENDp' docs/operations/reliability_workstreams/handoff_prompts.md`.
   If no topic matches, widen to the closest parent heading rather than reading
   the whole file.
7. Cite the governing heading and its line range in the reply. If the exact
   wording decides the result, quote only the short passage actually read.

## Constraints

- Keep the index navigation-only: no policy body text, no excerpts, no invented
  section names, and no recorded line ranges reused after a digest mismatch.
- Never fabricate a heading, topic, line range, or digest to make the index look
  complete. An empty or unindexed map is the truthful state until a runtime
  build succeeds.
- If the source is missing or unreadable, stop and either fall back to a normal
  targeted read of the best-known location or report that the source is
  unavailable; do not answer from the index alone.
- Do not edit the policy source and do not write policy content back into the
  index. The index records navigation metadata only.
- Do not present a cached range as fresh when the digest was not recomputed in
  the current step.

## Verification

Before answering, confirm all of the following:

1. The index names the correct source path and the read-when condition.
2. The runtime digest was actually recomputed and its value compared with the
   recorded value, or the index was explicitly recognized as unindexed.
3. A mismatch or unindexed state triggered heading re-extraction from the
   source, while a match reused the recorded ranges without re-extraction.
4. Only the matching range or ranges were read, not the whole document.
5. The reply reports the freshness status and cites the governing heading with
   its line range.
6. The answer uses only text inside the cited range; anything outside it is not
   attributed to the source.

## Output Format

Report:

- **Freshness status**: `match`, `refreshed`, or `source unavailable`.
- **Governing heading and line range**: the verbatim heading and `START-END`.
- **Answer**: only the content drawn from that range, with a short quote when
  exact wording matters.

For `source unavailable`, state the missing or unreadable path, report that no
governing range was cited, and offer the targeted-read fallback instead of an
answer derived from the index.

## Limitations

The index locates content but does not reproduce it, so exact wording still
requires reading the cited source section. Recorded line ranges are valid only
while the digest matches; any edit above a heading shifts the ranges. Topic
coverage is limited to the headings present when the map was last built, so a
newly added section is invisible until the next rebuild. The index cannot
recover a deleted, renamed, or unreadable source.
