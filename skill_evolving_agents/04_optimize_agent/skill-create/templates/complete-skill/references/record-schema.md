# Record schema

Read this reference before accepting input or changing the normalizer.

Each input line is one JSON object with:

- `id`: required non-empty string, preserved exactly.
- `text`: required non-empty string; consecutive whitespace becomes one space.
- `tags`: optional array of strings; blanks are removed, then values are
  deduplicated and sorted.

Each output line contains exactly `id`, `text`, and `tags` in that order. Input
order is preserved. Invalid JSON, an invalid required field, or a non-string
tag causes a nonzero exit with a line-numbered error on standard error.
