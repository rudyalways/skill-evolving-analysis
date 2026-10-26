---
name: establish-browser-surface
description: Establish a controllable browser surface before authenticated browser work by identifying which surface the agent actually controls, binding to it, and verifying the loaded page's identity. Use before the first navigation in a task that depends on an already-signed-in browser, or when a browser handle must be resolved before console, dashboard, or provider-page work; treat an unavailable named-browser lookup as a switch signal, not a retry.
---

# Establish browser surface

## Overview

Resolve the browser surface you actually control before doing authenticated
browser work. This skill owns that pre-flight step: inventory the available
surfaces, bind to one, navigate to the target, and confirm the loaded page's
title and URL.

It prevents two related failures: acting as if a named browser is attached when
it is not, and looping on a lookup that has already reported the named browser
unavailable. The scope is surface selection, binding, navigation, and identity
confirmation before any reading, extraction, or console action. Authentication
and provider-specific page layouts are outside this scope.

## When to Use

Use this skill when any one of these conditions holds; each is sufficient on
its own:

- You are about to perform the first browser navigation in a task that depends
  on an already-signed-in browser.
- A browser handle must be resolved before console, dashboard, or provider-page
  work.
- A named-browser lookup has just reported unavailable and the task still needs
  the authenticated page.

Do not wait for more than one condition to be true. If the current task already
has an attached, verified surface, this pre-flight is not needed; see Do Not
Use.

## Do Not Use

Skip this skill when either holds:

- The task is a plain HTTP or API call with no browser involved.
- The controllable surface is already attached and verified for the current
  task.

Also out of scope: installing or launching a browser, choosing or entering
credentials, and diagnosing provider console layouts. If no controllable
surface exists at all, report the block instead of inventing a handle.

## Prerequisites

- Know which surface identifiers the current session exposes for control: an
  attached tab, a tab-creation or tab-attach facility, or a named browser
  handle.
- Know the target URL or URLs that must be opened.
- If either is unknown, discover the available surface before navigating.
  Inspect the current tool or harness surface operations; do not guess a handle
  or assume a tab exists.

Treat browser ids, project ids, and URLs as per-task inputs. Do not copy one
task's identifiers into this skill as reusable instructions.

## Workflow

1. Inventory the controllable surfaces. Prefer a surface already attached to
   this task; otherwise identify the tab-creation or tab-attach operation
   available on the controllable surface.
2. Check whether the named browser handle is attached, once. Use an explicit
   status or attach check if one is exposed; otherwise perform the named
   lookup exactly once.
3. If the named handle is attached, bind to it and continue at step 5.
4. If the lookup reports unavailable, not found, or not attached, treat that as
   a switch signal. Do not repeat the lookup. Create a new tab or attach to an
   existing tab on the available controllable surface, bind to that handle, and
   continue.
5. Navigate to the target authenticated URL. Reuse the bound tab if it is
   already at the target; otherwise open the target in the bound tab.
6. Wait for the page to finish loading, then read the tab title and the current
   URL.
7. Compare the title and URL with the expected destination. Allow an expected
   sign-in or consent redirect only when it is part of the task; otherwise
   treat a mismatch as a wrong-tab or wrong-surface signal and resolve it before
   continuing.
8. Only after the identity check passes, read from or act on the page.

### Closing sequence for a claimed fix

Steps 9-13 apply when the task claims a fix to a surface the user reported on,
such as a live page region or an email the host delivers. Passing tests, a
green build, and a healthy deployment are inputs to this sequence, never a
substitute for it.

9. Name the reported surfaces before checking anything. List each one as a
   concrete target: the route and the exact region for a page, and the
   recipient, subject, and message for an email. If a surface cannot be named
   from the task, stop and ask for it; do not substitute a proxy such as a test
   report, a local fixture, or an email template.
10. Verify the live rendered page itself. Load the page in the bound surface
    and inspect the exact reported region through the live DOM or a screenshot.
    Confirm the requested copy and the layout at the user's viewport: the text
    matches, and the elements are present, positioned, and styled as requested.
    Compare against the user's report or the pre-fix state, not merely against
    a selector that happens to exist.
11. Verify the delivered email itself. Retrieve the message from the hosting or
    mail provider that actually delivered it and open the received copy, not a
    template, preview, or send log. Check the rendered subject, sender, body
    copy, and layout, and record the message id and received timestamp. If the
    message has not arrived, poll within a stated budget; if it still has not
    arrived, record it as unverified.
12. Carry an open-items ledger across rounds. For every item an external
    dependency blocks, record: the item, the surface or artifact still
    unverified, the blocking dependency, the credential or action required to
    unblock it, the owner if known, and the date first recorded. Keep the
    ledger when the round ends; do not drop, downgrade, or silently close an
    item because the round is over.
13. Close only when every reported surface has its own live artifact evidence.
    If any item remains blocked, declare the round incomplete, present the
    ledger and the escalation, and do not present the overall fix as done.

| Observation | Action |
| --- | --- |
| Named handle attached | Bind to it, navigate, verify title and URL |
| Named lookup unavailable | Switch once to the controllable surface; do not retry the lookup |
| Title or URL mismatch | Check the tab and surface, re-navigate, verify again |
| No controllable surface | Report blocked; do not invent a handle |
| Live page copy or layout differs | Keep the item open; correct it and re-inspect the named region |
| Delivered email differs or is missing | Keep the item open; retrieve the received copy or record the block |
| Item blocked by rejected credential | Record it in the carried ledger, escalate the required access, do not close the round |

## Constraints

- One named-browser lookup is the budget. Never repeat a lookup that already
  reported the named browser unavailable; switch surfaces instead.
- Never assume a signed-in tab exists, that a named browser is attached, or
  that the foreground tab is the intended one.
- Verify title and URL before extracting or acting. Page content alone is not
  proof that the destination is correct.
- Do not encode task-specific browser ids, project ids, or URLs as reusable
  instructions. Resolve them fresh for each task.
- Do not create an authenticated session by guessing credentials. If the
  controllable surface lacks the signed-in session, report that condition.
- Treat any unavailable or not-found result as a surface-selection fact, not a
  transient error to retry.
- Do not declare a round complete from passing test counts, a green build,
  deployment health, or a successful send response. A claimed fix is complete
  only after its live rendered artifact and, when claimed, its received email
  have been inspected.
- Do not accept a local fixture, an email template or preview, or a
  selector-presence check as evidence for a live artifact. Evidence must come
  from the live deployment and the hosting provider that delivered the
  artifact.
- When an external dependency such as a rejected management credential blocks
  an item, stop re-declaring the round complete. Escalate the missing access
  explicitly, including what was attempted, the exact error, and the credential
  or role required, and keep the item open in the carried ledger until its
  hosted artifact is verified.
- Carry every unresolved externally blocked item forward as an explicit
  precondition for the next round or session. Do not omit it from the report or
  re-label it as done.
- Name each reported surface when closing. A general statement that the page
  "looks good", or a passing suite with no artifact inspection, is not a
  surface check.

## Verification

The pre-flight is complete only when all of these are observable:

- A surface is bound and named in the report.
- The target URL is open in that surface.
- The loaded tab title and URL match the expected destination, or an explicitly
  expected redirect.
- The named lookup was attempted at most once before the switch.

Positive evidence for the pre-flight is a named-browser lookup that reported
unavailable, followed by a tab created or attached on the controllable surface
that reached the expected title and URL. A successful-looking page without the
title and URL check is not completion. On a mismatch, report it and do not
present downstream findings as if the page were confirmed.

When the task claims a fix to a reported surface, completion additionally
requires artifact-level evidence captured from the live deployment and the
hosting provider, for each named surface:

- Rendered page: a screenshot or DOM excerpt of the exact reported region on
  the live URL, showing the requested copy and layout. State the route,
  viewport, account or access class, and capture time.
- Delivered email: the actual message as received from the host, including the
  rendered subject, sender, body copy, and layout, with the message id and
  received timestamp. A template, preview, or send log does not satisfy this.
- Deployment identity: the live URL or artifact id and the deployment or
  version currently serving it, so the evidence is tied to the deployed build
  rather than local code.

These are not completion evidence for a claimed fix, alone or together:

- passing unit, integration, or browser test counts;
- a green build, successful upload, or successful send response;
- a healthy deployment or health check;
- a local fixture, an email template or preview, or a selector-presence check;
- a general statement that the page or email "looks correct" without a named
  region, viewport, and received copy.

If a reported surface differs from the request, keep the item open and report
the observed difference. If an external dependency prevents capture, record the
item in the carried open-items ledger with the credential or action required,
escalate it, and mark the round incomplete; do not report the item as verified
or the round as complete.

## Output Format

Report the pre-flight evidence before any downstream findings:

```text
Surface used: named attached browser | newly created tab | attached existing tab on controllable surface
Named lookup: attached | unavailable (single attempt) | not needed
Target URL: ...
Loaded title: ...
Loaded URL: ...
Identity check: match | mismatch (reason)
```

Then present the downstream findings, or state the concrete reason the work is
blocked. Keep the block short; do not paste raw page content.

## Limitations

- Does not perform authentication, create accounts, or recover lost sessions.
- Does not install, launch, or provision a browser.
- Does not describe provider-specific console layouts, selectors, or menu
  paths.
- Assumes at least one controllable browser surface exists; when none does, the
  skill can only report the block.
- Relies on the harness exposing some way to read the current tab title and
  URL.
