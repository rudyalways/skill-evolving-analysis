---
name: lark-doc-reference-index
description: Consult a durable navigational index for the lark-doc skill documentation before rereading its SKILL.md or reference files, and rebuild the index at runtime when the source digest changes.
---

# Lark doc reference index

## Overview

Maintain a small navigation layer over the lark-doc skill documentation. It answers "which lark-doc documentation file should I open for this request?" and avoids rereading the whole source for information that has already been located. The index in `references/lark-doc-index.md` records the source locator, a file-level topic map, the recorded source digest, the freshness rule, and the exact read-when condition. It is navigation only: it never copies or paraphrases documentation content.

## When to Use

Use this skill when either condition holds; each one is independently sufficient:

- A request needs lark-doc documentation, such as a Docx or Wiki read, create, edit, image, attachment, or embedded-resource decision.
- A lark-doc question returns in a later turn and the same authoritative documentation file is needed again.

Also use it immediately before the conditional lark-doc workflow that would otherwise reopen `doc/skill.md` and several reference files. Do not wait for a restatement of the request.

## Do Not Use

- Do not use it for lark-sheets, lark-base, lark-slides, lark-drive-only, or general writing tasks.
- Do not answer a lark-doc question from the index alone; the index maps files and does not contain source content.
- Do not use it when the source root cannot be located or hashed. Run lark-doc normally and state that freshness could not be checked.
- Do not use it for unrelated local Markdown, office documents, or documentation from other skills.

## Workflow

1. Open `references/lark-doc-index.md`. Resolve the lark-doc skill root through the normal skill loader and set `LARK_DOC_ROOT` to it; never hardcode a machine path.
2. Read the source locator and the recorded digest row. Compute the current source digest with `shasum -a 256 "$LARK_DOC_ROOT/doc/skill.md"` (use `sha256sum` only if `shasum` is unavailable).
3. Apply the freshness rule:
   - Match: the recorded digest equals the computed digest and the topic map has a row for the task. Use that row.
   - Mismatch or unrecorded: rebuild before any lookup. Enumerate the source tree with `find "$LARK_DOC_ROOT/doc" -type f -name '*.md' | sort`, then rewrite the file-level map using relative paths and topic labels derived from the paths or task names only. Never copy headings, excerpts, or body text. Record the new digest in the same pass.
   - Hash or enumeration failure: do not guess a digest or a path. Report the index as unverified and fall back to lark-doc.
4. Select exactly one mapped file whose topic and read-when condition match the request. If several match, choose the narrowest. Read only that file, not the whole source tree.
5. If no row matches, read the source entry file once, add the missing row and read-when condition, then continue. If the path cannot be confirmed, use lark-doc normally and leave the map unchanged.
6. Return to the lark-doc workflow with the located file. Do not reread every reference file to prove the lookup.

## Constraints

- Store navigational metadata only: relative paths, topic labels, the digest, the freshness rule, and read-when conditions. Never embed source headings, section text, excerpts, or paraphrased documentation content.
- The recorded digest is the SHA-256 of the source entry file `doc/skill.md`. Never invent, estimate, or reuse a digest from another file. An unrecorded value is a mandatory rebuild trigger, not a verified digest.
- Keep one map row per source file, with paths relative to `LARK_DOC_ROOT` and confined to its `doc/` tree.
- Do not modify lark-doc source files. Refresh `references/lark-doc-index.md` in place only when the environment allows writing it; otherwise keep the refreshed map in the session and report that persistence failed.
- If the source changed during a task, rebuild before selecting a file. Never serve a row from a stale map.

## Verification

Before relying on the index, confirm all of the following:

- The digest command returns 64 hexadecimal characters and they equal the recorded digest.
- The selected map path exists under `LARK_DOC_ROOT/doc/`.
- A mismatch rebuild updates the map and digest in the same pass, and no stale row remains for a removed file.
- The reference file contains no source headings, excerpts, or document body text.
- An unrelated documentation request does not activate this skill.

## Output Format

Maintain `references/lark-doc-index.md` with these parts: source locator, recorded source digest, freshness rule, file-level topic map table, and the exact read-when condition. At runtime, report the single selected path and a one-sentence reason. For a rebuild, report the old and new digest and the number of rows added, changed, or removed.

## Limitations

The recorded digest covers only the source entry file `doc/skill.md`, so an edit to another mapped file may not change it; verify a mapped path's freshness when the edit is known. The index cannot locate files outside the lark-doc documentation tree, and it cannot substitute for reading the selected source file. When the runtime cannot write the reference file, the refresh lasts only for the current session.
