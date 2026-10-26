# Operations quality and delivery reference

Navigational record for the repository document that governs delivery and
quality work. This file is a pointer and index, not a copy of the document.

## Source

- Repository-relative path: `owner/docs/operations/engineering_quality_and_delivery.md`
- Authority: the source document. This record only tells a reader where to look.
- Read when: a task must satisfy a merge gate, run CI (including `ci:merge`),
  take or release a resource lease, pass a Playwright browser gate, run an
  infrastructure test, or complete a delivery checklist; also read it when an
  earlier turn used the document and the current step needs the same rule.

## Content digest

- Algorithm: SHA-256 over the raw source bytes.
- Recorded value: not yet captured in this snapshot; the source was not read
  when this record was authored.
- Capture or check (run from the repository root, no file read needed):

  ```bash
  shasum -a 256 owner/docs/operations/engineering_quality_and_delivery.md
  # fallback: sha256sum ...  or  openssl dgst -sha256 ...
  ```

- Status: unverified until the first consultation records the 64-character hex
  value here.

## Section map

Use the search terms to find the heading, then read only from that heading to
the next heading of the same or higher level. Heading titles below are topic
matches, not verified literal titles.

| Rule area | Heading search terms | Read it when | Extract |
| --- | --- | --- | --- |
| Quality gates and definition of done | quality, gate, definition of done, acceptance | planning or checking whether delivery is acceptable | Required checks, pass/fail conditions, evidence to retain |
| CI and merge gate | CI, merge, pipeline, `ci:merge`, required check | running or interpreting CI, especially the merge gate | Exact command, ordering, required jobs, failure handling |
| Resource leases | lease, resource, lock, quota, acquire, release | before taking, renewing, or releasing shared resources | Lease scope, duration or TTL, owner, cleanup and conflict rules |
| Playwright and browser gates | Playwright, browser, e2e, end-to-end | running a browser-based gate | Browser install prerequisites, command, retry and artifact rules |
| Infrastructure tests | infrastructure, infra, integration test, environment | running or repairing an infrastructure test | Environment prerequisites, command, teardown, allowed exceptions |
| Delivery checklist | delivery, release, checklist, ship, handoff | before declaring delivery complete | Ordered checklist items and the evidence each requires |

## Heading discovery

Scan headings only; do not read the body just to find a section:

```bash
grep -n '^#' owner/docs/operations/engineering_quality_and_delivery.md
```

Match the search terms above against that heading list. If several headings
match, prefer the one whose surrounding parent heading matches the rule area.
If none match, read the two nearest candidate sections and record the literal
heading in the map.

## Refresh rule

1. Check the digest before citing a section whenever the source may have
   changed; a hash check is cheap and avoids a full read.
2. If the digest differs, or the recorded heading no longer exists, re-scan the
   headings, re-read only the affected section, and update the section map,
   digest, and refresh date in this record.
3. If the source is missing or unreadable, mark the digest unavailable and
   report it; do not cite a rule from memory.
4. Never copy section bodies, credentials, volatile command output, or live CI
   status into this record. Keep it to path, read-when condition, section map,
   digest, and refresh rule.
