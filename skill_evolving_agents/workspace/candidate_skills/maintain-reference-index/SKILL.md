---
name: maintain-reference-index
description: Build a compact heading-and-line index for a long reference guide, store a file fingerprint, and serve later lookups from the index instead of re-reading the whole source when that guide is consulted again across steps or context windows.
---

# Maintain reference index

## Overview

Own the reuse of a stable, long-form knowledge source. Capture its navigational
structure once as a compact index, store a fingerprint beside it, and serve
later lookups from the index rather than repeating whole-document reads. The
index locates content; the source remains authoritative for what the content
says.

## When to Use

Any one of these conditions is sufficient:

- The same long guide, reference document, or specification has been read,
  searched, or dumped at least three times across separate steps or context
  windows.
- A previously consulted source is about to be opened again.
- A document is too large to keep in context but you expect repeated section
  lookups during the task.

## Do Not Use

Do not use this skill for a one-off read, for a document small enough to read
comfortably in context, or for a source whose content changes on every access
where an index would be stale immediately. Do not use it when the task requires
quoting the source verbatim from start to finish rather than locating a section.
Do not index a source you have never opened or that you cannot fingerprint.

## Workflow

1. Look for an existing index and fingerprint near the source or in the working
   directory. If one exists, read only its fingerprint block first; do not open
   the source yet.
2. Compute the current fingerprint from the source's absolute path, byte size,
   modification time, and SHA-256 content hash. Follow
   `references/freshness-check.md` for the commands and comparison rules.
3. Compare the stored fingerprint with the computed one. If both are present and
   identical, consult the index and jump to the recorded line anchor or locator.
4. If there is no index, or the fingerprint differs, index the source: enumerate
   its headings in document order, record one compact row per heading with its
   line range and a short locator, and write the index using
   `references/navigational-index-template.md`. On a fingerprint mismatch,
   compare the changed source against the previous copy where available and
   re-index only the affected sections; when the affected range cannot be
   determined cheaply, re-index the whole source.
5. Store the newly computed fingerprint in the same file as the index, then use
   the index for the current lookup. Recompute and compare the fingerprint
   before every later consultation; never consult a stale index as if it were
   current.
6. If the lookup needs the actual wording, open only the located line range from
   the source. Do not dump the whole document back into context.

## Constraints

- Keep the index navigational only: headings, line ranges, and short locators.
  Do not copy excerpts, summaries of section content, or paraphrased rules into
  the index.
- Bound locators to a few words, such as a parent heading path or a distinctive
  nearby term. The index must stay much smaller than the source.
- Never treat the index as authoritative over the source. When they disagree,
  the source wins and the index is corrected.
- Require the fingerprint check before every consultation. Do not skip it
  because the previous check passed.
- Do not use background watchers, daemons, file-system events, or unbounded
  polling. Freshness is checked on demand at lookup time.
- Do not add a script or store a placeholder digest. The commands in
  `references/freshness-check.md` are the supported procedure.
- Keep the index and fingerprint in one Markdown file so they cannot drift
  apart. Do not write metadata or edit any changelog beside the skill.

## Verification

Before relying on a lookup, confirm:

- Every top-level heading in the source has one index row, and every row's line
  range exists in the source.
- The fingerprint block names the source path, size, modification time, SHA-256
  hash, and the timestamp of the check, and recomputing the hash reproduces the
  stored value.
- A deliberately changed source produces a fingerprint mismatch and triggers
  re-indexing of the affected sections before any lookup uses the index.
- A lookup returns a source anchor or line range without a full-document read,
  and the cited source text at that anchor matches the requested section.

## Output Format

Write one Markdown file containing a heading table and a fingerprint block, in
the layout defined by `references/navigational-index-template.md`. The table has
columns for heading, line range, and locator. The fingerprint block names the
source path, size, modification time, SHA-256 hash, and check timestamp. The
index file contains no copied source prose. Behavioral fixtures for activation
and near-miss behavior live in `evals/evals.json`.

## Limitations

The index locates sections but does not summarize, validate, or update their
content. Fingerprint comparison detects byte-level change only when the stored
hash is current; it cannot detect semantic changes when metadata and content
hash are unchanged, and it cannot tell whether a changed section is still
correct. The procedure assumes the source is a readable local file whose path,
size, modification time, and bytes are observable.
