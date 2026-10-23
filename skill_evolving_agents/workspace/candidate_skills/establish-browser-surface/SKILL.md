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

| Observation | Action |
| --- | --- |
| Named handle attached | Bind to it, navigate, verify title and URL |
| Named lookup unavailable | Switch once to the controllable surface; do not retry the lookup |
| Title or URL mismatch | Check the tab and surface, re-navigate, verify again |
| No controllable surface | Report blocked; do not invent a handle |

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

## Verification

The pre-flight is complete only when all of these are observable:

- A surface is bound and named in the report.
- The target URL is open in that surface.
- The loaded tab title and URL match the expected destination, or an explicitly
  expected redirect.
- The named lookup was attempted at most once before the switch.

Positive evidence is a named-browser lookup that reported unavailable, followed
by a tab created or attached on the controllable surface that reached the
expected title and URL. A successful-looking page without the title and URL
check is not completion. On a mismatch, report it and do not present downstream
findings as if the page were confirmed.

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
