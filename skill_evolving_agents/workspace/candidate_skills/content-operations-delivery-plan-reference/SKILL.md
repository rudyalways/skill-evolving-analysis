---
name: content-operations-delivery-plan-reference
description: Consult a durable navigational index for docs/architecture/content_operations_phased_delivery_plan.md before answering questions about its authentication or browser ownership, MVP content sources, RedNote or Xiaohongshu scope, delivery phases, or owner/MUST decisions, and rebuild the index at runtime when the source digest changes.
---

## Overview

Own the durable entry point for the content operations phased delivery plan.
Store only a source locator, a runtime-produced topic-to-section map, a
freshness rule, and the exact condition that warrants reading the plan, so a
later step jumps to the governing section instead of dumping or rescanning the
whole document. The index lives in
`references/content-operations-delivery-plan-index.md`.

## When to Use

Use this skill when any one of these is true:

- A step needs the content operations phased delivery plan, even if no earlier
  turn has retrieved it yet.
- The question is about authentication or browser automation ownership as
  recorded in the plan.
- The question is about MVP content sources, or about whether RedNote or
  Xiaohongshu is in scope.
- The question is about delivery phases, or about a specific owner or MUST
  decision recorded in the plan.
- A prior turn already retrieved the plan and the current step needs the same
  rule; a later restatement of the question alone is enough to activate again.

## Do Not Use

Do not use for unrelated documentation, product, or API reading. Do not use it
for decisions already answered in the current conversation. Do not use it as a
substitute for reading the cited plan section when the exact wording governs
the result, and do not use it to author or edit the plan itself.

## Workflow

1. Open `references/content-operations-delivery-plan-index.md` and confirm it
   names the source path and the read-when condition.
2. Resolve `docs/architecture/content_operations_phased_delivery_plan.md`
   relative to the repository root. If it is missing or unreadable, stop and
   fall back to a normal targeted read or report that the source is
   unavailable; do not guess its content.
3. Compute the current digest at runtime, for example
   `shasum -a 256 docs/architecture/content_operations_phased_delivery_plan.md`
   (use `sha256sum` where available). Compare it with the index's recorded
   `source_sha256`.
4. If the index is unindexed or the digest differs, rebuild only the locator
   layer. Extract the document's section headings with line numbers, for
   example `grep -nE '^#{1,6} ' docs/architecture/content_operations_phased_delivery_plan.md`,
   map the known query topics to the extracted sections, record the new digest
   and UTC refresh timestamp, and mark the index fresh.
5. Read just the matching section, using the recorded line range to bound the
   read. If no topic matches, read the smallest relevant range, answer from
   that range, and append the new topic mapping to the index.
6. Return the governing section reference with the answer. Never dump the full
   document when a bounded section answers the question.

## Constraints

Treat the index as navigation only: never store document body text, excerpts,
verbatim headings beyond what runtime extraction produced, or a stale digest.
Never claim freshness without recomputing it, and never invent a heading, a
section range, or a digest. Keep the recorded source path relative to the
repository root. Fail closed to a normal targeted read when the source is
missing or unreadable. Rebuild the map when the digest changes rather than
reusing old entries.

## Verification

Confirm the index exists at
`references/content-operations-delivery-plan-index.md`, resolves to the named
source, and contains the topic-to-section map schema and refresh rule. Confirm
a simulated digest mismatch triggers a rebuild rather than reuse. Confirm a
plan-related query reaches the correct section without reading the full
document.

## Output Format

Return the governing section reference (source path, heading, line range), the
freshness status (`fresh`, `refreshed`, or `source missing`), and either a
bounded excerpt-free answer or the next action to take. When refreshing, update
`references/content-operations-delivery-plan-index.md` in place with the source
path, digest, refresh timestamp, and topic-to-section entries. The complete
field layout and procedure are in that reference.

## Limitations

The finding supplies no document content, so this skill carries no precomputed
headings or content digest; both are populated on first use. It covers only
the one named source document until another resource contract adds a source.
It does not replace the canonical documentation audit or review commands, and
it cannot answer questions whose exact wording requires reading a section that
the runtime map has not yet located.
