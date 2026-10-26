---
name: operations-quality-reference
description: Record and consult a durable section-level reference for owner/docs/operations/engineering_quality_and_delivery.md instead of re-reading the whole document. Use before merge-gate, CI (including ci:merge), resource-lease, Playwright browser-gate, infrastructure-test, or delivery-checklist work, and whenever a prior turn already read the document and the current step needs the same rule.
---

# Operations quality reference

## Overview

Own the durable navigational record for the repository operations quality and
delivery document. The record lives at
`references/operations/engineering_quality_and_delivery.md`. It stores the
source path, the condition that warrants consulting it, a topic-to-heading map,
a content digest, and the refresh rule.

Use it to jump straight to the governing section instead of re-reading
`owner/docs/operations/engineering_quality_and_delivery.md` from the top on
every delivery or quality task.

## When to Use

Any one of these is sufficient; a later restatement is not required.

- Before a merge gate, a CI run such as `ci:merge`, or a required-check
  decision whose rules live in the operations quality document.
- Before acquiring, renewing, or releasing a resource lease, or before
  diagnosing a lease conflict.
- Before a Playwright browser gate, an infrastructure test, or a delivery
  checklist.
- When a previous turn already read the document and the current step needs
  the same rule; consult the record instead of reading the whole file again.
- When a result depends on the document's exact pass/fail condition, command,
  lease scope, or delivery evidence.

## Do Not Use

- Do not use for unrelated documentation reading such as README summaries,
  product docs, API guides, or onboarding material.
- Do not use when the user already answered the question or supplied the
  governing rule in the current conversation.
- Do not use for work outside delivery and quality scope, including ordinary
  feature implementation with no gate, lease, or delivery decision.
- Do not use it as a substitute for running the canonical gate command and
  observing its output.

## Workflow

1. Open `references/operations/engineering_quality_and_delivery.md` and read
   its source path, digest status, and section map.
2. Identify the rule area for the current task (quality gate, CI or merge
   gate, resource lease, Playwright gate, infrastructure test, or delivery
   checklist) and note the mapped heading keywords before touching the source.
3. Check the digest against
   `owner/docs/operations/engineering_quality_and_delivery.md` with the command
   in the record. A hash check is cheap and does not require reading the file.
4. If the digest matches, read only the mapped section: locate the heading with
   a heading-only search, then read from that heading to the next heading of the
   same or higher level.
5. If the digest is missing or differs, re-scan the source headings, read only
   the needed section, and refresh the record's heading text, section map, and
   digest. Keep the recorded fields bounded.
6. Cite the source path and the consulted heading, apply the rule, then perform
   the delivery action or gate command. Never infer the gate result from the
   record.

## Constraints

- Never claim a gate, test, or delivery result from the reference alone; only
  observed command output establishes a result.
- Keep the record bounded to the source path, read-when condition, section map,
  digest, and refresh rule. Do not paste whole sections, volatile command
  output, credentials, or secrets into it.
- Do not silently cite an unconfirmed heading. Heading names in the map are
  topic matches until the first source scan confirms the literal title.
- Do not edit the source document while consulting it, and do not edit the
  skill changelog or repository metadata.
- Keep the source path repository-relative so the record survives checkout
  moves.

## Verification

Before acting on a recorded rule, confirm all of the following:

- The relevant source section was identified by its literal heading, not by
  memory or a keyword guess.
- The recorded digest matches the file on disk, or the record was refreshed in
  this turn and now matches.
- The action cites that heading and applies the recorded rule rather than
  relying on a fresh whole-file read.
- If the source path is absent or unreadable, report that fact and fall back to
  the canonical command; do not fabricate a digest or heading.

## Output Format

Report four short fields and then the action:

- `source`: repository-relative path of the document.
- `section`: literal heading consulted, with its level.
- `digest`: `match`, `refreshed`, or `unavailable`.
- `rule`: the pass/fail condition, command, lease term, or checklist item
  applied.

## Limitations

This reference is a navigational cache, not an authority. It cannot cover edits
made to the source after its digest, delivery policies that live outside the
repository, or live CI state and queue conditions. When the document and the
record disagree, the document wins and the record must be refreshed.
