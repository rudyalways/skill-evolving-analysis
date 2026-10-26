# Content operations delivery plan index

Navigation only. This file records where the plan is and how to prove the
index still matches it. It must not contain plan body text, excerpts, or
invented section names.

## Source locator

| Field | Value |
| --- | --- |
| `source_path` | `docs/architecture/content_operations_phased_delivery_plan.md` |
| `path_base` | Repository root |
| `document` | Content operations phased delivery plan |
| `index_state` | `unindexed` |
| `source_sha256` | Not recorded at authoring time |
| `refreshed_at_utc` | Not recorded at authoring time |

The finding that created this skill supplies no document content and no digest,
so no heading, line range, or digest is seeded here. Populate
`source_sha256`, `refreshed_at_utc`, and the topic map on the first runtime
refresh. Never write a guessed digest, and never treat `unindexed` as fresh.

## Read when

Read or refresh this index before any step that needs the plan, including a
question about authentication or browser ownership, MVP content sources,
RedNote or Xiaohongshu scope, delivery phases, or an owner/MUST decision
recorded in the plan. A first mention is enough; a later restatement of a plan
question is also enough. Do not read the plan for unrelated documentation,
product, or API questions, or for a decision already answered in the current
conversation.

## Freshness check

Run these steps at the start of every use. Do not skip the digest comparison
because the index looks recent.

1. Resolve `source_path` from the repository root. If it is missing or
   unreadable, report `source missing` and fall back to a normal targeted read;
   do not answer from this index alone.
2. Compute the current digest:

   ```sh
   shasum -a 256 docs/architecture/content_operations_phased_delivery_plan.md
   # or: sha256sum docs/architecture/content_operations_phased_delivery_plan.md
   ```

3. Compare it with `source_sha256`.
   - Equal and `index_state` is `fresh`: reuse the map, report `fresh`.
   - `index_state` is `unindexed`, or the digest differs, or the field is not a
     hex digest: rebuild the locator layer, then report `refreshed`.
4. A digest mismatch invalidates every recorded line range. Re-extract
   headings; do not reuse old ranges even when a heading text still exists.

## Rebuild procedure

1. Extract headings and line numbers without reading the body:

   ```sh
   grep -nE '^#{1,6} ' docs/architecture/content_operations_phased_delivery_plan.md
   ```

2. For each topic in the map (and each known query topic that has no entry
   yet), choose the extracted heading whose wording governs it. Use the next
   heading's line number minus one as the section end. If no heading clearly
   governs a topic, record the smallest relevant line range instead of guessing
   a heading.
3. Append or replace only the map rows and the three freshness fields in this
   file. Keep `source_path` unchanged.
4. Set `source_sha256` to the digest from step 2 of the freshness check,
   `refreshed_at_utc` to `date -u +%Y-%m-%dT%H:%M:%SZ`, and `index_state` to
   `fresh`.
5. Read only the matching range, for example
   `sed -n 'START,ENDp' docs/architecture/content_operations_phased_delivery_plan.md`.
   If no topic matches, read the smallest plausible range, answer from it, and
   add the newly discovered topic mapping.

## Topic-to-section map

Schema: `topic | query cues | heading | start_line | end_line | verified_digest`.
The map starts empty by design; runtime extraction fills it.

| topic | query cues | heading | start_line | end_line | verified_digest |
| --- | --- | --- | --- | --- | --- |
| _(none yet — populated by first runtime refresh)_ | | | | | |

Resolve these known query topics on the first refresh, using the document's own
headings:

- Authentication and browser automation ownership.
- MVP content sources.
- RedNote / Xiaohongshu scope.
- Delivery phases and sequencing.
- Owner decisions and MUST requirements.

## Bounded answer contract

Return the source path, the governing heading, its line range, and the
freshness status (`fresh`, `refreshed`, or `source missing`). Paraphrase the
governing rule and cite the section; do not reproduce body text. If the source
is missing or the map cannot locate a governing section, say so and name the
targeted read that would settle it.
