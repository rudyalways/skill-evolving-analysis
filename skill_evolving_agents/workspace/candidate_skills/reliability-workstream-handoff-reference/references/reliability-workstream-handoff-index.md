# Reliability workstream handoff index

Navigation-only index for the reliability workstream handoff and promotion
policy. It records where to look and how to prove the pointer is current; it
does not contain policy text.

## Source locator

- **Path**: `docs/operations/reliability_workstreams/handoff_prompts.md`
- **Resolve against**: repository root, not the skill directory.
- **Read when**: before the conditional workflow that repeatedly retrieves this
  knowledge, and again whenever a later step needs the same policy rule.
- **Owns**: workstream sequencing, admission and handoff rules, production
  promotion constraints, and owner decisions recorded in that source.

## Index state

- **Status**: `unindexed` at authoring time.
- **Source content**: not available when this index was written.
- **Source digest**: not available when this index was written, so no
  `source_sha256` value and no topic-to-section rows are recorded here.
- **Consequence**: the first runtime check must take the rebuild path. Do not
  treat this file as a cached policy or pretend its map is populated.

## Runtime build (required before citing)

Run these steps in order. Build the map in the task's working notes; do not copy
policy text into this file.

1. Resolve and confirm the source:
   `test -r docs/operations/reliability_workstreams/handoff_prompts.md`
   If this fails, stop and report `source unavailable`.
2. Compute the current digest:
   `shasum -a 256 docs/operations/reliability_workstreams/handoff_prompts.md`
   On systems without `shasum`, use
   `sha256sum docs/operations/reliability_workstreams/handoff_prompts.md`.
3. Extract only the real headings with line numbers:
   `grep -nE '^#{1,6}[[:space:]]+' docs/operations/reliability_workstreams/handoff_prompts.md`
4. Build one row per heading that actually appears: verbatim heading text,
   heading line, and range from that line to the line before the next heading
   (or end of file). Use the heading wording as the topic key and add question
   synonyms only when they map unambiguously to that heading.
5. Record the computed digest next to the new map for the life of the task.
   Never record a digest for a build that did not run.

## Freshness check

1. Recompute the digest with the command above. Never reuse a prior turn's
   value.
2. If a runtime map exists and its recorded digest equals the computed digest,
   status is `match`: reuse its ranges without re-extraction.
3. If the digest differs, or no runtime map exists, status is `refreshed`:
   re-extract headings and rebuild all ranges before citing anything.
4. If the source is missing or unreadable, status is `source unavailable`: do
   not cite a range and do not answer from this index.

## Reading a selected range

After choosing the governing topic, read only its range:

`sed -n 'START,ENDp' docs/operations/reliability_workstreams/handoff_prompts.md`

If no topic matches, read the closest parent heading, not the whole file.

## Reporting

State the freshness status (`match`, `refreshed`, or `source unavailable`), the
verbatim governing heading, and its `START-END` range. The answer may use only
text inside that range.

## Guardrails

- No policy body text, excerpts, or paraphrased rules belong in this index.
- No invented headings, topics, ranges, or digest values.
- No recorded range survives a digest mismatch.
- This index never substitutes for reading the source when exact wording
  governs the answer.
- Do not edit the source document from this workflow.
