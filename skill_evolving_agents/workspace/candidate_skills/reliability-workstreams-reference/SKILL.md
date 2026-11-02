---
name: reliability-workstreams-reference
description: Record and consult a durable section-level index for docs/operations/reliability_workstreams instead of re-reading the whole document. Use before P0 workstream coordination, ownership, merge-order, leaf-agent push, or finalizer decisions, and whenever a prior turn already retrieved the document and the current step needs the same rule.
---

# Reliability workstreams reference

## Overview

Maintain a navigational index for `docs/operations/reliability_workstreams`.
The index lives at `references/operations/reliability_workstreams.md`. It gives
a later step a source locator, a read-when condition, a topic-to-section map
materialized at runtime, and a freshness rule. It is not a copy, summary, or
replacement for the source document.

The index answers one kind of question: which section of the source governs a
P0 workstream decision, and what does that section say. Use the source wording
for the answer; use the index only to reach the right range without scanning
the whole document.

## When to Use

Any one of these conditions is sufficient; they are alternatives, not a
checklist.

- A step concerns P0 workstream ownership, merge order, leaf-agent push
  restrictions, coordination-owner integration, or finalizer responsibilities
  recorded in `docs/operations/reliability_workstreams`.
- A conditional workflow needs `docs/operations/reliability_workstreams/p0_coordination_guide.md`,
  including when an earlier window already retrieved that guide. Settle its
  source locator and freshness status before consulting it again instead of
  re-reading the file.
- A prior turn already retrieved the document and the current step needs the
  same rule to make or justify a decision.
- The current step needs the document even though no earlier turn retrieved it.
- The user asks to consult, refresh, or repair the section-level index rather
  than re-read the whole document.

## Do Not Use

- Do not use for unrelated repository, product, or API documentation.
- Do not use when the governing answer is already present in the current
  conversation and is sufficient for the decision.
- Do not use as a substitute for reading the cited source section when its
  exact wording governs the result.
- Do not use to author, edit, or reformat the source document.
- Do not use to dump, summarize, or bulk-read the whole document.

## Workflow

1. Open `references/operations/reliability_workstreams.md` before opening the
   p0 coordination guide or any other workstreams source.
2. Resolve the guide path once per checkout: take
   `docs/operations/reliability_workstreams/p0_coordination_guide.md` relative
   to the repository root, and record the resolved absolute path plus the
   repository root in checkout-scoped scratch state. If it is absent or
   unreadable, report `unavailable`; do not reconstruct rules from memory.
3. Compute a fresh SHA-256 digest of the resolved guide file on every later
   reuse:
   `shasum -a 256 docs/operations/reliability_workstreams/p0_coordination_guide.md`
   (or `sha256sum`). Reuse the path recorded for this checkout; re-resolve it
   only when the checkout or repository root changes.
4. Compare the computed digest with the digest recorded in the same
   checkout-scoped scratch state. Classify freshness:
   - no digest or no map for this checkout: `unindexed`;
   - digest equal: `matched`;
   - digest different: `refreshed`;
   - source absent or unreadable: `unavailable`.
   Never persist the digest or the path in the index file; both are
   checkout-scoped state.
5. On `unindexed` or `refreshed`, discard every previously held range and
   rebuild the runtime topic-to-section map from the current guide. Enumerate
   its level-2 headings with line numbers, for example
   `grep -nE '^##[[:space:]]+' docs/operations/reliability_workstreams/p0_coordination_guide.md`.
   A section runs from its heading line to the line before the next heading of
   the same or higher level. Normalize each heading into a topic key at
   extraction time. Do not reuse a recorded range after a mismatch.
6. On `matched`, use the existing map. If the requested topic is absent from
   the map, report that gap rather than guessing a range or reading the whole
   guide.
7. Read only the governing section range for the requested topic. Apply the
   rule as written there. If the source wording is ambiguous or incomplete,
   say so and cite the consulted heading and range.
8. For a question about the broader `docs/operations/reliability_workstreams`
   directory, apply the same resolve, digest, compare, and rebuild sequence to
   that source, hashing a directory as
   `find docs/operations/reliability_workstreams -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 | shasum -a 256`.
9. Update the checkout-scoped digest and map after extraction so later steps in
   the same checkout can reuse them without re-reading.

## Constraints

- Store navigational metadata only: source path, read-when condition, the
  runtime map schema, freshness state, and refresh rule. Never copy source
  prose, excerpts, or exact heading text into the repository index beyond what
  runtime extraction produces.
- Do not record a source digest in `references/operations/reliability_workstreams.md`.
  The contract marks source content and its digest unavailable; freshness is
  computed on every run.
- Do not invent headings, line numbers, topic keys, or rules when the source is
  unavailable. An empty or unindexed map is truthful; a fabricated map is not.
- Do not read the whole document when a single section range answers the
  question. Do not broaden a targeted lookup into a summary.
- Do not edit `docs/operations/reliability_workstreams` or treat the index as
  the source of record.
- Do not read or write skill metadata. Do not edit the changelog beside the
  skill directory.

## Verification

- Confirm the index was opened before the p0 coordination guide or any other
  workstreams source.
- Confirm the guide path was resolved from the repository root once for this
  checkout and that the SHA-256 digest was recomputed on reuse. Report the
  guide's freshness status as `matched`, `refreshed`, `unindexed`, or
  `unavailable`.
- Confirm a mismatch triggered map rebuild and that no stale range was reused.
- Confirm only the governing section range was read, and cite the heading and
  line range taken from the runtime map. Do not quote the whole guide.
- Claim no rule without observed source text. If the relevant section is
  absent, report that residual uncertainty instead of filling it in.

## Output Format

Reply with:

- `source`: `docs/operations/reliability_workstreams`
- `index`: `references/operations/reliability_workstreams.md`
- `freshness`: `matched`, `refreshed`, `unindexed`, or `unavailable`
- `section`: the consulted heading, or `none` when unindexed or absent
- `lines`: the consulted line range, or `none`
- `rule`: the applied rule, quoted or tightly paraphrased from the observed
  section
- `uncertainty`: any gap, ambiguity, or missing section, or `none`

## Limitations

The index is only as current as its last runtime extraction and cannot answer
questions about sections the source omits. It does not cache source text and is
not a citation substitute: when the exact wording governs a decision, read the
cited section. When the source is unavailable, report the missing source rather
than reconstructing it from memory.
