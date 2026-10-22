---
name: unchanged-retry-stop
description: "Stop a retry loop when the action, observed state, and result are unchanged. Retry only after a relevant state change, a meaningful search or scope refinement, or a bounded transient failure; otherwise change the action or acquire new evidence."
---

# unchanged-retry-stop

## Overview

This skill owns the decision to stop or continue a retry. Compare the next call with the recorded action, the observed state, and the result already returned. Continue only when that comparison shows new evidence or a bounded transient failure. Stop when the next call would repeat the same action, the same state, and the same result.

## When to Use

Use this skill when a repeated call would use the same action against the same state and the previous result is already known.

A known result for that same action and state is enough to apply the check. A later restatement of the same unchanged triple is also enough. Either case can stand alone.

## Do Not Use

Do not use this skill to block a retry after any one of these:

- A relevant state change means the observed world the action reads is different from the recorded state.
- A meaningful search or scope refinement changes what the action is looking for or the bounds of the search.
- A bounded transient failure is a temporary fault with a finite retry budget, not an identical successful or completed result.
- The named gate the user asked to make green still reports failures. A remaining-failure status is not an unchanged retry and is not a completed stop.

Any one of those is sufficient to allow the retry. Do not require the others to be present. Do not apply an unchanged-retry or turn-complete stop while that named gate still reports failures.

## Workflow

1. Record the prior action, the observed state it ran against, and the result it returned. Keep that record as the comparison baseline.
2. Before the next call, compare its action, state, and expected evidence with that record.
3. Refuse an unchanged repeat that is not a bounded transient failure. Do not issue the call.
4. When the triple matches and the failure is not a bounded transient, change the action or acquire new evidence before any further call.
5. Treat the loop as finished when the next call would not change the evidence. The terminal outcome is stop, with the compared action, state, result, and the reason.
6. A remaining-failure status on a named gate the user asked to make green is not an unchanged retry and is not a turn-complete stop. Continue the repair loop: fix the listed failures and rerun that same gate. End the retry only when that gate passes or a hard external blocker, such as an authorization or access denial, prevents another run.

## Constraints

Keep the check reusable across tools and sessions.

- Do not hard-code a tool name, a session id, a token budget, or constants copied from one trace.
- Compare the action, the observed state, and the result as values. A parameter that does not change the action, the state, or the result does not count as a new attempt.
- A bounded transient retry stays finite and is recorded separately from an unchanged completed result.
- Do not treat a larger output limit, a repeated empty input, or the same completed result as a scope refinement.

## State Machine

States:

- **First attempt.** No prior record exists. Run the action once and store its action, state, and result.
- **Changed-state retry.** The action may repeat only because the observed state differs from the prior record. Store the new triple.
- **Refined-scope retry.** The action or its search bounds meaningfully differ from the prior record. Store the new triple.
- **Bounded transient retry.** The action and state match, and the prior result is a transient failure still inside its finite budget. Record the attempt count.
- **Terminal unchanged-result.** The next call's action, state, and result match the prior record, and the case is not a bounded transient failure.

Transition to **terminal unchanged-result** when the action, state, and result match the prior record. From any non-terminal state, a matching triple ends the loop. A real state change moves to changed-state retry. A meaningful scope change moves to refined-scope retry. A bounded transient failure moves to bounded transient retry until the budget is exhausted, then to terminal unchanged-result if the triple is still unchanged.

## Verification

Accept a stop when the same action, an unchanged state, and an identical result would be repeated.

Accept a retry when any one of these is true:

- The observed state actually changed.
- The search or scope was meaningfully refined.
- The prior result is a bounded transient failure and the retry budget remains.

Reject a stop that fires on a real state change, a scope refinement, or a bounded transient failure. Reject a retry whose action, state, and result all match the prior record.

## Output Format

Record one decision object:

- `decision`: `stop` or `retry`.
- `action`: the action compared with the prior record.
- `state`: the observed state compared with the prior record.
- `result`: the prior result compared with what the next call would repeat.
- `reason`: why the loop ended or continued, naming the state-machine state that was reached.
- `next_step`: on `stop`, change the action or acquire new evidence; on `retry`, the allowed change (state, scope, or remaining transient budget).

## Limitations

The check does not judge whether the first action was the right one. It does not replace evidence gathering after a real state change. It does not decide that a refined search is sufficient, only that a refined search may be tried. Promotion stays provisional until at least two held-out cases pass and the exit check does not fire on a real state change, a scope refinement, or a bounded transient failure.
