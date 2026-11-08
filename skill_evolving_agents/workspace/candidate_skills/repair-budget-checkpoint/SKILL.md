---
name: repair-budget-checkpoint
description: Checkpoint a long repair or iterative debugging loop against its remaining wall-clock or tool-call budget, emit every required artifact before exploring further, and reserve a final interval for deterministic verification so budget exhaustion never leaves an incomplete deliverable.
---

# Repair budget checkpoint

## Overview

Iterative repair loops can consume the entire execution window on diagnosis,
retries, and exploration, leaving no verifiable deliverable. This skill adds an
explicit budget checkpoint and an artifact-first completion path to any repair
workflow. It does not decide what to repair: the domain method, such as
`geometric-layout-repair` when that skill is available, still chooses the
changes. This skill decides when to stop exploring, which artifact to write
next, and what to verify with the budget that remains.

## When to Use

Use when any one of these conditions holds:

- The task has a wall-clock deadline or a tool-call, turn, or iteration limit.
- The task requires more than one output artifact, such as a repaired file plus
  a report, log, or summary.
- The work involves repeated diagnosis and repair rather than a single edit.
- A prior run on the same task ended with budget exhaustion, a truncated
  verification, or missing artifacts.
- The task mixes open-ended exploration with a contract that must be satisfied.

Any single condition above is sufficient; the conditions are alternatives, not
a checklist that must all be true.

## Do Not Use

- Do not use for a short single-step task that fits comfortably in one pass.
- Do not use for a task with no required artifacts or acceptance checks.
- Do not use as a replacement for the domain repair method. This skill does not
  diagnose layouts, code, data, or content; it only manages budget and artifact
  completion.
- Do not use to justify stopping early on a task whose artifacts are still
  demonstrably wrong.

## Workflow

1. **Record the budget before touching the problem.** Write down the total
   allowance (wall-clock minutes or tool calls), the amount already consumed,
   and the estimated cost of one full verification pass. Mark the final-check
   interval: the last portion of the budget reserved solely for verification
   and artifact completion.
2. **Enumerate every required artifact.** List each file, field, or output the
   task contract demands, and mark whether it currently exists and parses.
   This list is the completion definition; nothing optional belongs on it.
3. **Emit artifacts early.** As soon as an artifact's content is coherent,
   write it. A complete draft that can be checked beats an improved draft that
   may never be written. Do not wait for the loop to converge before producing
   the first full version of each artifact.
4. **Checkpoint before every repair iteration.** Compare elapsed time or tool
   calls against the reserve boundary. If the reserve is reached, stop
   exploration immediately and go to step 6 with the best current artifacts.
   Otherwise continue with the next repaired defect only.
5. **Repair one concrete defect at a time.** Read the latest verification
   output, pick the first specific contract defect it shows, change only what
   addresses that defect, and re-run that same check. Do not start a second
   speculative improvement in the same iteration. Do not re-run an unchanged
   read or check.
6. **Spend the reserve on completeness and consistency.** During the reserved
   interval, write any missing artifact, make every artifact parse, check that
   names, counts, and cross-references agree, and run the deterministic check
   once. Do not spend reserve time on optional previews, refactors, or
   speculative cleanup.
7. **Record the checkpoint state.** Note remaining budget, artifacts written,
   the latest verified defect and whether it is fixed, and the next concrete
   defect. Report this in progress updates, not in the user-facing deliverable.
8. **Report honestly at the boundary.** If the reserve ends with an artifact
   still missing or a named defect still unfixed, say exactly which artifact
   or defect is incomplete and what was verified. A budget stop is not a
   compliant result.

## Constraints

- Never spend remaining budget on optional previews, cosmetic polish, or
  speculative cleanup before all required artifacts exist.
- Do not repeat an unchanged read, command, or check merely to fill time or
  confirm a result already observed.
- Do not claim completion from an unchanged or truncated result. Completion
  needs the latest check output, not an earlier one.
- A budget checkpoint must preserve correctness: the checkpoint stops
  exploration, not required verification or required artifact writing.
- Treat each iteration as one named defect. If no new defect is named, stop
  editing rather than making open-ended improvements.
- Keep the artifact list and checkpoint record in working notes or progress
  reporting; do not add them to a deliverable unless the task asks for them.
- When time is unavailable, use tool-call count as the budget proxy and state
  that substitution in the checkpoint record.

## Verification

Before claiming completion, confirm all of the following from the latest run:

1. Every required artifact exists at its required path and parses.
2. The latest deterministic check was executed after the final edit and shows
   the named defect fixed.
3. A recorded checkpoint states the remaining budget, artifacts written, and
   the next concrete defect or "none".
4. The reserved final-check interval was used for completeness and consistency:
   names, counts, and cross-references agree across artifacts.

If any item fails, report the incomplete artifact or unfixed defect explicitly
instead of reporting success. Do not substitute structural presence of files
for passing verification output.

## Output Format

Produce the artifacts the task contract names. In addition, maintain a compact
checkpoint record with these fields:

```
budget_total: <minutes or tool calls>
budget_remaining: <amount>
artifacts_written: <relative paths>
latest_verified_defect: <named defect and fixed/not fixed>
next_concrete_defect: <defect or none>
final_check_reserve: <amount reserved for verification>
```

Include this record in progress reporting or working notes. Do not paste it
into the user deliverable unless the task explicitly requests it.

## Limitations

- Wall-clock estimates are approximate; when a clock is unavailable, tool-call
  count is only a proxy for effort.
- The checkpoint does not replace domain correctness or a full verifier run; it
  only protects time and completion.
- A budget stop with missing artifacts or an unfixed named defect is not a
  compliant result, even when the checkpoint record is complete.
- This skill cannot recover work already lost to an earlier overrun; its value
  depends on taking the first checkpoint seriously.
