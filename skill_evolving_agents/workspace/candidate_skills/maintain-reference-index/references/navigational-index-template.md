# Navigational index template

Read this file before creating or updating an index. It defines the file shape
only. It is not captured source content: do not copy headings, rules, or prose
from this template into an index, and do not present the field tokens below as
if they came from the source.

## File location and name

Put the index beside the source when that directory is writable, named after the
source, for example `p0_coordination_guide.md.index.md`. Otherwise place it in
the working directory and make the fingerprint's source path absolute. One
source has exactly one index file; the fingerprint and the table must stay in
that same file.

## Required layout

```markdown
# Reference index: {source_path}

## Fingerprint

- source path: {absolute_path}
- size bytes: {byte_count}
- modified: {mtime_iso8601}
- sha256: {hex_digest}
- checked: {check_timestamp_iso8601}

## Index

| Heading | Lines | Locator |
| --- | --- | --- |
| {heading_text} | {start_line}-{end_line} | {short_locator} |
```

## Field rules

- `source_path`: the path exactly as it will be opened later. Prefer absolute.
- `size bytes`: integer from a byte count, not a human-readable size.
- `modified`: source modification time in UTC ISO 8601, to the second.
- `sha256`: 64 lowercase hexadecimal characters from the full file bytes.
- `checked`: UTC ISO 8601 timestamp of the fingerprint computation, not the
  time the index was first written.
- `Heading`: the heading text as written, without the leading `#` characters.
  Preserve its words exactly; do not paraphrase.
- `Lines`: inclusive `start-end` line range of the section, from the heading
  line through the line before the next heading of the same or higher level.
  Use a single line number when the section is empty.
- `Locator`: a few words that help a reader confirm the target, such as the
  parent heading path or one distinctive term from the heading. No sentences,
  no excerpts.

## Ordering and coverage

List rows in document order. Include the document title and every top-level
heading; including deeper headings is allowed when the source is long and the
deeper sections are likely lookup targets. Never merge two headings into one
row. If a heading has no content, still record its line.

## Example shape only

The following row illustrates column usage. Its values are illustrative field
values, not headings from any source:

```markdown
| {heading_text} | 120-168 | {parent} > {heading_text} |
```

Do not ship this illustrative row. Replace every `{}` token with an observed
value from the source.

## Anti-patterns

- A table of contents copied from the source with no line anchors.
- Section summaries, quoted sentences, or decision rules in place of a locator.
- A fingerprint block without a hash, or with a hash left as a token.
- Reusing an old `checked` timestamp after recomputing the hash.
- Storing the index in a different file from its fingerprint.
