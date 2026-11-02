# Fingerprint freshness check

Read this file before computing a fingerprint, comparing one, or re-indexing a
changed source. The check runs on demand at lookup time; there is no watcher.

## Compute the four inputs

Run these commands with the real source path. The hash reads file bytes but does
not put the document text into the conversation context.

```bash
src="/absolute/path/to/guide.md"
wc -c < "$src"
date -u -r "$src" +%Y-%m-%dT%H:%M:%SZ
shasum -a 256 "$src"        # macOS and systems with Perl shasum
# sha256sum "$src"          # GNU coreutils alternative
date -u +%Y-%m-%dT%H:%M:%SZ
```

`wc -c` yields the byte size. `date -r` formats the file's modification time.
The hash command yields the SHA-256 digest. The final `date` is the check
timestamp recorded in the index.

If `shasum` and `sha256sum` are both unavailable, compute the digest with a
short one-off Python invocation and take the `hexdigest()` value; do not store
an unverified or truncated digest.

## Compare before consulting

Read the stored fingerprint block, then compare in this order:

1. **Path** differs: treat the index as belonging to another source. Do not use
   it; build a new index.
2. **Size, modification time, and hash** all match: the index is fresh. Consult
   the table and open only the located line range.
3. **Any of size, modification time, or hash** differs: the index is stale. Do
   not answer from it. Re-index the affected sections, update the table, and
   rewrite the fingerprint block with the new values and a new check timestamp.
4. **Hash missing or malformed**: treat the index as unverified and rebuild the
   fingerprint. Never leave a placeholder digest in place.

The hash is required even when size and modification time are unchanged. A file
can be edited within the same timestamp granularity while keeping the same size,
and only the hash detects that case.

## Re-index a changed source

Prefer a bounded repair over a full rebuild:

1. Re-enumerate headings with `grep -n '^#\{1,6\} ' "$src"` or an equivalent
   line-oriented scan. Compare the heading sequence with the existing table to
   find inserted, removed, renamed, and moved sections.
2. If an earlier copy of the source is still available, diff it against the
   current source to locate the changed line region. Re-index headings whose
   line ranges overlap or follow that region, because later anchors shift.
3. Update the affected rows and every row whose line range shifted. Leave
   unaffected rows and locators unchanged.
4. If the changed region or the previous copy cannot be determined cheaply,
   rebuild the whole table from the current source. A correct rebuild is
   preferable to guessing which rows are still valid.
5. Rewrite the fingerprint block from the values just computed. The stored
   `checked` timestamp must be the time of this check.

## Cost and bounds

Hashing is linear in file size but consumes I/O, not context tokens. Do not
replace it with a metadata-only check, and do not add a background process,
file watcher, or polling loop to avoid it. For very large sources, hash at
lookup time only, and cache nothing beyond the index file itself.

If the file is unreadable, the hash command fails, or the path is not a regular
file, stop and report that freshness cannot be established. Do not consult the
index as a fallback.
