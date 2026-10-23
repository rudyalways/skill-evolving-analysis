---
name: retry-guard
description: Decide whether a repeated tool action is justified. Use before repeating a tool call, poll, or search whose previous result is already known. Allow a repeat only after relevant state changed, a search or scope change produced new information, or a single bounded transient failure; otherwise change the action or gather different evidence.
---

## Overview

This skill is the retry gate for a repeated tool action. The same action is allowed only when something that can change the outcome has happened: relevant state changed, a search or scope change produced new information, or this is the single allowed retry of a bounded transient failure. If the action, the state that matters, and the result would stay the same, replace the action or gather different evidence.

The gate judges only the next attempt. It is a reusable method for that decision.

## When to Use

Use this skill before repeating a tool action whose previous result is already known. Any one of these is enough:

- The next step would repeat a tool call that already returned.
- The next step would poll again for that same known result.
- The next step would run the same search again.

A later restatement of the same plan is not required. The first recognition is enough.

## Do Not Use

Do not use this skill in either of these situations. Each one is enough on its own:

- The call is a first attempt and has no previous completed result.
- The next action is already a different command, a different query, or a different evidence source.

## Workflow

Compare the proposed repeat with the last completed attempt before issuing it.

1. Name the proposed action, the state that action depends on, and the previous result.
2. Proceed with one repeat only if one of these gates holds:
   - Relevant state changed since the last attempt.
   - A search or scope change produced information the last attempt did not have.
   - The last result was a bounded transient failure, and that failure has not already been retried once.
3. Otherwise replace the action or gather different evidence. Stop when a repeat would leave the action, the state, and the result unchanged.
4. Treat a deprecation or migration warning as an instruction for the next attempt. When a status command emits a warning that names a replacement, use the named replacement on the next call and do not invoke the deprecated form again.
5. Re-poll a long-running deployment only after a bounded wait or a state-changing action. If two consecutive polls return the same non-terminal state, stop polling and inspect the build or deploy logs. Resume status checks only after a new event or state transition.
6. On a failed push or deploy step, classify the failure before deciding to stop. A transport error, meaning a nonzero exit with a connectivity or empty-reply signature, is not a build failure. When the local tree is verified deployable, deploy directly from that tree, assert the live artifact exposes the intended behavior, and retry the original push once connectivity returns.

## State Machine

- **first attempt.** No previous completed result. Issue the call. This is not a repeat.
- **justified repeat.** Enter from a relevant state change, from a novel search or scope result, or from one transient failure that has not already been retried. Issue one repeat, then compare again.
- **terminal stop.** Enter when the proposed action, the state that matters, and the result match the previous attempt. Do not return to the same call. The next step is a different action or different evidence.

## Constraints

- When a tool result names a deprecated invocation and its replacement, the next attempt must use the recommended invocation instead of repeating the deprecated one.
- Do not issue repeated sleep-and-status cycles that produce no new state. Do not treat identical BUILDING/SUCCESS output as progress. Cap unchanged polls at two, then switch to a different diagnostic action or report the concrete blocker.
- Do not treat an argument that does not affect the outcome as a new attempt. A parameter tweak that leaves the action, the relevant state, and the result the same is still the same attempt.
- Cap transient retries at one. A second identical transient failure is an unchanged result.
- On an unreachable push remote, do not report the change as failed, do not abandon the push permanently, and do not retry the same remote command repeatedly without new connectivity evidence.
- Do not copy trace-specific commands, token limits, or event ids into the rule. Those details do not decide whether a repeat is allowed.

## Verification

Accept a repeat only with one of these records:

- a recorded state change that can affect the call
- result novelty from a search or scope change
- one transient error that has not already been retried

Reject a repeat whose action, state, and result match the previous attempt, including a parameter tweak that does not change the outcome.

The guard passes only when later output no longer repeats the deprecation warning. After a deprecation warning, accept the sequence only when the next call uses the named replacement.

Confirm the revised guidance by replaying a deployment poll in which status returns a deprecation warning and two identical non-terminal states. The agent must switch to the named replacement and pivot to build or deploy logs instead of polling a third time.

Confirm a transport failure with a connectivity probe, confirm the live artifact after the direct deploy, and confirm the original push succeeds on retry.

## Output Format

Record the decision with these fields:

- **decision:** `repeat` or `replace`
- **gate:** `state change`, `new information`, `transient failure`, or `none`
- **evidence:** the recorded state change, the new information, or the transient failure; `none` when the decision is `replace`

## Limitations

The gate judges the next attempt. It does not choose a replacement strategy beyond gathering different evidence, and it does not score domain correctness of a successful result.
