---
name: scheduled-monitoring-automation
description: Create and verify a durable scheduled monitoring automation from a bounded recurring request, resolving cadence and an absolute deadline into one RFC 5545 rule string, creating it in ACTIVE status, and reading the persisted schedule back. Use when someone asks to monitor, check, or report every N minutes or hours until a named time, requests a heartbeat or recurring task, or asks for a scheduled automation that must stop at a deadline.
license: MIT
---

## Overview

Own the conversion of a request to monitor something repeatedly for a limited
period into a durable scheduled automation, and the confirmation that the
persisted schedule matches the request. This skill covers deadline and cadence
resolution, recurrence encoding, creation, and post-create verification. It
does not cover deciding whether an already running operation should be polled
again.

## When to Use

Use when any one of the following holds:

- A request asks to monitor, check, or report on something every N minutes or
  hours until a named time.
- A request asks for a heartbeat, a recurring task, or a scheduled automation
  that must stop at a deadline.
- A later message restates or schedules an earlier monitoring request. A
  restatement is sufficient on its own; do not require the original wording,
  a fresh justification, or a second confirmation before acting.
- The request names both a repeat interval and a stopping point, so a single
  one-off check would miss the intent.

## Do Not Use

Do not use for:

- A single status check, or a one-off poll of an operation.
- Deciding whether to repeat a wait or poll on an already running operation.
- An open-ended recurring task with no deadline or stopping condition.
- One-off scheduled jobs that need no recurring-rule verification.
- Unbounded "just keep checking" requests; ask for or infer a stopping point
  first, and if none can be established, do not create a durable automation.

## Workflow

1. Resolve the intent from the request before touching the API. Record the
   monitored subject and scope, the cadence (for example every 15 minutes), the
   intended start time, the deadline or stopping condition, and the timezone.
2. Convert the deadline to an absolute UTC timestamp. Preserve the user's
   timezone intent when doing the conversion; do not silently treat a local
   wall-clock deadline as UTC.
3. Encode the cadence and the absolute deadline as exactly one bounded RFC 5545
   rule string, for example
   `FREQ=MINUTELY;INTERVAL=15;UNTIL=20261028T061500Z`. The rule must carry the
   frequency, the interval, and an absolute `UNTIL`; do not emit two rules, an
   unbounded rule, or a relative end such as a count that does not express the
   named deadline.
4. Create the automation in ACTIVE status with a prompt that names the
   monitored scope, the actions the runs may take, and the final stop-and-report
   step. The prompt must stand on its own: a stored schedule does not carry the
   reasoning for what each run may do.
5. Send the recurrence as a string. If the host accepts object-shaped rules,
   still pass the string form.
6. Re-read the persisted automation configuration. Compare the stored status,
   the stored rule, and the stored prompt against the resolved intent.
7. Correct any mismatch: rewrite the rule or reactivate the automation, then
   read it back again and report the corrected persisted values.

## Constraints

- Send `rrule` as a string, never as an object, even if the host's examples
  show a structured shape.
- Keep exactly one bounded rule per automation with an absolute `UNTIL`
  timestamp. Do not use relative, open-ended, or count-based recurrences in
  place of the named deadline.
- Preserve the user's timezone intent when converting the deadline to UTC.
- Keep the monitor read-only or within explicitly allowed in-scope actions.
- Never widen the automation to production promotion, deployment, or other
  state-changing operations without separate approval.
- Do not report success from a create or update response alone; the persisted
  record is the evidence.
- Do not create an automation with no stopping condition.

## Verification

Do not treat a create or update response as proof of the schedule. Before
completing:

1. Read back the persisted automation record by its id or name.
2. Confirm the persisted status is ACTIVE.
3. Confirm the stored `rrule` contains the intended frequency, the intended
   interval, and the intended absolute `UNTIL` value.
4. Confirm the stored prompt includes the terminal stop-and-report
   instruction and the monitored scope.
5. Report those observed stored values as the verification evidence, not a
   paraphrase of the request.

If a read-back is unavailable, say so explicitly and treat the schedule as
unverified rather than claiming success. Use `evals/evals.json` as the
behavioral fixture for the positive and near-miss boundaries.

## Output Format

Report, at minimum:

- The automation name or id.
- The persisted `rrule` verbatim, as read back.
- The resolved deadline with its timezone, plus the UTC value used in `UNTIL`.
- The persisted status.
- A short statement of the read-back check that confirmed the schedule.
- Any discrepancy that was corrected before completion, naming the original
  and corrected stored values.

## Limitations

The automation API's accepted recurrence syntax and persistence format are
host-specific, so the exact rule grammar and read-back path must be confirmed
against the host rather than assumed. Some hosts return a normalized rule, so
compare semantics (frequency, interval, deadline) as well as the literal
string. Schedule storage cannot guarantee that later runs act correctly, so
the prompt must still carry its own scope and stop condition. This skill does
not decide whether an already running operation should be polled again.
