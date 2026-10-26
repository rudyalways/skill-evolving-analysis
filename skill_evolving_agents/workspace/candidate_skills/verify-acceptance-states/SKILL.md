---
name: verify-acceptance-states
description: Verify every user-facing acceptance state end to end in the running app before reporting a task complete. Enumerate the states the request names, drive each through the real client with a separate account when role or ownership gates it, and attach one labeled screenshot or artifact per state. Use when a feature, bug fix, or migration is about to be called done, when the request lists acceptance criteria or asks to check behavior as different users, or when passing unit, component, or database tests are offered as proof that the app works.
---

## Overview

Turn a request's acceptance criteria into a driven, evidenced state ledger. A
state is verified only when an actor drove it in the running app and produced a
labeled artifact showing the observed outcome. Unit, component, integration,
and database tests are supporting checks; they never close a state.

When the request is open-ended and does not list its acceptance criteria, the
skill starts by turning it into explicit criteria before implementation:
relevance to the stated audience or topic, source coverage, inclusion and
exclusion rules, canonical destination links, and the delivery target. The
resulting ledger covers those content requirements as well as interaction
states.

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
- You are provisioning an account or identity through a browser and must decide
  whether the final submission created it or only advanced to a provider
  challenge such as anti-bot, identity, email, SMS, or device verification.
- The requested evidence is a screenshot, recording, or per-state artifact.
- Someone offers a green test suite, passing CI, or a merged pull request as
  proof that the user-facing flow works.
- A previous completion claim is disputed and needs state-by-state evidence.
- The request is an open-ended feature request whose acceptance criteria are
  unstated, such as "build a feed", "add a dashboard", or "make a digest", so
  the criteria must be derived before implementation.
- A completion claim is backed by tests or a build while relevance, source
  coverage, inclusion or exclusion rules, or canonical destination links remain
  unverified.

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
- A first-time visitor state that is intentionally clean, such as a signup,
  onboarding, or acceptance check that must start anonymous. Those still
  require a fresh profile or incognito context; do not replay them against the
  reporting user's persisted session.

## Workflow

### 1. Consolidate and derive the acceptance checklist

Do this before implementation when criteria are missing, and always before
verifying. Re-read every earlier request and correction in the thread, not just
the latest message. Consolidate them into one explicit acceptance checklist.
Treat a recurring complaint as an unresolved criterion that still gates the
next revision, not as a new one-off instruction to acknowledge and move past.
Carry each criterion forward with the clause it came from and whether the
previous revision met it.

When the request is open-ended and does not state its criteria, derive them
before building. At minimum enumerate:

- relevance: the content matches the audience or topic the request names
- source coverage: every requested source or category is represented
- inclusion and exclusion: what must appear and what must be filtered out
- canonical destination: each displayed item links to its intended official
  destination, not a search result, aggregator, or ambiguous proxy
- delivery: where the result must be delivered, published, or activated

Add these content criteria to the interaction states below, with the same
observable-outcome form. If a criterion cannot be made observable, record the
assumption and settle it before implementation.

### 2. Open the requirement-to-evidence ledger

Before implementing or, when implementation is already underway, before the
first status or completion report, write one ledger row for every requirement
the request names, including later restatements, corrections, and "same for X"
clauses. Each row records:

- requirement: the request clause or derived criterion it covers
- actor: the role, ownership, tenant, plan, or session that must observe it
- check: the concrete action and observable outcome that would prove it
- artifact: the labeled screenshot, response, record, or file that would carry
  the proof
- status: blank or unverified until a check is actually observed

Treat the ledger as the definition of scope, not as a report written at the
end. Update the status and artifact path in the same step as each check; never
reconstruct rows from memory. If a requirement has no plausible check or
artifact, settle that gap before implementing rather than leaving the row
implicit. Before reporting, walk the ledger end to end and confirm that no
requested requirement is missing. A requirement whose planned check could not
run stays in the ledger with an explicit unverified, blocked, or not-run status
and a bounded follow-up. The work is not done until every row has either
observed evidence or an explicit user-accepted gap.

### 3. Build the acceptance contract

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

### 4. Assign actors

Name the actor for every state. When visibility or permission depends on role,
ownership, tenant, plan, or invitation status, create a distinct account or
session for each such actor and use the least privilege that can reach the
state. Never substitute an admin account for the member view; a state seen only
by an admin is not evidence for a member-gated state. Keep credentials out of
the report.

States that do not depend on identity may share an account, but each still gets
its own drive and its own artifact.

### 5. Prepare the running app and preserve the reporting session

Confirm the environment, build or commit under test, and data baseline. Start
the app with its documented command and wait for readiness rather than assuming
it is up. Seed or create the minimum data each state needs. Clear cookies and
storage or use separate browser contexts when switching accounts so sessions
cannot bleed. Record environment, commit, and date.

When the request comes from a user reporting a failure in their own session,
capture that user's existing browser state before clearing or replacing
anything: the persisted profile with its cookies, localStorage, and sign-in
session, plus any stored billing, cart, or checkout state the failing flow
depends on. Keep a labeled snapshot of that profile so it can be replayed, and
never overwrite it while preparing fresh contexts for other actors. The
snapshot is the baseline the reported failure must be reproduced from.

### 6. Gate with automated checks, never substitute them

Run the relevant unit, component, integration, or database suites once to catch
a broken build before driving. Treat the result as a gate and as supporting
evidence only. A green suite does not verify any user-facing state and must not
change any status in the ledger.

### 7. Drive every state through the real surface

When a state reproduces a failure the user reported from an existing session,
load the reporting user's preserved profile first and drive the failing flow
from that persisted state before doing anything else. Capture the result as the
"before fix / persisted session" artifact. Only then repeat the same flow with a
fresh profile or incognito context and record both outcomes side by side in the
state row. The fresh run is the comparison, not the primary evidence.

After implementation, drive every derived content criterion and record one
artifact per criterion. For a relevance or source-coverage criterion, sample
several displayed items rather than one favorable example, and record which
ones match and which do not. For a canonical-destination criterion, open a
representative link per destination and confirm it resolves to the intended
official page. For a delivery criterion, inspect the actual delivery target the
user will open, not a local build or draft URL.

For each state, in a stable order:

1. Sign in as the assigned actor, restoring the preserved profile when this
   state carries a reported-session failure.
2. Enter through the entry point a real user uses, such as navigation, a deep
   link, or a button. Do not jump straight to a final URL or call the API
   directly unless the request defines that interface as the user surface.
3. Perform the action with realistic input.
4. Observe the full outcome: message, visible state change, list and detail
   consistency, permission behavior, persistence after refresh or re-login, and
   any downstream effect the state claims.
5. Capture the labeled artifact at the decisive moment, before navigating away.
   For a persisted-state replay, capture the previously failing flow from that
   same state, then capture the fresh-session comparison separately.
6. Write the verdict and artifact path into the ledger immediately. Do not
   reconstruct it from memory later.

When a state fails, keep driving the remaining independent states so the ledger
stays complete. After a fix, restart or redeploy and re-drive the failed state
from the same preserved reporting profile before trusting a fresh-session pass,
plus every state that depends on the changed behavior.

### 8. Confirm provisioning terminal state

When a state creates an account, identity, or other provider-managed entity
through a browser form, the submission is not the outcome. After the final
submission, read the provider-visible page and require explicit confirmation
that the entity exists, such as a success panel naming the account, an account
detail page, or a provider confirmation message visible in the session. Record
the exact confirmation observed and capture it as the state artifact.

If the page still displays an anti-bot, identity, email or SMS, or device
verification challenge, do not treat navigation, a redirect, a URL change, or
the absence of an error as creation. Stop provisioning, record the persona as
`pending-verification` with the challenge observed, and do not resubmit the same
form repeatedly. Resume only after the challenge is visibly cleared and a fresh
provider-visible confirmation appears; recheck the entity state at that point
before recording success.

If the provider exposes no explicit confirmation and no way to observe the
entity, mark the state blocked rather than guessing that it was created.

### 9. Handle blocked states honestly

If a required capability is unavailable, such as no browser, no credentials, an
unreachable environment, or a third-party sandbox, attempt one documented
unblock: launch or install the browser, request the account, or retry once after
readiness. If it is still unavailable, mark the state blocked, record exactly
what was tried and what stopped it, and attach the best artifact of the blocker,
such as a console error or an unavailable screen.

Never promote blocked to verified. Never infer the outcome from code, logs, or
tests when the browser check could not run.

### 10. Report

Write the ledger and the completion statement described in Output Format.
Report complete only when every requested state is verified with its own
artifact. Otherwise report incomplete and name every state that failed, is
blocked, is pending verification, or was not run.

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
- Keep failed, blocked, pending-verification, and not-run rows visible. Do not
  delete, merge, or reword them to make the report look green.
- Do not report completion while any requested state is unverified, failed,
  blocked, or not-run unless the user explicitly accepts that specific gap.
  Even with acceptance, keep the row unverified and name the accepted gap
  beside the verdict; never convert it to verified or let the report imply the
  behavior was observed.
- A resource lease, scheduling conflict, canceled job, environment quota, or
  unavailable worker explains why evidence is missing but says nothing about
  behavior. Never cite it as a passing observation, a test result, or a reason
  to infer that the unrun flow works.
- Do not widen the contract with unrequested states and do not drop ambiguous
  ones; list open questions explicitly.
- Never infer that an account or identity exists from a submitted form,
  navigation away from the form, a redirect or URL change, or the absence of an
  error.
- Do not report a provisioning state as complete while an anti-bot, identity, or
  device-verification challenge is displayed. Report it as `pending-verification`
  with the observed challenge state.
- Passing tests and a successful build are supporting checks only. They never
  close a criterion, populate a status cell, or justify a completion claim.
- Do not claim an official-link or relevance guarantee unless each displayed
  item, or a named sample with its selection rule, was checked against the
  stated rule and every exception is listed.
- Do not implement an open-ended request against an implicit or invented
  checklist. Make the derived criteria explicit first, and keep a recurring
  correction as an open criterion until the next revision is driven against it.

## Verification

Before sending any completion message, check each item and either fix the gap
or downgrade the claim:

1. Coverage: every acceptance state from the request, including later
   restatements and "same for X" clauses, has a ledger row.
2. Actor: every role- or ownership-gated state names a distinct account, and
   the artifacts or session log show different identities.
3. Artifact: every verified row has an existing, openable, legible artifact
   labeled with its state ID and showing both the expected outcome and the
   acting identity.
4. Persisted-session replay: when the user reported the failure from an
   existing session, a fresh-session pass is insufficient evidence. The row is
   closed only after the preserved reporting profile completes the previously
   failing flow, with labeled before and after artifacts from that same
   persisted state, alongside the separate fresh-session comparison.
5. Provisioning terminal state: every account- or identity-provisioning row
   names the explicit provider-visible confirmation observed after the final
   submission. A challenge page, redirect, unchanged form, or missing error is
   treated as unresolved, not as creation.
6. Recheck after verification: when a challenge or verification step was
   involved, the row records a fresh visibility check performed after it and
   the confirmation observed at that point. Do not record success from the
   pre-verification page.
7. Observation: the row records what was seen, not what was expected, and
   includes persistence, refresh, and negative permission checks where the
   state claims them.
8. Support separation: automated test results appear only as supporting checks
   and never as a state verdict.
9. Honesty: every failed, blocked, pending-verification, or not-run state is
   still listed with its blocker or challenge and attempted unblock, and the
   completion statement matches the ledger.
10. Traceability: environment, commit, and date are recorded, and each row cites
    the request clause it covers.
11. Final read: re-read the original request top to bottom once more after the
    ledger is complete and add any missed state before reporting.
12. Carry-forward: every correction from an earlier round is present as a
    criterion, and each previously corrected behavior was re-driven in the
    running app rather than inferred from the new code or a fresh build.
13. Deployed revision: the ledger records the deployed revision or artifact
    identifier that produced each observed state, so a pass cannot be attributed
    to a local build or a stale deployment.
14. Derived-criteria verdicts: every derived content criterion is marked
    `verified` or `failed`, or is explicitly recorded as unverified with the
    blocking status (`blocked` or `not-run`) and its own artifact. A relevance
    criterion cites a sample of displayed items, and a canonical-destination
    criterion cites a link that was opened and resolved to the intended official
    page.
15. Ownership split: the report separates work completed locally from
    deployment, publishing, or activation that the user still owns, and does not
    claim a live outcome from local work alone.
16. Unrun phase coverage: when a planned browser, database, or integration
    phase was canceled or could not run, every requirement that phase would
    have covered is marked unverified, blocked, or not-run, with a bounded
    follow-up naming the check to run and the next decision point. Passing unit,
    migration, type, or documentation checks are supporting checks only; they
    do not shrink the uncovered set or imply the unrun phase would have passed.
17. Scope exhaustion: the final ledger contains one row per requested
    requirement, and every row carries observed evidence or an explicit
    user-accepted unverified status. No row was dropped, merged, or reworded
    because its verification phase was unavailable.

Completion rule: all rows verified means complete. Any failed, blocked,
pending-verification, not-run, or unverified row means incomplete. A row that
reproduces a reported-session failure is not verified on a fresh-session pass
alone. A canceled or unavailable browser, database, or integration phase leaves
every requirement it would have covered unverified; it is never itself a pass
and never justifies a completed verdict.

## Output Format

Report in this order.

### 1. State ledger

| ID | Acceptance state | Actor / account | Entry point | Observed result | Artifact | Status |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | ... | ... | ... | ... | `evidence/S1-...png` | verified |

Use exactly one status per row: `verified`, `failed`, `blocked`, `not-run`, or
`pending-verification` for a provisioned account or identity whose provider
confirmation has not appeared. Quote the request clause under the table or in a
source column.

### 2. Evidence index

For each artifact: path, label, what it proves, and the identity visible in it.
State plainly when an artifact shows a blocker rather than a passing outcome.

### 3. Supporting checks

List the automated suites that were run, their result, and the explicit note
that they support but do not verify the states above.

### 4. Provisioning outcome

For each account- or identity-provisioning state, report exactly one outcome:

- `CREATED: <account or persona> - confirmed by <observed provider-visible confirmation>.`
- `PENDING VERIFICATION: <account or persona> - <challenge observed>; no confirmation yet.`

Report `CREATED` only when the provider-visible confirmation was observed and,
after any verification step, rechecked. Never derive it from form submission,
navigation, a redirect or URL change, or an error-free page.

### 5. Completion statement

One of:

- `COMPLETE: all N requested states verified end to end.`
- `INCOMPLETE: FAILED - S2, S4; BLOCKED - S5 (no test account for tenant B).`
- `INCOMPLETE: PENDING VERIFICATION - S6 (<challenge observed>); no provider confirmation yet.`
- `INCOMPLETE: NOT RUN - <reason and what is needed>.`

Never emit `COMPLETE` with an unverified row, including a pending-verification
provisioning row, and never leave the verdict implicit.

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
