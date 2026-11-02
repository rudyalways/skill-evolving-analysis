# Reliability workstreams index

## Source locators

- Guide path: `docs/operations/reliability_workstreams/p0_coordination_guide.md`
- Broader source path: `docs/operations/reliability_workstreams`
- Resolve both relative to the repository root. Resolve the guide once per
  checkout and record its absolute path and the repository root in
  checkout-scoped scratch state; re-resolve only when the checkout or
  repository root changes.
- Confirm whether each path is a file or a directory before hashing or
  extracting headings. The guide is expected to be a file; confirm it rather
  than assuming.
- The sources are the sole authority for their rules. This file carries
  navigation metadata only and never source prose, excerpts, or exact headings.

## Read when

Open this index before a conditional workflow that repeatedly retrieves either
source, and in particular before:

- a step that needs `docs/operations/reliability_workstreams/p0_coordination_guide.md`,
  including when an earlier window already read it;
- P0 workstream ownership, merge-order, or coordination-owner decisions;
- leaf-agent push decisions;
- finalizer decisions;
- a step that needs the same rule a prior turn already retrieved.

If the exact answer is already present and sufficient in the current
conversation, do not re-open the source.

## Runtime map contract

Build one map per source at runtime from the current source. Do not commit
source headings or line numbers to this file.

Each map entry has:

| Field | Meaning |
|---|---|
| `topic` | Normalized key derived from the heading text at extraction time |
| `heading` | Heading text observed during this run |
| `start` | 1-based line number of the heading |
| `end` | Line before the next heading of the same or higher level |

Entries: none captured at authoring time. Source content was unavailable, so
no heading, range, or topic key is asserted here. Populate entries in the
checkout-scoped scratch state, not in this repository copy.

## Freshness procedure

1. Recompute SHA-256 at runtime for the source being reused:
   - guide file:
     `shasum -a 256 docs/operations/reliability_workstreams/p0_coordination_guide.md`
     (use `sha256sum` where available);
   - broader directory: hash the sorted per-file digests:
     `find docs/operations/reliability_workstreams -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 | shasum -a 256`.
2. Compare with the digest recorded for that source in the same
   checkout-scoped scratch state.
3. Report one status for the guide:
   - `unindexed`: no digest or no map for this checkout; extract before use.
   - `matched`: digests equal; reuse the run map.
   - `refreshed`: digests differ; discard all ranges and re-extract.
   - `unavailable`: source absent or unreadable; report it, do not fabricate.
4. Write the new digest only to checkout-scoped state. This file must never
   contain a recorded source digest or a resolved absolute path.

## Extraction and range reading

Enumerate level-2 headings with line numbers from the current source, for
example for the guide:

```bash
grep -nE '^##[[:space:]]+' docs/operations/reliability_workstreams/p0_coordination_guide.md
```

A section spans from its heading line through the line before the next heading
of the same or higher level. Normalize heading text into the topic key at
extraction time. Select the single best-matching section, read only that range,
and cite the observed heading and line range. Do not quote the whole guide. If
no section matches, report the gap instead of widening the read.

## Refresh and retention rules

- Resolve the guide path once per checkout; keep the resolved path and digest
  checkout-scoped, not in this repository file.
- Discard the run map on any digest mismatch, on a different repository
  revision, or when the source path changes.
- Never reuse a recorded line range after a mismatch.
- Keep only navigation metadata in this file. Do not add prose, excerpts,
  exact headings, a content digest, or a resolved absolute path.
- When the source is unavailable, the index is not a fallback: report the
  missing source and stop.
