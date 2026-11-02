# Lark doc documentation index

This is a navigational index for the lark-doc skill documentation. It records where the source lives, which file covers which task, how freshness is checked, and when to read it. It deliberately contains no source headings, excerpts, or documentation content.

## Source locator

- Skill: `lark-doc`
- Source entry file: `doc/skill.md`, relative to the lark-doc skill root.
- Root resolution: use the skill root returned by the normal skill loader and expose it as `LARK_DOC_ROOT`. Never hardcode a machine path.
- Documentation tree: `"$LARK_DOC_ROOT/doc"`.

## Recorded source digest

| Field | Value |
| --- | --- |
| Algorithm | SHA-256 |
| Covered file | `doc/skill.md` |
| Recorded digest | Not captured. The authoring session could not read the source or its digest, so no hash is asserted here. |
| Status | Unrecorded, which is a mandatory rebuild trigger on first use. |

Do not treat the status above as a verified digest. On first use, compute the digest, rebuild the map, and replace this row in the same pass.

## Freshness rule

1. Compute `shasum -a 256 "$LARK_DOC_ROOT/doc/skill.md"` (fall back to `sha256sum` only if needed).
2. If the result is 64 hexadecimal characters and equals the recorded digest, the index is fresh.
3. If the recorded digest is unrecorded, differs, is malformed, or the source file is missing, the index is not fresh. Rebuild the map before any lookup.
4. Rebuild by enumerating the documentation tree:

   ```bash
   find "$LARK_DOC_ROOT/doc" -type f -name '*.md' | sort
   ```

   For each relative path, keep one row. Derive its topic label from the path segments (for example, a path about reading maps to a read topic). Do not open or quote the file's headings or body to build a label. Record the new digest with the rebuilt map.
5. If hashing or enumeration fails, stop and fall back to the lark-doc skill without asserting freshness.

## File-level topic map

Rows are added or replaced only after the path is confirmed during a fresh rebuild. The seed row is the entry file; topic files are enumerated at refresh so no invented path enters the map.

| Source file (relative to `LARK_DOC_ROOT`) | Topic label | Read when |
| --- | --- | --- |
| `doc/skill.md` | Entry and routing | First lookup, or when no topic-file row matches the request. Read once, then add any missing row. |
| `doc/*.md` and descendant topic files, enumerated at refresh | Path-derived task label | Only when the request's operation matches that label. Never preload the whole tree. |

## Read-when condition

Read this index immediately before the conditional lark-doc workflow that would otherwise reopen `doc/skill.md` or several reference files. A first lark-doc request and a later restatement of the same request each trigger this lookup on their own; no prior turn or restatement is required.
