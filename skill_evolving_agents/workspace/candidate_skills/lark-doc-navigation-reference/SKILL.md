---
name: lark-doc-navigation-reference
description: Consult a durable navigational index for the live lark-doc skill before repeatedly reading its SKILL.md or references. Use when a Feishu/Lark docx or wiki task needs the exact command, flag, workflow, or reference-file choice, or when an earlier turn already read lark-doc and the current step needs the same rule checked against a recomputed sha256 digest.
---

## Overview

Own the durable entry point for lark-doc knowledge. `references/lark-doc-index.md` stores source locators, a topic-to-heading map, recorded sha256 digests, the read trigger, and the refresh rule. It lets a later step jump to the governing section or reference file instead of dumping the whole lark-doc SKILL.md or its references.

This skill is an index and freshness protocol, not a copy of lark-doc. The live lark-doc files remain authoritative.

## When to Use

- A task needs lark-doc behavior for Feishu/Lark docx or wiki content: reading, creating, editing, media handling, history, whiteboards, mindnotes, or XML authoring.
- The exact command, flag, scope, or reference file must be located before acting.
- A prior turn already read the lark-doc skill and the current step needs the same rule; a fresh restatement of the request is not required.
- Several lark-doc reference files seem plausible and the right one must be selected before reading it.

## Do Not Use

- Do not use for unrelated documentation, API reading, or writing tasks outside Feishu/Lark docx and wiki content.
- Do not use when the current conversation already contains the governing answer and no freshness check is needed.
- Do not use the index as a substitute for reading the cited section when its exact wording governs the result.
- Do not use this skill to author or edit lark-doc content; it only routes to the authoritative instructions.

## Workflow

1. Resolve the live lark-doc skill root: the directory containing lark-doc's `SKILL.md`. Check `LARK_DOC_SKILL_DIR` first, then the host skill root, then `~/.agents/skills/lark-doc`. Never assume a recorded absolute path is valid on this machine.
2. Open `references/lark-doc-index.md` and read its source locators and digest ledger.
3. Recompute the sha256 digest for every recorded source path before consulting the map. Use `shasum -a 256` where available, otherwise `sha256sum`.
4. If every digest matches and the topic is mapped, jump to the mapped heading in the recorded reference file. Read from that heading to the next heading of the same or higher level, and no further.
5. If any digest differs or a source is missing, refresh before using the map. Re-run a heading listing pass over `SKILL.md` and every recorded reference file, for example with `grep -nE '^#{1,6} '`. Use the actual headings to update the topic-to-heading map and line ranges, recompute and record the digests, and mark the refresh status. Do not copy body text into the index.
6. If the topic is not mapped, treat it as stale coverage: run the same heading and digest refresh, add only the missing route, then read the mapped range.
7. Report the source path, freshness status, governing heading, reference file, and the line range consulted. List the index fields that were refreshed.

## Constraints

- Keep `references/lark-doc-index.md` an index: source locators, heading map, line ranges, sha256 digests, read trigger, and refresh rule only. No copied body text, excerpts, command output, credentials, or invented digest.
- Run the freshness check before every consult. Never claim current guidance without a recomputed digest match, and never present a stale digest as current.
- On a mismatch, missing file, or unindexed topic, re-extract headings instead of reusing recorded ranges.
- Never re-dump the full lark-doc source when a mapped section answers the need. Do not read every reference file at task start.
- Do not edit the live lark-doc skill or its files. Update only the index's locator, map, range, and digest metadata.
- Never invent a heading, rule, excerpt, source path, or digest. If a source is absent, record the digest as unavailable and route only after the source is restored.
- Keep the map limited to topics the live heading listing actually supports.

## Verification

Before relying on the index, confirm that:

- The digest was recomputed for every recorded source and reported as matched, refreshed, or unavailable.
- The governing heading, reference file, and line range consulted are cited in the result.
- Only the mapped range was opened, not the full source or unrelated reference files.
- A stale digest triggered a heading re-extraction and an index refresh rather than reuse of recorded ranges.
- The index still contains no copied prose, command output, credentials, or invented digest.

## Output Format

Report a short block with these fields:

- `source`: the lark-doc source path consulted.
- `freshness`: `matched`, `refreshed`, or `unavailable`, with the digest basis.
- `heading`: the governing heading text and level.
- `reference`: the reference file consulted, if any.
- `range`: the line range read.
- `refreshed`: index fields updated, or `none`.

Then give the answer that the cited section supports. Do not paste the section in full.

## Limitations

- The index depends on the live lark-doc skill path, which may differ per machine.
- A missing source makes its digest unavailable and blocks a current-guidance claim until the source is restored.
- The heading map can lag until the runtime refresh runs; unindexed topics require a refresh first.
- The index never replaces the authoritative lark-doc section text, and it does not cover every file under `references/genres/`; those are selected by the create workflow and read on demand.
