---
name: retry-after-information-gain
description: Decide whether another attempt is justified from the last recorded action, observed state, and result. Use after a recorded action returned a result and another attempt is being considered, including polling and search.
---

# retry-after-information-gain

## Overview

Own the decision to repeat an action only when the repetition can change the outcome. Compare the proposed attempt with the last recorded action, the state that action observed, and the result it returned. Allow a retry when that comparison shows the outcome can differ. Otherwise stop the same attempt and change the action or gather new evidence.

## When to Use

Use this skill when another attempt is being considered after a recorded action has already returned a result. Any one of these situations is enough:

- The same action may be polled again.
- The same search may be run again.
- A repeat is proposed for any other recorded action that already has a result.

## Do Not Use

Do not use this skill in any one of these situations:

- The action has not been tried yet. Make the first attempt without this decision.
- The next action is already a different method.
- The next action is already a new evidence source.

## Prerequisites

Before judging a retry, require all three records from the prior attempt:

- The action that was taken.
- The state that action observed.
- The result that action returned.

If any of the three is missing, do not judge a retry. Record the missing item and gather it first.

## Workflow

1. Read the proposed attempt and the recorded prior action, observed state, and result.
2. Compare the proposed attempt with that record. Note whether the action, the state, or the result would differ, and whether the result is novel.
3. When the user reports that the earlier negative finding is wrong, or that someone did attempt the flow, treat that report as new information and record the contradiction as new evidence. Re-query the live signup or auth record and the relevant staging configuration, and re-run the smallest discriminating check against both. Include timestamp fields that could explain the discrepancy. Respond with either the concrete finding and its evidence, or the exact check that blocked verification plus the next step.
4. Guard any status poll before repeating it: compare the latest result with the result before it. Retry only when the observable state changed or the latest output contains new diagnostic information. Otherwise stop polling and switch to a different action or evidence source.
5. Before the first repeat, state a bounded retry budget: the maximum number of repeats and the maximum elapsed wait. Count every repeat against it, and on exhaustion report the last observed state instead of polling again.
6. When the user asks to repair CI or a named verification gate until it is fully green, treat a still-failing named gate as information gain. Keep fixing the listed failures and rerun that same gate. Do not end the turn on a remaining-failure status.
7. Allow the retry when any one of these is true:
   - A relevant state change has occurred since the prior attempt.
   - The search or scope is meaningfully narrower or otherwise refined.
   - New information is available that the prior attempt did not have.
   - The prior result was a transient failure, and this is still the one allowed retry after that failure.
   - A named verification gate the user asked to make fully green still reports failures.
   - A poll observed a relevant state change or produced new diagnostic output.
8. For a status poll, apply only the state-change or new-diagnostic-output condition from the list above. An unchanged command-plus-wait pair is not a valid retry even when the budget still has room.
9. Otherwise do not repeat the attempt. Choose `change-action`: use a different method or gather new evidence.
10. Stop the named-gate repair-and-rerun loop only when that gate passes, or a hard external blocker such as an authorization or access denial prevents another run. A remaining-failure status is not a stop.
11. Emit the decision in the output format, naming what changed and the evidence for it.

## State Machine

- `ready`: a prior action, its observed state, and its result are recorded, and a repeat is proposed.
- `retry`: the comparison found a relevant state change, a meaningful scope refinement, new information, or the single allowed transient-failure retry. Perform that one attempt, then return to `ready` with the new record.
- `stop`: terminal. Enter `stop` when the action, the state, and the result are all unchanged. Also enter `stop` when a later attempt returns an unchanged result after the one transient-failure retry has already been used. Do not leave `stop` by repeating the same triple.

One transient-failure transition may return from `ready` to `retry`. A later unchanged result is terminal.

## Constraints

- Do not count an identical empty result as progress.
- Do not count an unchanged result as progress.
- Do not keep the same action when result novelty is absent.
- Do not treat a second unchanged result after a transient failure as another allowed retry.
- A state change, a narrower search, new information, or one bounded transient failure remains a valid reason to retry.
- Stop a named-gate repair loop only when that gate passes or a hard external blocker, such as an authorization or access denial, prevents another run. A still-failing named gate is information gain that requires another repair and rerun of that same gate.
- Do not repeat the earlier negative conclusion as the final answer when the user has contradicted it. Do not claim that no record exists without re-querying the live record and configuration after the contradiction.
- Do not ask the user to reproduce the flow before inspecting the live signup or auth record and the relevant staging configuration. If that access fails, report the failed check and the blocker instead of guessing a cause.
- Require a bounded retry budget before the first repeat, and forbid repeating an identical command-plus-wait pair whose result is unchanged. On exhaustion, report the last observed state instead of polling again.

## Verification

Allow the next attempt only when the record shows one of these:

- a relevant state change
- information gain
- a meaningful scope refinement
- a transient failure that is still within the one allowed retry

For a status poll, allow only a relevant state change or new diagnostic output, and confirm that the bounded retry budget has not been exhausted.

An unchanged action-state-result triple must not be retried. Completion evidence is the written decision: `retry` or `change-action`, the fields that changed, and the evidence named for that choice.

After a contradiction, the debug turn is complete only when the user receives a non-empty response that explicitly addresses the contradiction and cites either updated record or configuration evidence, or the exact blocker and next action. A response that repeats the earlier negative conclusion, or that asks the user to reproduce the flow before the live record was inspected, fails completion.

Confirm the polling guard with two cases before treating the run as complete:

- Positive: a poll returns a changed state or new diagnostic output, so one more poll within the remaining budget is permitted.
- Near-miss: an identical command-plus-wait returns unchanged output, so the retry loop stops and switches to a different action or evidence source.

## Output Format

State exactly one decision:

- `retry` when a repeat can change the outcome.
- `change-action` when the same attempt must stop.

Name which of `action`, `state`, and `result` changed. Name `none` when all three are unchanged. Name the evidence that justifies the choice: the state change, the information gained, the scope refinement, or the still-bounded transient failure. When the decision is `change-action` because nothing changed, name the unchanged triple as the evidence.

## Limitations

This skill does not choose the replacement action. It does not interpret domain-specific tool output beyond whether the action, the observed state, or the result changed. It does not decide the first attempt.
