---
name: lark-doc-navigation-reference
description: Consult and maintain a durable navigational index over the live lark-doc skill documentation, with source locators, a combined file-and-heading topic map, recorded sha256 digests, and a runtime freshness and rebuild rule.
---

## Overview

This skill is a navigation and freshness layer over the live lark-doc files. It answers two questions before a lark-doc-dependent step: which lark-doc file covers this request, and which heading or line range inside it governs. `references/lark-doc-index.md` holds the source locators, the combined file-and-heading topic map with line ranges, the recorded sha256 digests, the read trigger, and the refresh rule.

The index is navigational metadata only. lark-doc remains authoritative, and this skill never copies or replaces its content.

## When to Use

Each condition below is independently sufficient; no prior turn or restatement is required.

- A Feishu/Lark docx or wiki task needs lark-doc behavior: reading, creating, editing, media handling, history, whiteboards, mindnotes, or XML/Markdown authoring.
- The exact command, flag, scope, or reference file must be located before acting.
- A later turn needs the same lark-doc rule that an earlier turn already looked up.
- Several lark-doc reference files seem plausible and the narrowest one must be selected.
- The index check is due immediately before the conditional lark-doc workflow that would otherwise reopen the full `SKILL.md` or several reference files.

## Do Not Use

- Do not use for non-lark-doc work: lark-sheets, lark-base, lark-slides, lark-drive-only, unrelated local documents, general writing, or reading APIs outside Feishu/Lark docx and wiki content.
- Do not use when the conversation already contains the governing answer and no freshness check is needed.
- Do not use the index as a substitute for reading the governing source section when its exact wording controls the result.
- Do not use this skill to author or edit lark-doc content, or to edit any live lark-doc source file; it only routes to authoritative instructions.
- Do not use it when the source root cannot be located or hashed; run lark-doc normally and state that freshness could not be checked.

## Workflow

1. Resolve the live lark-doc skill root through `LARK_DOC_SKILL_DIR`, then the normal skill loader or host skill root, then `~/.agents/skills/lark-doc`. Never assume a recorded absolute path is valid on this machine.
2. Read `references/lark-doc-index.md` and its source locators, file map, heading map, and digest ledger.
3. Recompute the sha256 digest for every recorded source before using the map. Use `shasum -a 256`, falling back to `sha256sum`.
4. When every digest matches and the topic is mapped, jump to the mapped heading and line range in the selected file. Read from that heading to the next heading of the same or higher level, and no further.
5. On a digest mismatch, a missing or unhashable source, or an unindexed topic, refresh before lookup: enumerate the lark-doc documentation tree and re-extract headings with `grep -nE '^#{1,6} '`, then update the file map, heading map, line ranges, and digests in the same pass. Do not copy body text into the index.
6. Select exactly one mapped file whose topic and read-when condition match the request. If several match, choose the narrowest; if none matches after refresh, add only a route the real headings support.
7. Report the source, freshness status, governing heading, reference file, line range, and refreshed fields, then return to the lark-doc workflow with the located section.

## Constraints

- Keep `references/lark-doc-index.md` navigational only: relative paths confined to the lark-doc documentation tree, a file map, heading map and line ranges, sha256 digests, the read trigger, and the refresh rule.
- Never embed body text, excerpts, command output, credentials, a paraphrased rule, or an invented digest, heading, or path.
- The digest is SHA-256, 64 hexadecimal characters, computed from the resolved file. An unrecorded value is a rebuild trigger, not a verified digest.
- Never edit the live lark-doc source files. Refresh only the index's locators, map rows, ranges, digests, and status.
- Do not re-dump the full lark-doc source or preload every reference file when a mapped range answers the need.
- If a source cannot be read or hashed, record it as `unavailable` and do not serve its routes as current guidance.
- Keep the map limited to routes the live heading listing or file enumeration actually supports, including on-demand `references/genres/` files.

## Verification

Before relying on the index, confirm that:

- The digest was recomputed for every recorded source and reported as `matched`, `refreshed`, or `unavailable`, with a 64-hex value where available.
- The governing heading text and level, reference file, and line range consulted are cited.
- The selected path exists under the resolved lark-doc root.
- Only the mapped range was read, not the full source or unrelated reference files.
- A mismatch, missing source, or unindexed topic triggered re-extraction and a refresh rather than reuse of recorded ranges.
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

- The live root varies per machine and per lark-doc packaging, so recorded paths and digests are baselines, not proof of presence.
- A missing or unhashable source is reported as `unavailable` and blocks a current-guidance claim until it is restored.
- The map can lag until the runtime refresh runs; unindexed topics require a refresh first.
- `references/genres/` is coverage selected on demand by the create workflow, not a fully enumerated part of the map.
- The index never replaces the authoritative lark-doc source text.
