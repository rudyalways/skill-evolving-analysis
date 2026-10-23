---
name: verify-acceptance-states
description: Verify every user-facing acceptance state end to end in the running app before reporting a task complete. Enumerate the states the request names, drive each through the real client with a separate account when role or ownership gates it, and attach one labeled screenshot or artifact per state. Use when a feature, bug fix, or migration is about to be called done, when the request lists acceptance criteria or asks to check behavior as different users, or when passing unit, component, or database tests are offered as proof that the app works.
---

## Overview

Turn a request's acceptance criteria into a driven, evidenced state ledger. A
state is verified only when an actor drove it in the running app and produced a
labeled artifact showing the observed outcome. Unit, component, integration,
and database tests are supporting checks; they never close a state.

This skill owns final pre-completion verification of user-facing behavior. It
does not own writing tests, release engineering, or static code review. Its
output is a complete state-by-state account of what was seen, by which actor,
with which artifact, plus an honest completion verdict.

## When to Use

Use this skill when any one of the following is true; each is sufficient:

- You are about to report a feature, bug fix, or migration as done and the
  request describes behavior a user can see or trigger.
- The request uses words such as verify, acceptance criteria, end to end,
  manual QA, check it in the app, works for real, or prove it.
- The behavior depends on role, ownership, tenant, plan, or invitation status,
  so one login cannot see every state.
- The requested evidence is a screenshot, recording, or per-state artifact.
- Someone offers a green test suite, passing CI, or a merged pull request as
  proof that the user-facing flow works.
- A previous completion claim is disputed and needs state-by-state evidence.

## Do Not Use

Do not use this skill for:

- A purely internal refactor or library change with no user-facing acceptance
  surface; its unit and integration tests are the contract.
- Writing or repairing automated tests as the deliverable. Use the project's
  test-authoring workflow instead.
- Static code review, architecture analysis, or code-read-only audits.
- Load, stress, security, penetration, or accessibility conformance testing;
  those need their own dedicated procedures.
- UX or visual design critique where no runnable build exists.
- A request with no acceptance surface and no runnable client; establish the
  contract first rather than inventing states to drive.

## Workflow

### 1. Build the acceptance contract

Convert the request into numbered states before touching the app. A state is a
single outcome an actor can observe:

- actor (role, ownership, tenant, plan)
- precondition and data
- entry point the user would use
- action
- observable expected outcome

One row per observable outcome. Split compound sentences. Treat later messages,
"same for the admin", and "also check that..." as added states, not as
restatements to ignore. Do not merge an allowed case and a forbidden case into
one state. Quote the request clause beside each state so coverage is auditable.

If a clause is ambiguous, record the assumption and settle it before driving.
Do not silently narrow the list to what is convenient to test.

### 2. Assign actors

Name the actor for every state. When visibility or permission depends on role,
ownership, tenant, plan, or invitation status, create a distinct account or
session for each such actor and use the least privilege that can reach the
state. Never substitute an admin account for the member view; a state seen only
by an admin is not evidence for a member-gated state. Keep credentials out of
the report.

States that do not depend on identity may share an account, but each still gets
its own drive and its own artifact.

### 3. Prepare the running app

Confirm the environment, build or commit under test, and data baseline. Start
the app with its documented command and wait for readiness rather than assuming
it is up. Seed or create the minimum data each state needs. Clear cookies and
storage or use separate browser contexts when switching accounts so sessions
cannot bleed. Record environment, commit, and date.

### 4. Gate with automated checks, never substitute them

Run the relevant unit, component, integration, or database suites once to catch
a broken build before driving. Treat the result as a gate and as supporting
evidence only. A green suite does not verify any user-facing state and must not
change any status in the ledger.

### 5. Drive every state through the real surface

For each state, in a stable order:

1. Sign in as the assigned actor and confirm the session actually started; a
   form that returns you to the sign-in page is not a session.
2. Enter through the entry point a real user uses, such as navigation, a deep
   link, or a button. Do not jump straight to a final URL or call the API
   directly unless the request defines that interface as the user surface.
3. Run the post-navigation checkpoint before reading the page. Compare the
   resolved URL and the visible heading against the intended authenticated
   target for this state. The expected URL is the target path, and the expected
   heading is that page's own heading, not a login, sign-in, SSO, or consent
   screen.
4. When the URL or heading does not match, treat the navigation as failed and
   route back to authentication: sign in again as the assigned actor, complete
   MFA, SSO, or consent prompts, then re-navigate to the target and repeat the
   checkpoint. Do not interpret the mismatched page and do not mark the step
   complete.
5. Perform the action with realistic input.
6. Observe the full outcome: message, visible state change, list and detail
   consistency, permission behavior, persistence after refresh or re-login, and
   any downstream effect the state claims.
7. Capture the labeled artifact at the decisive moment, before navigating away.
8. Write the verdict and artifact path into the ledger immediately. Do not
   reconstruct it from memory later.

When a state fails, keep driving the remaining independent states so the ledger
stays complete. After a fix, restart or redeploy and re-drive the failed state
plus every state that depends on the changed behavior.

### 6. Handle blocked states honestly

If a required capability is unavailable, such as no browser, no credentials, an
authentication wall or login redirect, an unreachable environment, or a
third-party sandbox, attempt one documented unblock: launch or install the
browser, request the account, complete the sign-in and its prompts, or retry
once after readiness. If it is still unavailable, mark the state blocked, record
exactly what was tried and what stopped it, and attach the best artifact of the
blocker, such as a console error, an unavailable screen, or the login page that
was reached instead of the target.

Never promote blocked to verified. Never infer the outcome from code, logs, or
tests when the browser check could not run.

### 7. Report

Write the ledger and the completion statement described in Output Format.
Report complete only when every requested state is verified with its own
artifact. Otherwise report incomplete and name every state that failed, is
blocked, or was not run.

## Constraints

- Tests never close a state. A passing count is supporting evidence and must be
  labeled as support, never placed in the status column.
- One labeled artifact per state. Do not reuse one screenshot across states, do
  not crop away the identity or the outcome, and never fabricate or substitute a
  representative image.
- Artifact labels carry the state ID and actor, for example
  `S3-member-cannot-edit.png`.
- Verify only from what was observed in the running app. Code reading, logs, API
  responses, and a colleague's report are not state evidence.
- Use a distinct account whenever role or ownership gates visibility or
  permission. Use least privilege, never a production admin standing in for
  another role.
- Do not mutate production data. Prefer a test or staging environment, use
  unique generated data, and clean up when it is safe.
- Keep failed, blocked, and not-run rows visible. Do not delete, merge, or
  reword them to make the report look green.
- Do not report completion while any requested state is unverified, failed, or
  blocked.
- Do not widen the contract with unrequested states and do not drop ambiguous
  ones; list open questions explicitly.

## Verification

Before sending any completion message, check each item and either fix the gap
or downgrade the claim:

1. Coverage: every acceptance state from the request, including later
   restatements and "same for X" clauses, has a ledger row.
2. Actor: every role- or ownership-gated state names a distinct account, and
   the artifacts or session log show different identities.
3. Authenticated target: a browser navigation counts as verified only when the
   loaded URL and page state match the intended authenticated target. A redirect
   to a login or sign-in URL, a "Welcome back"-style auth page, or any
   unauthenticated shell is a failed check, not proof that the control or key
   state was read. Record it as a blocker, authenticate, and re-read the target
   state; do not score anything from the mismatched page.
4. Artifact: every verified row has an existing, openable, legible artifact
   labeled with its state ID and showing both the expected outcome and the
   acting identity.
5. Observation: the row records what was seen, not what was expected, and
   includes persistence, refresh, and negative permission checks where the
   state claims them.
6. Support separation: automated test results appear only as supporting checks
   and never as a state verdict.
7. Honesty: every failed or blocked state is still listed with its blocker and
   attempted unblock, and the completion statement matches the ledger.
8. Traceability: environment, commit, and date are recorded, and each row cites
   the request clause it covers.
9. Final read: re-read the original request top to bottom once more after the
   ledger is complete and add any missed state before reporting.

Completion rule: all rows verified means complete. Any failed, blocked, or
not-run row means incomplete. A row whose page was a login redirect or an
unauthenticated shell is blocked, not verified, even when the page rendered
cleanly.

## Output Format

Report in this order.

### 1. State ledger

| ID | Acceptance state | Actor / account | Entry point | Observed result | Artifact | Status |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | ... | ... | ... | ... | `evidence/S1-...png` | verified |

Use exactly one status per row: `verified`, `failed`, `blocked`, or `not-run`.
Quote the request clause under the table or in a source column.

### 2. Evidence index

For each artifact: path, label, what it proves, and the identity visible in it.
State plainly when an artifact shows a blocker rather than a passing outcome.

### 3. Supporting checks

List the automated suites that were run, their result, and the explicit note
that they support but do not verify the states above.

### 4. Completion statement

One of:

- `COMPLETE: all N requested states verified end to end.`
- `INCOMPLETE: FAILED - S2, S4; BLOCKED - S5 (no test account for tenant B).`
- `INCOMPLETE: NOT RUN - <reason and what is needed>.`

Never emit `COMPLETE` with an unverified row, and never leave the verdict
implicit.

## Limitations

- Requires a runnable environment plus credentials for each gated actor. Without
  them, states are blocked, not passed.
- Browser automation cannot always capture OS-native dialogs, email or SMS
  delivery, payment sandboxes, or third-party iframes. Use test sinks and note
  the substitution.
- A screenshot proves what was rendered at one moment, not data integrity or
  concurrency behavior. Pair it with a direct data assertion when the state is
  about stored data.
- Eventual consistency and background jobs need explicit waiting or polling; a
  single artifact can miss a race that a later refresh would expose.
- States the request leaves ambiguous cannot be verified until the contract is
  settled; guessing produces false coverage.
- Multi-device, long-lived-session, and notification states may need several
  browser contexts or real time to pass.
- This skill does not replace security, performance, load, or accessibility
  testing, and it does not prove absence of regressions outside the enumerated
  states.
