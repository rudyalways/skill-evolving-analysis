---
name: live-state-handoff-reconciliation
description: Author parallel-workstream handoff prompts only after re-resolving live repository state: enumerate worktrees and branches, check each named path for uncommitted or diverged state, resolve the published base SHA, and stamp the draft with a current timestamp so stale branch, worktree, or base-SHA claims never enter the handoff.
---

# Live-state handoff reconciliation

## Overview

Own the reconciliation step between repository reality and a parallel-workstream
handoff. Turn verified live state into accurate copy-paste prompts, so another
agent can start from the branch, worktree path, and base commit that actually
exist rather than from claims copied out of an older document. This skill
inspects the repository read-only, reconciles prior docs against that evidence,
and drafts the prompts only after the state is settled.

## When to Use

Use this skill when any one of these conditions applies; they are independent
entry points, and the first one alone is enough:

- Drafting copy-paste handoff prompts for two or more workstreams, agents, or
  branches that will run in parallel.
- Refreshing or extending an existing handoff whose earlier version already
  names a branch, worktree path, or base SHA.
- Reconciling a design doc, status note, or earlier prompt with live worktree,
  branch, and remote state before anyone acts on it.
- Splitting work across parallel agents when starting from the wrong base or a
  dirty worktree would waste a run.
- Adding a provenance timestamp and post-draft state check to a handoff that is
  about to be published.

A single workstream with no handoff, or a request to execute the handed-off
work, is not a trigger.

## Do Not Use

Do not use this skill for a single local change that needs no handoff, for
reviewing an authentication flow, or as a substitute for executing the
handed-off workstreams.

Do not use it to rubber-stamp cached state: if the request is to reproduce an
older prompt's branches, worktrees, or base SHA without fresh repository
inspection, reject that shortcut and obtain live state first.

Do not use it to choose architectures, estimate effort, review code, or edit
application files. Repository inspection here is read-only unless the user
separately asks for a change.

## Workflow

Reconcile first, draft second, and re-check after drafting. Do not write any
prompt field until step 5.

1. **Capture repository context.** Confirm the repository root and enumerate
   what exists before trusting any document:
   - `git rev-parse --show-toplevel`
   - `git worktree list --porcelain`
   - `git branch -a --no-color`
   - `git remote -v`
   Record the repository root, the default or target remote, and every
   worktree path with its checked-out branch or detached HEAD.

2. **Inspect every named path.** For each worktree or directory that a prompt
   will mention, run inspection commands from that path, not from a neighboring
   checkout:
   - `git -C <path> status --short --branch`
   - `git -C <path> rev-parse HEAD`
   - `git -C <path> rev-list --left-right --count HEAD...@{upstream}` when an
     upstream exists
   Record uncommitted, untracked, staged, detached, ahead, behind, and diverged
   state separately. Never describe a path as clean unless the status output is
   empty and the branch has an upstream.

3. **Resolve the published base SHA.** Determine the remote target reference and
   resolve it without changing local refs:
   - `git ls-remote <remote> refs/heads/<target-branch>`
   - `git ls-remote <remote> refs/tags/<target-tag>` when the base is a tag
   - `git cat-file -e <sha>^{commit}` to confirm the recorded object is a commit
   Prefer the remote-published SHA over a local branch tip. If the intended base
   is local-only, say so explicitly and record the exact local ref. Do not
   silently substitute one for the other.

4. **Timestamp the snapshot.** Capture one UTC timestamp in ISO 8601 form with
   `date -u +%Y-%m-%dT%H:%M:%SZ`. Keep the state table and the timestamp
   together so every claim has a single provenance point.

5. **Reconcile prior claims.** Extract every branch name, worktree path, status
   assertion, base SHA, and timestamp from existing docs or prompts. Mark each
   as verified, stale, or unverifiable against the captured commands. Correct
   stale values and call out unavailable paths; never copy a claim forward
   because it looks recent.

6. **Draft the prompts.** Write one prompt per requested workstream. State the
   verified branch, worktree path, and base SHA; the workstream scope; explicit
   exclusions such as a deferred phase; starting checks; and the completion
   contract. Keep each prompt independently copy-pasteable.

7. **Re-check after drafting.** After the last prompt edit, rerun the state
   capture from steps 1 through 4, including a fresh timestamp. Compare the
   second snapshot with the first. If any branch, path, status, or SHA moved,
   resolve the difference and update the affected prompts before calling them
   ready.

## Constraints

- Treat every existing doc, status note, and earlier prompt as an unverified
  claim. Never copy a branch name, worktree path, or SHA from prose without
  re-resolving it with a command.
- Keep repository inspection read-only. Do not run `fetch`, `pull`, `checkout`,
  `switch`, `reset`, `clean`, `stash`, `commit`, or any command that changes
  refs, the index, or the working tree unless the user separately requests that
  change. `git ls-remote` is preferred because it observes the remote without
  updating local refs.
- Scope each prompt to the workstreams actually requested. Record explicit
  exclusions, including a deferred phase, instead of silently expanding scope.
- Use one prompt per workstream. Do not merge two workstreams into one prompt or
  add a workstream the user did not name.
- Distinguish clean, dirty, detached, ahead, behind, and diverged states. Do not
  collapse them into "up to date."
- Prefer a remote-published base SHA. A local-only base must be labeled as
  local-only and must not be presented as the published base.
- Keep the timestamp in UTC ISO 8601 and attach it to the prompt batch; do not
  use a relative time such as "today" or "just now."
- If the repository or a named path is unavailable, request the missing state
  and stop drafting rather than inferring it from memory or cached docs.

## Verification

Before calling the batch ready, confirm all of the following against captured
command output:

- Every prompt branch appears in `git worktree list --porcelain` or
  `git branch -a --no-color`, and every worktree path exists.
- Every status statement matches that path's `git status --short --branch`
  output, including untracked files and detached HEAD.
- Every base SHA matches `git ls-remote` output for the named remote ref at the
  capture time, or is explicitly labeled local-only.
- Every recorded SHA passes `git cat-file -e <sha>^{commit}`.
- Each prompt contains branch, worktree path, base SHA, scope, exclusions,
  starting checks, and completion contract.
- The provenance timestamp is present and is the UTC time of the capture that
  supports the claims.
- The post-edit snapshot still matches the prompts. Any path whose state changed
  between snapshots is recorded and resolved, or the batch is not ready.
- No write command was executed during reconciliation.

## Output Format

Begin with a short reconciled-state table and provenance line:

```text
Reconciled at 2026-10-29T17:20:00Z from git worktree list, per-path status,
and git ls-remote. Post-edit recheck: 2026-10-29T17:24:00Z, no changes.
```

Then emit one copy-paste prompt per workstream, each with these fields:

- **Workstream:** short name.
- **Branch:** verified branch or detached HEAD.
- **Worktree path:** verified absolute path.
- **Base SHA:** remote-published SHA, or explicitly labeled local-only SHA.
- **Scope:** what this workstream owns.
- **Exclusions:** explicitly deferred or out-of-scope items.
- **Starting checks:** commands to confirm the path, branch, HEAD, and clean or
  dirty state before editing.
- **Completion contract:** the observable result, checks, and handoff back.
- **Provenance:** capture timestamp and the commands that support the fields.

Keep the provenance note short; do not restate the full evidence log.

## Limitations

Live-state capture is a point-in-time snapshot, so a prompt can become stale
immediately after a push, merge, rebase, or worktree change. The post-edit
recheck narrows that window but cannot guarantee future state. Without access to
the repository, this skill can only request the missing state rather than infer
it. Repository inspection cannot prove that an agent will follow the prompt, and
this skill does not execute or supervise the handed-off workstreams.
