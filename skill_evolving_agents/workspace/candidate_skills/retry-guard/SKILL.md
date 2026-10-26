---
name: retry-guard
description: Decide whether to repeat a tool action, poll, or wait, and bound the watching of asynchronous builds, deployments, migrations, jobs, and persistent interactive sessions through terminal states, deadlines, unchanged-observation bounds, liveness checks, and diagnostic-log escalation.
---

## Overview

This skill owns two linked decisions. The retry gate compares a proposed repeat with the last completed attempt and permits it only when something that can change the outcome has happened. The bounded watch applies the same discipline over time: name the terminal values and the bounds before the first observation, compare each observation with the previous one, and route a stalled operation to logs and liveness evidence instead of another copy of the same status line.

The combined method prevents both failure modes: an identical retry after an unchanged result, and an unbounded poll loop that keeps re-reading a non-terminal status. It judges the next attempt and the next observation, not the domain correctness of a successful build or the system's own retry policy. Deprecation-guided replacement, transport-versus-build classification, named-gate repair, deadline handling, and interactive-session supervision all use these same rules.

## When to Use

Use this skill before repeating a tool action whose previous result is already known, or when an asynchronous operation must reach a terminal state before dependent work can continue. Any one of these is enough, and a later restatement of the same plan is not required:

- The next step would repeat a tool call, poll, or search that already returned.
- An unchanged action, state, and result triple might justify ending the loop.
- The operation does not return its result in a single call, so completion must be observed over time.
- A status check has already been repeated with the same result and the next step is still unclear. That repetition is itself a reason to switch to the bounded watch; it is not an additional prerequisite.
- The watched target is a build, deployment, migration, job, pipeline run, release gate, or persistent interactive session with a status command, API, status resource, or attached terminal.
- A status command returned a deprecation or migration warning that names a replacement.
- A push or deploy step failed and the failure must be classified before deciding whether to retry.
- A retry, rollback, or handoff decision depends on whether the operation actually advanced since the last check.
- A named gate the user asked to make green still reports failures.
- A previous attempt overran its expected duration and the agent is tempted to "just check once more."

## Do Not Use

Do not gate the call in any of these retry situations. Each one is enough on its own:

- The call is a first attempt and has no previous completed result; issue it and record the baseline.
- The next action is already a different command, a different query, or a different evidence source.
- A relevant state change means the world the action reads is different from the recorded state.
- A meaningful search or scope refinement changes what the action looks for or the bounds of the search.
- A bounded transient failure still has retry budget and is not an identical completed result.
- A named gate the user asked to make green still reports failures; do not apply an unchanged-result stop or a turn-complete stop.

Do not start a bounded watch in any of these situations:

- Synchronous commands that return their result and exit status directly. There is no asynchronous state to observe.
- Status sources with no discernible terminal state or no stable state vocabulary. Polling cannot converge on a terminal value that does not exist.
- Cases where the status query itself is the diagnostic log. Read the log directly instead of wrapping it in a polling loop.
- Continuous monitoring or dashboards with no completion decision attached.
- Root-cause debugging of an operation already in a known terminal failure state. The bounded watch can produce the log excerpt, but deeper diagnosis is a separate task.

Do not use this skill to block a retry or a watch after any permitting condition already holds, and do not require the others to be present when one holds.

## Workflow

### Establish the comparison record

1. Record the baseline: the proposed action and its arguments, the relevant state that action reads, and the previous result. Keep all three as the comparison record.
2. If there is no previous completed result, issue the first attempt and record its triple. This is not a repeat.
3. For a watch, identify the target precisely before observing anything: build ID, deployment name and namespace, migration job, pipeline run, composed release-gate entrypoint, or equivalent. A persistent session is a status source whose observation is the result of a bounded wait, not a new command.

### Declare the bound before watching

1. Enumerate the terminal success and terminal failure values from the target system's documentation, schema, observed output, or the script's own completion line. Do not invent a vocabulary. For an interactive session, the terminal values are the command's own pass or fail line and the session's exit or closed state; a bare prompt with no result line is not completion. If terminal states cannot be named, do not start polling; inspect the detail resource and logs instead.
2. Declare the bound before the first status query or wait: a wall-clock deadline, a base poll interval or wait yield, a backoff schedule with a maximum interval, a maximum number of consecutive unchanged observations, a bounded retry budget for status queries, and, for sessions, an escalation ladder for yields. A workable default is one query every 10 to 30 seconds or an initial 10- to 30-second yield, doubling the wait after each unchanged result up to a 2-minute cap, stop after 6 unchanged observations or 4 consecutive no-information retries, and a deadline near twice the operation's expected duration, adjusted to the system's known cadence.
3. Record that bound in the working notes so the final report can show the run stayed inside it.

### Gate a retry

1. Before any retry, name the gate that permits it. A retry is allowed only when one of these holds: relevant state changed since the last attempt; a meaningful query or scope refinement produced information the last attempt did not have; or the last result was an identified bounded transient failure with retry budget remaining. If none holds, do not retry. Change the action, change arguments that affect the outcome, or acquire evidence from a different source.
2. An unchanged non-timeout result, including empty output or the same non-terminal status, is no progress, not new information. Elapsed wait time, a longer timeout, and an unchanged interval are not progress and are not a state change.
3. After a completed wait that reports no progress, do not re-issue the identical wait. Either collect the pending agent or task results directly, or apply one increased backoff and issue one bounded wait whose different timeout could observe a change. If two consecutive waits already returned the same no-progress result and no observable state change, stop waiting; do not issue a third. A status-query watch follows its declared unchanged-observation bound instead, and a persistent session follows its escalation ladder.
4. Do not issue a call whose action, arguments, state, and result match the baseline. A parameter tweak that leaves the outcome unchanged is still the same attempt.
5. Cap transient retries at one. A second identical transient failure is an unchanged result.
6. Treat a deprecation or migration warning as an instruction for the next attempt. When a status command emits a warning that names a replacement, use the named replacement on the next call and do not invoke the deprecated form again.
7. On a failed push or deploy step, classify the failure before deciding to stop. A transport error, meaning a nonzero exit with a connectivity or empty-reply signature, is not a build failure. When the local tree is verified deployable, deploy directly from that tree, assert the live artifact exposes the intended behavior, and retry the original push once connectivity returns. A genuine build failure, named in the build log, must be fixed before any deploy or push of that tree.
8. A remaining-failure status on a named gate the user asked to make green is not an unchanged retry and is not a completed stop. Partition the reported failures before acting: fix the failures attributable to the current diff and rerun that same gate, but do not rerun while only pre-existing baseline failures remain. Continue the repair loop only for failures the current change can affect. End it when that gate passes, when only baseline failures remain, or when a hard external blocker, such as an authorization or access denial, prevents another run.
9. For a user-requested delivery action such as a commit or push, run the mandatory gate once before the delivery attempt and record its command, the complete failure list, and the diff under review. Partition every reported failure into pre-existing baseline failures and failures attributable to the current diff. If any failure is diff-attributable, fix it and rerun the gate. If only baseline failures remain, stop repeating the commit or push and present one compliant path: scope or exclude the pre-existing check through the project's documented mechanism, request a waiver, or deliver on a branch that does not require the failing gate. State the chosen path, the evidence that attributes each failure to the baseline, and what the user must authorize when the path needs a decision outside the agent's authority.

### Run the bounded watch

1. Take a baseline observation and record the state, stage or current step, progress indicator, resource version or revision, result field, status message, and update timestamp when the system exposes them.
2. Wait one declared interval, applying the backoff schedule after an unchanged result. Do not busy-loop, keep at most one status query in flight, and do not spend more than the declared retry budget on one target.
3. Re-query the same target and record the same fields.
4. Before every retry, compare the new observation with the immediately preceding one across state, stage or completed step, progress indicator, resource version or revision, explicit result, and failure field. Progress requires a change in a field that reflects work advancing. A reworded status message with an unchanged state, stage, revision, and progress is not progress.
5. Stop immediately when a terminal success or terminal failure value appears, including an explicit result field or failure field.
6. Stop when the deadline, the unchanged-observation bound, or the consecutive no-information retry budget is reached. While the process is demonstrably advancing, keep the deadline and unchanged bound as the stop rule instead of a fixed total poll cap. Report that the operation did not reach a terminal state within the bound; do not relabel the timeout as success or failure.
7. After two consecutive unchanged reads, or the smaller threshold declared in the bound, run the independent liveness check below before issuing another query. A third identical read of the same status output is not liveness evidence and must not be sent.
8. On a stall or a terminal failure, fetch the build, deployment, or job logs or the detailed status resource once. Extract the failing step, error, or last meaningful event.
9. Decide the next action from that evidence: retry within the remaining budget if the cause looks transient, fix the deterministic cause, or escalate with the excerpt. Start any retry as a new attempt with its own bound and attempt identifier.
10. Emit the report described in Output Format and stop polling.

### Poll a managed deployment with the helper

For a managed deployment that must reach a terminal status, use the bundled helper instead of writing another inline polling loop. `scripts/poll_deployment_status.py` is the canonical helper: it combines a deadline with adaptive backoff. The earlier `scripts/deployment-status-poller.py` has the same status-extraction and exit-code contract but a fixed interval; keep it only for callers that already invoke it, and use the adaptive helper for new work.

1. Invoke `scripts/poll_deployment_status.py` with `--service`, `--environment`, `--deployment-id`, `--timeout`, and `--poll-interval`. Supply the status command through `--status-command` or `DEPLOYMENT_STATUS_COMMAND`; the command may use `{service}`, `{environment}`, and `{deployment_id}` placeholders.
2. Declare the terminal values before the first call. The helper defaults to `SUCCESS` as terminal success and `FAILED`, `CRASHED`, and `REMOVED` as terminal failure. Override them with `--terminal-success` and `--terminal-failure` when the target system uses a different vocabulary. Any other status is non-terminal and stays inside the declared bound.
3. Let the helper apply adaptive backoff. It waits `--poll-interval` after the first non-terminal observation, multiplies the interval by `--backoff-factor` after an unchanged non-terminal result, resets to the base interval when the status changes, and caps growth at `--max-poll-interval`. Do not replace this with a fixed sleep or a second inline loop.
4. Read the single machine-readable JSON line and the exit code. The `exit_result` field is `success` at code `0`, `terminal_failure` at `2`, `timeout` at `3`, `command_failure` at `4`, and `configuration_error` at `5`. Report the service, environment, deployment ID, final status, `exit_result`, `polls`, `elapsed_seconds`, and `poll_intervals`.
5. Stop on success, a terminal failure, a timeout, or a status-command failure. Never relabel a nonzero helper exit as success. On a failure or timeout, fetch the deployment logs or detailed status resource once and continue with the stall and escalation rules above.
6. Use `--fixture BUILDING,BUILDING,SUCCESS` for a deterministic check without a live service. A fixture that repeats `BUILDING` exercises the timeout path; a status command that exits nonzero exercises the command-failure path. Both must terminate nonzero within the configured timeout, and the timeout path must show intervals that grow toward `--max-poll-interval` rather than a fixed cadence; a final wait may be clipped to the remaining deadline.

### Supervise a persistent interactive session

1. Launch the composed gate entrypoint once in a persistent TTY session, then record its session identifier and root process ID. That one attached session is the source of truth for the rest of the run.
2. Wait on that same session with a short first yield. Do not relaunch the entrypoint, open a parallel session, or start a fresh gate run to get a cleaner look at the output.
3. Classify each result before waiting again: a terminal pass or failure line, or the script-completed or exit output, means stop immediately and report; new output, a streamed log tail, or a progress fragment such as dotted output means progress, so keep the session, clear the unchanged counter, and continue; an empty or unchanged result counts one unchanged observation and applies the escalation rule.
4. Escalate rather than repeat. Use a short initial yield, a visibly larger yield window after each unchanged result, and finally a blocking wait with an explicit internal timeout. Never issue the same yield value a third time in a row.
5. Before any further wait after an empty result, run the independent liveness check below. For a persistent session, that check includes a process-tree snapshot showing the expected children still present.
6. Allow at most two consecutive empty or unchanged waits at one yield value. Before a third at that value, either escalate the yield, run a liveness check, or stop with an explicit terminal or bounded-stop decision.
7. Stop immediately when the terminal line or script-completed output appears. Do not wait once more to confirm what the terminal output already states.

### Establish liveness independently

After two consecutive unchanged reads, or the smaller threshold declared in the bound, establish liveness before any further query or wait. The liveness check must use a source independent of the status output that just repeated; otherwise it only proves the status endpoint can still answer.

1. Choose a signal that reflects the worker rather than the facade: the retained session's root process and descendants, a controller event or reconcile timestamp, a worker heartbeat, queue depth and oldest in-flight item, log or artifact growth, an independent health endpoint, or the execution record's presence outside the cached status view.
2. Take one snapshot and record its timestamp and evidence. Compare it with the previous liveness snapshot when one exists; a changed heartbeat or an advanced reconcile time is evidence, a bare successful query is not.
3. If the operation is alive, keep the existing attempt, continue the declared backoff and unchanged count, and do not restart or abandon it.
4. If the operation is absent, wedged, or the liveness source cannot be reached after the declared retry budget, record which check failed and when, then diagnose once. Escalate or abort rather than issuing another identical status query.

For a persistent interactive session, the independent liveness check takes one process-tree snapshot before deciding anything from an empty result:

1. Resolve the session's root process and list its descendants.
2. Confirm that the gate entrypoint process, the database process it started, and the end-to-end test process are all present.
3. If every expected child is present, treat the empty result as normal waiting: keep the existing session, continue the escalation ladder, and do not restart or abandon the gate.
4. If an expected child is absent, record which one is missing and when it disappeared, then diagnose once. Do not start a second gate while the original session still exists.

### Compare observations

Use the strongest signal the system exposes, in this order: explicit state value, completed stage or step, revision or generation, progress indicator, explicit result, update timestamp, then status text. When only status text is available, require a semantic change that names new work, not a cosmetic difference. When several signals disagree, trust the explicit state, the revision, and the update timestamp over prose. Before each retry, record which fields changed and which stayed the same.

## State Machine

| State | Meaning | Allowed next states |
| --- | --- | --- |
| `first attempt` | No previous completed result. The call is issued once and its action, state, and result are stored. | `justified repeat`, `terminal stop`, `watching` |
| `justified repeat` | A relevant state change, novel search or scope result, or one unretried transient failure permits one repeat. | `justified repeat`, `terminal stop`, `repair continuation` |
| `terminal stop` | The proposed action, the state that matters, and the result match the previous attempt. | `repair continuation` only when a named gate still reports a diff-attributable failure |
| `repair continuation` | A named gate still reports failures; the next step fixes listed failures and reruns that gate. | `repair continuation`, `terminal stop`, `justified repeat` |
| `watching` | A non-terminal operation is observed within the declared bound. | `watching`, `succeeded`, `failed`, `stalled`, `bounded-stop` |
| `stalled` | The unchanged-observation bound was reached without a terminal state. | `diagnosing` |
| `diagnosing` | Logs or the detailed status resource are inspected for a cause. | `watching`, `failed`, `bounded-stop`, `escalated` |
| `succeeded` | A terminal success value was observed. | none |
| `failed` | A terminal failure value was observed, or diagnosis established one. | none |
| `bounded-stop` | The deadline or retry budget expired without a terminal state. | none |
| `escalated` | Diagnosis requires a human or another owner. | none |

Transitions:

- A first attempt with asynchronous state enters `watching`; a synchronous first attempt simply records its result.
- A real state change or a meaningful scope change enters `justified repeat`. A bounded transient failure enters `justified repeat` until its budget is exhausted, then `terminal stop` if the triple is still unchanged.
- When the action, state, and result match the prior record and no repair continuation applies, enter `terminal stop`. The next step is a different action or different evidence.
- A remaining named-gate failure enters `repair continuation` instead of `terminal stop`.
- `watching` stays in `watching` while an observation shows progress or the unchanged count remains below the bound.
- `watching` enters `succeeded` or `failed` when the observed value matches a declared terminal value, `stalled` when the unchanged bound is reached, and `bounded-stop` when the deadline or maximum poll count is reached.
- `stalled` enters `diagnosing`; always fetch logs or the detailed status resource before deciding to retry, fix, or escalate.
- `diagnosing` enters `watching` only after a transient cause is addressed and a new attempt starts with a fresh bound and attempt identifier. It enters `failed`, `bounded-stop`, or `escalated` when the evidence establishes a terminal failure, exhausts the budget, or needs another owner.
- `succeeded`, `failed`, `bounded-stop`, and `escalated` are absorbing; no further polling occurs from them.

## Constraints

- A deadline, an unchanged-observation bound, and a bounded retry budget are mandatory before the watch starts. Never poll without a bound, even when the user says to keep checking until it finishes.
- Poll with the declared interval and backoff schedule. Respect the target system's rate limits and backoff guidance; do not hammer a status endpoint.
- Never repeat an identical status check or fixed-timeout wait without comparing it with the previous observation and counting the repetition. Never repeat one after an identical non-progress result without new evidence: a changed compared field, a completed backoff step, an independent liveness result, or a changed stage or revision.
- Require a relevant state change, a meaningful query or scope refinement, new information, or an identified bounded transient failure before repeating the same action. Empty output, an unchanged interval, a longer timeout, or a repeated empty response is not a state change and does not justify another attempt.
- Cap a fixed-timeout wait or agent wait at one unchanged non-timeout result. That first result reaches the cap, so switch to inspecting the underlying state or a different tool; do not spend a second identical wait on the same action. If a second identical wait was already issued and also returned unchanged, no third is permitted. A status-query watch may take a second read only within its declared unchanged-observation bound, and it must run the independent liveness check or stop before a third. An unchanged non-timeout status is not a bounded transient failure and earns no retry budget.
- Cap transient retries at one. A second identical transient failure is an unchanged result.
- Do not treat elapsed wait time alone as progress. A longer timeout, an unchanged interval, or a completed sleep is not a state change, new information, or a transient failure.
- Do not treat an argument that does not affect the outcome as a new attempt. A parameter tweak that leaves the action, the relevant state, and the result the same is still the same attempt.
- When a tool result names a deprecated invocation and its replacement, the next attempt must use the recommended invocation instead of repeating the deprecated one.
- On an unreachable push remote, do not report the change as failed, do not abandon the push permanently, and do not retry the same remote command repeatedly without new connectivity evidence. A genuine build failure must be reported or fixed instead of deployed.
- Do not apply an unchanged-result stop, or declare a turn complete, while a named gate the user asked to make green still reports a diff-attributable failure.
- Before reporting a mandatory gate result for a commit or push, classify every failure as pre-existing baseline or diff-attributable and report both sets with their counts. A gate report that omits the partition is incomplete.
- Do not repeat a commit, push, or gate run whose action, gate state, and refusal would be unchanged. When only baseline failures remain, present a compliant path instead of another identical attempt.
- Do not silently bypass, skip, or weaken a mandatory gate. An exclusion, waiver, or alternate branch is allowed only when the project supports it, is explicitly reported, and is never used to hide a diff-introduced failure.
- Treat unreadable, empty, missing-row, and error output from a status resource as no information, not as progress and not as completion. Consecutive no-information results consume the unchanged-observation budget and should trigger a detail or log fetch before the deadline.
- An empty result from a bounded wait on an interactive session is different: when a liveness probe shows the command and its expected children still running, it is normal waiting. Do not call it a hang, a failure, or a reason to detour to an unrelated check.
- Allow at most two consecutive empty or unchanged waits at the same yield value. Before a third at that value, escalate the yield, run an independent liveness check, or make an explicit stop decision; do not keep issuing the same wait value.
- A liveness check is not another status read. Use a source independent of the repeated status output, and when liveness cannot be established do not treat the operation as merely slow.
- Count only genuine no-progress as unchanged. A progressing fragment, such as a stream of dots, a growing log tail, or a new step line, is progress and must not be counted as a wasted retry.
- Never impose a fixed total poll count or a fixed number of waits while the process is demonstrably advancing. The stop rule is the unchanged-observation bound plus the deadline, not a cap that cuts off a live, progressing run.
- Never restart, relaunch, or abandon an in-flight gate because a wait returned no output. Keep the existing session and its bound. Start a new attempt only after a terminal failure or a diagnosed dead session.
- Do not treat a changed status message alone as progress when the underlying state, step, and update time are unchanged. Do not treat elapsed time, a still-running process, or the absence of an error as success.
- Do not retrigger, redeploy, or delete the operation while it is still running. Retry only after a terminal failure or a diagnosed stall, and never create a duplicate job merely because status output was unreadable.
- When the deadline expires, stop waiting and diagnose, escalate, or abort. Do not extend the deadline or reset the unchanged counter in place because the operation is still running.
- When the independent liveness check fails, or liveness cannot be established within the retry budget after the small unchanged-read threshold, stop waiting and escalate or abort. Never keep polling an operation whose liveness is unknown.
- When a gate-control test spawns child processes, neutralize the inherited gate-budget override variables in the child environment before trusting its result. Prove that isolation on the single test file first, then rerun the whole phase.
- Compare the action, observed state, and result as values. A larger output limit, a repeated empty input, or the same completed result is not a scope refinement.
- Keep the bound visible in the final report, including when the bound was hit early because of a terminal state.
- Do not hard-code a tool name, a session id, a token budget, or constants copied from one trace. Keep the check reusable across tools and sessions.

## Verification

Check the retry and watch trace before concluding:

1. Enumerate every attempt with its action, arguments, observed state, and result.
2. Require each retry to carry a stated justification: a relevant state change, information gain from a meaningful query or scope refinement, or a bounded transient failure with remaining budget. Reject any retry whose justification is missing or is only elapsed wait time.
3. Confirm that no two consecutive attempts are identical in action and arguments when the previous result showed no progress. The only identical retry allowed is one repeat of an identified bounded transient failure within its budget.
4. For waits and polls, confirm that the trace stops after one unchanged non-timeout result and then inspects the underlying state or uses a different tool. Reject a trace that spends a second identical wait on that unchanged result.
5. The deadline, poll interval, backoff schedule, unchanged-observation bound, and retry budget were declared before the first status query or wait. The poll or wait count and elapsed time are at or below the declared bound.
6. Every retry is backed by evidence of advancement: a stage or step transition, a revision or generation increase, a progress change, an explicit result, or an explicit failure. A repeated read with none of these is not a reason to retry again.
7. After a small number of unchanged reads, an independent liveness check is recorded, and its result is used rather than another copy of the status output.
8. Either a terminal state was observed and its exact value is quoted, or the run stopped on the deadline, unchanged bound, or retry budget. The report states whether the operation is terminal, stalled, or unresolved, and gives a next action when it is not terminal.
9. Completion is accepted only on the phase's own pass line, for example `impact_phase_passed` for the named phase, together with the HEAD commit recorded for that run. An empty wait, a still-running session, the absence of an error, and a plausible log tail do not satisfy this check.
10. A stalled run includes an actual log or detail-resource excerpt; another status line alone does not satisfy this check. No progress claim rests only on a changed status message with an unchanged state, stage, revision, or progress value.
11. For an interactive session, the trajectory shows waits against the one session that was launched, not a second gate run. Read it for the failure signature: repeated identical `write_stdin` yield values with empty result previews and no intervening escalation or liveness check. Before any intervention on a session whose wait returned no output, a process-tree snapshot is recorded and shows whether the gate, database, and end-to-end child processes were alive.
12. When the deadline expired or liveness could not be established, the run stops waiting and records an escalation, abort, or bounded-stop decision instead of another identical wait. The wait policy passes when no more than two unchanged polls occur at one yield value, an independent liveness check follows the small unchanged-read threshold, and the loop ends at the terminal result rather than at an arbitrary total-count cap.
13. For a blocked delivery gate, name the gate command and the failure count, then give the evidence that attributes each baseline failure to a state that predates the diff, such as reproduction on the unmodified base revision or in files the diff does not touch. Name the focused check that shows the diff itself is clean.
14. Treat a push or delivery as verified only when the gate passes or an authorized waiver or documented scoped path has been recorded with the authority that approved it. Reject verification that cites only a repeated refusal, an unrecorded bypass, or a report that never separated baseline failures from diff-attributable ones.
15. Confirm that a named gate which reports a diff-attributable failure triggers another repair and rerun, while a gate reporting only baseline failures produces the partition and one compliant path rather than an unchanged-result stop or a repeated commit.
16. For a deployment poll, confirm that `scripts/poll_deployment_status.py` accepts the service, environment, deployment ID, timeout, and poll interval, and that the recorded `BUILDING,BUILDING,SUCCESS` fixture reaches `SUCCESS` within three polls and exits `0` with `exit_result` equal to `success`.
17. Confirm that a near-miss fixture of an unchanged non-terminal status, such as repeated `BUILDING`, exits `3` with `exit_result` equal to `timeout` at or before the configured timeout, and that a nonzero status command exits `4` with `exit_result` equal to `command_failure`. Neither near-miss may be reported as success.
18. Read `poll_intervals` from the timeout or repeated-status JSON line and confirm that the first wait equals `--poll-interval`, each unabridged wait after an unchanged non-terminal result grows by `--backoff-factor`, no wait exceeds `--max-poll-interval`, and a changed status resets the next wait to the base interval. A final wait may be clipped to the remaining deadline. The run must also show `elapsed_seconds` at or below `timeout_seconds`.

Accept a repeat only with one of these records: a recorded state change that can affect the call, result novelty from a meaningful search or scope change, or one bounded transient error that has not already been retried. Reject a repeat whose action, arguments, state, and result match the previous attempt, including a parameter tweak that does not change the outcome.

Accept a stop only when the same action, an unchanged state, and an identical result would be repeated. Reject a stop that fires on a real state change, a scope refinement, a bounded transient failure with budget remaining, or a named gate that still reports a diff-attributable failure. The guard passes only when later output no longer repeats a deprecation warning; after a deprecation warning, accept the sequence only when the next call uses the named replacement.

Confirm the revised guidance by replaying a deployment poll in which status returns a deprecation warning and one unchanged non-terminal state. The agent must switch to the named replacement and pivot to build or deploy logs instead of issuing an identical second poll. Confirm a transport failure with a connectivity probe, confirm the live artifact after the direct deploy, and confirm the original push succeeds on retry.

Confirm the delivery-gate guidance by replaying a push blocked only by failures that reproduce on the unmodified base revision. The agent must attribute those failures to the baseline, skip a second identical commit or push, and present one escalation path with the evidence and any authorization it needs. In the near-miss replay, a failure introduced by the diff must be fixed and the gate rerun rather than waived, excluded, or reported as pre-existing.

## Output Format

Record one decision object.

- `decision`: `repeat` or `stop`. `retry` is an accepted label for `repeat`; `replace` is an accepted label for `stop`.
- `gate`: `state change`, `new information`, `transient failure`, or `none`.
- `action`: the action compared with the prior record.
- `state`: the observed state compared with the prior record.
- `result`: the prior result compared with what the next call would repeat.
- `evidence`: the recorded state change, the new information, or the transient failure; `none` when the decision is `stop`.
- `reason`: why the loop continued or ended, naming the state-machine state that was reached.
- `next_step`: on `stop`, change the action or acquire new evidence; on `repeat`, the allowed change (state, scope, or remaining transient budget); on a repair continuation, the listed failures to fix before rerunning the named gate.

For an asynchronous watch, add the watch block in this field order so a reader can audit the bound and the evidence quickly.

```text
Target: (build, deployment, migration, or job identifier)
Initial state: (value at the first observation)
Final state: (terminal value, or "unchanged" / "not terminal by deadline")
Polling: interval 15s, 7 polls, deadline 10m, elapsed 1m 45s
Progress: yes | no | terminal
Evidence: (terminal value, changing field, or the log/detail excerpt)
Next action: (retry, fix, escalate, or none when terminal)
```

When the run stalled, include the number of consecutive unchanged observations and the failing step or last event from the log excerpt. When the status output was unreadable, say so explicitly and name the detail resource or log that was inspected instead.

For a poll run through `scripts/poll_deployment_status.py`, report the terminal status together with the helper's machine-readable exit result so the caller can distinguish success, terminal failure, timeout, and command failure. Include these fields, copied from the JSON line:

- `status`: the final observed deployment status, quoted exactly.
- `exit_result`: `success`, `terminal_failure`, `timeout`, `command_failure`, or `configuration_error`, matching the helper's process exit code.
- `exit_code`: `0`, `2`, `3`, `4`, or `5` as defined by the helper.
- `terminal`: `true` only when a declared terminal success or failure value was observed.
- `polls`, `elapsed_seconds`, and `poll_intervals`: the evidence that the adaptive backoff stayed within `timeout` and `max_poll_interval`.
- `reason`: why polling stopped.

Include the JSON line or these fields without rewriting a `timeout` or `command_failure` as a terminal deployment result. On a terminal failure, report the failing status separately from the diagnosis that follows it.

## Limitations

- Status output can be eventually consistent. A query taken immediately after a change may still show the previous state, so one observation is not proof of a stall.
- Status output can omit rows, lag behind the real workload, or be deprecated or renamed between system versions. Missing output is not evidence of completion.
- Terminal-state vocabulary must come from the target system. This skill cannot infer a success value that the system never emits.
- Coarse status sources without a step or update timestamp make progress detection weak; prefer logs, artifacts, or the detailed status resource in that case.
- A legitimately long step can look identical to a stall. Inspect details before killing, retrying, or escalating, and treat the unchanged bound as a trigger for diagnosis rather than automatic failure.
- The skill stops at a bounded diagnosis. It does not explain root causes beyond the inspected log or detail excerpt, and it does not own the system's retry policy.
- The gate judges the next attempt. It does not choose a replacement strategy beyond gathering different evidence, and it does not score domain correctness of a successful result. It does not decide that a refined search is sufficient, only that a refined search may be tried. It does not judge whether the first action was the right one.
- Promotion stays provisional until at least two held-out cases pass and the exit check does not fire on a real state change, a scope refinement, or a bounded transient failure.
