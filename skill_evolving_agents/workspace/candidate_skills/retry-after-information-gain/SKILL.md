---
name: retry-after-information-gain
description: Decide whether another attempt is justified from the last recorded action, observed state, and result, and drive a named CI or merge gate to closure. Use for retry, polling, and search decisions as well as for a gate that stays red after unit and review suites pass, including repeated requests to make CI fully green; classify each distinct failure, fix shared-boundary causes first, and never claim green from a passing subset.
---

# Retry after information gain

## Overview

Own two connected decisions: whether to repeat an action, and whether a named
CI or merge gate is actually closed. For a retry, compare the proposed attempt
with the last recorded action, the state that action observed, and the result
it returned. Repeat only when that comparison shows the outcome can differ;
otherwise change the action or gather new evidence.

For a red gate, turn the gate output into a bounded failure ledger, fix the
cause of each distinct failure at the highest shared boundary, and rerun the
complete gate until it exits zero or an external block is proven with evidence.
The unit of work is the canonical gate, not the last failing test file. A
passing focused suite, a green unit run, or a partially successful E2E scenario
is diagnostic input, never a completion claim.

## When to Use

Use when any one of these is true; each is sufficient on its own:

- A recorded action has already returned a result and the same action is
  proposed again, including a poll, a repeat search, or any other repeat.
- A canonical merge, pre-push, or CI gate exits nonzero after review and unit
  suites pass.
- The last gate stage is production browser E2E and failures repeat across
  attempts or appear only in that stage.
- The user asks to run CI and fix all failures or to make the build fully green,
  even if the request is a first ask that has not been restated.
- A later message restates the same gate failures or pushes back because a prior
  answer admitted the gate was still red.
- Multiple failing checks share a symptom such as missing landmarks, broken
  accessibility semantics, or fixture lifecycle errors, and the caller expects a
  single closure pass.

Apply this skill before any adjacent cleanup, worktree merge, or new invariant
work. If a single failure is already localized by a stack trace to the current
diff, ordinary test-failure debugging is enough.

## Do Not Use

Do not use when any one of these is true:

- The action has not been tried yet. Make the first attempt without this
  decision.
- The next action is already a different method or an already chosen new
  evidence source.
- The problem is a single test failure already localized by a stack trace to
  the current diff.
- The task is workspace-versus-clean-checkout contamination triage alone, a
  first-attempt transport error, or general UI design review.

Do not use it to relabel a still-red gate as done, to convert a subset run into a
green claim, or to start unrelated refactors or coverage work while the gate is
unresolved.

## Prerequisites

Before judging a retry, require all three records from the prior attempt:

- The action that was taken.
- The state that action observed.
- The result that action returned.

If any of the three is missing, do not judge a retry. Record the missing item
and gather it first. Before the first repeat, also require a bounded retry
budget: the maximum number of repeats and the maximum elapsed wait.

## Workflow

1. **Record the baseline before editing.** Capture the exact gate command, the
   working directory, the commit or tree state, the exit code, the failing
   stage, and the first failing assertions. Save enough raw output to re-read
   later; do not paraphrase an error you have not seen.
2. **Build one ledger row per distinct failing check.** Each row records stage,
   check name or scenario, error class, suspected owner, and one classification:
   application defect, stale assertion or fixture, environment or infrastructure,
   or flaky. Merge duplicates that share one root cause; keep separate rows when
   different causes produce similar messages.
3. **Compare the proposed repeat with the recorded triple.** Note whether the
   action, the state, or the result would differ, and whether the result is
   novel. Allow the retry when any one of these is true:
   - A relevant state change has occurred since the prior attempt.
   - The search or scope is meaningfully narrower or otherwise refined.
   - New information is available that the prior attempt did not have.
   - The prior result was a transient failure, and this is still the one allowed
     retry after that failure.
   - A named verification gate the user asked to make fully green still reports
     failures.
   - A poll observed a relevant state change or produced new diagnostic output.
4. **Guard polls and gate reruns against unchanged results.** For a status poll,
   apply only the state-change or new-diagnostic-output condition above; an
   unchanged command-plus-wait pair is not a valid retry even when the budget
   still has room. For a gate rerun, continue only while the failure set shrinks
   or changes for a stated reason. When the same failure recurs with no new
   evidence, do not repeat the command: inspect the artifact or trace, isolate
   the environment, reproduce on a clean checkout, or instrument the failing
   boundary. Count every repeat against the bounded budget and record each
   attempt.
5. **Order fixes by shared boundary.** Address global shell, landmark,
   accessibility, routing, and fixture-lifecycle causes that explain many checks
   before individual stale expectations. A cause that closes several rows is
   worth more than a narrow assertion edit. Confirm a stale assertion against
   current schema, API, or storage behavior before changing it; never edit it to
   match a defect.
6. **Land one scoped fix per cause class.** State which ledger rows each fix is
   expected to close and why. Keep the diff attributable: no drive-by renames, no
   new invariants, no unrelated dependency upgrades.
7. **Rerun the full canonical gate.** Do not run only the focused suite. Diff the
   new failure set against the ledger and mark rows closed only when the rerun
   evidence shows them gone. Continue only while the failure set shrinks or
   changes for a stated reason.
8. **Treat a still-failing named gate as information gain.** When the user asks
   to repair CI or a named verification gate until it is fully green, keep fixing
   the listed failures and rerun that same gate. Do not end the turn on a
   remaining-failure status. Stop the repair-and-rerun loop only when that gate
   passes, or a hard external blocker such as an authorization or access denial
   prevents another run.
9. **Re-query after a contradiction.** When the user reports that the earlier
   negative finding is wrong, or that someone did attempt the flow, treat that
   report as new information and record the contradiction as new evidence.
   Re-query the live signup or auth record and the relevant staging
   configuration, and re-run the smallest discriminating check against both.
   Include timestamp fields that could explain the discrepancy. Respond with
   either the concrete finding and its evidence, or the exact check that blocked
   verification plus the next step.
10. **Terminate at a full-gate exit zero or at a documented external block.** An
    external block names the exact command, error, retry count, and why no
    repository change can resolve it. Anything else remains still red with named
    open rows. When no gate is involved and nothing changed, choose
    `change-action` instead of repeating the attempt.
11. **Emit the decision in the output format,** naming what changed and the
    evidence for it.

## State Machine

- `ready`: a prior action, its observed state, and its result are recorded, and
  a repeat is proposed.
- `retry`: the comparison found a relevant state change, a meaningful scope
  refinement, new information, or the single allowed transient-failure retry.
  Perform that one attempt, then return to `ready` with the new record.
- `stop`: terminal. Enter `stop` when the action, the state, and the result are
  all unchanged. Also enter `stop` when a later attempt returns an unchanged
  result after the one transient-failure retry has already been used. Do not
  leave `stop` by repeating the same triple.

One transient-failure transition may return from `ready` to `retry`. A later
unchanged result is terminal. A named gate is a separate loop: it leaves `retry`
only on a passing full gate or a hard external blocker, never on a
remaining-failure status alone.

## Constraints

- Do not count an identical empty result as progress.
- Do not count an unchanged result as progress.
- Do not keep the same action when result novelty is absent.
- Do not treat a second unchanged result after a transient failure as another
  allowed retry.
- Never claim a fully green build from a subset. Unit, review, and focused E2E
  results may narrow the ledger but cannot satisfy closure.
- Do not weaken, skip, quarantine, or delete an assertion without recording the
  concrete reason and owner. A silenced check is still red.
- Do not mix unrelated pushes, worktree merges, or new coverage invariants into a
  session whose requested outcome is gate closure.
- Keep every fix attributable to ledger rows; unrelated improvements belong in a
  separate change.
- Do not exceed the bounded retry budget for an unchanged failure. Repeating an
  identical command is not new evidence.
- Do not declare an external block while a repository-side cause is still
  plausible or untested. Credential and provider failures need direct evidence.
- Report browser E2E scenarios individually. A scenario that never ran is not
  passed, and a skipped scenario is not green.
- Do not repeat the earlier negative conclusion as the final answer when the
  user has contradicted it. Do not claim that no record exists without
  re-querying the live record and configuration after the contradiction.
- Do not ask the user to reproduce the flow before inspecting the live signup or
  auth record and the relevant staging configuration. If that access fails,
  report the failed check and the blocker instead of guessing a cause.

## Verification

For a retry decision, allow the next attempt only when the record shows one of
these:

- a relevant state change
- information gain
- a meaningful scope refinement
- a transient failure that is still within the one allowed retry

For a status poll, allow only a relevant state change or new diagnostic output,
and confirm that the bounded retry budget has not been exhausted.

An unchanged action-state-result triple must not be retried. Completion evidence
is the written decision: `retry` or `change-action`, the fields that changed, and
the evidence named for that choice.

For gate closure, require all of the following evidence:

- The canonical gate command exited zero on a clean checkout at a named commit,
  **or** an external-block record names the exact command, error, retry count,
  and why no repository change can resolve it.
- Every ledger row is marked closed with the commit or rerun evidence that closed
  it, or is explicitly blocked with its owner.
- Browser E2E scenarios are each reported as passed, fixed, or explicitly
  blocked; none is inferred from a suite-level summary alone.
- Any assertion that was changed or skipped has a recorded reason and owner.
- If the full gate was not rerun, say so explicitly and do not use green
  language anywhere in the report.

After a contradiction, the debug turn is complete only when the user receives a
non-empty response that explicitly addresses the contradiction and cites either
updated record or configuration evidence, or the exact blocker and next action.
A response that repeats the earlier negative conclusion, or that asks the user
to reproduce the flow before the live record was inspected, fails completion.

Confirm the polling guard with two cases before treating the run as complete:

- Positive: a poll returns a changed state or new diagnostic output, so one more
  poll within the remaining budget is permitted.
- Near-miss: an identical command-plus-wait returns unchanged output, so the
  retry loop stops and switches to a different action or evidence source.

## Output Format

State exactly one decision:

- `retry` when a repeat can change the outcome.
- `change-action` when the same attempt must stop.

Name which of `action`, `state`, and `result` changed. Name `none` when all three
are unchanged. Name the evidence that justifies the choice: the state change, the
information gained, the scope refinement, or the still-bounded transient failure.
When the decision is `change-action` because nothing changed, name the unchanged
triple as the evidence.

When a named gate is involved, also report, in this order:

1. **Baseline** — exact gate command, working directory, commit, exit code, and
   failing stage.
2. **Failure ledger** — a table with columns: stage, failing check,
   classification, fix, rerun result.
3. **Closure** — final full-gate exit code and commit, or the external-block
   record.
4. **Verdict** — `green`, `external block`, or `still red` with the remaining
   rows.

State explicitly when the full gate was not rerun. Never substitute a focused
suite result for the final rerun.

## Limitations

This skill does not choose the replacement action. It does not interpret
domain-specific tool output beyond whether the action, the observed state, or the
result changed. It does not decide the first attempt.

Gate closure depends on a reproducible gate command and access to its logs. A
provider or credential failure may be genuinely external; this skill proves and
reports that block rather than forcing a false green. It does not replace deep
product debugging once a ledger row is isolated to a specific function, and it
cannot make an unreproducible or nondeterministic environment deterministic.
